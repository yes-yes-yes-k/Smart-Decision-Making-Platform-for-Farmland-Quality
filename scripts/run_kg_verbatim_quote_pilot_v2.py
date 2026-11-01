"""Run a finite exact-quote protocol pilot with source-visible adjudication."""
import asyncio
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import scripts.run_kg_benchmark_pilot as engine
from scripts.rebuild_kg_extraction_benchmark import OUT,OLD,dump,lines,readlines,budget_snapshot
from scripts.prepare_kg_benchmark_metadata import current_qualification
from framework.knowledge_graph.benchmark_budget_policy_v2 import AuthorizedBudgetV2
from framework.knowledge_graph.benchmark_protocol import source_packet,load_schema
from framework.knowledge_graph.benchmark_verbatim_quote_v2 import materialize_quoted
from framework.knowledge_graph.benchmark_rebuild import sha256_file

BASE=OUT/'execution/verbatim-quote-pilot-v2';AUTH=BASE/'remote-authorization.json'
PARENT_AUTH=OUT/'execution/remote-authorization.json';MODEL='deepseek-ai/DeepSeek-V4.1-Flash';ENDPOINT='https://api.siliconflow.cn/v1'
ENT_TYPES=['indicator','obstacle','measure','standard'];MODS=['asserted','normative','hypothetical','negated','unknown']
CASES=[
 dict(id='control-cn-positive',source='对照试验表明，施用石灰改善了酸性土壤状况，土壤pH提高。',entities=[('施用石灰','measure'),('酸性土壤','obstacle'),('土壤pH','indicator')],relations=[('addresses','施用石灰','酸性土壤','asserted'),('improves_indicator','施用石灰','土壤pH','asserted')]),
 dict(id='control-cn-lab-negative',source='称取土壤样品，加入盐酸振荡浸提有效磷，然后比色测定。',entities=[('有效磷','indicator')],relations=[]),
 dict(id='control-en-positive',source='Liming reduced soil acidity and increased soil pH in the field trial.',entities=[('Liming','measure'),('soil acidity','obstacle'),('soil pH','indicator')],relations=[('addresses','Liming','soil acidity','asserted'),('improves_indicator','Liming','soil pH','asserted')]),
 dict(id='control-en-negated',source='Biochar did not significantly improve soil organic carbon in this experiment.',entities=[('Biochar','measure'),('soil organic carbon','indicator')],relations=[]),
 dict(id='control-title-identity',source='土壤样品风干后研磨过筛。',title='NY/T 1121.7 土壤有效磷测定方法',entities=[('NY/T 1121.7','standard'),('土壤有效磷','indicator')],relations=[]),
 dict(id='control-list-fragment',source='Indicators: soil pH; available P. Laboratory steps: add acid, shake and filter.',entities=[('soil pH','indicator'),('available P','indicator')],relations=[]),
 dict(id='control-repeated-quote',source='Soil pH increased after liming. Later, soil pH remained stable.',entities=[('Soil pH','indicator'),('liming','measure')],relations=[]),
]
FAILURES=['rebuild-v2:118:54:d1e49ea009a1','rebuild-v2:100:72:846326ed7e9f',
          'rebuild-v2:314:36:c74c6296d698','rebuild-v2:615:4:bd2f0f09bf20']


def obj(properties,required=None):return dict(type='object',properties=properties,required=list(properties) if required is None else required,additionalProperties=False)
def arr(items,min_items=None):
    result=dict(type='array',items=items)
    if min_items is not None:result['minItems']=min_items
    return result
def en(items):return dict(type='string',enum=items)
def span():return obj(dict(block_id=en(['chunk','document_title']),quote=dict(type='string',minLength=1),occurrence=dict(type='integer',minimum=0)),required=['block_id','quote'])
def response_format(schema,name):return dict(type='json_schema',json_schema=dict(name=name,strict=True,schema=schema))


def initial_schema(ontology):
    entity=obj(dict(id=dict(type='string'),type=en(ENT_TYPES),surface=span()))
    evidence=obj(dict(role=en(['identity','assertion']),span=span()))
    relation=obj(dict(id=dict(type='string'),type=en([r['id'] for r in ontology['relation_types']]),source_id=dict(type='string'),
        target_id=dict(type='string'),modality=en(MODS),conditions=arr(dict(type='string')),
        evidence=arr(evidence,1)))
    return obj(dict(entities=arr(entity),relations=arr(relation)))


