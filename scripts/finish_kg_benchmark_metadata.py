"""Finish never-requested metadata sources with the explicit field contract."""
import asyncio
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import scripts.run_kg_benchmark_pilot as engine
import scripts.review_kg_benchmark_metadata as first
import scripts.review_kg_benchmark_metadata_v2 as second
import scripts.review_kg_benchmark_metadata_remaining as third
from scripts.review_kg_benchmark_metadata_v4 import check
from scripts.validate_kg_metadata_contract import CONTRACT
from scripts.validate_kg_metadata_identity_scope import CLARIFICATION
from scripts.rebuild_kg_extraction_benchmark import OUT,OLD,dump,readlines
from scripts.prepare_kg_benchmark_metadata import current_qualification
from framework.knowledge_graph.benchmark_budget_policy import AuthorizedBudget
from framework.knowledge_graph.benchmark_rebuild import sha256_file

RUN=OUT/'execution/source-metadata-review-v5'


async def run():
    engine.RUN=RUN
    auth=OUT/'execution/project-budget-authorization.json';allocation=OUT/'execution/phase-allocation.json'
    engine.Budget=lambda path,**ignored:AuthorizedBudget(path,authorization=auth,allocation=allocation)
    engine.limits=lambda:dict(stability=2200000,total=10000000,requests=5000)
    engine.validate_proposal=check
    budget=AuthorizedBudget(OLD/'budget.sqlite3',authorization=auth,allocation=allocation)
    snapshot=RUN/'selection.json'
    if snapshot.exists():chosen=json.loads(snapshot.read_text(encoding='utf-8'))['document_ids']
    else:
        with budget.connect() as conn:before=[r[0] for r in conn.execute('SELECT job FROM attempts')]
        attempted={int(j.split(':')[1]) for j in before if j.split(':')[0] in ['metadata','metadata-v2','metadata-v3','metadata-v4']}
        chosen=[p['document_id'] for p in readlines(OUT/'metadata-review-preparation/source-packets.jsonl') if p['document_id'] not in attempted]
        dump(snapshot,dict(document_ids=chosen,prior_attempted_ids=sorted(attempted),failed_or_interrupted_not_retried=True))
    packets=[p for p in readlines(OUT/'metadata-review-preparation/source-packets.jsonl') if p['document_id'] in chosen]
    pool={d['id']:d for d in readlines(OUT/'execution/source-review-r1/document-pool-refined.jsonl')}
    if not all(current_qualification([pool[p['document_id']] for p in packets]).values()):raise ValueError('source_qualification_changed')
    jobs=[]
    for p in packets:
        source=dict(sections=[dict(id='s'+str(i),kind=s['kind'],page=s['page'],text=s['text']) for i,s in enumerate(p['sections'])],profile_scope=p['profile_scope'])
        packet=dict(p,short_id_mapping={'s'+str(i):s['id'] for i,s in enumerate(p['sections'])})
        prompt=first.INSTRUCTION+'\n'+CONTRACT+'\n'+CLARIFICATION+'\n编号须包含字母前缀、斜杠/T、完整数字（含小数分部）和年份；分行时选择所有相邻片段，不能只选数字行。无法给出完整证据时标unknown，不猜编号。\nJSON_SCHEMA\n'+json.dumps(second.schema()['json_schema']['schema'],ensure_ascii=False)
        jobs.append(dict(id='metadata-v5:'+str(p['document_id']),phase='source_metadata',packet=packet,
            options=dict(messages=[dict(role='system',content=prompt),dict(role='user',content=json.dumps(source,ensure_ascii=False))],
                max_tokens=1536,response_format=third.schema_for(p))))
    dependencies=[Path(__file__),Path(first.__file__),Path(second.__file__),Path(third.__file__),snapshot,
        ROOT/'scripts/review_kg_benchmark_metadata_v4.py',ROOT/'scripts/validate_kg_metadata_contract.py',ROOT/'scripts/validate_kg_metadata_identity_scope.py']
    config=dict(model='deepseek-ai/DeepSeek-V4.1-Flash',endpoint='https://api.siliconflow.cn/v1',source_count=len(jobs),
        purpose='remaining_unattempted_source_metadata',blind_to_prior_answers=True,
        jobs={j['id']:engine.digest(j) for j in jobs},files=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha256_file(p)) for p in dependencies])
    path=RUN/'run-config.json'
    if path.exists() and json.loads(path.read_text(encoding='utf-8'))!=config:raise ValueError('metadata_v5_config_frozen')
    if not path.exists():dump(path,config)
    print(json.dumps(await engine.execute(jobs,config)))


if __name__=='__main__':asyncio.run(run())
