from __future__ import annotations

import json
from pathlib import Path

from framework.knowledge_graph.adapter_gate import evaluate_adapter_policy


ROOT = Path(__file__).resolve().parents[1]


def _policy():
    return json.loads((
        ROOT / "governance" / "knowledge-platform" / "adapter-policy-v1.json"
    ).read_text(encoding="utf-8"))


def _evaluation(name, version):
    return {
        "status": "completed",
        "evaluation_mode": "live_backend_predictions",
        "backend": {"name": name, "version": version},
        "metrics": {
            "entities": {"precision": 0.95},
            "relations": {"precision": 0.94},
            "evidence_location": {"recall": 0.93},
        },
    }


def _conformance(name, version):
    return {"backend_name": name, "backend_version": version, "passed": True}


def test_pending_checked_in_policy_cannot_enable_production():
    result = evaluate_adapter_policy(_policy(), [], [])

    assert result["production_ready"] is False
    assert result["selected"] == {"primary": None, "fallback": None}
    assert "policy_not_approved" in result["blockers"]
    assert any("live_gold_evaluation_required" in item for item in result["blockers"])


def test_exact_live_reports_conformance_and_approval_select_both_roles():
    policy = _policy()
    policy["status"] = "approved"
    for candidate in policy["candidates"]:
        candidate["approved"] = True
    evaluations = [_evaluation(item["name"], item["version"]) for item in policy["candidates"]]
    conformances = [_conformance(item["name"], item["version"]) for item in policy["candidates"]]

    result = evaluate_adapter_policy(policy, evaluations, conformances)

    assert result["production_ready"] is True
    assert result["selected"] == {
        "primary": "microsoft-graphrag@3.3.0",
        "fallback": "openspg-kag@0.8.0",
    }


def test_fixture_replay_or_wrong_version_cannot_satisfy_live_gate():
    policy = _policy()
    policy["status"] = "approved"
    policy["candidates"][0]["approved"] = True
    report = _evaluation("microsoft-graphrag", "3.3.0")
    report["evaluation_mode"] = "gold_fixture_replay"

    result = evaluate_adapter_policy(
        policy, [report], [_conformance("microsoft-graphrag", "3.2.0")],
    )

    first = result["decisions"][0]
    assert "live_prediction_provenance_required" in first["blockers"]
    assert "conformance_required" in first["blockers"]
