"""Separate reference support/eligibility review from entity/relationship writing.

Default reference masks are applicable. Only independently reviewed literal source
issues can override them; absence of predictions never creates an exclusion.
"""
import asyncio
from collections import Counter
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import scripts.run_kg_benchmark_pilot as engine
import scripts.archive.run_kg_benchmark_pilot_r4 as pilot
from scripts.rebuild_kg_extraction_benchmark import OUT,dump,readlines
from framework.knowledge_graph.benchmark_cells import indexed_block,materialize
from framework.knowledge_graph.benchmark_protocol import load_schema,validate_proposal
from framework.knowledge_graph.benchmark_rebuild import sha256_file

RUN=OUT/'execution/pilot-r4-reference-review'
RULES='''这是独立的参考有效性复核，不是抽取预测或多数票。只按source原文复核candidate中的全部候选。
candidate是前一来源裁决请求的结果，仍可能有共同漏标、类型错误或字段错误；逐项核查，发现漏项可补充。
不得因为候选理由写“排除”却decision错误而继续纳入：应依据原文在decision_reviews明确include/exclude/uncertain。
soil properties等泛称不是具体具名土壤指标；作物/粮食/仪器/算法属性不属于土壤指标。
所有引文只提交block_id/start_cell/end_cell，两个端点包含，不写text/occurrence。不能修改原文字符。
输出JSON且只需这些顶层字段：
decision_reviews:[{id,decision,entity_type,reason,evidence:[]}]
覆盖candidate.decisions中的每个id且不重复。decision=include/exclude/uncertain；include的entity_type必须indicator/obstacle/measure/standard，exclude或uncertain时可为null。
additions:[{id,type,decision,reason,fragment:{block_id,start_cell,end_cell}}] 只补充确认漏标的实体，可为空。
relation_reviews:[{index,status,reason,evidence:[]}] 覆盖candidate.relations所有索引；status=supported/unsupported/uncertain，检查方向、否定、条件、两个端点与证据。
add_relations:[] 仅补充确有来源依据但漏标的关系，格式与candidate相同并附review_reason，可为空。
normalization_reviews:[{index,status,reason,evidence:[]}] 覆盖candidate.normalization所有索引，不能依常识建立别名，不是known不能假装已知；该任务与字面实体分离。
mask_overrides:[{task,block_id,status,reason,evidence:[]}] 只输出确需unknown/excluded的任务，默认三个任务在chunk/document_title均为applicable。
只有原文本身损坏、不可读或无法可靠确定任务真值才可override。没有实体/关系、未知别名、模型错误、候选缺失、难抽取均不是排除理由；规范化缺少等价证据通常是无known链接，而非整个任务不可评。
每个unknown/excluded必须有原文位置证据与来源原因；裁决后的固定掩码不得由未来被测模型更改。
policy_conflicts:[{issue,reason}] 仅放未解决规则冲突，个体unknown和有来源依据的unknown掩码不是流程冲突。
每个review必须非空reason及可见原文位置evidence。不同意候选时改判并说明，不能只认可A/B一致。
本体关系方向以给定ontology为准。措施片段不含田间/旱地/温室等地点或情境词。证据role仅identity/assertion。
不作专家认证。不能把图谱缺关系当事实否定。'''


