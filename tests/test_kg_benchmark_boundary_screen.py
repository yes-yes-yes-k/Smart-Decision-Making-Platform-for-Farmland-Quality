from scripts.screen_kg_benchmark_reference_boundaries import screen


def test_internal_word_fragment_is_flagged_without_label_changes():
    reference=dict(visible_input=dict(blocks=[dict(block_id='chunk',text='soil compaction')]),
        reference=dict(entities=[dict(id='x',type='obstacle',block_id='chunk',text='mpaction',start=7,end=15)],relations=[]))
    hints=screen(reference)
    assert hints[0]['kind']=='latin_token_internal_boundary'
    assert reference['reference']['entities'][0]['text']=='mpaction'
