import copy
from pathlib import Path
import pytest
from framework.knowledge_graph.benchmark_protocol import (
    source_packet,literal_span,validate_proposal,load_schema)

ROOT=Path(__file__).resolve().parents[1]


def test_packet_ignores_old_answers_and_sampling_layer():
    packet=source_packet(dict(sample_id='x',text='土壤',document_title='标题',
        reference={'secret':True},partition='test',stratum='easy'),'manual')
    assert set(packet)=={'sample_id','blocks','handbook','output_protocol'}
    assert packet['blocks'][0]['text']=='土壤'


def test_span_cannot_repair_ocr_or_choose_different_occurrence():
    blocks={'chunk':'土壈 土壤 土壤'}
    with pytest.raises(ValueError,match='span_not_literal'):
        literal_span(dict(block_id='chunk',text='土壤',start=0,end=2,occurrence=0),blocks)
    with pytest.raises(ValueError,match='occurrence_span_conflict'):
        literal_span(dict(block_id='chunk',text='土壤',start=6,end=8,occurrence=0),blocks)
    assert literal_span(dict(block_id='chunk',text='土壤',start=6,end=8,occurrence=1),blocks)==('chunk',6,8)


def test_partial_bad_entity_does_not_erase_other_literal_candidates():
    packet=source_packet(dict(sample_id='x',text='石灰缓解土壤酸化。',document_title='论文'),'manual')
    proposal=dict(entities=[dict(id='a',type='measure',block_id='chunk',text='石灰',start=0,end=2,occurrence=0),
        dict(id='bad',type='obstacle',block_id='chunk',text='盐渍化',start=4,end=8,occurrence=0)],relations=[])
    original=copy.deepcopy(proposal)
    result=validate_proposal(packet,proposal,load_schema(ROOT))
    assert not result['protocol_complete']
    assert [m['id'] for m in result['literal_valid_entities']]==['a']
    assert result['semantic_support_not_certified'] and proposal==original


def test_standard_identity_alone_does_not_support_relation():
    packet=source_packet(dict(sample_id='x',text='土壤pH',document_title='GB/T 123'),'manual')
    proposal=dict(entities=[dict(id='s',type='standard',block_id='document_title',text='GB/T 123',start=0,end=8,occurrence=0),
        dict(id='i',type='indicator',block_id='chunk',text='土壤pH',start=0,end=4,occurrence=0)],
        relations=[dict(type='prescribes_measurement',source_id='s',target_id='i',modality='normative',conditions=[],
                       evidence=[dict(block_id='document_title',text='GB/T 123',start=0,end=8,occurrence=0,role='identity')])])
    result=validate_proposal(packet,proposal,load_schema(ROOT))
    assert result['errors'][0]['error']=='identity_only_does_not_establish_relation'


def test_malformed_identifier_is_an_item_error_not_batch_crash():
    packet=source_packet(dict(sample_id='x',text='土壤pH',document_title='方法'),'manual')
    result=validate_proposal(packet,dict(entities=[dict(id=[],type='indicator')],relations=[]),load_schema(ROOT))
    assert not result['protocol_complete'] and result['errors'][0]['task']=='entity'


def test_control_keys_are_separate_from_source_packets():
    from scripts.prepare_kg_benchmark_protocol import controls
    packets,keys=controls('handbook')
    assert len(packets)==len(keys)==12
    assert all('expected' not in p and 'rationale' not in p for p in packets)
    assert all(validate_proposal(p,k['expected'],load_schema(ROOT))['protocol_complete']
               for p,k in zip(packets,keys))
