"""Conservative source-window routes; raw model decisions remain immutable."""


def route_metadata(packet, metadata):
    result=dict(metadata);changes=[]
    readable_identity=any(s['kind']=='pdf_page_text' and s['text'].strip() for s in packet['sections'])
    if not readable_identity and result.get('identifier_kind')=='not_found_in_windows':
        result['identifier_kind']='unknown'
        changes.append(dict(field='identifier_kind',raw='not_found_in_windows',effective='unknown',
            reason='no_identity_window_cannot_establish_identifier_search_coverage'))
    return dict(effective_metadata=result,routes=changes,raw_metadata_modified=False,
        scope='bibliographic_source_audit_only_not_extraction_scoring')