def review_schema(union,ontology):
    entity_ids=[x['id'] for x in union['entities']];relation_ids=[x['id'] for x in union['relations']]
    entreview=obj(dict(id=en(entity_ids or ['__none__']),decision=en(['include','exclude','uncertain']),
        entity_type=dict(anyOf=[en(ENT_TYPES),dict(type='null')]),selected_surface=dict(anyOf=[span(),dict(type='null')]),reason=dict(type='string')))
    relreview=obj(dict(id=en(relation_ids or ['__none__']),decision=en(['include','exclude','uncertain']),
        type=dict(anyOf=[en([r['id'] for r in ontology['relation_types']]),dict(type='null')]),
        source_id=dict(type='string'),target_id=dict(type='string'),modality=en(MODS),conditions=arr(dict(type='string')),
        assertions=arr(span()),reason=dict(type='string')))
    additions=obj(dict(type=en(ENT_TYPES),surface=span(),reason=dict(type='string')))
    missed=obj(dict(type=en([r['id'] for r in ontology['relation_types']]),source_surface=span(),target_surface=span(),
        source_type=en(ENT_TYPES),target_type=en(ENT_TYPES),modality=en(MODS),conditions=arr(dict(type='string')),assertion=span(),reason=dict(type='string')))
    rschema=obj(dict(entity_reviews=arr(entreview,len(entity_ids)),relation_reviews=arr(relreview,len(relation_ids)),
        additions=arr(additions),missed_relations=arr(missed)))
    for key,ids in [('entity_reviews',entity_ids),('relation_reviews',relation_ids)]:
        rschema['properties'][key]['minItems']=len(ids);rschema['properties'][key]['maxItems']=len(ids)
    return rschema


def make_packet(row,handbook):
    return source_packet(dict(sample_id=row['id'],text=row['source'],document_title=row.get('title','')),handbook)


def initial_job(packet,role,ontology,handbook):
    prompt=(handbook+'\n实体和关系证据必须引用source中连续、逐字的原文子串。仅输出block_id和quote；不得输出start/end字符位置。若同一quote在同一块重复出现，输出从0开始的非重叠occurrence；唯一出现时省略occurrence。程序将从原文唯一定位quote并计算坐标。完整术语不可从英文词内部截断。题名只能提供身份。关系证据的正文断言应包含足以支持关系谓词、端点方向和条件的上下文；只引用两个端点不够。实验室浸提操作不是农艺措施，双栏参考文献和图表残片不构成关系断言。\n关系本体：'+json.dumps(ontology['relation_types'],ensure_ascii=False))
    visible=dict(sample_id=packet['sample_id'],blocks=[dict(block_id=b['block_id'],text=b['text']) for b in packet['blocks']])
    return dict(id=role+':'+packet['sample_id'],phase='stability',packet=packet,answer_keys_in_request=False,
        options=dict(messages=[dict(role='system',content=prompt),dict(role='user',content=json.dumps(visible,ensure_ascii=False))],
            max_tokens=3072,response_format=response_format(initial_schema(ontology),'verbatim_quote_initial_v2')))


def validate_initial(packet,raw,ontology):
    result=materialize_quoted(packet,raw);entities={};seen=set()
    for e in result.get('entities',[]):
        if e['type'] not in ENT_TYPES:raise ValueError('invalid_entity_type')
        s=e['surface'];k=(e['type'],s['block_id'],s['start'],s['end'])
        if k in seen:raise ValueError('duplicate_entity_span')
        if e['id'] in entities:raise ValueError('duplicate_entity_id')
        seen.add(k);entities[e['id']]=e
    for r in result.get('relations',[]):
        a=entities.get(r['source_id']);b=entities.get(r['target_id'])
        if not a or not b:raise ValueError('missing_relation_endpoint')
        definition=next((x for x in ontology['relation_types'] if x['id']==r['type']),None)
        if not definition or a['type'] not in definition['source_types'] or b['type'] not in definition['target_types']:
            raise ValueError('invalid_relation_direction')
        if not any(e['role']=='assertion' and e['block_id']=='chunk' for e in r['evidence']):raise ValueError('body_assertion_required')
    return dict(protocol_complete=True,materialized_proposal=result,errors=[],semantic_support_not_certified=True)


def initial_proposal(record,packet):
    if not record or not record.get('content'):return None
    try:raw=json.loads(record['content']);return materialize_quoted(packet,raw)
    except (ValueError,TypeError,KeyError):return None


