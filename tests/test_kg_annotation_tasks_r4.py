import asyncio
import json
from types import SimpleNamespace
from framework.knowledge_graph.annotation_tasks_r4 import annotate
from framework.knowledge_graph.evaluation_v4 import digest

def test_failed_normalization_preserves_entities_and_runs_relation_stage():
    text='翻耕改善结构稳定性。';visible=dict(sample_id='s',blocks=[dict(block_id='chunk',kind='chunk',text=text,text_sha256=digest(text))])
    responses=[dict(entities='evaluable',relations='evaluable',reason='clear'),
        dict(mentions=[dict(type='measure',fragment=dict(block_id='chunk',text='翻耕',occurrence=0),reason='explicit'),dict(type='indicator',fragment=dict(block_id='chunk',text='结构稳定性',occurrence=0),reason='explicit')]),
        dict(mappings=[dict(mention_id='m0',canonical_name='invented',evidence=dict(block_id='chunk',text='翻耕',occurrence=0))]),
        dict(relations=[dict(candidate_id=0,modality='asserted',evidence=[dict(block_id='chunk',text=text,occurrence=0)],reason='explicit')])]
    async def create(**kwargs):
        return SimpleNamespace(usage=None,choices=[SimpleNamespace(finish_reason='stop',message=SimpleNamespace(content=json.dumps(responses.pop(0))))])
    r=asyncio.run(annotate(visible,create))
    assert r['state']=='partial' and r['task_status']['normalization']=='failed'
    assert r['task_status']['relations']=='completed' and len(r['annotation']['mentions'])==2 and len(r['annotation']['relations'])==1
    assert all(m['canonical_name'] is None for m in r['annotation']['mentions'])

def test_unreadable_does_not_trigger_entity_or_relation_calls():
    calls=[];text='���';visible=dict(sample_id='s',blocks=[dict(block_id='chunk',kind='chunk',text=text,text_sha256=digest(text))])
    async def create(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(usage=None,choices=[SimpleNamespace(finish_reason='stop',message=SimpleNamespace(content=json.dumps(dict(entities='unreadable',relations='unreadable',reason='garbled'))))])
    r=asyncio.run(annotate(visible,create))
    assert len(calls)==1 and r['state']=='completed' and r['annotation']['quality']['grade']=='C'
    assert not r['annotation']['completeness']['entities']
