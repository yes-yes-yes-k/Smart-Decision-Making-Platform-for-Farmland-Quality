"""Prepare a frozen, isolated quoted-span pilot; this command makes no calls."""
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.rebuild_kg_extraction_benchmark import OUT,readlines,dump
from framework.knowledge_graph.benchmark_rebuild import sha256_file
from framework.knowledge_graph.benchmark_protocol import source_packet,load_schema
from framework.knowledge_graph.benchmark_quoted_selection_v1 import materialize_quoted

BASE=OUT/'execution/quoted-selection-pilot-v1'
PARENT_AUTH=OUT/'execution/remote-authorization.json'
AUTH=BASE/'remote-authorization.json'
MODEL='deepseek-ai/DeepSeek-V4.1-Flash';ENDPOINT='https://api.siliconflow.cn/v1'
ENTITY=['indicator','obstacle','measure','standard']
MODALITY=['asserted','normative','hypothetical','negated','unknown']

CASES=[
 dict(id='control-cn-positive',source='对照试验表明，施用石灰提高了酸性土壤的pH。',expected_entities=[('施用石灰','measure'),('酸性土壤','obstacle'),('pH','indicator')],expected_relations=[('improves_indicator','施用石灰','pH','asserted')]),
 dict(id='control-cn-lab-negative',source='称取土壤样品，加入盐酸振荡浸提有效磷，然后比色测定。',expected_entities=[('土壤样品','indicator'),('有效磷','indicator')],expected_relations=[]),
 dict(id='control-en-positive',source='Liming reduced soil acidity and increased soil pH in the field trial.',expected_entities=[('Liming','measure'),('soil acidity','obstacle'),('soil pH','indicator')],expected_relations=[('improves_indicator','Liming','soil pH','asserted')]),
 dict(id='control-en-negated',source='Biochar did not significantly improve soil organic carbon in this experiment.',expected_entities=[('Biochar','measure'),('soil organic carbon','indicator')],expected_relations=[]),
 dict(id='control-title-only',source='The standard NY/T 1121.7 specifies the measurement of available phosphorus in soil.',title='Soil available phosphorus measurement protocol',expected_entities=[('NY/T 1121.7','standard'),('available phosphorus','indicator')],expected_relations=[('prescribes_measurement','NY/T 1121.7','available phosphorus','normative')]),
 dict(id='control-list-fragment',source='Indicators: soil pH; available P. Laboratory steps: add acid, shake and filter.',expected_entities=[('soil pH','indicator'),('available P','indicator')],expected_relations=[]),
]
FAILURES=[
 ('rebuild-v2:118:54:d1e49ea009a1','body'),
 ('rebuild-v2:100:72:846326ed7e9f','body'),
 ('rebuild-v2:314:36:c74c6296d698','body'),
 ('rebuild-v2:615:4:bd2f0f09bf20','calibration'),
]


def span_schema():
    return dict(type='object',properties=dict(block_id=dict(type='string',enum=['chunk','document_title']),
        quote=dict(type='string',minLength=1),start=dict(type='integer',minimum=0),end=dict(type='integer',minimum=1)),
        required=['block_id','quote','start','end'],additionalProperties=False)


def obj(properties):return dict(type='object',properties=properties,required=list(properties),additionalProperties=False)
def arr(items):return dict(type='array',items=items)
def enumeration(items):return dict(type='string',enum=items)


def initial_schema(ontology):
    entity=obj(dict(id=dict(type='string',pattern='^e[0-9]+$'),type=enumeration(ENTITY),surface=span_schema(),
        type_reason=dict(type='string')))
    evidence=obj(dict(role=enumeration(['identity','assertion']),span=span_schema()))
    relation=obj(dict(id=dict(type='string',pattern='^r[0-9]+$'),type=enumeration([x['id'] for x in ontology['relation_types']]),
        source_id=dict(type='string'),target_id=dict(type='string'),modality=enumeration(MODALITY),conditions=arr(dict(type='string')),
        evidence=dict(type='array',items=evidence,minItems=1),reason=dict(type='string')))
    return obj(dict(entities=arr(entity),relations=arr(relation)))


def review_schema(ontology):
    entity_review=obj(dict(id=dict(type='string'),decision=enumeration(['include','exclude','uncertain']),
        final_type=dict(anyOf=[enumeration(ENTITY),dict(type='null')]),surface=dict(anyOf=[span_schema(),dict(type='null')]),reason=dict(type='string')))
    relation_review=obj(dict(id=dict(type='string'),decision=enumeration(['include','exclude','uncertain']),
        type=dict(anyOf=[enumeration([x['id'] for x in ontology['relation_types']]),dict(type='null')]),
        source_id=dict(type='string'),target_id=dict(type='string'),modality=enumeration(MODALITY),conditions=arr(dict(type='string')),
        assertions=arr(span_schema()),reason=dict(type='string')))
    additions=copy_obj= obj(dict(type=enumeration(ENTITY),surface=span_schema(),reason=dict(type='string')))
    return obj(dict(entity_reviews=arr(entity_review),relation_reviews=arr(relation_review),additions=arr(additions),
        missed_relation_candidates=arr(dict(type='object',properties=dict(type=enumeration([x['id'] for x in ontology['relation_types']]),
            source_id=dict(type='string'),target_id=dict(type='string'),source_surface=span_schema(),target_surface=span_schema(),
            modality=enumeration(MODALITY),conditions=arr(dict(type='string')),assertion=span_schema(),reason=dict(type='string')),
            required=['type','source_id','target_id','source_surface','target_surface','modality','conditions','assertion','reason'],additionalProperties=False))))


