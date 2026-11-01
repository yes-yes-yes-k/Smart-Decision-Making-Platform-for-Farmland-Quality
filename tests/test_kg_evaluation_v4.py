import copy
import pytest
from framework.knowledge_graph.evaluation_v4 import digest,validate_annotation
from framework.knowledge_graph.evaluation_v4_scoring import score_sample,score_given_entities,cluster_bootstrap,aggregate,release_gates,score_given_mentions_normalization

def fixture():
    text='Liming increases soil pH. Liming'
    visible=dict(sample_id='s',blocks=[dict(block_id='chunk',kind='chunk',text=text,text_sha256=digest(text))])
    answer=dict(quality=dict(grade='A',entity_eligible=True,relation_eligible=True,numeric_eligible=False,reason='clear'),
        mentions=[dict(id='a',type='measure',fragment=dict(block_id='chunk',text='Liming',occurrence=0),canonical_name=None,normalization_status='unknown',reason='explicit'),
        dict(id='b',type='indicator',fragment=dict(block_id='chunk',text='soil pH',occurrence=0),canonical_name='soil acidity',normalization_status='known',reason='test mapping')],
        relations=[dict(source='a',target='b',relation_type='improves_indicator',modality='asserted',evidence=[dict(block_id='chunk',text='Liming increases soil pH',occurrence=0)],reason='explicit')],
        completeness=dict(entities=True,relations=True),notes='')
    return visible,answer

def test_literal_mentions_and_normalization_are_separate():
    v,a=fixture();r=validate_annotation(v,a)
    assert r['mentions'][1]['fragment']['text']=='soil pH'
    assert r['mentions'][1]['canonical_name']=='soil acidity'
    p=copy.deepcopy(r);p['mentions'][1]['canonical_name']='different'
    s=score_sample(r,p)
    assert s['mentions']['f1']==1 and s['normalization_on_reference_known_mentions']['f1']==0
    assert score_given_mentions_normalization(r,p)['f1']==0

def test_missing_failed_and_unknown_are_not_correct_negatives():
    v,a=fixture();a.update(mentions=[],relations=[]);r=validate_annotation(v,a)
    assert not score_sample(r)['correct_negative']
    assert score_sample(r,r)['correct_negative']
    r['completeness']['entities']=False
    assert score_sample(r,r)['mentions'] is None and not score_sample(r,r)['negative']

def test_repeated_mention_positions_are_not_interchangeable():
    v,a=fixture();r=validate_annotation(v,a);a['mentions'][0]['fragment']['occurrence']=1;p=validate_annotation(v,a)
    assert score_sample(r,p)['relations']['tp']==0
    with pytest.raises(ValueError,match='oracle_entity_inventory_changed'):score_given_entities(r,p)
    with pytest.raises(ValueError,match='oracle_mention_inventory_changed'):score_given_mentions_normalization(r,p)

def test_valid_short_evidence_not_scored_only_by_hash():
    v,a=fixture();r=validate_annotation(v,a);a['relations'][0]['evidence'][0]['text']+='.';p=validate_annotation(v,a)
    s=score_sample(r,p)
    assert s['relations']['f1']==1
    assert s['evidence_character_overlap_on_matched_facts']['recall']==1
    assert s['evidence_character_overlap_on_matched_facts']['precision']<1

def test_negated_relations_not_positive_and_context_mismatch_rejected():
    v,a=fixture();r=validate_annotation(v,a);a['relations'][0]['modality']='negated';p=validate_annotation(v,a)
    assert score_sample(r,p)['relations']['tp']==0
    p['input_sha256']='changed'
    with pytest.raises(ValueError,match='input_context_mismatch'):score_sample(r,p)

def test_unreadable_and_fake_quotes_rejected():
    v,a=fixture();a['quality']['grade']='C'
    with pytest.raises(ValueError,match='unreadable_cannot_be_negative'):validate_annotation(v,a)
    v,a=fixture();a['mentions'][0]['fragment']['text']='invented'
    with pytest.raises(ValueError,match='fragment_not_in_visible_input'):validate_annotation(v,a)

def test_cluster_intervals_require_documents_and_facts():
    v,a=fixture();r=validate_annotation(v,a);s=score_sample(r,r)
    assert cluster_bootstrap({'a':s},{'a':'doc'})['lower'] is None
    ci=cluster_bootstrap({'a':s,'b':s},{'a':'doc1','b':'doc2'},repeats=20)
    assert ci['lower']==ci['upper']==1

def test_empty_agreement_cannot_open_gates_and_ai_never_certifies_production():
    gate=release_gates(dict(samples=10,paired_completed=10,numeric_agreement_gate=True,adjudication_complete=True),True)
    assert not gate['allow_model_experiment']
    gate=release_gates(dict(samples=100,paired_completed=100,numeric_agreement_gate=True,adjudication_complete=True),True)
    assert gate['allow_model_experiment'] and not gate['production_approved'] and not gate['expert_certified']

def test_macro_uses_documents_not_chunks_and_failure_affects_availability():
    good=dict(completed=True,mentions=dict(tp=1,fp=0,fn=0))
    bad=dict(completed=False,mentions=dict(tp=0,fp=0,fn=1))
    report=aggregate({'a':good,'b':good,'c':bad},{'a':'doc1','b':'doc1','c':'doc2'})
    assert report['document_macro_f1']==.5
    assert report['micro_f1']==.8 and report['availability']==pytest.approx(2/3)