def check(packet,raw,schema):
    reviewed=materialize(raw,packet)
    candidate=packet['candidate']
    raw_decisions=candidate.get('decisions',[])
    ids=[d.get('id') for d in raw_decisions]
    reviews=reviewed.get('decision_reviews')
    if not isinstance(reviews,list) or len(reviews)!=len(ids) or {r.get('id') for r in reviews}!=set(ids):
        raise ValueError('each_candidate_decision_requires_review')
    byid={d['id']:d for d in raw_decisions}
    masks={(t,b):dict(task=t,block_id=b,status='applicable',reason='default_source_task_applicable',evidence=[])
           for t in ('entities','relations','normalization') for b in ('chunk','document_title')}
    from framework.knowledge_graph.benchmark_protocol_r2 import locate
    blocks={b['block_id']:b['text'] for b in packet['blocks']}
    def evidence(row):
        if not row.get('reason') or not isinstance(row.get('evidence'),list) or not row['evidence']:
            raise ValueError('independent_review_requires_literal_source_evidence')
        for f in row['evidence']:locate(f,blocks)
    proposal=dict(entities=[],relations=[],normalization=[],
        task_masks={t:'applicable' for t in ('entities','relations','normalization')},notes=[])
    unresolved=[]
    for r in reviews:
        evidence(r)
        if r.get('decision') not in {'include','exclude','uncertain'}:raise ValueError('invalid_review_decision')
        if r['decision']=='include':
            original=byid[r['id']]
            fragment=materialize(dict(fragment=original['fragment']),packet)['fragment']
            f=locate(fragment,blocks)
            proposal['entities'].append(dict(id=r['id'],type=r['entity_type'],**f))
        if r['decision']=='uncertain':unresolved.append(dict(task='entities',id=r['id']))
    additions=reviewed.get('additions')
    if not isinstance(additions,list):raise ValueError('additions_list_required')
    for d in additions:
        if d.get('decision')!='include' or not d.get('reason'):raise ValueError('new_entity_requires_explicit_inclusion')
        if d.get('id') in byid:raise ValueError('addition_cannot_retarget_existing_candidate_id')
        proposal['entities'].append(dict(id=d['id'],type=d['type'],**locate(d['fragment'],blocks)))
    for key,items in [('relation_reviews',candidate.get('relations',[])),('normalization_reviews',candidate.get('normalization',[]))]:
        rs=reviewed.get(key)
        if not isinstance(rs,list) or len(rs)!=len(items) or {r.get('index') for r in rs}!=set(range(len(items))):
            raise ValueError('all_'+key+'_required')
        for r in rs:
            evidence(r)
            if r.get('status') not in {'supported','unsupported','uncertain'}:raise ValueError('invalid_support_status')
            if r['status']=='uncertain':unresolved.append(dict(task=key,index=r['index']))
            if r['status']=='supported':
                item=materialize(items[r['index']],packet)
                proposal['relations' if key=='relation_reviews' else 'normalization'].append(item)
    add_relations=reviewed.get('add_relations')
    if not isinstance(add_relations,list):raise ValueError('add_relations_list_required')
    for relation in add_relations:
        if not relation.get('review_reason'):raise ValueError('new_relation_requires_review_reason')
        proposal['relations'].append(relation)
    overrides=reviewed.get('mask_overrides')
    if not isinstance(overrides,list):raise ValueError('mask_overrides_list_required')
    overridden=set()
    for m in overrides:
        key=m.get('task'),m.get('block_id')
        if key not in masks or key in overridden or m.get('status') not in {'unknown','excluded'}:raise ValueError('invalid_source_mask_override')
        evidence(m);masks[key]=m;overridden.add(key)
    conflicts=reviewed.get('policy_conflicts')
    if not isinstance(conflicts,list):raise ValueError('policy_conflicts_list_required')
    checked=validate_proposal(packet,proposal,schema)
    # Unknown individual judgments remain explicit unless their task is already
    # source-masked; they never become silent negatives in a published reference.
    for item in unresolved:
        if item['task']=='entities':
            block=byid[item['id']]['fragment']['block_id'];task='entities'
        else:task='relations' if item['task']=='relation_reviews' else 'normalization';block='chunk'
        if masks[task,block]['status']=='applicable':conflicts.append(dict(issue='unmasked_unknown_judgment',item=item))
    return dict(checked,materialized_proposal=proposal,source_reference_masks=list(masks.values()),
        decision_reviews=reviews,relation_reviews=reviewed['relation_reviews'],normalization_reviews=reviewed['normalization_reviews'],
        additions=additions,source_mask_overrides=overrides,unresolved=conflicts,
        reference_ready=checked['protocol_complete'] and not conflicts,
        normalization_status='source_reviewed_proposals_no_expert_canonical_registry',
        expert_certified=False,same_model_error_correlation=True)


def prepare():
    controls,pilots,handbook=pilot.protocol()
    packets={p['sample_id']:p for p in controls+pilots}
    records={}
    for path in (OUT/'execution/pilot-r4-adjudication/proposals').glob('*.json'):
        r=json.loads(path.read_text(encoding='utf-8'));records[r['id'].removeprefix('arbitrate:')]=r
    jobs=[]
    for sid,p in packets.items():
        record=records.get(sid)
        if record is None or not record.get('content'):raise ValueError('source_content_adjudication_required')
        candidate=json.loads(record['content'])
        packet=dict(p,candidate=candidate)
        source=dict(sample_id=sid,blocks=[indexed_block(b) for b in p['blocks']],candidate=candidate)
        schema=load_schema(ROOT)
        instruction=handbook+'\n'+RULES+'\nontology\n'+json.dumps(dict(entity_types=schema['entity_types'],relation_types=schema['relation_types']),ensure_ascii=False)
        jobs.append(dict(id='review:'+sid,phase='stability',packet=packet,
            options=dict(messages=[dict(role='system',content=instruction),dict(role='user',content=json.dumps(source,ensure_ascii=False))],max_tokens=6144,response_format=dict(type='json_object'))))
    dump(RUN/'budget-approval.json',json.loads((OUT/'execution/pilot-r1/budget-approval.json').read_text(encoding='utf-8')))
    paths=[Path(__file__),ROOT/'scripts/run_kg_benchmark_pilot.py',ROOT/'scripts/run_kg_benchmark_pilot_r4.py',ROOT/'framework/knowledge_graph/benchmark_cells.py',OUT/'protocol-r4/annotation-handbook.md']
    config=dict(model='deepseek-ai/DeepSeek-V4.1-Flash',endpoint='https://api.siliconflow.cn/v1',budget_limits=engine.limits(),
        task='independent_reference_support_and_eligibility',same_model_error_correlation=True,expert_certified=False,
        jobs={j['id']:engine.digest(j) for j in jobs},files=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha256_file(p)) for p in paths])
    path=RUN/'run-config.json'
    if path.exists() and json.loads(path.read_text(encoding='utf-8'))!=config:raise ValueError('reference_review_config_frozen')
    if not path.exists():dump(path,config)
    return jobs,config


def main():
    engine.RUN=RUN;jobs,config=prepare();engine.validate_proposal=check
    print(json.dumps(asyncio.run(engine.execute(jobs,config))))


if __name__=='__main__':main()
