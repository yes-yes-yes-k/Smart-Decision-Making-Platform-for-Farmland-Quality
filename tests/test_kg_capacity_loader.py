from __future__ import annotations

import json

import pytest

from framework.knowledge_graph.capacity_loader import (
    SyntheticLoadError, load_synthetic_dataset,
)
from framework.knowledge_graph.synthetic import SyntheticScale, generate_synthetic_dataset


class RecordingStore:
    def __init__(self):
        self.entities = {}
        self.relations = {}
        self.releases = []
        self.active = None
        self.indexes = ("kg_entity_properties_gin", "kg_relation_properties_gin")

    def ensure_graph(self):
        pass

    def ensure_schema_indexes(self):
        return self.indexes

    def upsert_entity(self, entity, **_kwargs):
        self.entities[entity["id"]] = dict(entity)

    def upsert_relation(self, relation, *, evidence_references, **_kwargs):
        self.relations[relation["id"]] = (dict(relation), list(evidence_references))

    def upsert_release(self, **kwargs):
        self.releases.append(dict(kwargs))

    def release_counts(self, _release_id):
        return {
            "entity_count": len(self.entities),
            "relation_count": len(self.relations),
            "evidence_count": sum(len(item[1]) for item in self.relations.values()),
        }

    def activate_release(self, release_id):
        assert self.releases[-1]["validated"] is True
        self.active = release_id


def test_streaming_loader_verifies_counts_and_activates_only_validated_release(tmp_path):
    generated = generate_synthetic_dataset(
        tmp_path, namespace="synthetic-loader-v1",
        scale=SyntheticScale(3, 4, 7, 2),
    )
    store = RecordingStore()

    report = load_synthetic_dataset(
        generated["path"], store,
        release_id="synthetic-capacity-release-1", release_sequence=1,
        activate=True, rollback_release_id="synthetic-capacity-release-0",
    )

    assert report["status"] == "completed"
    assert report["counts"] == generated["counts"]
    assert report["age_counts"] == {
        "entity_count": 4, "relation_count": 4, "evidence_count": 7,
    }
    assert report["peak_relation_evidence_in_memory"] == 2
    assert report["indexes"] == list(store.indexes)
    assert store.releases[0]["validated"] is False
    assert store.releases[-1]["validated"] is True
    assert report["rollback_release_id"] == "synthetic-capacity-release-0"
    assert report["activated_release"] == "synthetic-capacity-release-0"
    assert store.active == "synthetic-capacity-release-0"
    assert all(
        "quote" not in reference
        for _, references in store.relations.values()
        for reference in references
    )


def test_loader_rejects_tampered_evidence_before_activation(tmp_path):
    generated = generate_synthetic_dataset(
        tmp_path, namespace="synthetic-loader-tampered",
        scale=SyntheticScale(2, 2, 2, 1),
    )
    evidence_path = tmp_path / "synthetic-loader-tampered" / "evidence.jsonl"
    rows = [json.loads(line) for line in evidence_path.read_text(encoding="utf-8").splitlines()]
    rows[0]["quote_sha256"] = "0" * 64
    evidence_path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8",
    )
    store = RecordingStore()

    with pytest.raises(SyntheticLoadError, match="quote hash"):
        load_synthetic_dataset(
            generated["path"], store,
            release_id="synthetic-capacity-release-2", release_sequence=2,
            activate=True,
        )

    assert store.active is None
    assert store.releases == []
