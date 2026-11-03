"""Bounded continuation only for never-emitted fields in final issue judgments."""
import asyncio
import copy
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import scripts.run_kg_benchmark_pilot as engine
from scripts.build_kg_benchmark_references import initial_job,response,review_job,freeze_config
from scripts.rebuild_kg_extraction_benchmark import OUT,OLD,readlines,dump
from scripts.replay_kg_benchmark_reference_review import validate
from framework.knowledge_graph.benchmark_final_field_completion import plan_relation_completion,merge_relation_completion
from framework.knowledge_graph.benchmark_partial_annotation import partial_annotation
from framework.knowledge_graph.benchmark_reference_schema import build_reference_schema
from framework.knowledge_graph.benchmark_protocol import load_schema
from framework.knowledge_graph.benchmark_cells import indexed_block
from framework.knowledge_graph.benchmark_budget_policy_v2 import AuthorizedBudgetV2
from framework.knowledge_graph.benchmark_rebuild import sha256_file
from framework.knowledge_graph.benchmark_reference_hold import require_no_semantic_hold

BASE=OUT/'references-v1/test';RUN=BASE/'truncated-field-continuation'
AUTH=OUT/'execution/project-budget-authorization-v2.json';ALLOCATION=OUT/'execution/phase-allocation-v2.json'


async def run():
    require_no_semantic_hold(OUT)
    budget=AuthorizedBudgetV2(OLD/'budget.sqlite3',authorization=AUTH,allocation=ALLOCATION)
    if budget.summary()['inflight']:raise ValueError('wait_for_all_original_requests_to_finish')
    state=json.loads((BASE/'issue-adjudication/run-state.json').read_text(encoding='utf-8'))
    if state.get('runner_active') is not False:raise ValueError('issue_runner_not_terminal')
    packets={r['sample_id']:r for r in readlines(OUT/'dataset-v1/annotation-inputs.jsonl')}
    jobs=[];plans={};unsupported=[];files=[Path(__file__),AUTH,ROOT/'framework/knowledge_graph/benchmark_final_field_completion.py']
    for path in sorted((BASE/'issue-adjudication/proposals').glob('*.json')):
        row=json.loads(path.read_text(encoding='utf-8'))
        if row['state']!='incomplete':continue
        sid=row['id'].removeprefix('unresolved-source-case:');packet=packets[sid]
        pair=[response(BASE/'initial',initial_job(packet,role,'reference_test')) for role in ['A','B']]
        p=review_job(packet,[dict(proposal=partial_annotation(r,packet)[0]) for r in pair],'reference_test_adjudication')['packet']
        try:completed,missing=plan_relation_completion(row['content'],len(p['candidate']['relations']))
        except ValueError as exc:
            unsupported.append(dict(sample_id=sid,error=str(exc),no_request_sent=True));continue
        item=copy.deepcopy(build_reference_schema(p['candidate'],load_schema(ROOT))['json_schema']['schema']['properties']['relation_reviews'])
        item['items']['properties']['index']['enum']=missing;item['minItems']=len(missing);item['maxItems']=len(missing)
        fmt=dict(type='json_schema',json_schema=dict(name='only_unemitted_relation_reviews',strict=True,
            schema=dict(type='object',properties=dict(relation_reviews=item),required=['relation_reviews'],additionalProperties=False)))
        source=dict(sample_id=sid,blocks=[indexed_block(b) for b in p['blocks']],candidate=p['candidate'],
            frozen_decision_reviews=completed['decision_reviews'],frozen_additions=completed['additions'],missing_relation_indices=missing)
        prompt=p['handbook']+'\n前一来源裁决因输出长度截断。本请求只判定未输出的relation_reviews索引，不重新判定已完整输出的实体、关系或掩码。逐项核对source及最终纳入实体。supported必须有正文断言，题名只能identity；端点被排除不能supported。不确定用uncertain，不猜答案。每个missing_relation_indices恰好一次，只输出relation_reviews列表，逐字证据用block_id/start_cell/end_cell（两端包含）。理由简短，项目完整。'
        job=dict(id='unemitted-fields:'+sid,phase='reference_test_continuation',packet=p,
            options=dict(messages=[dict(role='system',content=prompt),dict(role='user',content=json.dumps(source,ensure_ascii=False))],max_tokens=8192,response_format=fmt))
        jobs.append(job);plans[sid]=dict(completed=completed,missing=missing,
            original_response_path=path.relative_to(ROOT).as_posix(),original_response_sha256=sha256_file(path));files.append(path)
    plan=dict(cases=plans,unsupported=unsupported,completed_judgments_immutable=True,
        original_response_remains_incomplete=True,full_request_not_repeated=True)
    freeze_config(RUN/'field-plan.json',plan);files.append(RUN/'field-plan.json')
    def check(packet,raw,schema):
        p=plans[packet['sample_id']]
        merged=merge_relation_completion(p['completed'],p['missing'],raw)
        return dict(validate(packet,merged,schema),field_continuation=True,original_judgments_modified=False)
    config=dict(model='deepseek-ai/DeepSeek-V4.1-Flash',endpoint='https://api.siliconflow.cn/v1',
        global_tokens=20000000,global_requests=5000,concurrency=2,semantic_retries=0,
        jobs={j['id']:engine.digest(j) for j in jobs},
        files=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha256_file(p)) for p in files])
    freeze_config(RUN/'run-config.json',config)
    engine.RUN=RUN;engine.validate_proposal=check
    engine.Budget=lambda p,**ignored:AuthorizedBudgetV2(p,authorization=AUTH,allocation=ALLOCATION)
    engine.limits=lambda:dict(stability=2200000,total=20000000,requests=5000)
    print(json.dumps(await engine.execute(jobs,config)))


if __name__=='__main__':asyncio.run(run())
