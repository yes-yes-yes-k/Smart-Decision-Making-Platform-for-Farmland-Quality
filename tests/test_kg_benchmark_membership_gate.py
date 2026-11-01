import pytest
from framework.knowledge_graph.benchmark_membership_gate import verify_membership


def data():
    docs={i:dict(document_id=i,sampling_eligible=True,blockers=[],exposure_status='no_exposure_found_in_audited_records',
        isolation_group=i,file_sha256=str(i),identifier_kind='standard_number',identifier=f'GB {i}-2020') for i in [1,2]}
    rows=[dict(sample_id=str(i),document_id=i,isolation_group=i,track='representative',partition='calibration' if i==1 else 'test',text_sha256=str(i)) for i in [1,2]]
    return rows,docs


def test_revision_family_conflict_blocks_release_even_with_wrong_group_ids():
    rows,docs=data();docs[2]['identifier']='GB 1-2026'
    with pytest.raises(ValueError,match='revision'):verify_membership(rows,docs)


def test_exposure_or_pending_identity_cannot_be_overridden_by_eligible_flag():
    rows,docs=data();docs[1]['blockers']=['identity_pending']
    with pytest.raises(ValueError,match='source_not_eligible'):verify_membership(rows,docs)
    docs[1]['blockers']=[];docs[1]['exposure_status']='unknown'
    with pytest.raises(ValueError,match='exposure'):verify_membership(rows,docs)


def test_exact_shared_content_blocks_and_unknown_quality_does_not_filter():
    rows,docs=data();docs[1]['quality']='unknown'
    assert verify_membership(rows,docs)['status']=='pass'
    rows[1]['text_sha256']=rows[0]['text_sha256']
    with pytest.raises(ValueError,match='exact_content'):verify_membership(rows,docs)
