import json
import pytest
from framework.knowledge_graph.benchmark_budget_policy_v2 import AuthorizedBudgetV2
from framework.knowledge_graph.acceptance_budget import BudgetStop


def budget(tmp_path):
    a=tmp_path/'auth.json';a.write_text(json.dumps(dict(approved_by='user',explicit_instruction='提高总上限至 2000 万 token',
        total_tokens=20000000,requests=5000,concurrency=2,historical_usage_retained=True,automatic_phase_reallocation=True)),encoding='utf-8')
    s=tmp_path/'allocation.json';s.write_text(json.dumps(dict(stability=1,adjustments=[])),encoding='utf-8')
    return AuthorizedBudgetV2(tmp_path/'ledger.sqlite3',authorization=a,allocation=s)


def test_original_history_is_retained_and_new_cap_is_hard(tmp_path):
    b=budget(tmp_path)
    with b.connect() as c:c.execute("INSERT INTO attempts(phase,job,reserved,charged,state,created) VALUES('old','history',19999999,19999999,'completed',0)")
    with pytest.raises(BudgetStop):b.reserve('stability','next',dict(messages=[],max_tokens=1))
    assert b.summary()['tokens_charged_or_reserved']==19999999 and b.summary()['requests']==1
    assert b.stability==1


def test_stage_growth_cannot_change_global_cap_or_concurrency(tmp_path):
    b=budget(tmp_path)
    b.reserve('stability','a',dict(messages=[],max_tokens=1));b.reserve('stability','b',dict(messages=[],max_tokens=1))
    with pytest.raises(BudgetStop,match='concurrency'):b.reserve('stability','c',dict(messages=[],max_tokens=1))
    assert b.total==20000000 and b.requests==5000 and b.stability==100000


def test_request_cap_still_stops_with_token_balance(tmp_path):
    b=budget(tmp_path)
    with b.connect() as c:c.executemany("INSERT INTO attempts(phase,job,reserved,charged,state,created) VALUES('old',?,1,1,'completed',0)",[(str(i),) for i in range(5000)])
    with pytest.raises(BudgetStop):b.reserve('reference_test','next',dict(messages=[],max_tokens=1))
