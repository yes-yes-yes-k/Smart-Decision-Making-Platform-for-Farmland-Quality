"""Evaluate backend prediction JSONL against the reviewed extraction gold set."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping


def _normalize(value: Any) -> str:
    return " ".join(str(value or "").strip().casefold().split())


def _entity_keys(rows: Iterable[Mapping[str, Any]]) -> set[tuple[str, str]]:
    result = set()
    for row in rows:
        relation = row.get("relation") or {}
        for endpoint in (relation.get("source") or {}, relation.get("target") or {}):
            result.add((_normalize(endpoint.get("type")), _normalize(endpoint.get("name"))))
    return result


def _relation_key(row: Mapping[str, Any]) -> tuple[str, str, str, str, str]:
    relation = row.get("relation") or {}
    source = relation.get("source") or {}
    target = relation.get("target") or {}
    return (
        _normalize(relation.get("type")),
        _normalize(source.get("type")),
        _normalize(source.get("name")),
        _normalize(target.get("type")),
        _normalize(target.get("name")),
    )


def _evidence_key(row: Mapping[str, Any]) -> tuple[Any, ...]:
    evidence = row.get("evidence") or {}
    return _relation_key(row) + (
        int(evidence.get("document_id") or 0),
        int(evidence.get("page") or 0),
        int(evidence.get("chunk_index") or 0),
        str(evidence.get("quote_sha256") or ""),
    )


def _scores(expected: set[Any], predicted: set[Any]) -> dict[str, Any]:
    true_positive = len(expected & predicted)
    precision = true_positive / len(predicted) if predicted else 0.0
    recall = true_positive / len(expected) if expected else 0.0
    f1 = (
        2 * precision * recall / (precision + recall)
        if precision + recall else 0.0
    )
    return {
        "expected": len(expected),
        "predicted": len(predicted),
        "true_positive": true_positive,
        "false_positive": len(predicted - expected),
        "false_negative": len(expected - predicted),
        "precision": round(precision, 6),
        "recall": round(recall, 6),
        "f1": round(f1, 6),
    }


def evaluate_rows(
    gold_rows: list[Mapping[str, Any]],
    predicted_rows: list[Mapping[str, Any]],
    *,
    backend_name: str,
    backend_version: str,
    elapsed_seconds: float,
    input_documents: int,
    cost_usd: float | None,
    cost_source: str,
    evaluation_mode: str,
) -> dict[str, Any]:
    if not backend_name or not backend_version or backend_version.casefold() == "latest":
        raise ValueError("backend name and exact version are required")
    if elapsed_seconds <= 0 or input_documents <= 0:
        raise ValueError("positive elapsed_seconds and input_documents are required")
    if (cost_usd is not None and cost_usd < 0) or not cost_source:
        raise ValueError("non-negative cost_usd and its source are required")
    if evaluation_mode not in {"live_backend_predictions", "gold_fixture_replay"}:
        raise ValueError("evaluation_mode must identify live predictions or fixture replay")
    gold_entities = _entity_keys(gold_rows)
    predicted_entities = _entity_keys(predicted_rows)
    gold_relations = {_relation_key(row) for row in gold_rows}
    predicted_relations = {_relation_key(row) for row in predicted_rows}
    gold_evidence = {_evidence_key(row) for row in gold_rows}
    predicted_evidence = {_evidence_key(row) for row in predicted_rows}
    serialized_predictions = "".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
        for row in predicted_rows
    )
    return {
        "schema": "knowledge-graph-extraction-evaluation-v1",
        "status": "completed",
        "evaluation_mode": evaluation_mode,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "backend": {"name": backend_name, "version": backend_version},
        "metrics": {
            "entities": _scores(gold_entities, predicted_entities),
            "relations": _scores(gold_relations, predicted_relations),
            "evidence_location": _scores(gold_evidence, predicted_evidence),
        },
        "performance": {
            "input_documents": input_documents,
            "prediction_rows": len(predicted_rows),
            "elapsed_seconds": elapsed_seconds,
            "documents_per_second": round(input_documents / elapsed_seconds, 6),
            "evidence_rows_per_second": round(len(predicted_rows) / elapsed_seconds, 6),
        },
        "cost": {"usd": cost_usd, "source": cost_source,
                 "status": "unavailable" if cost_usd is None else "reported"},
        "prediction_sha256": hashlib.sha256(
            serialized_predictions.encode("utf-8")
        ).hexdigest(),
    }


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSONL at {path}:{line_number}") from exc
        if not isinstance(row, dict):
            raise ValueError(f"JSONL row must be an object at {path}:{line_number}")
        rows.append(row)
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gold", type=Path, required=True)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--backend-name", required=True)
    parser.add_argument("--backend-version", required=True)
    parser.add_argument("--elapsed-seconds", required=True, type=float)
    parser.add_argument("--input-documents", required=True, type=int)
    parser.add_argument("--cost-usd", required=True, type=float)
    parser.add_argument("--cost-source", required=True)
    parser.add_argument(
        "--evaluation-mode", required=True,
        choices=("live_backend_predictions", "gold_fixture_replay"),
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = evaluate_rows(
        read_jsonl(args.gold),
        read_jsonl(args.predictions),
        backend_name=args.backend_name,
        backend_version=args.backend_version,
        elapsed_seconds=args.elapsed_seconds,
        input_documents=args.input_documents,
        cost_usd=args.cost_usd,
        cost_source=args.cost_source,
        evaluation_mode=args.evaluation_mode,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
