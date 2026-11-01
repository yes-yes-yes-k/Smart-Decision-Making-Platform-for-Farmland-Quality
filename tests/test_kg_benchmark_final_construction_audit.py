from scripts.audit_kg_benchmark_reference_construction import compare_pair


def inventory(*names):
    return dict(entities=[dict(id=str(i),type='indicator',block_id='chunk',text=name) for i,name in enumerate(names)],relations=[])


def test_agreement_is_not_accuracy_and_shared_omission_is_recorded():
    result=compare_pair(inventory('pH'),inventory('pH'),inventory('pH','有机质'))
    assert result['entity_inventory_agreement'] is True
    assert result['jointly_omitted_entity_surfaces']==1


def test_one_annotator_recalled_entity_is_not_joint_omission():
    result=compare_pair(inventory('pH'),inventory('pH','有机质'),inventory('pH','有机质'))
    assert result['jointly_omitted_entity_surfaces']==0
    assert result['entity_inventory_agreement'] is False
