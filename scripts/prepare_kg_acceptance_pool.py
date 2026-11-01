"""Read-only DB/vector audit and deterministic holdout snapshot; no production writes."""
from collections import Counter,defaultdict
from pathlib import Path
import json
import re
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.experiment_kg_recall import read,write,jsonl,sha
from framework.knowledge_graph.acceptance_data import digest,normalized,identity_groups,deterministic_selection
from scripts.run_kg_acceptance_v1 import OUT,immutable,verify_freeze

def exposures():
    ids=set();hashes=set();files=[]
    # Candidate metadata inventories are not evidence of reading their contents.
    ignored=('candidate','inventory','blind-pool','tracks-and-gates','history-freeze','manifest','progress','source-validation')
    paths=list((ROOT/'artifacts').rglob('*.jsonl'))+list((ROOT/'artifacts/minimal_kg').glob('*.json'))
    for p in sorted(set(paths)):
        if OUT in p.parents or any(s in p.name for s in ignored):continue
        if 'backup' in str(p).lower():continue
        try:
            data=read(p) if p.suffix=='.jsonl' else json.loads(p.read_text(encoding='utf-8'))
        except (ValueError,UnicodeError):continue
        before=len(ids)+len(hashes)
        def walk(x):
            if isinstance(x,dict):
                for k,v in x.items():
                    if k=='document_id' and type(v) is int:ids.add(v)
                    if k in ('file_sha256','content_sha256') and isinstance(v,str) and len(v)==64:hashes.add(v)
                    if isinstance(v,(dict,list)):walk(v)
            elif isinstance(x,list):
                for v in x:walk(v)
        walk(data)
        if len(ids)+len(hashes)>before:files.append(dict(path=str(p.relative_to(ROOT)),sha256=sha(p)))
    return ids,hashes,files