def wrapped(schema,name):
    return dict(type='json_schema',json_schema=dict(name=name,strict=True,schema=schema))


def request(packet,role,ontology,handbook):
    system=(handbook+'\n对每个实体和每段证据都必须原样抄录连续source字符，并同时给出Python Unicode左闭右开start/end。不得先猜名称再令坐标配合；两者不一致即无效。实体仅包含完整、可独立识别的术语，不截取词内部片段。正文和题名分开；题名可作身份，不能证明关系断言。每条关系必须给出包含谓词、两个端点及必要条件的连续正文assertion窗口；只重复端点词不支持关系，图表/双栏/参考文献拼接不可当单一事实。盐酸、震荡、实验室浸提不是农艺措施。含义不清不要猜。输出JSON。\n关系方向本体：'+json.dumps(ontology['relation_types'],ensure_ascii=False))
    source=dict(sample_id=packet['sample_id'],blocks=[dict(block_id=b['block_id'],text=b['text']) for b in packet['blocks']])
    schema=initial_schema(ontology)
    return dict(id=role+':'+packet['sample_id'],phase='stability',packet=packet,
        options=dict(messages=[dict(role='system',content=system),dict(role='user',content=json.dumps(source,ensure_ascii=False))],
            max_tokens=3072,response_format=wrapped(schema,'quoted_span_initial_v1')))


def controls_packet(row,handbook):
    return source_packet(dict(sample_id=row['id'],text=row['source'],document_title=row.get('title','')),handbook)


def prepare():
    OUT.mkdir(parents=True,exist_ok=True);BASE.mkdir(parents=True,exist_ok=True)
    original=json.loads(PARENT_AUTH.read_text(encoding='utf-8'))
    if original.get('resumed_by')!='user' or original.get('suspended'):
        raise ValueError('parent_public_source_authorization_unavailable')
    scoped=dict(original,scope='approved_public_documents_and_synthetic_protocol_controls',
        scope_detail='new quoted-span protocol pilot only; six synthetic controls plus four publicly approved failure-audit source fragments',
        parent_authorization_path=PARENT_AUTH.relative_to(ROOT).as_posix(),
        parent_authorization_sha256=sha256_file(PARENT_AUTH),inherited_user_authorization=True)
    dump(AUTH,scoped)
    handbook=(OUT/'protocol/annotation-handbook.md').read_text(encoding='utf-8')
    ontology=load_schema(ROOT)
    packets=[controls_packet(r,handbook) for r in CASES]
    snapshot={r['sample_id']:r for r in readlines(OUT/'semantic-quality-audit-v1/reviewed-reference-snapshots.jsonl')}
    for sid,part in FAILURES:
        old=snapshot[sid];blocks={b['block_id']:b['text'] for b in old['visible_input']['blocks']}
        packets.append(dict(sample_id=sid,blocks=[dict(b) for b in old['visible_input']['blocks']],handbook=handbook,
            output_protocol='quoted_selection_v1',audit_partition=part))
    jobs=[request(p,role,ontology,handbook) for p in packets for role in ['A','B']]
    runconfig=dict(status='prepared_no_model_calls',protocol='quoted_selection_v1',model=MODEL,endpoint=ENDPOINT,
        cases=len(packets),synthetic_controls=len(CASES),known_failure_sources=len(FAILURES),
        independent_initial_requests=len(jobs),adjudication_requests=len(packets),max_requests=len(jobs)+len(packets),
        concurrent_requests=2,transient_retries=1,semantic_retries=0,global_token_cap=20000000,request_cap=5000,
        source_text_only=True,old_labels_not_in_source_packets=True,same_model_error_correlation=True,
        jobs={j['id']:__import__('hashlib').sha256(json.dumps(j,ensure_ascii=False,sort_keys=True).encode()).hexdigest() for j in jobs},
        files=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha256_file(p)) for p in [Path(__file__),
            ROOT/'framework/knowledge_graph/benchmark_quoted_selection_v1.py',OUT/'protocol/annotation-handbook.md',
            OUT/'execution/project-budget-authorization-v2.json',AUTH]])
    cfg=BASE/'run-config.json'
    if cfg.exists():
        if json.loads(cfg.read_text(encoding='utf-8'))!=runconfig:raise ValueError('quoted_selection_pilot_frozen')
    else:dump(cfg,runconfig)
    dump(BASE/'source-packets.json',dict(cases=packets,synthetic_expected={r['id']:r for r in CASES},
        source_packet_hashes={p['sample_id']:__import__('hashlib').sha256(json.dumps(p,ensure_ascii=False,sort_keys=True).encode()).hexdigest() for p in packets},
        old_answers_not_included=True))
    return packets,jobs,runconfig


def copy_obj(value):return json.loads(json.dumps(value))


if __name__=='__main__':
    packets,jobs,config=prepare()
    print(json.dumps(dict(status='prepared_no_model_calls',cases=len(packets),initial_requests=len(jobs),
        adjudication_requests=len(packets),maximum_requests=len(jobs)+len(packets)),ensure_ascii=False))
