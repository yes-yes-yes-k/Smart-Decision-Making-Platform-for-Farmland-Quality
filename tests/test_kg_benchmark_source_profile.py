import pytest
from scripts.adjudicate_kg_benchmark_source_profiles import check


def packet():
    return dict(document_id=1,file_sha256='hash',profile_scope='sampled',short_id_mapping=dict(s0='pdf',s1='body'),
        sections=[dict(id='pdf',kind='pdf_page_text',text='封面'),dict(id='body',kind='stored_chunk_excerpt',text='乱码')])


def raw():return dict(source_kind='standard',kind_evidence_ids=['s0'],language='zh',language_evidence_ids=['s0'],
    body_profile='unreadable',body_evidence_ids=['s1'])


def test_readable_cover_cannot_be_used_to_certify_body_quality():
    r=raw();r['body_evidence_ids']=['s0']
    with pytest.raises(ValueError,match='quality_must_use_body'):check(packet(),r,None)


def test_quality_and_identity_are_separate_without_old_answer_leakage():
    r=check(packet(),raw(),None)
    assert r['protocol_complete'] and r['identity_not_redecided']
    assert r['profile']['source_kind']=='standard' and r['profile']['body_profile']=='unreadable'
    assert r['previous_model_and_database_classifications_hidden']
