"""One source adjudication per unresolved case; preserve every original failure."""
import asyncio
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import scripts.run_kg_benchmark_pilot as engine
from scripts.build_kg_benchmark_references import initial_job,response,review_job
from scripts.replay_kg_benchmark_reference_review import validate
from scripts.rebuild_kg_extraction_benchmark import OUT,dump,readlines
from framework.knowledge_graph.benchmark_budget_policy import AuthorizedBudget
from framework.knowledge_graph.benchmark_rebuild import sha256_file
from scripts.prepare_kg_benchmark_metadata import current_qualification
from framework.knowledge_graph.benchmark_partial_annotation import partial_annotation

BASE=OUT/'references-v1/calibration';RUN=BASE/'issue-adjudication'
RULES='''本次为未决案件的单独来源裁决，不沿用先前裁决，不投票。candidate仅含两份独立初标候选并集，不含旧参考答案。
严格执行已冻结规则：document_title中的引文只能作identity证据，关系assertion必须来自chunk正文。
仅有标准编号、题名、共现或治理目标，不能断言已实际改善或缓解；没有正文断言时关系为无，不把题名中的“改良”当实测效果。
“改良/改善/治理/修复”等泛称没有具体干预动作及必要对象时，不能凭常识补出措施。逐项核查实体、关系及共同漏项。
每个候选必须有独立取舍和原文依据，不重复加入同类型同位置实体；关系端点必须来自最终纳入实体。
不同适用条件必须保留，不合并为无条件事实。无实体/关系仍是有效负例，不能因此设unknown/excluded掩码。
只因来源本身无法可靠判定才可给固定任务未知，并提供原文证据；不得用掩码掩盖标注或校验失败。
这是每个未决案件唯一一次补充裁决请求；若仍不可靠，明确policy_conflicts，不编造确定答案。'''


async def run():
    state=json.loads((BASE/'run-state.json').read_text(encoding='utf-8'))
    # The caller must have observed the original runner terminate before running
    # this stage; the fully attempted initial roster is an additional guard.
    packets={p['sample_id']:p for p in readlines(OUT/'dataset-v1/annotation-inputs.jsonl')}
    items=readlines(BASE/'items.jsonl')
    if any(i['status']=='not_started' for i in items):raise ValueError('initial_batch_not_finished')
    max_attempt=0
    for folder in [BASE/'initial/proposals',BASE/'review/proposals']:
        for p in folder.glob('*.json'):
            r=json.loads(p.read_text(encoding='utf-8'));max_attempt=max([max_attempt]+r.get('attempt_ids',[]))
    if state.get('active') is not False or state.get('budget',{}).get('requests',0)<max_attempt:
        raise ValueError('original_runner_terminal_checkpoint_not_current')
    path=RUN/'selection.json'
    if path.exists():cases=json.loads(path.read_text(encoding='utf-8'))['cases']
    else:
        accepted_path=OUT/'reference-release-v1/calibration/references.jsonl'
        accepted={r['sample_id'] for r in readlines(accepted_path)} if accepted_path.exists() else set()
        cases={i['sample_id']:dict(source='incomplete_source_reference',errors=i.get('compiled',{}).get('errors',[])) for i in items if not i['reference_ready'] and i['sample_id'] not in accepted}
        for r in readlines(OUT/'reference-release-v1/calibration/requires-adjudication.jsonl'):
            cases[r['sample_id']]=dict(source='independent_release_gate',errors=r['release_gate']['errors'])
        dump(path,dict(cases=cases,previous_responses_immutable=True,one_new_adjudication_per_case=True,semantic_retry_loop=False))
    membership={r['sample_id']:r for r in readlines(OUT/'dataset-v1/calibration-samples.jsonl')}
    document_ids={membership[sid]['document_id'] for sid in cases}
    documents=[d for d in readlines(OUT/'execution/source-review-r1/document-pool-refined.jsonl') if d['id'] in document_ids]
    qualification=current_qualification(documents)
    if not all(qualification.values()):raise ValueError('current_public_source_qualification_changed')
    dump(RUN/'source-qualification.json',dict(current_public_approved_verified=qualification,read_only=True))
    engine.RUN=RUN
    engine.Budget=lambda p,**ignored:AuthorizedBudget(p,authorization=OUT/'execution/project-budget-authorization.json',allocation=OUT/'execution/phase-allocation.json')
    engine.limits=lambda:dict(stability=2200000,total=10000000,requests=5000);engine.validate_proposal=validate
    jobs=[];diagnostics=[]
    for sid in cases:
        p=packets[sid];pair=[response(BASE/'initial',initial_job(p,role,'reference_calibration')) for role in ['A','B']]
        if not all(pair):continue
        proposals=[]
        for role,r in zip(['A','B'],pair):
            proposal,diagnostic=partial_annotation(r,p)
            proposals.append(dict(proposal=proposal));diagnostics.append(dict(sample_id=sid,role=role,**diagnostic))
        job=review_job(p,proposals,'reference_calibration_adjudication')
        job['id']='unresolved-source-case:'+sid;job['options']['messages'][0]['content']+='\n'+RULES
        if any(r['state']!='protocol_valid' for r in pair):
            job['options']['messages'][0]['content']+='\n两份初标可能含截断或非法项目。candidate仅保留实际完整发出的原文候选，不代表完整清单；必须重新通读全部source，补齐共同漏项，不能把候选缺失当负例或据此排除任务。原初标仍记不完整/无效，本次为单独来源裁决，不改初标完成率。'
        if any(r['state']=='incomplete' for r in pair):
            job['options']['max_tokens']=8192
            job['options']['messages'][0]['content']+='\n逐项理由简短，保留必要的原文证据和全部真实对象，不能用长篇理由挤掉项目。'
        jobs.append(job)
    dump(RUN/'initial-response-diagnostics.json',dict(items=diagnostics,original_responses_modified=False,
        original_protocol_failures_not_reclassified_as_success=True))
    dependencies=[Path(__file__),path,OUT/'dataset-v1/manifest.json',OUT/'annotation-workflow-v1.json']
    config=dict(model='deepseek-ai/DeepSeek-V4.1-Flash',endpoint='https://api.siliconflow.cn/v1',
        purpose='one_independent_source_adjudication_of_remaining_cases',no_same_request_semantic_retry=True,
        jobs={j['id']:engine.digest(j) for j in jobs},files=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha256_file(p)) for p in dependencies])
    cfg=RUN/'run-config.json'
    if cfg.exists() and json.loads(cfg.read_text(encoding='utf-8'))!=config:raise ValueError('issue_adjudication_frozen')
    if not cfg.exists():dump(cfg,config)
    print(json.dumps(await engine.execute(jobs,config)))


if __name__=='__main__':asyncio.run(run())
