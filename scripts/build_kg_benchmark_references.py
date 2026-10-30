"""Frozen three-stage reference construction, complete small batches under caps."""
import argparse
import asyncio
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import scripts.run_kg_benchmark_pilot as engine
from scripts.run_kg_benchmark_pilot_r4 import check as initial_check,EXAMPLE,ENUMS
from scripts.review_kg_benchmark_reference import RULES
from scripts.replay_kg_benchmark_reference_review import validate as review_check
from scripts.rebuild_kg_extraction_benchmark import OUT,OLD,dump,lines,readlines,budget_snapshot
from framework.knowledge_graph.benchmark_protocol import load_schema
from framework.knowledge_graph.benchmark_cells import indexed_block
from framework.knowledge_graph.benchmark_legacy_proposal_union import union_legacy_proposals
from framework.knowledge_graph.benchmark_reference_schema import build_reference_schema
from framework.knowledge_graph.benchmark_reference_compile import compile_reference
from framework.knowledge_graph.benchmark_budget_policy import AuthorizedBudget
from framework.knowledge_graph.benchmark_rebuild import sha256_file
from scripts.report_kg_benchmark_pilot import signature


def response(run,job):
    path=run/'proposals'/(engine.digest(job['id'])+'.json')
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else None


def initial_job(packet,role,phase):
    ontology=load_schema(ROOT)
    instruction='只返回JSON。下面是字段形式示例，不是待抽取事实，不要照抄示例实体或关系。\n'+json.dumps(EXAMPLE,ensure_ascii=False)+'\n允许值枚举：'+json.dumps(ENUMS,ensure_ascii=False)
    instruction+='\n本体方向：'+json.dumps(dict(entity_types=ontology['entity_types'],relation_types=ontology['relation_types']),ensure_ascii=False)
    source=dict(sample_id=packet['sample_id'],blocks=[indexed_block(b) for b in packet['blocks']],output_protocol=packet['output_protocol'])
    return dict(id=role+':'+packet['sample_id'],phase=phase,packet=packet,answer_keys_in_request=False,
        options=dict(messages=[dict(role='system',content=packet['handbook']+'\n'+instruction),dict(role='user',content=json.dumps(source,ensure_ascii=False))],
            max_tokens=4096,response_format=dict(type='json_object')))


def review_job(packet,pair,phase):
    candidate=union_legacy_proposals([r['proposal'] for r in pair])
    p=dict(packet,candidate=candidate)
    source=dict(sample_id=p['sample_id'],blocks=[indexed_block(b) for b in p['blocks']],candidate=candidate)
    return dict(id='source-review:'+p['sample_id'],phase=phase,packet=p,
        options=dict(messages=[dict(role='system',content=p['handbook']+'\n'+RULES),dict(role='user',content=json.dumps(source,ensure_ascii=False))],
            max_tokens=6144,response_format=build_reference_schema(candidate,load_schema(ROOT))))


def configuration(run,jobs,stage):
    paths=[Path(__file__),OUT/'dataset-v1/manifest.json',OUT/'annotation-workflow-v1.json']
    return dict(model='deepseek-ai/DeepSeek-V4.1-Flash',endpoint='https://api.siliconflow.cn/v1',stage=stage,
        sample_partition=run.parent.name,global_tokens=10000000,global_requests=5000,concurrency=2,
        semantic_retries=0,expert_certified=False,same_model_error_correlation=True,
        files=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha256_file(p)) for p in paths],
        jobs={j['id']:engine.digest(j) for j in jobs})


def freeze_config(path,config):
    if path.exists() and json.loads(path.read_text(encoding='utf-8'))!=config:raise ValueError('reference_configuration_frozen')
    if not path.exists():dump(path,config)


