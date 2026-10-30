from pathlib import Path
import pytest
from framework.knowledge_graph.benchmark_protocol import source_packet,load_schema
from scripts.run_kg_benchmark_pilot_r3 import check,controls,CONTRACT


def test_advisory_quality_cannot_exclude_scoring_task():
    packet=source_packet(dict(sample_id='x',text='损坏文字',document_title='来源'),'manual')
    raw=dict(decisions=[],normalization=[],relations=[],
             quality=dict(readability='unreadable',source_issues=['OCR']))
    result=check(packet,raw,load_schema(Path(__file__).resolve().parents[1]))
    assert all(v=='applicable' for v in result['materialized_proposal']['task_masks'].values())
    raw['task_masks']={'entities':'excluded'}
    with pytest.raises(ValueError,match='no_scoring_exclusion_authority'):
        check(packet,raw,load_schema(Path(__file__).resolve().parents[1]))


def test_new_control_keys_and_declared_roles_match_validator():
    packets,keys=controls('manual')
    assert len(packets)==len(keys)==12
    assert CONTRACT['relations'][0]['evidence'][0]['role']==['identity','assertion']
    assert all(k['expected']['task_masks']['relations']=='applicable' for k in keys)
    assert all(not k['formal_acceptance_eligible'] for k in keys)
