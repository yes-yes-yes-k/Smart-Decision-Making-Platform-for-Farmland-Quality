"""Run one finite 10-case protocol pilot; no production data writes or auto-resume."""
import asyncio
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import scripts.run_kg_benchmark_pilot as engine
from scripts.prepare_kg_quoted_selection_pilot import (BASE,AUTH,ENDPOINT,MODEL,prepare,
    review_schema,wrapped)
from scripts.prepare_kg_benchmark_metadata import current_qualification
from scripts.rebuild_kg_extraction_benchmark import OUT,OLD,readlines,dump,lines,budget_snapshot
from framework.knowledge_graph.benchmark_budget_policy_v2 import AuthorizedBudgetV2
from framework.knowledge_graph.benchmark_protocol import load_schema
from framework.knowledge_graph.benchmark_quoted_selection_v1 import materialize_quoted
from framework.knowledge_graph.benchmark_rebuild import sha256_file


def validate_initial(packet,raw,schema):
    value=materialize_quoted(packet,raw)
    entities=value.get('entities');relations=value.get('relations')
    if not isinstance(entities,list) or not isinstance(relations,list):raise ValueError('initial_lists_required')
    ids={};seen=set()
    for e in entities:
        if e.get('type') not in {'indicator','obstacle','measure','standard'}:raise ValueError('invalid_entity_type')
        if e.get('id') in ids:raise ValueError('duplicate_entity_id')
        span=e['surface'];key=(e['type'],span['block_id'],span['start'],span['end'])
        if key in seen:raise ValueError('duplicate_entity_span')
        seen.add(key);ids[e['id']]=e
    validrelations=[]
    for r in relations:
        src=ids.get(r.get('source_id'));tgt=ids.get(r.get('target_id'))
        if src is None or tgt is None:raise ValueError('missing_relation_endpoint')
        definition=next((x for x in schema['relation_types'] if x['id']==r.get('type')),None)
        if not definition or src['type'] not in definition['source_types'] or tgt['type'] not in definition['target_types']:
            raise ValueError('invalid_relation_direction')
        if r.get('modality') not in {'asserted','normative','hypothetical','negated','unknown'}:raise ValueError('invalid_modality')
        evidence=r.get('evidence')
        if not isinstance(evidence,list) or not evidence:raise ValueError('relation_evidence_required')
        if not any(e['role']=='assertion' and e['block_id']=='chunk' for e in evidence):raise ValueError('body_assertion_required')
        validrelations.append(r)
    return dict(protocol_complete=True,materialized_proposal=value,errors=[],semantic_support_not_certified=True)


def observed_span(span,blocks):
    if not isinstance(span,dict):return dict(raw=span,coordinate_slice=None,coordinate_matches=False)
    block=span.get('block_id');start=span.get('start');end=span.get('end');quote=span.get('quote')
    sliced=blocks[block][start:end] if block in blocks and type(start) is int and type(end) is int and 0<=start<end<=len(blocks[block]) else None
    return dict(block_id=block,quote=quote,start=start,end=end,coordinate_slice=sliced,
        coordinate_matches=sliced==quote if sliced is not None else False)


def neutral_union(packet,records):
    """Candidates only: omit roles, votes and rationale; expose source slices."""
    blocks={b['block_id']:b['text'] for b in packet['blocks']};entities={};relations={};origins={};serial=0
    for record in records:
        raw=record
        if not isinstance(raw,dict):continue
        entityids={}
        for e in raw.get('entities',[]) if isinstance(raw.get('entities'),list) else []:
            span=e.get('surface');observed=observed_span(span,blocks)
            canonical=json.dumps(dict(type=e.get('type'),span=observed),sort_keys=True,ensure_ascii=False)
            if canonical not in entities:
                cid=f'candE{serial:03d}';serial+=1
                entities[canonical]=dict(id=cid,type=e.get('type'),selection=observed)
            entityids[e.get('id')]=entities[canonical]['id']
        for r in raw.get('relations',[]) if isinstance(raw.get('relations'),list) else []:
            source=entityids.get(r.get('source_id'));target=entityids.get(r.get('target_id'))
            evidence=[dict(role=x.get('role'),selected=observed_span(x.get('span'),blocks))
                for x in r.get('evidence',[]) if isinstance(x,dict)]
            value=dict(type=r.get('type'),source_id=source,target_id=target,modality=r.get('modality'),
                conditions=r.get('conditions'),evidence=evidence)
            canonical=json.dumps(value,sort_keys=True,ensure_ascii=False)
            if canonical not in relations:relations[canonical]=dict(id=f'candR{len(relations):03d}',**value)
    return dict(entities=list(entities.values()),relations=list(relations.values()))


