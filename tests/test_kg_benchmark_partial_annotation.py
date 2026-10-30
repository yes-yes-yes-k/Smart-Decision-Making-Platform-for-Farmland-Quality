from framework.knowledge_graph.benchmark_partial_annotation import complete_array_objects,partial_annotation


def test_truncation_never_invents_last_object_or_closing_syntax():
    text='{"decisions":[{"id":"a"},{"id":"b"'
    objects,complete=complete_array_objects(text,'decisions')
    assert objects==[dict(id='a')] and not complete


def test_complete_source_bound_prefix_is_diagnostic_not_successful_original_response():
    raw='{"decisions":[{"id":"a","type":"indicator","decision":"include","fragment":{"block_id":"chunk","start_cell":"c0","end_cell":"c1"}}],"relations":['
    packet=dict(blocks=[dict(block_id='chunk',text='土壤')])
    proposal,diagnostic=partial_annotation(dict(state='incomplete',content=raw),packet)
    assert len(proposal['decisions'])==1 and proposal['relations']==[]
    assert not diagnostic['original_protocol_accepted'] and not diagnostic['complete_json']
    assert diagnostic['missing_items_not_assumed_negative']
