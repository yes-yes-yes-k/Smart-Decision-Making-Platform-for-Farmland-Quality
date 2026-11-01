from framework.knowledge_graph.annotation_tasks_r41 import clarify
from framework.knowledge_graph.annotation_protocol_r4 import SYSTEM,entity_schema

def test_occurrence_semantics_are_explicit_without_mutating_historical_protocol():
    original=dict(messages=[dict(role='system',content=SYSTEM),dict(role='user',content='source')],response_format=entity_schema())
    updated=clarify(original)
    assert '同一个 text 在同一个 block_id 中从0起' in updated['messages'][0]['content']
    assert '不是mention列表编号' in updated['messages'][0]['content']
    item=updated['response_format']['json_schema']['schema']['properties']['mentions']['items']
    assert 'Zero-based' in item['properties']['fragment']['properties']['occurrence']['description']
    assert original['messages'][0]['content']==SYSTEM
    assert 'description' not in original['response_format']['json_schema']['schema']['properties']['mentions']['items']['properties']['fragment']['properties']['occurrence']