def build_review(packet,union,ontology,handbook):
    entity_ids=[e['id'] for e in union['entities']];relation_ids=[r['id'] for r in union['relations']]
    schema=review_schema(ontology)
    schema['properties']['entity_reviews']['minItems']=len(entity_ids);schema['properties']['entity_reviews']['maxItems']=len(entity_ids)
    schema['properties']['entity_reviews']['items']['properties']['id']['enum']=entity_ids or ['__none__']
    schema['properties']['relation_reviews']['minItems']=len(relation_ids);schema['properties']['relation_reviews']['maxItems']=len(relation_ids)
    schema['properties']['relation_reviews']['items']['properties']['id']['enum']=relation_ids or ['__none__']
    user=dict(sample_id=packet['sample_id'],blocks=[dict(block_id=b['block_id'],text=b['text']) for b in packet['blocks']],candidate_union=union)
    rules=('独立来源审核：只根据source和逐字物化候选，不能投票或沿用候选理由。每个候选必须逐一决定；候选给出的quote和原文coordinate_slice不同，按原文重新判断且不可默默修正。审实体时检查完整术语边界、介质、类别与规范范围；实验室浸提不属于田间措施。新增或替换项必须抄录连续原文并给出匹配坐标。关系只在连续正文assertion足以支持谓词、方向、否定和条件时支持；重复端点、题名身份、列表/图表/双栏拼接不能单独支撑关系。可提出共同漏项。不能确定时标uncertain并说明来源；不得用排除掩盖困难。审查人仍是同模型，错误可能相关。')
    jobschema=wrapped(schema,'quoted_span_source_adjudication_v1')
    sourceprompt=handbook+'\n'+rules
    return dict(id='review:'+packet['sample_id'],phase='stability',packet=dict(packet,candidate_union=union),
        options=dict(messages=[dict(role='system',content=sourceprompt),dict(role='user',content=json.dumps(user,ensure_ascii=False))],
            max_tokens=6144,response_format=jobschema))


def validate_review(packet,raw,schema):
    value=materialize_quoted(packet,raw);u=packet['candidate_union']
    ers=value.get('entity_reviews');rrs=value.get('relation_reviews')
    if not isinstance(ers,list) or {x.get('id') for x in ers}!={x['id'] for x in u['entities']}:raise ValueError('all_candidate_entities_require_review')
    if not isinstance(rrs,list) or {x.get('id') for x in rrs}!={x['id'] for x in u['relations']}:raise ValueError('all_candidate_relations_require_review')
    if len(ers)!=len({x['id'] for x in ers}) or len(rrs)!=len({x['id'] for x in rrs}):raise ValueError('duplicate_review')
    selected={}
    for item in ers:
        if item['decision'] not in {'include','exclude','uncertain'}:raise ValueError('invalid_entity_decision')
        if item['decision']=='include':
            if item['final_type'] not in {'indicator','obstacle','measure','standard'} or not isinstance(item.get('surface'),dict):raise ValueError('included_entity_requires_typed_source_span')
            selected[item['id']]=dict(id=item['id'],type=item['final_type'],**item['surface'])
    for addition in value.get('additions',[]):
        span=addition['surface'];cid=f"addE{len(selected):03d}"
        selected[cid]=dict(id=cid,type=addition['type'],**span)
    valid_relations=[]
    reviewmap={x['id']:x for x in rrs};originals={x['id']:x for x in u['relations']}
    for rid,item in reviewmap.items():
        if item['decision'] not in {'include','exclude','uncertain'}:raise ValueError('invalid_relation_decision')
        if item['decision']!='include':continue
        if item['source_id'] not in selected or item['target_id'] not in selected:raise ValueError('relation_endpoint_not_in_final_entities')
        if not any(e['block_id']=='chunk' for e in item.get('assertions',[])):raise ValueError('relation_requires_body_assertion')
        valid_relations.append(dict(id=rid,type=item['type'],source_id=item['source_id'],target_id=item['target_id'],
            modality=item['modality'],conditions=item['conditions'],evidence=[dict(e,role='assertion') for e in item['assertions']]))
    for item in value.get('missed_relation_candidates',[]):
        if item['source_id'] not in selected or item['target_id'] not in selected:raise ValueError('new_relation_endpoint_not_in_final_entities')
        a=item['assertion']
        if a['block_id']!='chunk':raise ValueError('new_relation_requires_body_assertion')
        valid_relations.append(dict(id=f"addR{len(valid_relations):03d}",type=item['type'],source_id=item['source_id'],target_id=item['target_id'],
            modality=item['modality'],conditions=item['conditions'],evidence=[dict(a,role='assertion')]))
    for r in valid_relations:
        definition=next((x for x in schema['relation_types'] if x['id']==r['type']),None)
        if not definition or selected[r['source_id']]['type'] not in definition['source_types'] or selected[r['target_id']]['type'] not in definition['target_types']:
            raise ValueError('invalid_final_relation_direction')
    return dict(protocol_complete=True,materialized_proposal=dict(entities=list(selected.values()),relations=valid_relations),
        source_reviews=value,semantic_support_not_machine_certified=True)


