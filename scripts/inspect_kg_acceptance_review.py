"""Audit source/sampling/old relabel records behind the static review pages. Offline."""
from pathlib import Path
from collections import Counter,defaultdict
from concurrent.futures import ThreadPoolExecutor
import json,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.experiment_kg_recall import read,write,jsonl,sha
from framework.knowledge_graph.acceptance_inspection import source_flags,inspect_relabel
from framework.knowledge_graph.acceptance_data import assert_isolation

BASE=ROOT/'artifacts/knowledge_platform/acceptance-v1'
OUT=BASE/'review-inspection-20261028'

def audit_database(rows):
    from dotenv import load_dotenv
    from sqlalchemy import create_engine,text,bindparam
    load_dotenv(ROOT/'.env')
    from framework.config import Config
    ids=sorted({r['document_id'] for r in rows});engine=create_engine(Config.SQLALCHEMY_DATABASE_URI,connect_args={'connect_timeout':5})
    try:
        with engine.connect() as conn:
            conn.execute(text('SET TRANSACTION READ ONLY'))
            stmt=text('SELECT id,file_path,file_hash,chunk_count,status,review_status,visibility_scope,processing_stage FROM kb_document WHERE id IN :ids').bindparams(bindparam('ids',expanding=True))
            docs=[dict(r._mapping) for r in conn.execute(stmt,dict(ids=ids))]
    finally:engine.dispose()
    byid={r['document_id']:r for r in rows};upload=Path(Config.UPLOAD_FOLDER)
    if not upload.is_absolute():upload=ROOT/upload
    def check(d):
        source=byid[d['id']];original=Path(d['file_path']);candidates=[original] if original.is_absolute() else [ROOT/original,upload/original]
        paths=list(dict.fromkeys(p.resolve() for p in candidates if p.is_file()))
        hashes={sha(p) for p in paths};expected=source['file_sha256'];reasons=[]
        if not(d['status']==1 and d['review_status']=='approved' and d['visibility_scope']=='public' and d['processing_stage']=='completed'):reasons.append('current_eligibility_changed')
        if d['file_hash']!=expected:reasons.append('current_database_file_hash_changed')
        if not paths:reasons.append('source_file_not_found')
        elif hashes!={expected}:reasons.append('source_bytes_mismatch_or_ambiguous_paths')
        return dict(document_id=d['id'],current_eligible='current_eligibility_changed' not in reasons,database_hash_matches=d['file_hash']==expected,
            original_file_found=bool(paths),original_bytes_match=hashes=={expected},current_chunk_count=d['chunk_count'],reasons=reasons)
    checked=list(ThreadPoolExecutor(max_workers=4).map(check,docs))
    missing=sorted(set(ids)-{d['id'] for d in docs})
    return checked,missing

