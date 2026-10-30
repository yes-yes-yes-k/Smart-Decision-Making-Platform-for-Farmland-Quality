import asyncio
import json
from types import SimpleNamespace
import pytest
from framework.knowledge_graph.span_extraction import tokens,span,extract_spans
from framework.knowledge_graph.schema import load_graph_schema

def test_unicode_offsets_and_repeated_mentions():
    text='土壤 pH\n土壤 pH'
    units=tokens(text)
    assert span(text,units,3,6)==('土壤 pH',6,11)
    for a,b in [(True,2),(-1,2),(0,99),(2,2)]:
        with pytest.raises(ValueError,match='invalid_span_bounds'):span(text,units,a,b)

@pytest.mark.parametrize('bad_evidence',[False,True])
def test_pointer_selection_resolves_names_and_rejects_wrong_occurrence(bad_evidence):
    text='liming mitigates acidification. liming'
    calls=[];trace=[];accepted=[]
    async def create(**kwargs):
        calls.append(kwargs)
        payload=dict(entities=[dict(start=0,end=1,type='measure'),dict(start=2,end=3,type='obstacle')]) if len(calls)==1 else dict(
            relationships=[dict(source_id='E0',target_id='E1',relation_type='addresses',start=2 if bad_evidence else 0,end=5 if bad_evidence else 3)])
        return SimpleNamespace(usage=None,choices=[SimpleNamespace(finish_reason='stop',message=SimpleNamespace(content=json.dumps(payload)))])
    run=extract_spans(create,text=text,schema=load_graph_schema(),options={},usage={},accepted_relations=accepted,trace=trace)
    if bad_evidence:
        with pytest.raises(ValueError,match='evidence_does_not_cover_selected_mentions'):asyncio.run(run)
        assert len(calls)==4
    else:
        result=asyncio.run(run)
        assert 'liming' in result and accepted[0]['quote']=='liming mitigates acidification'
        assert trace[0]['resolved'][0]['span_start']==0
        assert len(calls)==2
