import pytest
from framework.knowledge_graph.benchmark_dual_selector import materialize_dual

PACKET=dict(blocks=[dict(block_id='chunk',text='soil compaction')])


def test_valid_offsets_cannot_silently_override_claimed_entity_name():
    fragment=dict(block_id='chunk',text='compaction',start_cell='c7',end_cell='c14')
    with pytest.raises(ValueError,match='verbatim_text_cell_disagreement'):
        materialize_dual(dict(fragment=fragment),PACKET)


def test_same_bad_fragment_is_not_falsely_semantically_certified():
    fragment=dict(block_id='chunk',text='mpaction',start_cell='c7',end_cell='c14')
    result=materialize_dual(dict(fragment=fragment),PACKET)
    assert result['fragment']['text']=='mpaction'  # semantic review remains mandatory


def test_exact_source_selection_no_boundary_repair():
    fragment=dict(block_id='chunk',text='compaction',start_cell='c5',end_cell='c14')
    assert materialize_dual(fragment,PACKET)['text']=='compaction'
    assert fragment['start_cell']=='c5'


def test_missing_quote_is_not_filled_from_coordinates():
    with pytest.raises(ValueError,match='verbatim_text_and_both_cells_required'):
        materialize_dual(dict(block_id='chunk',start_cell='c5',end_cell='c14'),PACKET)
