from pathlib import Path
from framework.knowledge_graph.benchmark_reference_compile_v2 import compile_reference_v2
from framework.knowledge_graph.benchmark_protocol import load_schema


def data():
    e=dict(id='a',type='measure',block_id='chunk',text='施用石灰',start=0,end=4,occurrence=0)
    o=dict(id='o',type='obstacle',block_id='chunk',text='土壤酸化',start=4,end=8,occurrence=0)
    evidence=dict(block_id='chunk',text='施用石灰土壤酸化',start=0,end=8,occurrence=0,role='assertion')
    r=dict(type='addresses',source_id='a',target_id='o',modality='asserted',conditions=[],evidence=[evidence])
    p=dict(entities=[e,dict(e,id='b'),o],relations=[r,dict(r,source_id='b')],normalization=[],task_masks=dict(entities='applicable',relations='applicable',normalization='applicable'))
    return dict(blocks=[dict(block_id='chunk',text='施用石灰土壤酸化')]),dict(materialized_proposal=p,errors=[dict(error='duplicate_entity_span')],unresolved=[])


def test_literal_duplicates_remap_endpoints_without_extra_facts():
    packet,v=data();r=compile_reference_v2(packet,v,load_schema(Path.cwd()))
    assert r['reference_ready'] and len(r['materialized_proposal']['entities'])==2
    assert len(r['materialized_proposal']['relations'])==1 and r['raw_entity_to_canonical']['b']=='a'
    assert len(v['materialized_proposal']['entities'])==3


def test_distinct_conditions_are_preserved_instead_of_silently_conjoined():
    packet,v=data();v['materialized_proposal']['relations'][1]['conditions']=['仅在旱地']
    r=compile_reference_v2(packet,v,load_schema(Path.cwd()))
    assert r['reference_ready'] and len(r['materialized_proposal']['relations'])==2
    assert r['materialized_proposal']['relations'][0]['conditions']==[]
    assert r['materialized_proposal']['relations'][1]['conditions']==['仅在旱地']
