from scripts.adjudicate_kg_final_reference_issues import select_cases


def test_canonical_structure_does_not_trigger_semantic_repeat():
    items=[dict(sample_id='duplicate',reference_ready=False),dict(sample_id='good',reference_ready=True),
        dict(sample_id='missing',reference_ready=False)]
    assert select_cases(items,{'duplicate','good'},[])=={
        'missing':dict(source='incomplete_source_reference',errors=[])}


def test_evidence_error_always_needs_source_adjudication():
    issues=[dict(sample_id='title',release_gate=dict(errors=['title_is_not_assertion']))]
    result=select_cases([dict(sample_id='title',reference_ready=True)],set(),issues)
    assert result['title']==dict(source='independent_release_gate',errors=['title_is_not_assertion'])
