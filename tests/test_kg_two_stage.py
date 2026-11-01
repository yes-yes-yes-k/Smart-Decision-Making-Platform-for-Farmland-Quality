import asyncio
import json
from types import SimpleNamespace
import pytest
from framework.knowledge_graph.two_stage_extraction import extract_two_stage,validate_inventory,validate_judgment
from framework.knowledge_graph.schema import load_graph_schema

ENTITIES=[dict(name='liming',type='measure'),dict(name='acidification',type='obstacle')]
TEXT='liming mitigates acidification.'

def test_inventory_rejects_nonliteral_names():
    with pytest.raises(ValueError,match='entity_name_not_literal'):
        validate_inventory(dict(entities=ENTITIES,relationships=[]),'unrelated')

def test_judgment_freezes_entities_and_requires_both_mentions():
    with pytest.raises(ValueError,match='frozen_inventory_changed'):
        validate_judgment(dict(entities=[],relationships=[]),TEXT,ENTITIES)
    with pytest.raises(ValueError,match='evidence_missing_endpoint_mentions'):
        validate_judgment(dict(entities=ENTITIES,relationships=[dict(source='liming',target='acidification',quote='liming')]),TEXT,ENTITIES)

@pytest.mark.parametrize('empty',[False,True])
def test_two_stages_preserve_entities_and_literal_quotes(empty):
    calls=[];trace=[];accepted=[]
    async def create(**kwargs):
        calls.append(kwargs)
        relation=[] if len(calls)==1 else [dict(source='liming',target='acidification',relation_type='addresses',quote=TEXT)]
        return SimpleNamespace(usage=None,choices=[SimpleNamespace(finish_reason='stop',message=SimpleNamespace(
            content=json.dumps(dict(entities=[] if empty else ENTITIES,relationships=relation))))])
    result=asyncio.run(extract_two_stage(create,text=TEXT,schema=load_graph_schema(),options={},usage={},accepted_relations=accepted,trace=trace))
    assert len(calls)==(1 if empty else 2)
    assert trace[0]['stage']=='entity_inventory'
    if not empty:
        assert trace[-1]['stage']=='relation_judgment'
        assert accepted[0]['quote']==TEXT
        assert 'addresses' in result

def test_inventory_failure_keeps_trace_and_bounded_repairs():
    trace=[]
    async def create(**kwargs):
        return SimpleNamespace(usage=None,choices=[SimpleNamespace(finish_reason='stop',message=SimpleNamespace(
            content=json.dumps(dict(entities=ENTITIES,relationships=[]))))])
    with pytest.raises(ValueError,match='entity_name_not_literal'):
        asyncio.run(extract_two_stage(create,text='unrelated',schema=load_graph_schema(),options={},usage={},accepted_relations=[],trace=trace))
    assert len(trace)==3
    assert all(not t['accepted'] and t['stage']=='entity_inventory' for t in trace)


def test_relation_stage_repairs_do_not_erase_inventory_trace():
    trace=[];calls=[]
    async def create(**kwargs):
        calls.append(kwargs)
        relations=[] if len(calls)==1 else [dict(source='liming',target='acidification',relation_type='addresses',quote='liming')]
        return SimpleNamespace(usage=None,choices=[SimpleNamespace(finish_reason='stop',message=SimpleNamespace(
            content=json.dumps(dict(entities=ENTITIES,relationships=relations))))])
    with pytest.raises(ValueError,match='evidence_missing_endpoint_mentions'):
        asyncio.run(extract_two_stage(create,text=TEXT,schema=load_graph_schema(),options={},usage={},accepted_relations=[],trace=trace))
    assert len(calls)==4
    assert trace[0]['accepted'] and trace[0]['stage']=='entity_inventory'
    assert len(trace)==4 and all(not t['accepted'] for t in trace[1:])
