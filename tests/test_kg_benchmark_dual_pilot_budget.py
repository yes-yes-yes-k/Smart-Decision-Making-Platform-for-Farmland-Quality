import json
from types import SimpleNamespace
import pytest
import scripts.pilot_kg_benchmark_dual_selector as pilot
from framework.knowledge_graph.acceptance_budget import BudgetStop


def create(tmp_path):
    auth=tmp_path/'auth.json';auth.write_text(json.dumps(dict(approved_by='user',
        explicit_instruction='提高总上限至 2000 万 token',total_tokens=20000000,requests=5000,
        concurrency=2,historical_usage_retained=True,automatic_phase_reallocation=True)),encoding='utf-8')
    alloc=tmp_path/'allocation.json';alloc.write_text(json.dumps(dict(stability=2200000,adjustments=[])),encoding='utf-8')
    return pilot.PilotBudget(tmp_path/'ledger.sqlite3',authorization=auth,allocation=alloc)


def test_pilot_cap_is_atomic_and_does_not_grant_extra_global_budget(tmp_path,monkeypatch):
    budget=create(tmp_path);options=dict(messages=[],max_tokens=1)
    size=len(json.dumps(options,ensure_ascii=False).encode())+1025
    monkeypatch.setattr(pilot,'PHASE_CAP',size+10)
    attempt=budget.reserve(pilot.PHASE,'one',options)
    budget.finish(attempt,SimpleNamespace(total_tokens=size))
    with pytest.raises(BudgetStop,match='bounded_semantic_pilot_cap'):
        budget.reserve(pilot.PHASE,'two',options)
    assert budget.summary()['requests']==1 and budget.total==20000000


def test_pilot_cannot_bypass_global_cap_with_a_new_phase(tmp_path):
    budget=create(tmp_path)
    with budget.connect() as c:
        c.execute("INSERT INTO attempts(phase,job,reserved,charged,state,created) VALUES('old','history',20000000,20000000,'completed',0)")
    with pytest.raises(BudgetStop,match='request_or_token_budget'):
        budget.reserve(pilot.PHASE,'new',dict(messages=[],max_tokens=1))
    assert budget.summary()['requests']==1
