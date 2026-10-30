from copy import deepcopy
import pytest
from framework.knowledge_graph.gold_sampling import sample_document_chunks,assign_splits,document_order
from framework.knowledge_graph.schema import load_graph_schema
from scripts.annotate_kg_gold_corpus import validate_annotation


def source(index=0,text='施用石灰\n治理土壤酸化。'):
    return dict(content=text,metadata=dict(document_id=1,content_sha256='file',visibility_scope='public',chunk_index=index,page=index+1))


def doc():
    return dict(id=1,file_sha256='file',title='公开论文',kind='academic_paper',domain_labels=['quality'])


def test_sampling_rejects_unbound_chunks_and_never_changes_source():
    chunks=[source()];original=deepcopy(chunks)
    rows=sample_document_chunks(doc(),chunks,seed='s',count=4,seen=set())
    assert chunks==original and rows[0]['text']==chunks[0]['content']
    assert rows[0]['gold_approved'] is False
    chunks[0]['metadata']['content_sha256']='wrong'
    with pytest.raises(ValueError,match='provenance'):
        sample_document_chunks(doc(),chunks,seed='s',count=4,seen=set())


def test_duplicate_chunk_text_is_not_sampled_twice():
    rows=sample_document_chunks(doc(),[source(0,'施用 石灰治理酸化'),source(1,'施用石灰治理酸化')],seed='s',count=4,seen=set())
    assert len(rows)==1


def test_source_file_and_near_duplicate_groups_do_not_cross_splits():
    text='农业土壤酸化问题应采用科学措施改善。'*20
    samples=[dict(file_sha256='a',text=text),dict(file_sha256='b',text=text+'结论'),dict(file_sha256='a',text='其他不同内容'),
        dict(file_sha256='c',text='完全不同的论文来源讨论灌溉水利用效率。')]
    assign_splits(samples,'seed')
    assert samples[0]['split']==samples[1]['split']==samples[2]['split']
    assert samples[0]['leakage_group']==samples[1]['leakage_group']


def test_document_order_is_stable_and_includes_rare_kind():
    docs=[{**doc(),'id':i,'file_sha256':str(i)} for i in range(20)]
    docs.append({**doc(),'id':30,'file_sha256':'rare','kind':'method_guideline'})
    assert document_order(docs,'s')==document_order(list(reversed(docs)),'s')
    assert any(row['id']==30 for row in document_order(docs,'s')[:3])


def test_preannotation_keeps_empty_samples_unapproved():
    result=validate_annotation({'sample_id':'s','text':'参考文献。'},{'entities':[],'relationships':[]},load_graph_schema())
    assert result['disposition']=='no_schema_facts'
    assert result['annotation_status']=='needs_adjudication' and result['gold_approved'] is False


def test_source_binding_restores_only_whitespace_and_rejects_invented_quote():
    answer=dict(entities=[dict(name='施用石灰',type='measure'),dict(name='土壤酸化',type='obstacle')],
        relationships=[dict(source='施用石灰',target='土壤酸化',relation_type='addresses',quote='施用石灰治理土壤酸化。')])
    result=validate_annotation({'sample_id':'s','text':'施用石灰\n治理土壤酸化。'},answer,load_graph_schema())
    assert result['relationships'][0]['quote']=='施用石灰\n治理土壤酸化。'
    assert result['gold_approved'] is False
    answer['relationships'][0]['quote']='施用石灰显著改善酸化'
    result=validate_annotation({'sample_id':'s','text':'施用石灰\n治理土壤酸化。'},answer,load_graph_schema())
    assert not result['relationships'] and result['validation_errors']


def test_model_consensus_never_approves_gold_and_missing_samples_are_kept():
    from scripts.assemble_kg_gold_rebuild import assemble
    sample=dict(sample_id='s',text='仅有参考文献',document_id=1)
    empty=validate_annotation(sample,dict(entities=[],relationships=[]),load_graph_schema())
    rows=assemble([sample],{'s':empty},{'s':empty})
    assert rows[0]['gold_approved'] is False
    assert rows[0]['review_status']=='needs_adjudication'
    assert 'no_fact_decision_requires_adjudication' in rows[0]['review_reasons']
    missing=assemble([sample],{}, {})
    assert len(missing)==1 and missing[0]['review_priority']==100


def test_gold_publication_requires_explicit_current_source_adjudication():
    from scripts.assemble_kg_gold_rebuild import assemble
    from scripts.export_kg_adjudicated_gold import adjudicated_rows
    import hashlib
    sample=dict(sample_id='s',text='仅有参考文献',text_sha256=hashlib.sha256('仅有参考文献'.encode()).hexdigest(),
        document_id=1,split='test')
    empty=validate_annotation(sample,dict(entities=[],relationships=[]),load_graph_schema())
    reference=assemble([sample],{'s':empty},{'s':empty})
    assert adjudicated_rows(reference,[])==[]
    decision=dict(sample_id='s',decision='accept',reviewer='test reviewer',reviewed_at='2026-10-27',
        text_sha256=sample['text_sha256'],proposal_sha256=reference[0]['proposal_sha256'])
    assert adjudicated_rows(reference,[decision])[0]['disposition']=='no_schema_facts'
    decision['text_sha256']='stale'
    with pytest.raises(ValueError,match='stale'):
        adjudicated_rows(reference,[decision])


def test_review_cache_is_bound_to_the_exact_first_pass_snapshot(tmp_path):
    from scripts.annotate_kg_gold_corpus import bind_review_proposals
    original=b'{"sample_id":"a","entities":[]}\n'
    assert 'a' in bind_review_proposals(tmp_path,original)
    assert 'a' in bind_review_proposals(tmp_path,original)
    with pytest.raises(ValueError,match='proposals changed'):
        bind_review_proposals(tmp_path,b'{"sample_id":"a","entities":[1]}\n')
