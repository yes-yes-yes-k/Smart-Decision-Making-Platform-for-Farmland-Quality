import pytest
from scripts.verify_kg_annotation_load import cases,target_value

def test_common_normalization_target_is_distinct_from_full_form_validity():
    c=next(c for c in cases() if c['id']=='unknown_name')
    # The target answer is null, but the contradictory status makes a complete annotation unusable.
    a=dict(mentions=[dict(fragment=dict(text='RZ9'),canonical_name=None,normalization_status='known')])
    assert target_value(c,a) is None
    with pytest.raises(ValueError,match='target_mention_omitted'):target_value(c,dict(mentions=[]))

def test_readable_empty_requires_evaluable_and_complete_tasks():
    c=next(c for c in cases() if c['id']=='clear_empty')
    a=dict(quality=dict(entity_eligible=True,relation_eligible=True),completeness=dict(entities=True,relations=True),mentions=[],relations=[])
    assert target_value(c,a)=='evaluable_empty'
    a['quality']['relation_eligible']=False
    assert target_value(c,a)=='not_evaluable_empty'

def test_title_control_does_not_accept_any_asserted_relation():
    c=next(c for c in cases() if c['id']=='title_not_fact')
    assert target_value(c,dict(relations=[]))=='unsupported'
    assert target_value(c,dict(relations=[dict(modality='asserted')]))=='asserted'
