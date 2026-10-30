import asyncio
import json
from types import SimpleNamespace
import pytest
from framework.knowledge_graph.candidate_selection import candidates,relation_candidates,extract_candidates
from framework.knowledge_graph.schema import load_graph_schema

def test_candidates_are_literal_and_longest_name_wins():
    text='施用石灰提高土壤pH。'
    pool=candidates(text)
    assert {e['name'] for e in pool}=={'施用石灰','土壤pH'}
    assert all(text[e['span_start']:e['span_end']]==e['name'] for e in pool)
    assert candidates('会议于星期三召开。')==[]
    assert candidates('limingness')==[]

def test_relation_evidence_contains_actual_selected_occurrences():
    text='Liming increases soil pH.'
    es=candidates(text);rs=relation_candidates(text,es,load_graph_schema())
    assert any(r['relation_type']=='improves_indicator' for r in rs)
    for r in rs:
        assert text[r['span_start']:r['span_end']]==r['quote']
        assert r['source'] in r['quote'] and r['target'] in r['quote']

@pytest.mark.parametrize('invalid',[False,True])
def test_id_selection_does_not_allow_generated_names_or_out_of_range_ids(invalid):
    calls=[];trace=[];accepted=[]
    async def create(**kwargs):
        calls.append(kwargs)
        payload=dict(selected_ids=[dict(id=999)]) if invalid else dict(selected_ids=[dict(id=0),dict(id=1)] if len(calls)==1 else [dict(id=0)])
        return SimpleNamespace(usage=None,choices=[SimpleNamespace(finish_reason='stop',message=SimpleNamespace(content=json.dumps(payload)))])
    run=extract_candidates(create,text='Liming increases soil pH.',schema=load_graph_schema(),options={},usage={},accepted_relations=accepted,trace=trace)
    if invalid:
        with pytest.raises(ValueError,match='invalid_candidate_id'):asyncio.run(run)
        assert len(calls)==3
    else:
        assert 'improves_indicator' in asyncio.run(run)
        assert accepted[0]['quote']=='Liming increases soil pH.'
