import json

import pytest

from framework.knowledge_graph.synthetic import (
    MARKER, SyntheticScale, cleanup_synthetic_dataset, generate_synthetic_dataset,
)


def test_synthetic_dataset_is_namespaced_deterministic_and_fully_cleanable(tmp_path):
    report = generate_synthetic_dataset(
        tmp_path, namespace="synthetic-test-v1",
        scale=SyntheticScale(documents=3, entities=4, evidence=7, jobs=2),
    )
    target = tmp_path / "synthetic-test-v1"
    assert report["synthetic_only"] is True
    assert report["counts"] == {
        "documents": 3, "entities": 4, "relations": 4,
        "evidence": 7, "jobs": 2,
    }
    assert (target / MARKER).is_file()
    rows = [json.loads(line) for line in (target / "entities.jsonl").read_text().splitlines()]
    assert all(row["id"].startswith("synthetic-test-v1:") for row in rows)
    relations = [
        json.loads(line) for line in (target / "relations.jsonl").read_text().splitlines()
    ]
    entity_types = {row["id"]: row["type"] for row in rows}
    assert all(
        (relation["type"], entity_types[relation["source"]], entity_types[relation["target"]])
        in {
            ("addresses", "measure", "obstacle"),
            ("improves_indicator", "measure", "indicator"),
            ("characterized_by", "obstacle", "indicator"),
            ("includes_indicator", "standard", "indicator"),
        }
        for relation in relations
    )
    evidence = [
        json.loads(line) for line in (target / "evidence.jsonl").read_text().splitlines()
    ]
    assert {row["relation_id"] for row in evidence} <= {row["id"] for row in relations}
    assert all(row["span_end"] > row["span_start"] for row in evidence)
    assert all(
        row["quote_sha256"] == __import__("hashlib").sha256(row["quote"].encode()).hexdigest()
        for row in evidence
    )
    assert cleanup_synthetic_dataset(tmp_path, namespace="synthetic-test-v1") is True
    assert not target.exists()


def test_cleanup_refuses_unmarked_or_unsafe_targets(tmp_path):
    unmarked = tmp_path / "synthetic-unmarked"
    unmarked.mkdir()
    with pytest.raises(ValueError, match="refusing cleanup"):
        cleanup_synthetic_dataset(tmp_path, namespace="synthetic-unmarked")
    with pytest.raises(ValueError, match="namespace"):
        generate_synthetic_dataset(
            tmp_path, namespace="production", scale=SyntheticScale(1, 1, 1, 1),
        )
