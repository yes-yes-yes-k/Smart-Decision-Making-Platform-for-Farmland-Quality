from scripts.report_kg_benchmark_reference_coverage import support_counts


def test_repeated_sample_and_different_conditions_cannot_inflate_core_fact_support():
    e=[dict(id='a',type='measure',block_id='chunk',text='施用石灰'),dict(id='b',type='obstacle',block_id='chunk',text='土壤酸化')]
    relation=dict(type='addresses',source_id='a',target_id='b',modality='asserted',conditions=[],evidence=[dict(block_id='chunk',role='assertion')])
    reference=dict(sample_id='one',reference=dict(entities=e,relations=[relation,dict(relation,conditions=['旱地'])]),reference_masks=[])
    second=dict(reference,sample_id='two')
    r=support_counts([reference,second],dict(one=dict(isolation_group=1),two=dict(isolation_group=1)))
    assert r['relations']['addresses']==dict(unique_group_and_literal_endpoint_facts=1,document_groups=1,conditional_claims=2)
