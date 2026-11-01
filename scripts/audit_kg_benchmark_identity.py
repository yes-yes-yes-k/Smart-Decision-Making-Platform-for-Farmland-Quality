"""Local identity/near-duplicate review candidates, never automatic certification."""
from collections import Counter,defaultdict
from pathlib import Path
import html
import json
import re
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.rebuild_kg_extraction_benchmark import OUT,dump,lines,readlines
from framework.knowledge_graph.benchmark_rebuild import sha256_file,standard_family


def identity_hints(document,chunks):
    first=[c for c in chunks if c['page']==1]
    candidates=[]
    for c in first:
        for match in re.finditer(r'10\.\d{4,9}/[^\s<>"{}]+',c['text'],re.I):
            quote=match.group().rstrip('.,;:)')
            candidates.append(dict(kind='doi',value=quote,
                sample_id=c['sample_id'],block_id='chunk',page=c['page'],
                start=match.start(),end=match.start()+len(quote),
                quote=quote,verified=False,
                reason='first_page_literal_candidate_current_document_identity_not_confirmed'))
    for match in re.finditer(r'(?i)(?:GB|NY|HJ|LY|DB\d{2}|TD|DZ|SL|CJ)\s*[/／]?\s*T?\s*\d{1,6}\s*[-—–]\s*(?:19|20)\d{2}',document['doc_name']):
        candidates.append(dict(kind='standard_number',value=match.group(),
            family_candidate=standard_family(match.group()),block_id='filename',
            start=match.start(),end=match.end(),quote=match.group(),verified=False,
            reason='filename_hint_not_verified_standard_identity'))
    return candidates


def main():
    pool=readlines(OUT/'audit/document-pool.jsonl')
    hints=[];texts=[];ids=[];exact=defaultdict(set);titles=defaultdict(list)
    for d in pool:
        title=''.join(c.casefold() for c in (d['title'] or d['doc_name']) if c.isalnum())
        if len(title)>=12:
            titles[title].append(d['id'])
        if d['chunk_status']!='verified':
            continue
        chunks=readlines(OUT/f"audit/chunks/{d['id']}.jsonl")
        hints.append(dict(document_id=d['id'],candidates=identity_hints(d,chunks),
            language_hint=d['language_hint'],language_verified=bool(d['language']),
            parse_quality_verified=d['parse_quality']!='unknown',
            all_identity_candidates_require_source_review=True))
        normalized=[]
        for c in chunks:
            value=''.join(x.casefold() for x in c['text'] if x.isalnum())
            normalized.append(value)
            if len(value)>=160:
                h=__import__('hashlib').sha256(value.encode('utf-8')).hexdigest()
                exact[h].add(d['id'])
        texts.append('\n'.join(normalized));ids.append(d['id'])
    lines(OUT/'audit/metadata-review-candidates.jsonl',hints)
    docmap={d['id']:d for d in pool}
    exact_rows=[dict(normalized_chunk_sha256=h,document_ids=sorted(ds),
        status='pending_shared_boilerplate_or_duplicate_review') for h,ds in sorted(exact.items())
        if len({docmap[i]['isolation_group'] for i in ds})>1]
    lines(OUT/'audit/exact-content-review.jsonl',exact_rows)
    title_rows=[dict(normalized_title=t,document_ids=ds,status='pending_identity_review')
                for t,ds in sorted(titles.items()) if len(ds)>1]
    lines(OUT/'audit/title-identity-review.jsonl',title_rows)
    print(json.dumps(dict(documents_for_similarity=len(texts),metadata_hint_documents=len(hints),
        exact_cross_group_shared_chunks=len(exact_rows))),flush=True)
    from sklearn.feature_extraction.text import TfidfVectorizer
    pairs=[]
    if len(texts)>1:
        matrix=TfidfVectorizer(analyzer='char',ngram_range=(5,5),
            max_features=100000,min_df=2,norm='l2').fit_transform(texts)
        similarity=(matrix@matrix.T).tocoo()
        for a,b,value in zip(similarity.row,similarity.col,similarity.data):
            if a>=b or value<.85 or docmap[ids[a]]['isolation_group']==docmap[ids[b]]['isolation_group']:
                continue
            pairs.append(dict(a=ids[a],b=ids[b],cosine=float(value),
                status='pending_semantic_duplicate_review',automatically_merged=False))
    pairs.sort(key=lambda p:(p['a'],p['b']))
    lines(OUT/'audit/near-duplicate-review.jsonl',pairs)
    pending_ids={i for r in exact_rows+title_rows for i in r['document_ids']}
    pending_ids.update(i for p in pairs for i in (p['a'],p['b']))
    summary=dict(status='candidates_prepared_not_semantically_resolved',
        documents_compared=len(ids),cosine_threshold=.85,ngram_size=5,max_features=100000,
        metadata_hints=Counter(c['kind'] for r in hints for c in r['candidates']),
        exact_cross_group_shared_chunks=len(exact_rows),
        title_identity_candidates=len(title_rows),near_duplicate_pairs=len(pairs),
        pending_document_ids=sorted(pending_ids),
        formal_partition_must_exclude_pending_groups=True,
        exhaustive_semantic_duplicate_certification=False,cloud_calls=0)
    dump(OUT/'audit/identity-review-report.json',summary)
    e=lambda v:html.escape(str(v),quote=True)
    rows=''.join(f'<tr><td>{r["document_id"]}</td><td>{e(docmap[r["document_id"]]["doc_name"])}</td><td>{e(json.dumps(r["candidates"],ensure_ascii=False))}</td></tr>' for r in hints if r['candidates'])
    (OUT/'audit/identity-review.html').write_text('<!doctype html><html lang="zh"><meta charset="utf-8"><title>身份与近重复待核实</title><style>body{font:15px system-ui;margin:30px}td,th{border:1px solid #ccc;padding:8px}table{border-collapse:collapse}pre{white-space:pre-wrap}</style><h1>身份与近重复待核实</h1><p>候选均未经来源确认；词面相似不代表同一文献，文件名编号不代表已验证身份。不能据此发布最终验收集。</p><pre>'+e(json.dumps(summary,ensure_ascii=False,indent=2))+'</pre><table><tr><th>ID</th><th>文件名</th><th>字面证据候选</th></tr>'+rows+'</table></html>',encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False),flush=True)


if __name__=='__main__':main()
