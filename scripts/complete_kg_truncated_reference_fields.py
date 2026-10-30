"""Complete only never-emitted review fields; no prior judgment is re-requested."""
import asyncio
import copy
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import scripts.run_kg_benchmark_pilot as engine
from scripts.build_kg_benchmark_references import initial_job,response,review_job
from scripts.rebuild_kg_extraction_benchmark import OUT,readlines,dump
from scripts.replay_kg_benchmark_reference_review import validate
from framework.knowledge_graph.benchmark_partial_annotation import partial_annotation,complete_array_objects
from framework.knowledge_graph.benchmark_reference_schema import build_reference_schema
from framework.knowledge_graph.benchmark_protocol import load_schema
from framework.knowledge_graph.benchmark_cells import indexed_block
from framework.knowledge_graph.benchmark_budget_policy import AuthorizedBudget
from framework.knowledge_graph.benchmark_rebuild import sha256_file

BASE=OUT/'references-v1/calibration';RUN=BASE/'truncated-field-continuation'
SID='rebuild-v2:615:1:b56b066380b3'


def prepare():
    packet=next(p for p in readlines(OUT/'dataset-v1/annotation-inputs.jsonl') if p['sample_id']==SID)
    pair=[response(BASE/'initial',initial_job(packet,role,'reference_calibration')) for role in ['A','B']]
    proposals=[dict(proposal=partial_annotation(r,packet)[0]) for r in pair]
    original=review_job(packet,proposals,'reference_calibration_adjudication');p=original['packet']
    path=next(path for path in (BASE/'issue-adjudication/proposals').glob('*.json') if json.loads(path.read_text(encoding='utf-8'))['id'].endswith(SID))
    row=json.loads(path.read_text(encoding='utf-8'))
    if row['state']!='incomplete':raise ValueError('only_truncated_field_completion_allowed')
    complete={};remaining=None
    for key in ['decision_reviews','additions','relation_reviews','add_relations','normalization_reviews','mask_overrides','policy_conflicts']:
        values,done=complete_array_objects(row['content'],key);complete[key]=values
        if key=='relation_reviews':remaining=not done
        elif not done:raise ValueError('unavailable_nonrelation_field:'+key)
    if not remaining:raise ValueError('relation_array_already_complete')
    expected=set(range(len(p['candidate']['relations'])));emitted={r['index'] for r in complete['relation_reviews']}
    if len(emitted)!=len(complete['relation_reviews']) or not emitted.issubset(expected):raise ValueError('invalid_emitted_review_indices')
    missing=sorted(expected-emitted)
    schema=build_reference_schema(p['candidate'],load_schema(ROOT));item=copy.deepcopy(schema['json_schema']['schema']['properties']['relation_reviews'])
    item['items']['properties']['index']['enum']=missing
    item['minItems']=len(missing);item['maxItems']=len(missing)
    fmt=dict(type='json_schema',json_schema=dict(name='only_unemitted_relation_reviews',strict=True,
        schema=dict(type='object',properties=dict(relation_reviews=item),required=['relation_reviews'],additionalProperties=False)))
    source=dict(sample_id=SID,blocks=[indexed_block(b) for b in p['blocks']],candidate=p['candidate'],
        frozen_decision_reviews=complete['decision_reviews'],frozen_additions=complete['additions'],missing_relation_indices=missing)
    prompt=p['handbook']+'\n前一来源裁决因输出长度截断。本请求只判定未输出的relation_reviews索引，不重新判定已完整输出的实体、关系或掩码。\n逐项核对source、最终纳入实体和对应关系。supported必须有正文断言，题名只能identity；端点被排除则不能supported。unknown使用uncertain，不猜答案。\n每个missing_relation_indices恰好一次，只输出relation_reviews列表；每项必须非空理由及逐字原文位置证据。只使用block_id/start_cell/end_cell，两个端点包含。理由简短但项目完整。\n'+json.dumps(fmt['json_schema']['schema'],ensure_ascii=False)
    job=dict(id='unemitted-relations:'+SID,phase='reference_calibration_continuation',packet=p,
        options=dict(messages=[dict(role='system',content=prompt),dict(role='user',content=json.dumps(source,ensure_ascii=False))],max_tokens=6144,response_format=fmt))
    return job,complete,missing,path


async def run():
    job,complete,missing,original_path=prepare()
    dump(RUN/'field-plan.json',dict(sample_id=SID,original_response_path=original_path.relative_to(ROOT).as_posix(),
        original_response_sha256=sha256_file(original_path),missing_relation_indices=missing,
        completed_judgments_immutable=True,original_response_remains_incomplete=True,full_request_not_repeated=True))
    def check(packet,raw,schema):
        values=raw.get('relation_reviews',[])
        if len(values)!=len(missing) or {r.get('index') for r in values}!=set(missing):raise ValueError('only_all_missing_indices_allowed')
        merged=copy.deepcopy(complete);merged['relation_reviews']+=values
        return dict(validate(packet,merged,schema),field_continuation=True,original_judgments_modified=False)
    engine.RUN=RUN;engine.validate_proposal=check
    engine.Budget=lambda p,**ignored:AuthorizedBudget(p,authorization=OUT/'execution/project-budget-authorization.json',allocation=OUT/'execution/phase-allocation.json')
    engine.limits=lambda:dict(stability=2200000,total=10000000,requests=5000)
    files=[Path(__file__),RUN/'field-plan.json',original_path]
    config=dict(model='deepseek-ai/DeepSeek-V4.1-Flash',endpoint='https://api.siliconflow.cn/v1',jobs={job['id']:engine.digest(job)},
        files=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha256_file(p)) for p in files],semantic_retry_of_completed_judgments=False)
    path=RUN/'run-config.json'
    if path.exists() and json.loads(path.read_text(encoding='utf-8'))!=config:raise ValueError('field_continuation_config_frozen')
    if not path.exists():dump(path,config)
    print(json.dumps(await engine.execute([job],config)))


if __name__=='__main__':asyncio.run(run())
