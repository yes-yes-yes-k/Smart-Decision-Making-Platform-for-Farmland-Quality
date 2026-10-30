import json
from pathlib import Path

import pytest

from scripts.evaluate_kg_extraction_backend import evaluate_rows, read_jsonl


ROOT = Path(__file__).resolve().parents[1]
GOLD = ROOT / "artifacts" / "minimal_kg" / "extraction_gold_v1.jsonl"


def test_self_evaluation_produces_perfect_versioned_metrics():
    rows = read_jsonl(GOLD)

    report = evaluate_rows(
        rows,
        rows,
        backend_name="deterministic-fixture",
        backend_version="1.0.0",
        elapsed_seconds=2.0,
        input_documents=4,
        cost_usd=0.0,
        cost_source="offline fixture",
        evaluation_mode="gold_fixture_replay",
    )

    assert report["status"] == "completed"
    assert report["evaluation_mode"] == "gold_fixture_replay"
    assert report["metrics"]["entities"]["f1"] == 1.0
    assert report["metrics"]["relations"]["f1"] == 1.0
    assert report["metrics"]["evidence_location"]["f1"] == 1.0
    assert report["metrics"]["evidence_location"]["expected"] == 94
    assert report["performance"]["documents_per_second"] == 2.0
    assert len(report["prediction_sha256"]) == 64


def test_evaluator_counts_wrong_direction_and_missing_evidence():
    gold = read_jsonl(GOLD)[:2]
    predictions = json.loads(json.dumps(gold, ensure_ascii=False))
    predictions[0]["relation"]["source"], predictions[0]["relation"]["target"] = (
        predictions[0]["relation"]["target"],
        predictions[0]["relation"]["source"],
    )
    predictions.pop()

    report = evaluate_rows(
        gold,
        predictions,
        backend_name="candidate",
        backend_version="1.2.3",
        elapsed_seconds=1.0,
        input_documents=1,
        cost_usd=0.01,
        cost_source="provider usage API",
        evaluation_mode="live_backend_predictions",
    )

    assert report["metrics"]["relations"]["true_positive"] == 0
    assert report["metrics"]["evidence_location"]["recall"] == 0.0


def test_evaluator_requires_exact_version_and_cost_provenance():
    with pytest.raises(ValueError, match="exact version"):
        evaluate_rows(
            [], [], backend_name="x", backend_version="latest",
            elapsed_seconds=1, input_documents=1, cost_usd=0, cost_source="offline",
            evaluation_mode="gold_fixture_replay",
        )
    with pytest.raises(ValueError, match="source"):
        evaluate_rows(
            [], [], backend_name="x", backend_version="1.0",
            elapsed_seconds=1, input_documents=1, cost_usd=0, cost_source="",
            evaluation_mode="gold_fixture_replay",
        )


def test_evaluator_requires_prediction_provenance_mode():
    with pytest.raises(ValueError, match="evaluation_mode"):
        evaluate_rows(
            [], [], backend_name="x", backend_version="1.0",
            elapsed_seconds=1, input_documents=1, cost_usd=0,
            cost_source="offline", evaluation_mode="unknown",
        )
