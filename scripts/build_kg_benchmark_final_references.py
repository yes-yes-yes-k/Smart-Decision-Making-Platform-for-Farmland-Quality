"""Build the frozen final 400 reference labels under explicit 20M authorization."""
import asyncio
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import scripts.run_kg_benchmark_pilot as engine
from scripts.build_kg_benchmark_references import initial_job,review_job,response,compile_progress,configuration,freeze_config
from scripts.run_kg_benchmark_pilot_r4 import check as initial_check
from scripts.replay_kg_benchmark_reference_review import validate as review_check
from scripts.rebuild_kg_extraction_benchmark import OUT,dump,readlines,budget_snapshot
from scripts.prepare_kg_benchmark_metadata import current_qualification
from framework.knowledge_graph.benchmark_budget_policy_v2 import AuthorizedBudgetV2
from framework.knowledge_graph.benchmark_rebuild import sha256_file

AUTH=OUT/'execution/project-budget-authorization-v2.json';ALLOCATION=OUT/'execution/phase-allocation-v2.json'
BASE=OUT/'references-v1/test'


def config_for(run,jobs,stage):
    result=configuration(run,jobs,stage)
    result.update(global_tokens=20000000,explicit_authorization=AUTH.relative_to(ROOT).as_posix(),
        explicit_authorization_sha256=sha256_file(AUTH),final_candidate_evaluation_allowed=False,
        purpose='reference_construction_only_not_candidate_acceptance')
    result['files'] += [dict(path=p.relative_to(ROOT).as_posix(),sha256=sha256_file(p)) for p in [Path(__file__),
        ROOT/'framework/knowledge_graph/benchmark_budget_policy_v2.py',AUTH]]
    return result


async def run():
    for manifest_path in [OUT/'dataset-v1/manifest.json',OUT/'calibration-silver-v1/manifest.json',OUT/'annotation-workflow-v1.json']:
        manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
        for f in manifest['files']:
            if sha256_file(ROOT/f['path'])!=f['sha256']:raise ValueError('frozen_reference_dependency_changed:'+f['path'])
    membership=readlines(OUT/'dataset-v1/test-samples.jsonl');ids={r['sample_id'] for r in membership}
    packets=[p for p in readlines(OUT/'dataset-v1/annotation-inputs.jsonl') if p['sample_id'] in ids]
    if len(packets)!=400:raise ValueError('frozen_final400_required')
    documents={r['document_id'] for r in membership}
    original=[r for r in readlines(OUT/'execution/source-review-r1/document-pool-refined.jsonl') if r['id'] in documents]
    qualified=current_qualification(original)
    if not all(qualified.values()):raise ValueError('final_reference_sources_no_longer_public_approved')
    dump(BASE/'source-qualification.json',dict(current_public_approved=qualified,read_only=True))
    approval=json.loads((OUT/'execution/remote-authorization.json').read_text(encoding='utf-8'))
    if approval['resumed_by']!='user' or approval['suspended']:raise ValueError('remote_authorization_not_active')
    approval.update(scope_detail='frozen_400_final_reference_construction_only',budget_authorization_sha256=sha256_file(AUTH))
    auth_path=BASE/'remote-authorization.json'
    if not auth_path.exists():dump(auth_path,approval)
    elif json.loads(auth_path.read_text(encoding='utf-8'))!=approval:raise ValueError('final_source_authorization_changed')
    packets.sort(key=lambda p:engine.digest('reference-order:'+p['sample_id']))
    engine.Budget=lambda path,**ignored:AuthorizedBudgetV2(path,authorization=AUTH,allocation=ALLOCATION)
    engine.limits=lambda:dict(stability=2200000,total=20000000,requests=5000)
    phase='reference_test';jobs={(p['sample_id'],role):initial_job(p,role,phase) for p in packets for role in ['A','B']}
    config=config_for(BASE/'initial',list(jobs.values()),'independent_A_B')
    freeze_config(BASE/'initial/run-config.json',config);stopped=False
    dump(BASE/'run-state.json',dict(active=True,expected=400,budget=budget_snapshot(),automatic_resume=False))
    try:
        for offset in range(0,len(packets),4):
            batch=packets[offset:offset+4];engine.RUN=BASE/'initial';engine.validate_proposal=initial_check
            result=await engine.execute([jobs[p['sample_id'],role] for p in batch for role in ['A','B']],config)
            review=[]
            for p in batch:
                pair=[response(BASE/'initial',jobs[p['sample_id'],role]) for role in ['A','B']]
                if all(r and r['state']=='protocol_valid' for r in pair):review.append(review_job(p,pair,phase))
            if review and not result['stopped']:
                engine.RUN=BASE/'review';engine.validate_proposal=review_check
                cfg=config_for(BASE/'review',review,'independent_source_adjudication')
                freeze_config(BASE/f'review/batch-{offset:03d}-config.json',cfg)
                result=await engine.execute(review,cfg)
            compile_progress(BASE,packets,jobs)
            if result['stopped']:stopped=True;break
    finally:
        compile_progress(BASE,packets,jobs)
        dump(BASE/'run-state.json',dict(active=False,expected=400,budget_or_service_stopped=stopped,budget=budget_snapshot(),automatic_resume=False))


if __name__=='__main__':asyncio.run(run())
