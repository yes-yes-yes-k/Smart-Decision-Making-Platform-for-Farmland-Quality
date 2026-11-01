"""One source adjudication per final-reference issue under the shared 20M cap."""
import asyncio
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import scripts.run_kg_benchmark_pilot as engine
from scripts.adjudicate_kg_reference_issues import RULES
from scripts.build_kg_benchmark_references import initial_job,response,review_job,freeze_config
from scripts.replay_kg_benchmark_reference_review import validate
from scripts.rebuild_kg_extraction_benchmark import OUT,OLD,dump,readlines
from scripts.prepare_kg_benchmark_metadata import current_qualification
from framework.knowledge_graph.benchmark_budget_policy_v2 import AuthorizedBudgetV2
from framework.knowledge_graph.benchmark_partial_annotation import partial_annotation
from framework.knowledge_graph.benchmark_rebuild import sha256_file
from framework.knowledge_graph.benchmark_reference_hold import require_no_semantic_hold

BASE=OUT/'references-v1/test';RUN=BASE/'issue-adjudication'
AUTH=OUT/'execution/project-budget-authorization-v2.json'
ALLOCATION=OUT/'execution/phase-allocation-v2.json'


def select_cases(items,accepted,gate_issues):
    """Canonical duplicate compilation can resolve structure, never evidence."""
    cases={i['sample_id']:dict(source='incomplete_source_reference',
        errors=i.get('compiled',{}).get('errors',[]))
        for i in items if not i['reference_ready'] and i['sample_id'] not in accepted}
    for r in gate_issues:
        cases[r['sample_id']]=dict(source='independent_release_gate',errors=r['release_gate']['errors'])
    return cases


async def run():
    require_no_semantic_hold(OUT)
    state=json.loads((BASE/'run-state.json').read_text(encoding='utf-8'))
    if state.get('active') is not False:raise ValueError('original_final_runner_not_terminal')
    budget=AuthorizedBudgetV2(OLD/'budget.sqlite3',authorization=AUTH,allocation=ALLOCATION)
    if budget.summary()['inflight']:raise ValueError('another_model_request_is_inflight')
    packets={p['sample_id']:p for p in readlines(OUT/'dataset-v1/annotation-inputs.jsonl')}
    membership={r['sample_id']:r for r in readlines(OUT/'dataset-v1/test-samples.jsonl')}
    items=readlines(BASE/'items.jsonl')
    if {i['sample_id'] for i in items}!=set(membership):raise ValueError('final400_roster_incomplete')
    if any(i['status']=='not_started' for i in items):raise ValueError('initial_batch_not_finished')
    max_attempt=0
    for folder in [BASE/'initial/proposals',BASE/'review/proposals']:
        for path in folder.glob('*.json'):
            row=json.loads(path.read_text(encoding='utf-8'))
            max_attempt=max([max_attempt]+row.get('attempt_ids',[]))
    if state.get('budget',{}).get('requests',0)<max_attempt:raise ValueError('terminal_checkpoint_not_current')
    path=RUN/'selection.json'
    if path.exists():cases=json.loads(path.read_text(encoding='utf-8'))['cases']
    else:
        accepted={r['sample_id'] for r in readlines(OUT/'reference-release-v1/test/references.jsonl')}
        cases=select_cases(items,accepted,readlines(OUT/'reference-release-v1/test/requires-adjudication.jsonl'))
        dump(path,dict(cases=cases,previous_responses_immutable=True,
            one_new_adjudication_per_case=True,semantic_retry_loop=False))
    if not set(cases).issubset(membership):raise ValueError('adjudication_wrong_partition')
    document_ids={membership[sid]['document_id'] for sid in cases}
    documents=[d for d in readlines(OUT/'execution/source-review-r1/document-pool-refined.jsonl') if d['id'] in document_ids]
    qualification=current_qualification(documents)
    if set(qualification)!=document_ids or not all(qualification.values()):raise ValueError('current_public_source_qualification_changed')
    dump(RUN/'source-qualification.json',dict(current_public_approved_verified=qualification,read_only=True))
    jobs=[];diagnostics=[]
    for sid in sorted(cases):
        packet=packets[sid]
        pair=[response(BASE/'initial',initial_job(packet,role,'reference_test')) for role in ['A','B']]
        if not all(pair):raise ValueError('missing_initial_response:'+sid)
        proposals=[]
        for role,row in zip(['A','B'],pair):
            proposal,diagnostic=partial_annotation(row,packet)
            proposals.append(dict(proposal=proposal));diagnostics.append(dict(sample_id=sid,role=role,**diagnostic))
        job=review_job(packet,proposals,'reference_test_adjudication')
        job['id']='unresolved-source-case:'+sid
        job['options']['messages'][0]['content']+='\n'+RULES
        if any(r['state']!='protocol_valid' for r in pair):
            job['options']['messages'][0]['content']+='\n初标可能含截断或非法项目。candidate仅保留实际完整发出的原文候选，不代表完整清单；必须通读全部source补齐共同漏项，不能把候选缺失当负例或据此排除任务。初标仍记不完整或无效。'
        if any(r['state']=='incomplete' for r in pair):job['options']['max_tokens']=8192
        job['options']['messages'][0]['content']+='\n逐项理由简短，保留必要原文证据和全部真实对象，不用长篇理由挤掉项目。'
        jobs.append(job)
    dump(RUN/'initial-response-diagnostics.json',dict(items=diagnostics,original_responses_modified=False,
        original_protocol_failures_not_reclassified_as_success=True))
    dependencies=[Path(__file__),path,AUTH,ROOT/'scripts/adjudicate_kg_reference_issues.py',
        OUT/'dataset-v1/manifest.json',OUT/'annotation-workflow-v1.json']
    config=dict(model='deepseek-ai/DeepSeek-V4.1-Flash',endpoint='https://api.siliconflow.cn/v1',
        global_tokens=20000000,global_requests=5000,concurrency=2,semantic_retries=0,
        purpose='one_independent_source_adjudication_per_final_reference_issue',
        final_candidate_evaluation_allowed=False,jobs={j['id']:engine.digest(j) for j in jobs},
        files=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha256_file(p)) for p in dependencies])
    freeze_config(RUN/'run-config.json',config)
    engine.RUN=RUN;engine.validate_proposal=validate
    engine.Budget=lambda p,**ignored:AuthorizedBudgetV2(p,authorization=AUTH,allocation=ALLOCATION)
    engine.limits=lambda:dict(stability=2200000,total=20000000,requests=5000)
    print(json.dumps(await engine.execute(jobs,config)))


if __name__=='__main__':asyncio.run(run())
