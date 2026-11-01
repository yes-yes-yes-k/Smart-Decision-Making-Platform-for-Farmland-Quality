from framework.knowledge_graph.benchmark_metadata_routing import route_metadata


def test_missing_pdf_does_not_turn_into_confirmed_identifier_absence():
    raw=dict(identifier_kind='not_found_in_windows',identity_status='requires_visual')
    p=dict(sections=[dict(kind='stored_chunk_excerpt',text='可读正文')])
    r=route_metadata(p,raw)
    assert r['effective_metadata']['identifier_kind']=='unknown'
    assert raw['identifier_kind']=='not_found_in_windows' and len(r['routes'])==1


def test_body_quality_cannot_rewrite_readable_pdf_identity():
    raw=dict(identifier_kind='not_found_in_windows',identity_status='verified',body_profile='unreadable')
    p=dict(sections=[dict(kind='pdf_page_text',text='题名'),dict(kind='stored_chunk_excerpt',text='���')])
    r=route_metadata(p,raw)
    assert r['effective_metadata']==raw and not r['routes']