def candidate_union(packet,proposals):
    entities={};relations={};maps=[]
    for proposal in proposals:
        mapping={}
        if not proposal:maps.append(mapping);continue
        blocks={b['block_id']:b['text'] for b in packet['blocks']}
        for e in proposal['entities']:
            s=e['surface'];key=(e['type'],s['block_id'],s['text'],s['occurrence'])
            if key not in entities:entities[key]=dict(id=f'candE{len(entities):03d}',type=e['type'],surface=dict(
                block_id=s['block_id'],quote=s['text'],occurrence=s['occurrence'],start=s['start'],end=s['end'],
                source_slice=blocks[s['block_id']][s['start']:s['end']]))
            mapping[e['id']]=entities[key]['id']
        for r in proposal['relations']:
            a=mapping.get(r['source_id']);b=mapping.get(r['target_id'])
            key=(r['type'],a,b,r['modality'],json.dumps(r['conditions'],ensure_ascii=False,sort_keys=True),
                json.dumps(r['evidence'],ensure_ascii=False,sort_keys=True))
            if key not in relations:relations[key]=dict(id=f'candR{len(relations):03d}',type=r['type'],source_id=a,target_id=b,
                modality=r['modality'],conditions=r['conditions'],evidence=[dict(block_id=e['block_id'],role=e['role'],quote=e['text'],
                    start=e['start'],end=e['end'],source_slice=e['text']) for e in r['evidence']])
        maps.append(mapping)
    return dict(entities=list(entities.values()),relations=list(relations.values()))


def review_job(packet,union,ontology,handbook):
    visible=dict(sample_id=packet['sample_id'],blocks=[dict(block_id=b['block_id'],text=b['text']) for b in packet['blocks']],candidate_union=union)
    prompt=handbook+'\n这是独立原文复核，不是投票。候选并集不含标注者身份与理由；每个实体和关系都要逐条重判，屏幕展示的quote已经由程序在原文定位。检查完整词界、实体类型、关系谓词和方向，断言窗口必须包含关系语义，端点位置不等于关系证据。不能跨列或跨区拼接。必须通读source并补充共同遗漏。若不确定说明原因，不扩大排除掩码。'
    return dict(id='review:'+packet['sample_id'],phase='stability',packet=dict(packet,candidate_union=union),
        options=dict(messages=[dict(role='system',content=prompt),dict(role='user',content=json.dumps(visible,ensure_ascii=False))],
            max_tokens=6144,response_format=response_format(review_schema(union,ontology),'verbatim_quote_source_review_v2')))


def validate_review(packet,raw,ontology):
    result=materialize_quoted(packet,raw);union=packet['candidate_union']
    ers=result['entity_reviews'];rrs=result['relation_reviews']
    if {e['id'] for e in ers}!={e['id'] for e in union['entities']} or len(ers)!=len({e['id'] for e in ers}):raise ValueError('all_neutral_union_entities_require_review')
    if {r['id'] for r in rrs}!={r['id'] for r in union['relations']} or len(rrs)!=len({r['id'] for r in rrs}):raise ValueError('all_neutral_union_relations_require_review')
    entities={}
    for e in ers:
        if e['decision']=='include':
            s=e['selected_surface'];entities[e['id']]=dict(id=e['id'],type=e['entity_type'],**s)
    for i,e in enumerate(result['additions']):
        s=e['surface'];key=next((x['id'] for x in entities.values() if x['type']==e['type'] and x['block_id']==s['block_id'] and x['text']==s['text']),None)
        if not key:key=f'addE{i:03d}'
        entities[key]=dict(id=key,type=e['type'],**s)
    relations=[]
    for r in rrs:
        if r['decision']!='include':continue
        if r['source_id'] not in entities or r['target_id'] not in entities:raise ValueError('review_relation_endpoint_not_selected')
        if not any(e['block_id']=='chunk' for e in r['assertions']):raise ValueError('relation_review_requires_body_assertion')
        relations.append(dict(id=r['id'],type=r['type'],source_id=r['source_id'],target_id=r['target_id'],modality=r['modality'],
            conditions=r['conditions'],evidence=[dict(e,role='assertion') for e in r['assertions']]))
    for i,r in enumerate(result['missed_relations']):
        ss=r['source_surface'];ts=r['target_surface']
        source=next((e['id'] for e in entities.values() if e['type']==r['source_type'] and e['block_id']==ss['block_id'] and e['text']==ss['text']),None)
        target=next((e['id'] for e in entities.values() if e['type']==r['target_type'] and e['block_id']==ts['block_id'] and e['text']==ts['text']),None)
        if not source or not target:raise ValueError('missed_relation_endpoint_not_in_final_entity_list')
        if r['assertion']['block_id']!='chunk':raise ValueError('missed_relation_requires_body_assertion')
        relations.append(dict(id=f'addR{i:03d}',type=r['type'],source_id=source,target_id=target,modality=r['modality'],
            conditions=r['conditions'],evidence=[dict(r['assertion'],role='assertion')]))
    for r in relations:
        d=next((x for x in ontology['relation_types'] if x['id']==r['type']),None)
        if not d or entities[r['source_id']]['type'] not in d['source_types'] or entities[r['target_id']]['type'] not in d['target_types']:
            raise ValueError('invalid_reviewed_relation_direction')
    return dict(protocol_complete=True,materialized_proposal=dict(entities=list(entities.values()),relations=relations),
        source_reviews=result,semantic_support_not_machine_certified=True)