def main():
    OUT.mkdir(exist_ok=True);selection=read(BASE/'pool/selection.jsonl');assert_isolation(selection)
    manifest=json.loads((BASE/'pool/selection-manifest.json').read_text(encoding='utf-8'))
    assert sha(BASE/'pool/selection.jsonl')==manifest['selection_sha256']
    current=ROOT/'artifacts/knowledge_platform/acceptance-v1-v41flash'
    assert sha(current/'pool/selection.jsonl')==manifest['selection_sha256']
    records=[];counts=Counter();doccounts=Counter();corpusdocmeta={}
    with (BASE/'pool/corpus-snapshot.jsonl').open(encoding='utf-8') as f:
        for line in f:
            r=json.loads(line);doccounts[r['document_id']]+=1;corpusdocmeta[r['document_id']]=r
    bystratum={};metadata=read(BASE/'pool/document-audit.jsonl')
    for track in ('representative','challenge'):
        for part in ('calibration','test'):
            rs=[r for r in selection if r['track']==track and r['partition']==part]
            bystratum[f'{track}:{part}']=dict(samples=len(rs),document_groups=len({r['isolation_group'] for r in rs}),
                kinds=Counter(r['document_kind'] for r in rs),quartiles=Counter(str(r['position_quartile']) for r in rs),languages=Counter(r['language'] for r in rs),parse_quality=Counter(r['parse_quality'] for r in rs))
    for r in selection:
        assert r['text_sha256']==__import__('hashlib').sha256(r['text'].encode('utf-8')).hexdigest()
        flags=source_flags(r['text']);counts.update(flags)
        records.append(dict(sample_id=r['sample_id'],document_id=r['document_id'],track=r['track'],partition=r['partition'],page=r['page'],chunk_index=r['chunk_index'],
            flags=flags,stored_flags=r['quality_flags'],unmapped_glyph_missing_from_stored_flags='unmapped_pdf_glyph' in flags and 'unmapped_pdf_glyph' not in r['quality_flags'],
            heuristic_flags_only=True,no_automatic_exclusion=True))
    file_checks,missing=audit_database(selection)
    jsonl(OUT/'source-file-checks.jsonl',file_checks);jsonl(OUT/'sample-diagnostics.jsonl',records)
    source_report=dict(samples=500,documents_checked=len(file_checks),missing_database_documents=missing,
        file_hash_matches=sum(r['original_bytes_match'] for r in file_checks),eligibility_matches=sum(r['current_eligible'] for r in file_checks),
        problems=[r for r in file_checks if r['reasons']],quality_flag_counts=counts,
        samples_with_cid_but_unflagged=sum(r['unmapped_glyph_missing_from_stored_flags'] for r in records),
        language_metadata_available=sum(bool(d['language']) for d in metadata),doi_metadata_available=sum(bool(d['doi']) for d in metadata),
        parse_quality_metadata_known=sum(d['parse_quality']!='unknown' for d in metadata),metadata_documents=len(metadata),
        scope='all selected source hashes verified; semantic reading is a separate targeted inspection')
    write(OUT/'sources.json',source_report)
    available_kinds=Counter(r['document_kind'] for r in corpusdocmeta.values())
    write(OUT/'sampling.json',dict(strata=bystratum,pool_document_kinds=available_kinds,
        short_document_groups_unrepresented=sum(v<3 for v in doccounts.values()),
        representative_quartile_3_samples=sum(r['track']=='representative' and r['position_quartile']==3 for r in selection),
        cause='three-slot deterministic round robin always consumes quartiles 0,1,2 before quartile 3',
        challenge_selection='generic keyword shortlist, not verified relation-positive coverage',frozen_selection_unchanged=True))
    inputs=read(BASE/'stability/inputs.jsonl');old=[]
    for p in sorted((BASE/'stability/responses').glob('*.json')):
        result=json.loads(p.read_text(encoding='utf-8'));old.append(inspect_relabel(inputs[result['index']],result))
    jsonl(OUT/'old-relabel-diagnostics.jsonl',old)
    write(OUT/'old-relabel-summary.json',dict(samples=len(old),protocol_complete=sum(not r['errors'] and r['state']=='needs_review' for r in old),
        samples_with_unbound_fragments=sum(r['unbound_fragment_count']>0 for r in old),unbound_fragments=sum(r['unbound_fragment_count'] for r in old),
        literally_bindable_entity_fragments=sum(r['literal_bindable_count'] for r in old),total_entity_fragments=sum(r['entity_fragment_count'] for r in old),
        errors=Counter(f'{k}:{v}' for r in old for k,v in r['errors'].items()),truncated_stages=Counter(t['stage'] for r in old for t in r['truncated_stages']),
        semantic_correctness_not_established=True,cloud_requests=0))
    before=json.loads((BASE/'run-config.json').read_text(encoding='utf-8'))['model']
    print(json.dumps(dict(source_documents=len(file_checks),source_problems=len(source_report['problems']),flags=counts,old_model=before,old_relabel_records=len(old),cloud_calls=0),ensure_ascii=False))
if __name__=='__main__':main()
