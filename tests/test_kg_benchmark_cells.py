import pytest
from framework.knowledge_graph.benchmark_cells import indexed_block,select,materialize


def test_source_cells_cover_unicode_spaces_and_linebreaks_without_normalization():
    text='土壈pH\n a\t'
    block=indexed_block(dict(block_id='chunk',text=text))
    assert 'c0="土"' in block['source_cells'] and 'c4="\\n"' in block['source_cells']
    selected=select(dict(block_id='chunk',start_cell='c0',end_cell='c3'),{'chunk':text})
    assert selected['text']=='土壈pH'
    assert block['text']==text


def test_repeat_location_and_invalid_ranges_are_not_repaired():
    blocks={'chunk':'pH pH'}
    assert select(dict(block_id='chunk',start_cell='c3',end_cell='c4'),blocks)['occurrence']==1
    with pytest.raises(ValueError):select(dict(block_id='chunk',start_cell='c7',end_cell='c8'),blocks)
    with pytest.raises(ValueError):select(dict(block_id='chunk',start_cell='c03',end_cell='c4'),blocks)


def test_materialization_uses_source_bytes_and_disallows_free_quotes():
    packet=dict(blocks=[dict(block_id='chunk',text='土壈pH')])
    raw=dict(evidence=[dict(block_id='chunk',start_cell='c0',end_cell='c3',role='assertion')])
    assert materialize(raw,packet)['evidence'][0]['text']=='土壈pH'
    assert 'start_cell' in raw['evidence'][0]
    with pytest.raises(ValueError):materialize(dict(evidence=[dict(block_id='chunk',text='土壤pH')]),packet)
