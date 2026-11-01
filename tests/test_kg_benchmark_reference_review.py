from pathlib import Path
from framework.knowledge_graph.benchmark_protocol import source_packet,load_schema
from scripts.review_kg_benchmark_reference import check


def fixture():
    packet=source_packet(dict(sample_id='x',text='小麦锰含量',document_title='结果'),'manual')
    packet['candidate']=dict(decisions=[dict(id='e1',type='indicator',decision='include',
        fragment=dict(block_id='chunk',start_cell='c0',end_cell='c4'))],relations=[],normalization=[])
    review=dict(decision_reviews=[dict(id='e1',decision='exclude',entity_type=None,reason='植物介质不属于土壤指标',
        evidence=[dict(block_id='chunk',start_cell='c0',end_cell='c4')])],additions=[],relation_reviews=[],
        add_relations=[],normalization_reviews=[],mask_overrides=[],policy_conflicts=[])
    return packet,review,load_schema(Path(__file__).resolve().parents[1])


def test_review_can_correct_shared_false_positive_without_excluding_task():
    result=check(*fixture())
    assert result['reference_ready'] and not result['materialized_proposal']['entities']
    assert all(m['status']=='applicable' for m in result['source_reference_masks'])


def test_unknown_candidate_cannot_be_published_as_silent_negative():
    packet,review,schema=fixture()
    review['decision_reviews'][0]['decision']='uncertain'
    result=check(packet,review,schema)
    assert not result['reference_ready'] and result['unresolved'][0]['issue']=='unmasked_unknown_judgment'


def test_mask_override_must_be_separate_literal_source_review():
    packet,review,schema=fixture()
    review['decision_reviews'][0]['decision']='uncertain'
    review['mask_overrides']=[dict(task='entities',block_id='chunk',status='unknown',reason='来源不足以判定',
        evidence=[dict(block_id='chunk',start_cell='c0',end_cell='c4')])]
    result=check(packet,review,schema)
    assert result['reference_ready']
    assert len(result['source_mask_overrides'])==1