def synthetic_score(expected,proposal):
    def entityset(rows):return {(x['type'],x['block_id'],x['text']) for x in rows}
    def relset(rows,entities):
        e={x['id']:x for x in entities}
        return {(r['type'],(e[r['source_id']]['block_id'],e[r['source_id']]['text']),
            (e[r['target_id']]['block_id'],e[r['target_id']]['text']),r['modality']) for r in rows}
    gold_e={(t,'chunk',q) for q,t in expected['expected_entities']}
    pred_e=entityset(proposal['entities']);g_entities=[dict(id=str(i),type=t,block_id='chunk',text=q) for i,(q,t) in enumerate(expected['expected_entities'])]
    g_rel={(t,('chunk',s),('chunk',o),m) for t,s,o,m in expected['expected_relations']}
    p_rel=relset(proposal['relations'],proposal['entities'])
    return dict(entity_tp=len(gold_e&pred_e),entity_fp=len(pred_e-gold_e),entity_fn=len(gold_e-pred_e),
        relation_tp=len(g_rel&p_rel),relation_fp=len(p_rel-g_rel),relation_fn=len(g_rel-p_rel))


async def run():
    packets,initial_jobs,config=prepare();schema=load_schema(ROOT);handbook=(OUT/'protocol/annotation-handbook.md').read_text(encoding='utf-8')
    docs={}
    selected_ids={r['sample_id'] for r in packets if r['sample_id'] in {sid for sid,_ in __import__('scripts.prepare_kg_quoted_selection_pilot',fromlist=['FAILURES']).FAILURES}}
    membership={r['sample_id']:r for r in readlines(OUT/'dataset-v1/samples.jsonl')}
    docids={membership[s]['document_id'] for s in selected_ids}
    source_docs=[r for r in readlines(OUT/'execution/source-review-r1/document-pool-refined.jsonl') if r['id'] in docids]
    qual=current_qualification(source_docs)
    if not all(qual.values()):raise ValueError('source_public_approval_changed')
    dump(BASE/'source-qualification.json',dict(public_approved_read_only=qual))
    runstate=BASE/'run-state.json'
    if runstate.exists() and json.loads(runstate.read_text(encoding='utf-8')).get('active'):
        raise ValueError('pilot_already_active')
    engine.RUN=BASE/'initial';engine.validate_proposal=validate_initial
    engine.Budget=lambda path,**kw:AuthorizedBudgetV2(path,authorization=OUT/'execution/project-budget-authorization-v2.json',allocation=OUT/'execution/phase-allocation-v2.json')
    engine.limits=lambda:dict(stability=2200000,total=20000000,requests=5000)
    dump(runstate,dict(active=True,phase='independent_A_B',expected_cases=len(packets),automatic_resume=False))
    try:
        await engine.execute(initial_jobs,config)
        results=[]
        for job in initial_jobs:
            path=BASE/'initial/proposals'/(engine.digest(job['id'])+'.json')
            if not path.exists():continue
            record=json.loads(path.read_text(encoding='utf-8'))
            if record.get('content'):
                try:raw=json.loads(record['content'])
                except ValueError:raw=None
                if raw is not None:
                    try:record['quoted_materialized']=materialize_quoted(job['packet'],raw)
                    except ValueError as exc:record['selection_check_error']=str(exc)
            results.append(record)
        byid={p['sample_id']:p for p in packets};proposals={}
        for sample in packets:
            pair=[]
            for role in ['A','B']:
                rec=next((x for x in results if x['id']==role+':'+sample['sample_id']),None)
                pair.append(rec.get('quoted_materialized') if rec else None)
            proposals[sample['sample_id']]=pair
        reviews=[]
        for p in packets:
            union=neutral_union(p,[x for x in proposals[p['sample_id']] if x is not None])
            reviews.append(build_review(p,union,schema,handbook))
        review_config=dict(config,stage='independent_source_review',jobs={j['id']:engine.digest(j) for j in reviews},
            source_review_schema='quoted_span_source_adjudication_v1',independent_full_source_review=True)
        cfg=BASE/'review/run-config.json';cfg.parent.mkdir(parents=True,exist_ok=True)
        if cfg.exists() and json.loads(cfg.read_text(encoding='utf-8'))!=review_config:raise ValueError('review_config_frozen')
        if not cfg.exists():dump(cfg,review_config)
        dump(BASE/'review/candidate-unions.jsonl',[dict(sample_id=j['packet']['sample_id'],union=j['packet']['candidate_union']) for j in reviews])
        engine.RUN=BASE/'review';engine.validate_proposal=validate_review
        await engine.execute(reviews,review_config)
        final=[]
        records={}
        for path in (BASE/'review/proposals').glob('*.json'):
            r=json.loads(path.read_text(encoding='utf-8'));records[r['id']]=r
        for case in packets:
            row=dict(sample_id=case['sample_id'],kind='synthetic_control' if case['sample_id'].startswith('control-') else 'known_failure_source',
                A_state=next((r['state'] for r in results if r['id']=='A:'+case['sample_id']),'missing'),
                B_state=next((r['state'] for r in results if r['id']=='B:'+case['sample_id']),'missing'))
            rr=records.get('review:'+case['sample_id'])
            if rr:
                row['review_state']=rr['state'];row['selection_check_errors']=[r.get('selection_check_error') for r in results if r['id'].endswith(case['sample_id']) and r.get('selection_check_error')]
                if rr.get('protocol'):
                    proposal=rr['protocol']['materialized_proposal'];row['source_reviewed_inventory']=dict(entities=len(proposal['entities']),relations=len(proposal['relations']))
                    expected=next((c for c in __import__('scripts.prepare_kg_quoted_selection_pilot',fromlist=['CASES']).CASES if c['id']==case['sample_id']),None)
                    if expected:row['control_counts']=synthetic_score(expected,proposal)
                    row['source_review_uncertain_count']=sum(x['decision']=='uncertain' for k in ['entity_reviews','relation_reviews'] for x in rr['protocol']['source_reviews'].get(k,[]))
            final.append(row)
        lines(BASE/'case-results.jsonl',final)
        report=dict(status='inconclusive',protocol='quoted_selection_v1',cases=len(packets),synthetic_controls=len(CASES),known_failure_sources=len(FAILURES),
            requests=budget_snapshot()['requests'],tokens=budget_snapshot()['tokens_charged_or_reserved'],budget=budget_snapshot(),
            control_results=[r for r in final if r['kind']=='synthetic_control'],failure_source_results=[r for r in final if r['kind']=='known_failure_source'],
            quote_coordinate_mismatch_rejected=True,invalid_initial_responses_preserved=True,old_reference_labels_modified=False,
            expert_certified=False,same_model_error_correlation=True,bulk_annotation_resumed=False,formal_acceptance=False)
        dump(BASE/'report.json',report)
    finally:
        dump(runstate,dict(active=False,phase='terminal',budget=budget_snapshot(),automatic_resume=False))


if __name__=='__main__':asyncio.run(run())
