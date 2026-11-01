import copy
from types import SimpleNamespace
import pytest
from framework.knowledge_graph.acceptance_budget import Budget,BudgetStop
from framework.knowledge_graph.acceptance_data import identity_groups,assert_isolation,deterministic_selection,validate_qa
from framework.knowledge_graph.acceptance_metrics import qa_report,require_final_approval,threshold_proposal

def options():return dict(messages=[],max_tokens=10)

def test_reservation_and_unknown_usage_remain_charged(tmp_path):
    b=Budget(tmp_path/'b.db',total=100000,stability=100000)
    i=b.reserve('stability','a',options());before=b.summary()['tokens_charged_or_reserved'];b.finish(i,error='timeout')
    assert b.summary()['tokens_charged_or_reserved']==before and b.summary()['requests']==1

def test_budget_persists_limits_across_instances(tmp_path):
    p=tmp_path/'b.db';b=Budget(p,requests=1);i=b.reserve('stability','a',options());b.finish(i,SimpleNamespace(total_tokens=1))
    with pytest.raises(BudgetStop):Budget(p,requests=1).reserve('stability','b',options())

def test_per_phase_cap_and_concurrency_enforced(tmp_path):
    b=Budget(tmp_path/'b.db',stability=1)
    with pytest.raises(BudgetStop):b.reserve('stability','a',options())
    b=Budget(tmp_path/'c.db');b.reserve('reference','a',options());b.reserve('reference','b',options())
    with pytest.raises(BudgetStop,match='concurrency'):b.reserve('reference','c',options())

def test_interrupted_attempt_never_becomes_free(tmp_path):
    b=Budget(tmp_path/'b.db');b.reserve('reference','a',options());before=b.summary()['tokens_charged_or_reserved'];b.recover_interrupted()
    assert b.summary()['tokens_charged_or_reserved']==before and b.summary()['inflight']==0

def test_versions_and_doi_form_transitive_isolation_group():
    docs=[dict(id=1,standard_number='NY/T 123—2020',file_sha256='a'),dict(id=2,standard_number='NY/T 123-2023',doi='x'),dict(id=3,doi='X')]
    g=identity_groups(docs)
    assert g.find(1)==g.find(2)==g.find(3)

@pytest.mark.parametrize('partition,track',[('test','representative'),('calibration','challenge')])
def test_document_group_cannot_cross_partition_or_track(partition,track):
    rows=[dict(sample_id='a',isolation_group=1,partition='calibration',track='representative'),dict(sample_id='b',isolation_group=1,partition=partition,track=track)]
    with pytest.raises(ValueError,match='crosses'):assert_isolation(rows)

def test_sampling_is_repeatable_and_keeps_damaged_chunks():
    docs=[dict(id=i,kind='paper',language='en',parse_quality='unknown') for i in range(110)]
    cs=[dict(sample_id=f'{i}:{j}',document_id=i,isolation_group=i,position_quartile=j,text='��� soil remediation') for i in range(110) for j in range(3)]
    a=deterministic_selection(docs,cs,'seed');b=deterministic_selection(list(reversed(docs)),list(reversed(cs)),'seed')
    assert a==b and len([r for r in a if r['track']=='representative'])==300
    assert sum(r['track']=='representative' and r['partition']=='calibration' for r in a)==60
    assert all('���' in r['text'] for r in a)

def test_qa_cannot_use_other_partition_or_fake_quote():
    blocks={'s':dict(text='abc',isolation_group=1,partition='test')}
    q=dict(question='q',rationale='source',partition='calibration',answerability='answerable',answer_points=['a'],evidence=[dict(sample_id='s',text='abc',span_start=0,span_end=3)])
    with pytest.raises(ValueError,match='cross_partition'):validate_qa(q,blocks,{1:'test'})
    q['partition']='test';q['evidence'][0]['text']='xyz'
    with pytest.raises(ValueError,match='unbound'):validate_qa(q,blocks,{1:'test'})

def test_multihop_requires_multiple_source_blocks():
    b={'s':dict(text='abc',isolation_group=1,partition='test')}
    q=dict(question='q',rationale='source',partition='test',answerability='answerable',answer_points=['a'],multihop=True,evidence=[dict(sample_id='s',text='abc',span_start=0,span_end=3)])
    with pytest.raises(ValueError,match='two_blocks'):validate_qa(q,b,{1:'test'})

def test_abstain_does_not_pass_answerable_question_and_missing_counts():
    refs=[dict(id='a',answerability='answerable',evidence=[dict(sample_id='s')]),dict(id='b',answerability='insufficient',evidence=[dict(sample_id='s')])]
    r=qa_report(refs,[dict(id='a',state='completed',abstain=True,answer='unknown')],[dict(id='a',state='completed',supported=True,correct_refusal=True)])
    assert r['answerable_completion']==0 and r['correct_refusal']==0 and r['availability']==.5 and r['supported_answer_rate'] is None

def test_missing_judge_does_not_certify_supported_answer():
    r=qa_report([dict(id='a',answerability='answerable',evidence=[dict(sample_id='s')])],[dict(id='a',state='completed',abstain=False,answer='x',retrieved_sample_ids=['s'])],[])
    assert r['supported_answer_rate']==0 and r['answerable_completion']==0 and r['evidence_recall_at_5']==1

