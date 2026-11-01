"""Block release on source identity, exposure or partition conflicts."""
from .acceptance_data import assert_isolation
from .benchmark_rebuild import standard_family


def verify_membership(samples,documents):
    assert_isolation(samples);identity={};texts={}
    for r in samples:
        d=documents[r['document_id']]
        if not d['sampling_eligible'] or d.get('blockers'):raise ValueError('source_not_eligible')
        if d['exposure_status']!='no_exposure_found_in_audited_records':raise ValueError('source_exposure_conflict')
        if r['isolation_group']!=d['isolation_group']:raise ValueError('source_group_mismatch')
        if r.get('file_sha256',d['file_sha256'])!=d['file_sha256']:raise ValueError('source_file_hash_mismatch')
        part=(r['track'],r['partition'])
        if r['text_sha256'] in texts and texts[r['text_sha256']]!=part:raise ValueError('exact_content_cross_partition')
        texts[r['text_sha256']]=part
        if d.get('identifier'):
            value=d['identifier'].strip().casefold() if d['identifier_kind']=='doi' else standard_family(d['identifier'])
            key=(d['identifier_kind'],value)
            if key in identity and identity[key]!=part:raise ValueError('identity_or_revision_cross_partition')
            identity[key]=part
    return dict(status='pass',samples=len(samples),document_groups=len({r['isolation_group'] for r in samples}),
        scope='source_identity_exposure_grouping_and_exact_content',semantic_near_duplicate_certification=False)
