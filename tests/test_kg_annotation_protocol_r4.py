import pytest
from framework.knowledge_graph.annotation_protocol_r4 import SYSTEM,quality_schema,entity_schema,resolve_quality,resolve_entities,resolve_normalization
from framework.knowledge_graph.evaluation_v4 import digest

def visible(text):return dict(sample_id='s',blocks=[dict(block_id='chunk',kind='chunk',text=text,text_sha256=digest(text))])

def test_neutral_prompt_and_disjoint_generated_fields():
    assert '只有answer' not in SYSTEM and '完成一个判断' not in SYSTEM
    q=quality_schema()['json_schema']['schema']['properties'];e=entity_schema()['json_schema']['schema']['properties']
    assert set(q)=={'entities','relations','reason'} and set(e)=={'mentions'}
    assert 'canonical_name' not in e['mentions']['items']['properties']

def test_readable_empty_eligibility_is_derived_without_conflicting_booleans():
    q=resolve_quality(dict(entities='evaluable',relations='evaluable',reason='readable'))
    raw,a=resolve_entities(visible('会议通知。'),q,dict(mentions=[]))
    assert a['quality']['grade']=='A' and a['quality']['relation_eligible'] and a['relations']==[]
    q=resolve_quality(dict(entities='unreadable',relations='unreadable',reason='garbled'))
    assert q['quality']['grade']=='C' and not q['quality']['entity_eligible']

def test_unknown_normalization_is_null_by_construction():
    v=visible('该土壤的电导率为20。');q=resolve_quality(dict(entities='evaluable',relations='evaluable',reason='clear'))
    raw,a=resolve_entities(v,q,dict(mentions=[dict(type='indicator',fragment=dict(block_id='chunk',text='电导率',occurrence=0),reason='explicit')]))
    assert a['mentions'][0]['normalization_status']=='unknown' and a['mentions'][0]['canonical_name'] is None
    _,b=resolve_normalization(v,raw,dict(mappings=[]))
    assert b['mentions'][0]['canonical_name'] is None
    with pytest.raises(ValueError,match='alias_mapping_missing_literal_evidence'):
        resolve_normalization(v,raw,dict(mappings=[dict(mention_id='m0',canonical_name='盐分',evidence=dict(block_id='chunk',text='电导率',occurrence=0))]))

def test_known_alias_requires_both_names_in_visible_evidence():
    v=visible('有效持水量（EWC）');q=resolve_quality(dict(entities='evaluable',relations='evaluable',reason='clear'))
    raw,_=resolve_entities(v,q,dict(mentions=[dict(type='indicator',fragment=dict(block_id='chunk',text='EWC',occurrence=0),reason='alias')]))
    _,a=resolve_normalization(v,raw,dict(mappings=[dict(mention_id='m0',canonical_name='有效持水量',evidence=dict(block_id='chunk',text='有效持水量（EWC）',occurrence=0))]))
    assert a['mentions'][0]['canonical_name']=='有效持水量'