def test_proposed_thresholds_cannot_authorize_final_test():
    p=threshold_proposal({})
    assert not p['approved']
    with pytest.raises(ValueError,match='confirmation_required'):require_final_approval({},None,config_sha256='c',threshold_sha256='t')
    with pytest.raises(ValueError,match='does_not_match'):require_final_approval({},dict(approved=True,approved_by='user',config_sha256='x'),config_sha256='c',threshold_sha256='t')

def test_user_suspend_blocks_remote_before_client_creation(tmp_path,monkeypatch):
    import scripts.run_kg_acceptance_v1 as runner
    import json,asyncio
    from framework.knowledge_graph.acceptance_remote import run_jobs
    monkeypatch.setattr(runner,'OUT',tmp_path)
    (tmp_path/'remote-policy.json').write_text(json.dumps(dict(suspended_by_user=True)),encoding='utf-8')
    with pytest.raises(ValueError,match='suspended_by_user'):runner.ensure_remote_enabled()
    with pytest.raises(ValueError,match='suspended_by_user'):
        asyncio.run(run_jobs([],tmp_path/'jobs',{},Budget(tmp_path/'b.db'),lambda j,a:a))

def test_provider_failure_blocks_remote_without_probe(tmp_path,monkeypatch):
    import scripts.run_kg_acceptance_v1 as runner
    import json
    monkeypatch.setattr(runner,'OUT',tmp_path)
    (tmp_path/'provider-status.json').write_text(json.dumps(dict(available=False,http_status=402)),encoding='utf-8')
    with pytest.raises(ValueError,match='provider_unavailable'):runner.ensure_remote_enabled()

def test_unvalidated_citation_cannot_pass_even_with_positive_judge():
    refs=[dict(id='a',answerability='answerable',evidence=[dict(sample_id='s')])]
    predictions=[dict(id='a',state='completed',abstain=False,answer='x')]
    reviews=[dict(id='a',state='completed',supported=True,answers_question=True,citations_supported=True)]
    r=qa_report(refs,predictions,reviews)
    assert r['supported_answer_rate']==r['answerable_completion']==r['citation_support_rate']==0

def test_qa_document_cluster_intervals_use_source_groups():
    refs=[dict(id=str(i),answerability='answerable',evidence=[dict(sample_id=str(i))],isolation_groups=[i]) for i in range(3)]
    r=qa_report(refs,[],[])
    assert r['document_group_intervals']['answerable_completion']['upper']==0
    assert r['document_group_intervals']['availability']['groups']==3

def test_zero_support_never_passes_threshold_and_failure_is_explicit():
    from framework.knowledge_graph.acceptance_metrics import evaluate_thresholds
    rules={'p':dict(minimum=.9,minimum_support=10)}
    assert evaluate_thresholds({'p':dict(value=1.,support=0)},rules)['status']=='inconclusive'
    assert evaluate_thresholds({'p':dict(value=.8,support=20)},rules)['status']=='fail'
    assert evaluate_thresholds({'p':dict(value=.95,support=20)},rules)['status']=='pass'

def test_ambiguous_or_vacuous_threshold_rules_are_rejected():
    from framework.knowledge_graph.acceptance_metrics import evaluate_thresholds
    with pytest.raises(ValueError):evaluate_thresholds({},dict(p=dict(minimum=.9,maximum=.95,minimum_support=1)))
    with pytest.raises(ValueError):evaluate_thresholds({},dict(p=dict(minimum=.9,minimum_support=0)))

def test_final_scoring_requires_user_confirmation_before_reading_test_labels(tmp_path,monkeypatch):
    import scripts.score_kg_acceptance_v1 as scoring
    monkeypatch.setattr(scoring,'OUT',tmp_path)
    (tmp_path/'run-config.json').write_text('{}',encoding='utf-8')
    with pytest.raises(ValueError,match='confirmation_required'):scoring.final_guard('test')

def test_active_model_run_keeps_old_outputs_and_shared_budget(tmp_path):
    import json
    from framework.knowledge_graph.acceptance_paths import active_output,shared_budget
    base=tmp_path/'artifacts/knowledge_platform';old=base/'acceptance-v1';new=base/'acceptance-v1-v41flash'
    old.mkdir(parents=True);new.mkdir()
    (old/'run-config.json').write_text('{"model":"old"}',encoding='utf-8')
    (old/'budget.sqlite3').write_bytes(b'historical ledger')
    (base/'acceptance-active-run.json').write_text(json.dumps(dict(directory=new.name)),encoding='utf-8')
    (new/'shared-budget.json').write_text(json.dumps(dict(path='artifacts/knowledge_platform/acceptance-v1/budget.sqlite3')),encoding='utf-8')
    assert active_output(tmp_path)==new and shared_budget(tmp_path,new)==old/'budget.sqlite3'
    assert json.loads((old/'run-config.json').read_text())['model']=='old'
    assert not (new/'stability/responses').exists()

def test_active_run_and_budget_cannot_escape_workspace(tmp_path):
    import json
    from framework.knowledge_graph.acceptance_paths import active_output,shared_budget
    base=tmp_path/'artifacts/knowledge_platform';base.mkdir(parents=True)
    (base/'acceptance-active-run.json').write_text(json.dumps(dict(directory='../../elsewhere')),encoding='utf-8')
    with pytest.raises(ValueError,match='invalid_acceptance'):active_output(tmp_path)
    (base/'shared-budget.json').write_text(json.dumps(dict(path='../elsewhere/budget.db')),encoding='utf-8')
    with pytest.raises(ValueError,match='outside_workspace'):shared_budget(tmp_path,base)
