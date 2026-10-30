"""Record explicit, per-source Codex decisions without impersonating a human."""
from copy import deepcopy
from datetime import UTC,datetime
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'artifacts/knowledge_platform/gold-rebuild-v3/candidate-reference.jsonl'
LEDGER=ROOT/'artifacts/knowledge_platform/gold-rebuild-v3/codex-adjudications.jsonl'


def record(decisions):
    from scripts.annotate_kg_gold_corpus import validate_annotation
    from framework.knowledge_graph.schema import load_graph_schema
    rows=[json.loads(line) for line in SOURCE.read_text(encoding='utf-8').splitlines()]
    existing=[json.loads(line) for line in LEDGER.read_text(encoding='utf-8').splitlines()] if LEDGER.exists() else []
    seen={r['index'] for r in existing}
    output=[]
    for decision in decisions:
        index=decision['index']
        if index in seen:
            raise ValueError(f'duplicate decision: {index}')
        if len(decision.get('reason',''))<12:
            raise ValueError('a source-specific review rationale is required')
        source=rows[index]['source'];proposal=rows[index]['proposal']
        entities=decision.get('entities',proposal['entities'])
        entities=[dict(name=e[0],type=e[1]) if isinstance(e,list) else e for e in entities]
        relations=[]
        for relation in decision.get('relations',list(range(len(proposal['relationships'])))):
            if isinstance(relation,int):
                relation=proposal['relationships'][relation]
            relations.append({k:relation[k] for k in ('source','target','relation_type','quote')})
        verified=validate_annotation(source,dict(entities=entities,relationships=relations),load_graph_schema())
        if verified['validation_errors']:
            raise ValueError(f'invalid adjudication {index}: {verified["validation_errors"]}')
        output.append(dict(index=index,sample_id=source['sample_id'],source_text_sha256=source['text_sha256'],
            parent_proposal_sha256=rows[index]['proposal_sha256'],reviewer='Codex',reviewer_kind='ai_agent',
            method='direct_source_adjudication',independent_human_review=False,
            reviewed_at=datetime.now(UTC).isoformat(),reason=decision['reason'],
            revised=(verified['entities']!=proposal['entities'] or verified['relationships']!=proposal['relationships']),
            annotation=verified))
        seen.add(index)
    with LEDGER.open('a',encoding='utf-8',newline='\n') as stream:
        for row in output:
            stream.write(json.dumps(row,ensure_ascii=False,sort_keys=True)+'\n')
    progress=dict(state='reviewing' if len(seen)<len(rows) else 'source_review_complete',
        reviewed_samples=len(seen),total_samples=len(rows),reviewer='Codex',reviewer_kind='ai_agent',
        independent_human_review=False,next_unreviewed_index=next((i for i in range(len(rows)) if i not in seen),None),
        updated_at=datetime.now(UTC).isoformat())
    LEDGER.with_name('codex-review-progress.json').write_text(json.dumps(progress,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    page=LEDGER.with_name('review.html')
    if page.exists():
        import re
        html=page.read_text(encoding='utf-8')
        banner=f'<p id="codex-progress">Codex 原文直接审核：{len(seen)} / {len(rows)}。审核者为 AI 智能体，未标记为专家人工审核；最终评测尚待完整参考集冻结。</p>'
        if 'id="codex-progress"' in html:
            html=re.sub(r'<p id="codex-progress">.*?</p>',banner,html,count=1)
        else:
            html=html.replace('<h1>金标 v3 原文复核</h1>','<h1>金标 v3 原文复核</h1>'+banner,1)
        page.write_text(html,encoding='utf-8')
    print(json.dumps(dict(reviewed=len(existing)+len(output),added=len(output),target=len(rows))))


def show(start,end):
    rows=[json.loads(x) for x in SOURCE.read_text(encoding='utf-8').splitlines()]
    last_document=None
    for i in range(start,min(end,len(rows))):
        r=rows[i];s=r['source'];p=r['proposal']
        if s['document_id']!=last_document:
            print(f'\nDOCUMENT {s["document_id"]}: {s["document_title"]}')
            last_document=s['document_id']
        print(f'\n=== {i} | page {s["page"]} ===\n{s["text"]}')
        print('E: '+'; '.join(f'{j}:{e["name"]}({e["type"]})' for j,e in enumerate(p['entities'])))
        for j,rel in enumerate(p['relationships']):
            print(f'R{j}: {rel["source"]} --{rel["relation_type"]}--> {rel["target"]}; QUOTE: {rel["quote"]}')
        if p['validation_errors']:
            print('VALIDATION_ERRORS',p['validation_errors'])


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('--show',nargs=2,type=int)
    args=parser.parse_args()
    if args.show:
        show(*args.show)
