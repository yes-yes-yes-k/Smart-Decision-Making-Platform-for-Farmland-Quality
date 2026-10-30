import copy
from pathlib import Path
import pytest
from framework.knowledge_graph.benchmark_protocol import source_packet,load_schema
from framework.knowledge_graph.benchmark_protocol_r2 import locate,ground


def test_literal_coordinates_derived_without_ocr_or_whitespace_repair():
    blocks={'chunk':'土壈pH 土壤pH 土壤pH'}
    assert locate(dict(block_id='chunk',text='土壤pH',occurrence=1),blocks)['start']==10
    with pytest.raises(ValueError):
        locate(dict(block_id='chunk',text='土壤 pH',occurrence=0),blocks)
    with pytest.raises(ValueError):
        locate(dict(block_id='chunk',text='土壤pH',occurrence=True),blocks)


def test_excluded_entity_stays_auditable_but_cannot_be_relation_endpoint():
    packet=source_packet(dict(sample_id='x',text='籽粒Cd含量；土壤Cd含量',document_title='结果'),'manual')
    raw=dict(decisions=[dict(id='a',type='indicator',decision='exclude',reason='植物介质',
        fragment=dict(block_id='chunk',text='籽粒Cd含量',occurrence=0)),
        dict(id='b',type='indicator',decision='include',reason='土壤介质',
        fragment=dict(block_id='chunk',text='土壤Cd含量',occurrence=0))],
        relations=[],normalization=[],task_masks={k:'applicable' for k in ['entities','relations','normalization']})
    before=copy.deepcopy(raw)
    result=ground(packet,raw,load_schema(Path(__file__).resolve().parents[1]))
    assert result['protocol']['protocol_complete']
    assert [e['id'] for e in result['proposal']['entities']]==['b']
    assert result['decisions'][0]['decision']=='exclude' and raw==before
