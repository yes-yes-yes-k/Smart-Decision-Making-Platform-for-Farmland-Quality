import copy
from framework.knowledge_graph.benchmark_compact_cells import indexed_block,to_linear,from_linear
from framework.knowledge_graph.benchmark_cells import select
from framework.knowledge_graph.benchmark_proposal_union import union_proposals


def test_compact_cells_roundtrip_preserves_every_unicode_position():
    text='土壈pH\n a\t|\\"😀123456789abc'
    block=indexed_block(dict(block_id='chunk',text=text))
    assert block['text']==text
    for start in range(len(text)):
        for end in range(start,len(text)):
            raw=dict(block_id='chunk',start_cell='c'+str(start),end_cell='c'+str(end))
            assert to_linear(from_linear(raw))==raw
            # Exact source slicing is independent of the display encoding.
            if start==end:
                assert select(to_linear(from_linear(raw)),{'chunk':text})['text']==text[start]


def test_union_retains_disputed_types_and_omits_votes_and_reasons():
    fragment=dict(block_id='chunk',start_cell='r0c0',end_cell='r0c3')
    a=dict(decisions=[dict(id='a',type='indicator',decision='include',reason='PRIVATE',fragment=fragment)],relations=[],normalization=[])
    b=dict(decisions=[dict(id='b',type='obstacle',decision='exclude',reason='PRIVATE',fragment=fragment)],relations=[],normalization=[])
    before=copy.deepcopy([a,b]);result=union_proposals([a,b])
    assert len(result['decisions'])==2
    assert all(set(d)=={'id','type','fragment'} for d in result['decisions'])
    assert [a,b]==before


def test_union_remaps_endpoint_ids_when_duplicate_mentions_are_merged():
    def proposal(prefix):
        return dict(decisions=[dict(id=prefix+'m',type='measure',fragment=dict(block_id='chunk',start_cell='r0c0',end_cell='r0c3')),
            dict(id=prefix+'o',type='obstacle',fragment=dict(block_id='chunk',start_cell='r0c6',end_cell='r0c9'))],
            relations=[dict(type='addresses',source_id=prefix+'m',target_id=prefix+'o',modality='asserted',conditions=[],evidence=[])],normalization=[])
    result=union_proposals([proposal('a'),proposal('b')])
    assert len(result['decisions'])==2 and len(result['relations'])==1
    assert (result['relations'][0]['source_id'],result['relations'][0]['target_id'])==('u0','u1')


def test_primary_schema_forbids_model_task_exclusion_and_bad_evidence_roles():
    import jsonschema
    from scripts.run_kg_benchmark_pilot_r5 import primary_schema
    schema=primary_schema()['json_schema']['schema']
    jsonschema.Draft202012Validator.check_schema(schema)
    raw=dict(decisions=[],normalization=[],relations=[],quality=dict(readability='readable',source_issues=[]),notes=[])
    jsonschema.validate(raw,schema)
    raw['task_masks']={'entities':'excluded'}
    assert list(jsonschema.Draft202012Validator(schema).iter_errors(raw))
