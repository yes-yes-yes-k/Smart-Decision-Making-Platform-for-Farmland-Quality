from copy import deepcopy
import hashlib
import pytest
from scripts.freeze_codex_kg_reference import freeze_rows
from scripts.score_kg_corpus import evaluate,normalize
from scripts.run_kg_corpus_graphrag import validate_input


def fixture():
    text='参考文献。'
    source=dict(sample_id='s',text=text,text_sha256=hashlib.sha256(text.encode()).hexdigest(),split='test')
    candidate=dict(source=source,proposal_sha256='proposal')
    decision=dict(index=0,sample_id='s',source_text_sha256=source['text_sha256'],
        parent_proposal_sha256='proposal',reviewer_kind='ai_agent',independent_human_review=False,
        reviewed_at='2026-10-27',reason='已直接阅读原文，当前块只有参考文献，没有正文土壤事实。',
        annotation=dict(entities=[],relationships=[]))
    return candidate,decision


def test_freeze_requires_complete_current_review_and_never_claims_human():
    c,d=fixture()
    with pytest.raises(ValueError,match='complete'):freeze_rows([c],[],{},1)
    row=freeze_rows([c],[d],{},1)[0]
    assert row['independent_human_review'] is False and row['production_approved'] is False
    d['source_text_sha256']='stale'
    with pytest.raises(ValueError,match='stale'):freeze_rows([c],[d],{},1)


def test_unknown_sources_are_retained_but_not_scored_as_negatives():
    c,d=fixture();rows=freeze_rows([c],[d],{0:'unreadable'},1)
    metrics,_=evaluate(rows,[])
    assert metrics['all']['sample_count']==1 and metrics['all']['scored_samples']==0
    assert metrics['all']['negative_samples']==0


def test_failure_and_missing_are_not_correct_negatives():
    c,d=fixture();rows=freeze_rows([c],[d],{},1)
    failed,_=evaluate(rows,[dict(sample_id='s',state='failed')])
    absent,_=evaluate(rows,[])
    assert failed['all']['correct_negative_samples']==absent['all']['correct_negative_samples']==0
    good=dict(sample_id='s',state='completed',source_text_sha256=c['source']['text_sha256'],
        artifact=dict(entities=[],relationships=[]))
    metrics,_=evaluate(rows,[good])
    assert metrics['all']['correct_negative_samples']==1


def test_isolated_gold_entity_is_a_miss_on_provider_failure():
    c,d=fixture();d['annotation']['entities']=[dict(name='土壤pH',type='indicator')]
    rows=freeze_rows([c],[d],{},1)
    metrics,_=evaluate(rows,[dict(sample_id='s',state='failed')])
    assert metrics['test']['entities']['false_negative']==1
    assert metrics['test']['negative_samples']==0


def test_numeric_and_chemical_distinctions_survive_normalization():
    assert normalize('5.0')!=normalize('50')
    assert normalize('NO3-')!=normalize('NO3+')
    assert normalize(' Soil pH ')==normalize('SOILPH')


def test_inference_inputs_reject_gold_labels_and_changed_text():
    c,_=fixture();source=dict(sample_id='s',source=deepcopy(c['source']))
    validate_input(source)
    source['entities']=[]
    with pytest.raises(ValueError,match='source only'):validate_input(source)
    del source['entities'];source['source']['text']='changed'
    with pytest.raises(ValueError,match='checksum'):validate_input(source)


def test_evidence_requires_literal_source_and_relation_scores_keep_direction():
    from scripts.score_kg_corpus import prediction,fact_sets
    source=dict(text='石灰治理酸化。',text_sha256='sha')
    record=dict(state='completed',source_text_sha256='sha',artifact=dict(entities=[
        dict(title='石灰',entity_type='measure'),dict(title='酸化',entity_type='obstacle')],
        relationships=[dict(source='石灰',target='酸化',relation_type='addresses')]))
    es,rs=prediction(record,source)
    assert rs[0]['quote']==source['text'] and rs[0]['span_start']==0
    original=fact_sets(es,rs)[1]
    rs[0]['source'],rs[0]['target']='酸化','石灰'
    assert not original & fact_sets(es,rs)[1]
    record['artifact']['relationships'][0]['quote']='石灰改善产量'
    with pytest.raises(ValueError,match='not literal'):prediction(record,source)
