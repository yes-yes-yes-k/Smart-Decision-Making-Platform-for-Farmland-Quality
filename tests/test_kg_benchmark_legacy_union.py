from framework.knowledge_graph.benchmark_legacy_proposal_union import union_legacy_proposals


def test_old_alias_proposals_are_remapped_without_inventing_canonical_names():
    a=dict(decisions=[dict(id='a',type='standard',fragment=dict(block_id='chunk',start_cell='c0',end_cell='c2'))],
        relations=[],normalization=[dict(entity_id='a',status='unknown',canonical_name=None,evidence=[])])
    b=dict(decisions=[dict(id='b',type='standard',fragment=dict(block_id='chunk',start_cell='c0',end_cell='c2'))],
        relations=[],normalization=[dict(entity_id='b',status='unknown',canonical_name=None,evidence=[])])
    result=union_legacy_proposals([a,b])
    assert len(result['decisions'])==1 and len(result['normalization'])==1
    assert result['normalization'][0]['entity_id']=='u0'
    assert result['normalization'][0]['canonical_name'] is None
    assert a['normalization'][0]['entity_id']=='a'
