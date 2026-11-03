from pathlib import Path
import pytest
from scripts.adjudicate_kg_benchmark_pilot import check
from framework.knowledge_graph.benchmark_protocol import source_packet,load_schema


def example():
    packet=source_packet(dict(sample_id='x',text='未发现关系。',document_title='来源'),'manual')
    fragment=dict(block_id='chunk',text='未发现关系。',occurrence=0)
    raw=dict(decisions=[],relations=[],normalization=[],quality=dict(readability='readable',source_issues=[]),
        reference_masks=[dict(task=t,block_id=b,status='applicable',reason='原文可读',evidence=[])
            for t in ('entities','relations','normalization') for b in ('chunk','document_title')],
        rulings=[dict(issue='独立检查',decision='无正例',reason='正文为负例',evidence=[fragment])],
        relation_reviews=[],normalization_reviews=[],unresolved=[])
    return packet,raw,load_schema(Path(__file__).resolve().parents[1])


def test_negative_case_stays_applicable_and_can_be_source_reviewed():
    result=check(*example())
    assert result['reference_ready'] and not result['expert_certified']
    assert all(m['status']=='applicable' for m in result['source_reference_masks'])


def test_excluding_task_requires_literal_source_evidence():
    packet,raw,schema=example()
    raw['reference_masks'][0]['status']='excluded'
    with pytest.raises(ValueError,match='requires_source_evidence'):
        check(packet,raw,schema)


def test_unresolved_source_question_blocks_reference_ready():
    packet,raw,schema=example()
    raw['unresolved']=[dict(issue='边界',reason='手册不明确')]
    assert not check(packet,raw,schema)['reference_ready']