def compile_progress(base,packets,initial_jobs):
    items=[];ready=[]
    for p in packets:
        sid=p['sample_id'];pair=[response(base/'initial',initial_jobs[sid,role]) for role in ['A','B']]
        item=dict(sample_id=sid,reference_ready=False,status='not_started',same_model_error_correlation=True,expert_certified=False)
        if all(pair):
            item['initial_states']=[r['state'] for r in pair]
            if all(r['state']=='protocol_valid' for r in pair):
                item['independent_inventory_equal']=signature(pair[0]['protocol']['materialized_proposal'])==signature(pair[1]['protocol']['materialized_proposal'])
                job=review_job(p,pair,'reference_'+base.name);r=response(base/'review',job)
                item['status']='source_review_pending'
                if r:
                    item['review_state']=r['state'];item['status']='source_review_incomplete'
                    if r.get('protocol'):
                        compiled=compile_reference(job['packet'],r['protocol'],load_schema(ROOT))
                        item.update(reference_ready=compiled['reference_ready'],status='ready' if compiled['reference_ready'] else 'requires_resolution',compiled=compiled)
                        if compiled['reference_ready']:
                            ready.append(dict(sample_id=sid,reference=compiled['materialized_proposal'],reference_masks=compiled['source_reference_masks'],
                                visible_input={k:p[k] for k in ['sample_id','blocks']},reference_status='AI_silver_source_adjudicated',
                                same_model_error_correlation=True,expert_certified=False))
            else:item['status']='independent_annotation_incomplete'
        items.append(item)
    lines(base/'items.jsonl',items);lines(base/'references.jsonl',ready)
    dump(base/'report.json',dict(status='inconclusive',expected=len(packets),ready=len(ready),
        pending=len(packets)-len(ready),candidate_backend_evaluations=0,
        numeric_thresholds_confirmed=False,shared_budget=budget_snapshot(),expert_certified=False))


async def run(partition):
    manifest=json.loads((OUT/'dataset-v1/manifest.json').read_text(encoding='utf-8'))
    for f in manifest['files']:
        if sha256_file(ROOT/f['path'])!=f['sha256']:raise ValueError('frozen_dataset_dependency_changed')
    workflow=json.loads((OUT/'annotation-workflow-v1.json').read_text(encoding='utf-8'))
    for f in workflow['files']:
        if sha256_file(ROOT/f['path'])!=f['sha256']:raise ValueError('frozen_annotation_workflow_changed')
    membership={r['sample_id'] for r in readlines(OUT/f'dataset-v1/{partition}-samples.jsonl')}
    packets=[p for p in readlines(OUT/'dataset-v1/annotation-inputs.jsonl') if p['sample_id'] in membership]
    packets.sort(key=lambda p:engine.digest('reference-order:'+p['sample_id']))
    base=OUT/'references-v1'/partition;phase='reference_'+partition
    auth=OUT/'execution/project-budget-authorization.json';allocation=OUT/'execution/phase-allocation.json'
    engine.Budget=lambda path,**ignored:AuthorizedBudget(path,authorization=auth,allocation=allocation)
    engine.limits=lambda:dict(stability=2200000,total=10000000,requests=5000)
    jobs={(p['sample_id'],role):initial_job(p,role,phase) for p in packets for role in ['A','B']}
    config=configuration(base/'initial',list(jobs.values()),'independent_A_B')
    freeze_config(base/'initial/run-config.json',config)
    stopped=False
    try:
        for offset in range(0,len(packets),4):
            batch=packets[offset:offset+4];initial=[jobs[p['sample_id'],role] for p in batch for role in ['A','B']]
            engine.RUN=base/'initial';engine.validate_proposal=initial_check
            result=await engine.execute(initial,config)
            review=[]
            for p in batch:
                pair=[response(base/'initial',jobs[p['sample_id'],role]) for role in ['A','B']]
                if all(r and r['state']=='protocol_valid' for r in pair):review.append(review_job(p,pair,phase))
            if not result['stopped'] and review:
                engine.RUN=base/'review';engine.validate_proposal=review_check
                cfg=configuration(base/'review',review,'independent_source_adjudication')
                freeze_config(base/f'review/batch-{offset:03d}-config.json',cfg)
                result=await engine.execute(review,cfg)
            compile_progress(base,packets,jobs)
            if result['stopped']:stopped=True;break
    finally:
        compile_progress(base,packets,jobs)
        dump(base/'run-state.json',dict(active=False,budget_or_service_stopped=stopped,budget=budget_snapshot(),automatic_resume=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--partition',choices=['calibration','test'],default='calibration');args=parser.parse_args()
    asyncio.run(run(args.partition))
