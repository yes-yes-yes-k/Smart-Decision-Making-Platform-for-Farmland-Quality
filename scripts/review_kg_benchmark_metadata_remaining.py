"""Finish untouched metadata items; enforce PDF/body evidence classes in schema."""
import asyncio
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import scripts.run_kg_benchmark_pilot as engine
import scripts.review_kg_benchmark_metadata as first
import scripts.review_kg_benchmark_metadata_v2 as second
from scripts.rebuild_kg_extraction_benchmark import OUT,dump,readlines
from scripts.prepare_kg_benchmark_metadata import current_qualification
from framework.knowledge_graph.benchmark_budget_policy import AuthorizedBudget
from framework.knowledge_graph.benchmark_rebuild import sha256_file

RUN=OUT/'execution/source-metadata-review-v3'


def schema_for(packet):
    fmt=second.schema();props=fmt['json_schema']['schema']['properties']
    pdf=['s'+str(i) for i,s in enumerate(packet['sections']) if s['kind']=='pdf_page_text']
    body=['s'+str(i) for i,s in enumerate(packet['sections']) if s['kind']=='stored_chunk_excerpt']
    def ids(values):return dict(type='array',items=dict(type='string',enum=values)) if values else dict(type='array',items=dict(type='string'),maxItems=0)
    props['title_ids']=ids(pdf);props['identifier_ids']=ids(pdf);props['body_quality_ids']=ids(body)
    if not pdf:props['identity_status']=dict(type='string',enum=['requires_visual','unknown'])
    fmt['json_schema']['name']='metadata_typed_evidence_ids'
    return fmt


async def run():
    engine.RUN=RUN
    auth=OUT/'execution/project-budget-authorization.json';allocation=OUT/'execution/phase-allocation.json'
    engine.Budget=lambda path,**ignored:AuthorizedBudget(path,authorization=auth,allocation=allocation)
    engine.limits=lambda:dict(stability=2200000,total=10000000,requests=5000)
    attempted={}
    for prior in [first.RUN,second.RUN]:
        for path in (prior/'proposals').glob('*.json'):
            row=json.loads(path.read_text(encoding='utf-8'));attempted[int(row['id'].split(':')[1])]=dict(sha256=sha256_file(path),state=row['state'])
    packets=[p for p in readlines(OUT/'metadata-review-preparation/source-packets.jsonl') if p['document_id'] not in attempted]
    pool={d['id']:d for d in readlines(OUT/'execution/source-review-r1/document-pool-refined.jsonl')}
    if not all(current_qualification([pool[p['document_id']] for p in packets]).values()):raise ValueError('public_source_qualification_changed')
    jobs=[]
    for p in packets:
        mapping={'s'+str(i):s['id'] for i,s in enumerate(p['sections'])}
        source=dict(document_id=p['document_id'],filename_hint=p['filename_hint'],filename_is_unverified_hint=True,
            sections=[dict(id='s'+str(i),kind=s['kind'],page=s['page'],text=s['text']) for i,s in enumerate(p['sections'])],profile_scope=p['profile_scope'])
        jobs.append(dict(id='metadata-v3:'+str(p['document_id']),phase='source_metadata',packet=dict(p,short_id_mapping=mapping),
            options=dict(messages=[dict(role='system',content=first.INSTRUCTION+'\n只选择显示的短证据编号，PDF身份和分块质量证据类别不得混用。'),
                dict(role='user',content=json.dumps(source,ensure_ascii=False))],max_tokens=1536,response_format=schema_for(p))))
    files=[Path(__file__),ROOT/'scripts/review_kg_benchmark_metadata.py',ROOT/'scripts/review_kg_benchmark_metadata_v2.py',OUT/'metadata-review-preparation/manifest.json']
    config=dict(model='deepseek-ai/DeepSeek-V4.1-Flash',endpoint='https://api.siliconflow.cn/v1',
        scope='untouched_bibliographic_metadata_only',prior_attempts_retained=attempted,remaining_documents=len(jobs),
        global_token_limit=10000000,global_request_limit=5000,concurrency=2,
        jobs={j['id']:engine.digest(j) for j in jobs},files=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha256_file(p)) for p in files])
    path=RUN/'run-config.json'
    if path.exists() and json.loads(path.read_text(encoding='utf-8'))!=config:raise ValueError('metadata_v3_config_frozen')
    if not path.exists():dump(path,config)
    engine.validate_proposal=second.check
    print(json.dumps(await engine.execute(jobs,config)))


if __name__=='__main__':asyncio.run(run())