def expected_score(case,proposal):
    gold={(t,'chunk',q) for q,t in case['entities']};pred={(e['type'],e['block_id'],e['text']) for e in proposal['entities']}
    e={x['id']:x for x in proposal['entities']}
    predicted={(r['type'],(e[r['source_id']]['block_id'],e[r['source_id']]['text']),
        (e[r['target_id']]['block_id'],e[r['target_id']]['text']),r['modality'])
        for r in proposal['relations'] if r['modality'] in {'asserted','normative'}}
    relations={(t,('chunk',s),('chunk',o),m) for t,s,o,m in case['relations']}
    return dict(entity_tp=len(gold&pred),entity_fp=len(pred-gold),entity_fn=len(gold-pred),
        relation_tp=len(relations&predicted),relation_fp=len(predicted-relations),relation_fn=len(relations-predicted))


async def run():
    BASE.mkdir(parents=True,exist_ok=True)
    approved=json.loads(PARENT_AUTH.read_text(encoding='utf-8'))
    if approved.get('resumed_by')!='user' or approved.get('suspended'):raise ValueError('original_remote_authorization_inactive')
    dump(AUTH,dict(approved,scope_detail='verbatim quote protocol v2 pilot only; seven synthetic controls and four public failure source fragments',
        parent_authorization_sha256=sha256_file(PARENT_AUTH),inherited_user_authorization=True))
    handbook=(OUT/'protocol/annotation-handbook.md').read_text(encoding='utf-8');ontology=load_schema(ROOT)
    packets=[make_packet(c,handbook) for c in CASES]
    oldrefs={r['sample_id']:r for r in readlines(OUT/'semantic-quality-audit-v1/reviewed-reference-snapshots.jsonl')}
    for sid in FAILURES:
        r=oldrefs[sid];packets.append(dict(sample_id=sid,blocks=[dict(b) for b in r['visible_input']['blocks']],handbook=handbook,output_protocol='verbatim_quote_v2'))
    initial=[initial_job(p,role,ontology,handbook) for p in packets for role in ['A','B']]
    remote=BASE/'remote-authorization.json'
    config=dict(status='finite_quote_only_protocol_pilot',protocol='verbatim_quote_v2',model=MODEL,endpoint=ENDPOINT,
        cases=len(packets),controls=len(CASES),known_failure_sources=len(FAILURES),initial_requests=len(initial),review_requests=len(packets),
        maximum_requests=len(initial)+len(packets),max_concurrency=2,transient_retries=1,semantic_retries=0,
        global_token_cap=20000000,request_cap=5000,same_model_error_correlation=True,old_reference_labels_modified=False,
        source_answer_keys_hidden=True,jobs={j['id']:engine.digest(j) for j in initial},
        files=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha256_file(p)) for p in [Path(__file__),
            ROOT/'framework/knowledge_graph/benchmark_verbatim_quote_v2.py',OUT/'protocol/annotation-handbook.md',AUTH]])
    cfg=BASE/'initial/run-config.json'
    if cfg.exists() and json.loads(cfg.read_text(encoding='utf-8'))!=config:raise ValueError('quote_v2_initial_config_frozen')
    if not cfg.exists():dump(cfg,config)
    packets_path=BASE/'source-packets.json'
    packets_obj=dict(cases=packets,expected_controls={c['id']:c for c in CASES},answer_keys_not_sent=True)
    if packets_path.exists() and json.loads(packets_path.read_text(encoding='utf-8'))!=packets_obj:raise ValueError('quote_v2_packets_frozen')
    if not packets_path.exists():dump(packets_path,packets_obj)
    # Recheck the frozen documents' public/approved eligibility before sending.
    ids={r['sample_id'] for r in packets if r['sample_id'] in FAILURES}
    membership={r['sample_id']:r for r in readlines(OUT/'dataset-v1/samples.jsonl')}
    docids={membership[s]['document_id'] for s in ids}
    docs=[d for d in readlines(OUT/'execution/source-review-r1/document-pool-refined.jsonl') if d['id'] in docids]
    qualifications=current_qualification(docs)
    if set(qualifications)!=docids or not all(qualifications.values()):raise ValueError('source_public_qualification_changed')
    dump(BASE/'source-qualification.json',dict(public_approved_read_only=qualifications))
    engine.Budget=lambda path,**kw:AuthorizedBudgetV2(path,authorization=OUT/'execution/project-budget-authorization-v2.json',allocation=OUT/'execution/phase-allocation-v2.json')
    engine.limits=lambda:dict(stability=2200000,total=20000000,requests=5000)
    state=BASE/'run-state.json'
    if state.exists() and json.loads(state.read_text(encoding='utf-8')).get('active'):raise ValueError('quote_v2_runner_active')
    dump(state,dict(active=True,phase='independent_A_B',cases=len(packets),automatic_resume=False))
    budget=None
    try:
        engine.RUN=BASE/'initial';engine.validate_proposal=lambda p,r,s:validate_initial(p,r,ontology)
        await engine.execute(initial,config)
        input_records={}
        for j in initial:
            p=BASE/'initial/proposals'/(engine.digest(j['id'])+'.json')
            if p.exists():input_records[j['id']]=json.loads(p.read_text(encoding='utf-8'))
        reviewjobs=[]
        for p in packets:
            pair=[]
            for role in ['A','B']:
                rec=input_records.get(role+':'+p['sample_id']);pair.append(initial_proposal(rec,p))
            union=candidate_union(p,pair)
            reviewjobs.append(review_job(p,union,ontology,handbook))
        dump(BASE/'review/candidate-unions.jsonl',[dict(sample_id=j['packet']['sample_id'],candidate_union=j['packet']['candidate_union']) for j in reviewjobs])
        reviewconfig=dict(config,status='independent_source_adjudication',jobs={j['id']:engine.digest(j) for j in reviewjobs})
        reviewcfg=BASE/'review/run-config.json'
        if reviewcfg.exists() and json.loads(reviewcfg.read_text(encoding='utf-8'))!=reviewconfig:raise ValueError('quote_v2_review_config_frozen')
        if not reviewcfg.exists():dump(reviewcfg,reviewconfig)
        engine.RUN=BASE/'review';engine.validate_proposal=lambda p,r,s:validate_review(p,r,ontology)
        await engine.execute(reviewjobs,reviewconfig)
        budget=budget_snapshot()
        rows=[];controls={x['id']:x for x in CASES}
        for p in packets:
            cr=json.loads((BASE/'review/proposals'/(engine.digest('review:'+p['sample_id'])+'.json')).read_text(encoding='utf-8'))
            result=dict(sample_id=p['sample_id'],kind='synthetic_control' if p['sample_id'] in controls else 'known_failure_source',
                A_state=input_records.get('A:'+p['sample_id'],{}).get('state','missing'),B_state=input_records.get('B:'+p['sample_id'],{}).get('state','missing'),review_state=cr['state'])
            if cr.get('protocol'):
                proposal=cr['protocol']['materialized_proposal'];result['counts']=dict(entities=len(proposal['entities']),relations=len(proposal['relations']))
                if p['sample_id'] in controls:result['synthetic_control_score']=expected_score(controls[p['sample_id']],proposal)
                result['uncertain_review_items']=sum(x.get('decision')=='uncertain' for x in cr['protocol']['source_reviews']['entity_reviews']+cr['protocol']['source_reviews']['relation_reviews'])
            rows.append(result)
        lines(BASE/'case-results.jsonl',rows)
        report=dict(status='inconclusive',protocol='verbatim_quote_v2',cases=len(packets),synthetic_controls=len(CASES),known_failure_sources=len(FAILURES),
            expected_requests=2*len(packets)+len(packets),budget=budget,results=rows,
            quote_offsets_are_program_derived=True,repeat_quote_requires_occurrence=True,semantic_support_requires_source_review=True,
            old_responses_and_calibration_labels_unchanged=True,expert_certified=False,same_model_error_correlation=True,
            formal_acceptance=False,bulk_annotation_resumed=False)
        dump(BASE/'report.json',report);print(json.dumps({k:report[k] for k in ['status','cases','budget','results']},ensure_ascii=False))
    finally:dump(state,dict(active=False,phase='terminal',budget=budget_snapshot(),automatic_resume=False))


if __name__=='__main__':asyncio.run(run())
