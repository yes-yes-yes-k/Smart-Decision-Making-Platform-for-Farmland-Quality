import json
from types import SimpleNamespace
import pytest
from framework.knowledge_graph.benchmark_budget_policy import AuthorizedBudget
from framework.knowledge_graph.acceptance_budget import BudgetStop


def setup(tmp_path):
    a=tmp_path/'auth.json';a.write_text(json.dumps(dict(approved_by='user',explicit_instruction='自动扩容但不能超过总上限',total_tokens=10000000,requests=5000,concurrency=2,automatic_phase_reallocation=True)),encoding='utf-8')
    s=tmp_path/'allocation.json';s.write_text(json.dumps(dict(stability=1,adjustments=[])),encoding='utf-8')
    return AuthorizedBudget(tmp_path/'ledger.sqlite3',authorization=a,allocation=s)


def test_phase_may_expand_without_resetting_or_increasing_total(tmp_path):
    b=setup(tmp_path);i=b.reserve('stability','first',dict(messages=[],max_tokens=10));b.finish(i,SimpleNamespace(total_tokens=5))
    assert b.stability==100000 and b.summary()['tokens_charged_or_reserved']==5
    assert b.total==10000000 and b.requests==5000


def test_global_limit_stops_without_phase_expansion(tmp_path):
    b=setup(tmp_path)
    with b.connect() as conn:conn.execute("INSERT INTO attempts(phase,job,reserved,charged,state,created) VALUES('stability','old',9999999,9999999,'completed',0)")
    with pytest.raises(BudgetStop):b.reserve('stability','next',dict(messages=[],max_tokens=10))
    assert b.summary()['requests']==1 and b.stability==1


def test_concurrency_limit_cannot_trigger_phase_expansion(tmp_path):
    b=setup(tmp_path)
    b.reserve('stability','one',dict(messages=[],max_tokens=10));b.reserve('stability','two',dict(messages=[],max_tokens=10))
    cap=b.stability
    with pytest.raises(BudgetStop,match='concurrency'):b.reserve('stability','three',dict(messages=[],max_tokens=10))
    assert b.stability==cap


def test_request_limit_blocks_even_when_tokens_remain(tmp_path):
    b=setup(tmp_path)
    with b.connect() as conn:
        conn.executemany("INSERT INTO attempts(phase,job,reserved,charged,state,created) VALUES('metadata',?,1,1,'completed',0)",
            [('old-'+str(i),) for i in range(5000)])
    with pytest.raises(BudgetStop):b.reserve('stability','next',dict(messages=[],max_tokens=10))
    assert b.summary()['requests']==5000 and b.stability==1


def test_unknown_usage_keeps_reservation_and_later_phase_expansion_keeps_history(tmp_path):
    b=setup(tmp_path);options=dict(messages=[],max_tokens=10)
    first=b.reserve('stability','timeout',options)
    reserved=b.summary()['tokens_charged_or_reserved']
    b.finish(first,error='timeout')
    assert b.summary()['tokens_charged_or_reserved']==reserved
    b.stability=1
    second=b.reserve('stability','new-independent-job',options)
    assert second!=first and b.summary()['requests']==2
    assert b.summary()['tokens_charged_or_reserved']==2*reserved
