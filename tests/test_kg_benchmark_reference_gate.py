from framework.knowledge_graph.benchmark_reference_gate import check_reference


def reference(block):
    span=dict(block_id=block,text='改良',start=0,end=2,occurrence=0,role='assertion')
    return dict(visible_input=dict(blocks=[dict(block_id='chunk',text='改良'),dict(block_id='document_title',text='改良')]),
        reference=dict(entities=[],relations=[dict(evidence=[span])]))


def test_title_only_assertion_does_not_become_valid_reference_or_empty_negative():
    raw=reference('document_title');check=check_reference(raw)
    assert not check['reference_ready'] and not check['labels_modified']
    assert len(raw['reference']['relations'])==1
    assert {'title_cannot_assert_relation','relation_requires_body_assertion'}=={e['error'] for e in check['errors']}


def test_body_span_support_is_necessary_but_not_expert_certification():
    check=check_reference(reference('chunk'))
    assert check['reference_ready'] and 'necessary' in check['scope']
