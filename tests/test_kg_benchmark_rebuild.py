from framework.knowledge_graph.benchmark_rebuild import (
    reconcile, identity_components, draft_representative, language_hint)


def test_provenance_never_matches_same_name_different_bytes():
    matches, unbound = reconcile([dict(path='a.pdf', sha256='x')],
                                [dict(id=1, doc_name='a.pdf', file_hash='y')])
    assert matches[0]['match'] == 'unmatched'
    assert len(unbound) == 1


def test_standard_revision_grouping_keeps_distinct_numbers():
    docs = [dict(id=1, standard_number_normalized='GB/T 123-2020'),
            dict(id=2, standard_number_normalized='GB/T 123—2024', file_hash='x'),
            dict(id=3, standard_number_normalized='GB/T 124-2020'),
            dict(id=4, file_hash='x')]
    groups, edges = identity_components(docs)
    assert groups[1] == groups[2] == groups[4]
    assert groups[3] != groups[1] and len(edges) == 2


def test_draft_position_coverage_short_groups_and_permutation_invariance():
    docs = [dict(id=i, document_kind='paper') for i in range(100)]
    chunks = [dict(sample_id=f'{i}:{q}', document_id=i, isolation_group=i,
                   position_quartile=q, text='damaged �')
              for i in range(100) for q in (range(1) if i == 0 else range(4))]
    a, report = draft_representative(docs, chunks, 'seed')
    b, other = draft_representative(docs[::-1], chunks[::-1], 'seed')
    assert a == b and report == other
    assert report['chunks'] == 298 and report['shortfall'] == 2
    assert any(r['document_id'] == 0 for r in a)
    for part in ('calibration', 'test'):
        assert set(report['quartiles'][part]) == {'0', '1', '2', '3'}
    assert all(r['group_inclusion_probability'] == 1 for r in a)
    assert all(r['selection_status'] == 'draft_not_acceptance_frozen' for r in a)


def test_language_hints_do_not_claim_verified_language():
    assert language_hint('Soil ' * 20) == 'en_candidate'
    assert language_hint('土壤指标' * 20) == 'zh_candidate'
    assert language_hint('pH') == 'unknown'


def test_doi_hints_are_literal_unverified_and_not_taken_from_later_references():
    from scripts.audit_kg_benchmark_identity import identity_hints
    chunks=[dict(sample_id='a',page=1,text='Publisher https://doi.org/10.1234/example. '),
            dict(sample_id='b',page=9,text='References 10.5678/other')]
    hints=identity_hints(dict(doc_name='GB_T_123-2020.pdf'),chunks)
    dois=[h for h in hints if h['kind']=='doi']
    assert len(dois)==1 and dois[0]['value']=='10.1234/example' and not dois[0]['verified']
    assert chunks[0]['text'][dois[0]['start']:dois[0]['end']]==dois[0]['quote']