def main():
    from dotenv import load_dotenv
    load_dotenv(ROOT/'.env');verify_freeze()
    from sqlalchemy import create_engine,text
    from framework.config import Config
    from framework.knowledge_graph.chunk_reader import WorkerPublishedChunkReader
    directory=OUT/'pool';directory.mkdir(exist_ok=True)
    if (directory/'selection-manifest.json').exists():raise ValueError('pool already frozen')
    exposed_ids,exposed_hashes,files=exposures()
    engine=create_engine(Config.SQLALCHEMY_DATABASE_URI,connect_args={'connect_timeout':5})
    try:
        with engine.connect() as conn:
            conn.execute(text('SET TRANSACTION READ ONLY'))
            result=conn.execute(text('SELECT id,title,doc_name,file_hash,document_kind,language,doi_normalized,standard_number_normalized,parse_metadata,chunk_count,status,review_status,visibility_scope,processing_stage FROM kb_document'))
            documents=[dict(id=r.id,title=r.title or r.doc_name,file_sha256=r.file_hash,kind=r.document_kind,language=r.language,
                doi=r.doi_normalized,standard_number=r.standard_number_normalized,parse_quality=(r.parse_metadata or {}).get('quality','unknown'),
                expected_count=r.chunk_count,status=r.status,review_status=r.review_status,visibility_scope=r.visibility_scope,processing_stage=r.processing_stage) for r in result]
    finally:engine.dispose()
    grouping=identity_groups(documents)
    exposed_groups={grouping.find(d['id']) for d in documents if d['id'] in exposed_ids or d['file_sha256'] in exposed_hashes}
    candidates={r['document_id'] for r in read(ROOT/'artifacts/knowledge_platform/gold-v4/evaluation-design/unseen-document-candidates.jsonl')}
    audit=[];eligible=[]
    for d in documents:
        if d['id'] not in candidates:continue
        group=grouping.find(d['id']);reasons=[]
        if group in exposed_groups:reasons.append('known_exposure_or_identity_group_exposure')
        if not(d['status']==1 and d['review_status']=='approved' and d['visibility_scope']=='public' and d['processing_stage']=='completed' and d['expected_count']>0 and d['file_sha256']):reasons.append('not_currently_public_approved_completed_hash_bound')
        record=dict(d,isolation_group=group,eligible=not reasons,reasons=reasons,exposure_status='known_exposed' if group in exposed_groups else 'no_known_local_exposure',certified_unexposed=False)
        audit.append(record)
        if not reasons:eligible.append(record)
    jsonl(directory/'document-audit.jsonl',audit)
    write(directory/'exposure-audit.json',dict(local_exposure_document_ids=len(exposed_ids),local_exposure_file_hashes=len(exposed_hashes),files=files,
        scope='local recorded artifacts only; no model training-data blindness claim',certified_unexposed=False))
    reader=WorkerPublishedChunkReader(Config.CHROMA_PERSIST_DIR);chunks=[];failed=[]
    for n,d in enumerate(eligible):
        try:
            cs=reader.read_published_chunks(document_id=d['id'],content_sha256=d['file_sha256'],expected_count=d['expected_count'])
            if len(cs)!=d['expected_count']:raise ValueError('chunk_count_or_hash_mismatch')
            indices=set()
            for c in cs:
                m=c['metadata'];idx=m.get('chunk_index')
                if type(idx) is not int or idx in indices or not isinstance(c['content'],str) or type(m.get('page')) is not int or m['page']<=0:raise ValueError('invalid_chunk_provenance')
                indices.add(idx)
            for c in cs:
                m=c['metadata'];txt=c['content'];idx=m['chunk_index']
                chunks.append(dict(sample_id='acceptance:'+digest(f"{d['file_sha256']}:{idx}:{digest(txt)}")[:24],document_id=d['id'],
                    isolation_group=d['isolation_group'],file_sha256=d['file_sha256'],document_title=d['title'],document_kind=d['kind'],
                    language=d['language'] or 'unknown',parse_quality=d['parse_quality'],page=m['page'],chunk_index=idx,
                    position_quartile=min(3,idx*4//max(1,d['expected_count'])),text=txt,text_sha256=digest(txt),quality_flags=['replacement_character'] if '\ufffd' in txt else []))
        except Exception as exc:failed.append(dict(document_id=d['id'],reason=type(exc).__name__+(':'+str(exc) if isinstance(exc,ValueError) else '')))
        if (n+1)%50==0:print(json.dumps(dict(documents_read=n+1,total=len(eligible),chunks=len(chunks))),flush=True)
    # Exact normalized duplicate chunks connect document groups, including exposed sources.
    old=read(ROOT/'artifacts/knowledge_platform/gold-v4/visible-inputs.jsonl')
    exposed_texts={digest(normalized(b['text'])) for r in old for b in r['blocks'] if b['block_id']=='chunk' and len(normalized(b['text']))>=80}
    duplicate_exposure_groups={c['isolation_group'] for c in chunks if digest(normalized(c['text'])) in exposed_texts}
    # Near duplicate comparisons use lexical cosine candidates and exact 5-gram Jaccard.
    # Ambiguous highly similar documents are quarantined, not declared independent.
    from sklearn.feature_extraction.text import TfidfVectorizer
    texts=[' '.join(c['text'] for c in chunks if c['document_id']==d['id']) for d in eligible]
    suspect=set();pairs=[]
    if len(texts)>1:
        matrix=TfidfVectorizer(analyzer='char',ngram_range=(5,5),max_features=100000,min_df=2).fit_transform(texts)
        similarity=(matrix@matrix.T).tocoo()
        for i,j,v in zip(similarity.row,similarity.col,similarity.data):
            if i>=j or v<.85 or eligible[i]['isolation_group']==eligible[j]['isolation_group']:continue
            a,b=eligible[i]['id'],eligible[j]['id'];suspect.update([a,b]);pairs.append(dict(a=a,b=b,cosine=float(v),status='quarantined_pending_semantic_duplicate_resolution'))
    allowed=[d for d in eligible if d['id'] not in suspect and d['isolation_group'] not in duplicate_exposure_groups and d['id'] not in {f['document_id'] for f in failed}]
    allowed_ids={d['id'] for d in allowed};usable=[c for c in chunks if c['document_id'] in allowed_ids]
    jsonl(directory/'near-duplicate-quarantine.jsonl',pairs);jsonl(directory/'read-failures.jsonl',failed)
    # Snapshot all eligible chunks locally; final inputs are not sent to candidate models.
    jsonl(directory/'corpus-snapshot.jsonl',usable)
    rows=deterministic_selection(allowed,usable,'acceptance-v1-20261027')
    jsonl(directory/'selection.jsonl',rows)
    for part in ('calibration','test'):
        destination=OUT/part;destination.mkdir(exist_ok=True);jsonl(destination/'samples.jsonl',[r for r in rows if r['partition']==part])
        jsonl(destination/'inputs.jsonl',[dict(sample_id=r['sample_id'],blocks=[dict(block_id=k,kind=k,text=t,text_sha256=digest(t)) for k,t in [('chunk',r['text']),('document_title',r['document_title'])]]) for r in rows if r['partition']==part])
    counts=Counter((r['track']+':'+r['partition']) for r in rows)
    write(directory/'selection-manifest.json',dict(candidate_documents=len(candidates),current_audited=len(audit),allowed_documents=len(allowed),
        read_failures=len(failed),quarantined_near_duplicate_pairs=len(pairs),exact_exposure_duplicate_groups=len(duplicate_exposure_groups),
        counts=counts,selected_document_groups=len({r['isolation_group'] for r in rows}),selection_sha256=sha(directory/'selection.jsonl'),
        corpus_sha256=sha(directory/'corpus-snapshot.jsonl'),seed='acceptance-v1-20261027',certified_unexposed=False,
        status='prepared_requires_label_and_duplicate_review',limitations=['local exposure audit is not exhaustive proof','cosine quarantine heuristic is not semantic independence certification','representative requires >=3 chunks per group; short-document exclusion is a selection limitation'],
        shortfalls={k:max(0,v-counts[k]) for k,v in {'representative:calibration':60,'representative:test':240,'challenge:calibration':40,'challenge:test':160}.items()}))
    print(json.dumps(dict(counts=counts,allowed_documents=len(allowed),chunks=len(usable))),flush=True)

if __name__=='__main__':main()
