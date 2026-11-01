import pytest
from scripts.archive.review_kg_benchmark_metadata_v2 import check,schema


def test_short_ids_resolve_to_full_provenance_and_do_not_rewrite_text():
    p=dict(document_id=1,file_sha256='x',profile_scope='sampled',short_id_mapping={'s0':'page1:line0:part0','s1':'stored_chunk:0'},
        sections=[dict(id='page1:line0:part0',kind='pdf_page_text',text='标题\n'),dict(id='stored_chunk:0',kind='stored_chunk_excerpt',text='土壤')])
    raw=dict(identity_status='verified',source_kind='academic_paper',title_ids=['s0'],identifier_kind='not_found_in_windows',identifier_ids=[],
        identity_reason='标题可见',language='zh',language_ids=['s1'],language_reason='中文',body_profile='readable',body_quality_ids=['s1'],quality_reason='可读')
    result=check(p,raw,None)
    assert result['metadata']['verified_title_source_text']=='标题'
    assert result['source_evidence']['title_ids'][0]['text']=='标题\n'
    assert raw['title_ids']==['s0']
    raw['title_ids']=['s1']
    with pytest.raises(ValueError,match='pdf_evidence'):check(p,raw,None)
