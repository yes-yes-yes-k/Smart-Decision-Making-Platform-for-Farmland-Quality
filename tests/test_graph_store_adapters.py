import json
from pathlib import Path
import re
from sqlalchemy import text

from framework.knowledge_graph.age_migration import (
    audit_checksum,
    canonical_audit_snapshot,
    migrate_reviewed_graph,
    snapshot_counts,
)
from framework.knowledge_graph.backup import build_restore_manifest, verify_restored_store
from framework.knowledge_graph.backup import (
    GraphBackupError,
    restore_postgres_age_backup,
)
from framework.knowledge_graph.contracts import GraphQuery
from framework.knowledge_graph.dual_read import compare_graph_stores
from framework.knowledge_graph.stores import AgeGraphStore, JsonGraphStore


ROOT = Path(__file__).resolve().parents[1]


def _graph():
    return {
        "schema_version": "minimal-cultivated-land-kg-v0.4",
        "release": {"release_id": "release-1"},
        "entities": [
            {"id": "measure:liming", "type": "measure", "name": "施用石灰"},
            {"id": "obstacle:acidification", "type": "obstacle", "name": "土壤酸化"},
            {"id": "indicator:soil_ph", "type": "indicator", "name": "土壤pH"},
        ],
        "relations": [
            {
                "id": "rel:1", "type": "addresses",
                "source": "measure:liming", "target": "obstacle:acidification",
                "evidence": [{
                    "evidence_id": "evidence:1", "document_id": 7,
                    "document_key": "document:7", "page": 2, "chunk_index": 1,
                    "quote": "施用石灰可治理土壤酸化。", "quote_sha256": "a" * 64,
                }],
            },
            {
                "id": "rel:2", "type": "characterized_by",
                "source": "obstacle:acidification", "target": "indicator:soil_ph",
                "evidence": [{
                    "evidence_id": "evidence:2", "document_id": 8,
                    "document_key": "document:8", "page": 4, "chunk_index": 3,
                    "quote": "土壤酸化由土壤pH表征。", "quote_sha256": "b" * 64,
                }],
            },
        ],
        "validation": {"passed": True},
    }


class MemoryAgeExecutor:
    """Interprets adapter operations while preserving AGE persistence semantics."""

    def __init__(self, *, postgres=160005, age="1.6.0"):
        self.postgres = postgres
        self.age = age
        self.graph_exists = False
        self.active = None
        self.releases = {}
        self.entities = {}
        self.relations = {}
        self.indexes = set()
        self.calls = []

    def _params(self, parameters):
        return json.loads((parameters or {}).get("cypher_params") or "{}")

    @staticmethod
    def _active(properties, sequence):
        return (
            int(properties["valid_from_sequence"]) <= sequence
            and (
                properties.get("valid_to_sequence") is None
                or int(properties["valid_to_sequence"]) > sequence
            )
        )

    def execute(self, statement, parameters=None):
        self.calls.append((statement, dict(parameters or {})))
        params = self._params(parameters)
        if "age.health" in statement:
            return [{
                "server_version_num": self.postgres,
                "age_version": self.age,
                "graph_exists": self.graph_exists,
            }]
        if "age.ensure_graph" in statement:
            self.graph_exists = True
            return []
        if "age.ensure_labels" in statement:
            return []
        if "age.ensure_indexes" in statement:
            match = re.search(r"EXISTS\s+(\w+)", statement)
            assert match
            self.indexes.add(match.group(1))
            return []
        if "age.index_health" in statement:
            return [{"indexname": name} for name in sorted(self.indexes)]
        if "age.entity_lookup_plan" in statement:
            return [{"QUERY PLAN": [{"Plan": {"Node Type": "Bitmap Index Scan"}}]}]
        if "age.active_release" in statement:
            return [{"active_release": self.active}] if self.active else []
        if "age.activate_release" in statement:
            release = self.releases.get(params["release_id"])
            if not release or not release["validated"]:
                return []
            self.active = params["release_id"]
            return [{"active_release": self.active}]
        if "age.upsert_release" in statement:
            self.releases[params["release_id"]] = dict(params["properties"])
            return [{"release_id": params["release_id"]}]
        if "age.upsert_entity" in statement:
            props = dict(params["properties"])
            self.entities[props["entity_version_key"]] = props
            return [{"entity_id": props["entity_id"]}]
        if "age.upsert_relation" in statement:
            props = dict(params["properties"])
            source = [
                item for item in self.entities.values()
                if item["entity_id"] == params["source_id"]
                and self._active(item, int(params["valid_from_sequence"]))
            ]
            target = [
                item for item in self.entities.values()
                if item["entity_id"] == params["target_id"]
                and self._active(item, int(params["valid_from_sequence"]))
            ]
            if not source or not target:
                return []
            props["_source_version_key"] = source[-1]["entity_version_key"]
            props["_target_version_key"] = target[-1]["entity_version_key"]
            self.relations[props["relation_version_key"]] = props
            return [{"relation_key": props["relation_key"]}]
        if "age.release_sequence" in statement:
            release = self.releases.get(params["release_id"])
            return [{"sequence": release["sequence"]}] if release else []
        if "age.count_entities" in statement:
            sequence = int(params["release_sequence"])
            return [{"item_count": sum(
                self._active(item, sequence) for item in self.entities.values()
            )}]
        if "age.count_relations" in statement:
            sequence = int(params["release_sequence"])
            active = [
                item for item in self.relations.values() if self._active(item, sequence)
            ]
            return [{
                "item_count": len(active),
                "evidence_count": sum(int(item.get("evidence_count") or 0) for item in active),
            }]
        if "age.export_release" in statement:
            release = self.releases.get(params["release_id"])
            return [{"release": release}] if release else []
        if "age.export_entities" in statement:
            sequence = int(params["release_sequence"])
            rows = [
                {"payload": json.dumps(item["payload_json"], ensure_ascii=False)}
                for item in self.entities.values() if self._active(item, sequence)
            ]
            return sorted(rows, key=lambda row: row["payload"])
        if "age.export_relations" in statement:
            sequence = int(params["release_sequence"])
            rows = [
                {
                    "payload": json.dumps(item["payload_json"], ensure_ascii=False),
                    "evidence": json.dumps(item["evidence_refs_json"], ensure_ascii=False),
                }
                for item in self.relations.values() if self._active(item, sequence)
            ]
            return sorted(rows, key=lambda row: row["payload"])
        if "age.neighbors" in statement:
            return self._neighbors(statement, params)
        raise AssertionError(f"unhandled AGE statement: {statement}")

    def _neighbors(self, statement, params):
        sequence = int(params["release_sequence"])
        max_hops = int(re.search(r"\*1\.\.(\d+)", statement).group(1))
        allowed = set(params["relation_types"])
        active_relations = [
            item for item in self.relations.values()
            if self._active(item, sequence)
            and (not allowed or item["relation_type"] in allowed)
        ]
        distance = {item: 0 for item in params["entity_ids"]}
        selected = set()
        frontier = list(distance)
        while frontier:
            entity_id = frontier.pop(0)
            if distance[entity_id] >= max_hops:
                continue
            for relation in active_relations:
                endpoints = (relation["source_entity_id"], relation["target_entity_id"])
                if entity_id not in endpoints:
                    continue
                selected.add(relation["relation_version_key"])
                other = endpoints[1] if endpoints[0] == entity_id else endpoints[0]
                if other not in distance:
                    distance[other] = distance[entity_id] + 1
                    frontier.append(other)
        limit = int(re.search(r"LIMIT (\d+)", statement).group(1))
        rows = []
        for key in sorted(selected):
            relation = self.relations[key]
            source = self.entities[relation["_source_version_key"]]
            target = self.entities[relation["_target_version_key"]]
            rows.append({"source": source, "relation": relation, "target": target})
        return rows[:limit]


def _migrated_store():
    executor = MemoryAgeExecutor()
    store = AgeGraphStore(executor)
    migrate_reviewed_graph(
        _graph(), store, release_id="release-1", release_sequence=1, activate=True,
    )
    return store, executor


def test_json_graph_store_locks_v04_counts_and_bounded_behavior():
    store = JsonGraphStore(
        ROOT / "artifacts/minimal_kg/cultivated_land_minimal_graph_v0.4.json"
    )
    health = store.health()
    assert (health["entity_count"], health["relation_count"], health["evidence_count"]) == (
        38, 66, 94,
    )
    result = store.neighbors(GraphQuery(
        ("measure:deep_loosening",), max_hops=1, top_k=2,
    ))
    assert len(result.relations) <= 2
    assert all("quote" not in item for item in result.evidence_references)
    assert all(item["relation_id"] for item in result.evidence_references)


def test_age_health_fails_closed_on_postgres_or_extension_version_mismatch():
    wrong_postgres = AgeGraphStore(MemoryAgeExecutor(postgres=150009)).health()
    wrong_age = AgeGraphStore(MemoryAgeExecutor(age="1.5.0")).health()
    assert "postgres_major_mismatch" in wrong_postgres["errors"]
    assert "age_version_mismatch" in wrong_age["errors"]
    assert not wrong_postgres["ready"] and not wrong_age["ready"]


def test_age_schema_installs_required_indexes_and_exposes_lookup_plan():
    executor = MemoryAgeExecutor()
    store = AgeGraphStore(executor)
    store.ensure_graph()

    indexes = store.ensure_schema_indexes()
    plan = store.entity_lookup_plan("measure:liming")

    assert set(indexes) == {
        "kg_entity_properties_gin", "kg_relation_properties_gin",
        "kg_release_properties_gin", "kg_control_properties_gin",
    }
    assert plan["uses_index"] is True
    assert plan["full_graph_scan"] is False


def test_v04_migration_is_idempotent_and_reverse_export_checksum_matches():
    store, executor = _migrated_store()
    second = migrate_reviewed_graph(
        _graph(), store, release_id="release-1", release_sequence=1, activate=True,
    )
    exported = store.export_snapshot("release-1")

    assert second.verified and second.activated
    assert len(executor.entities) == 3
    assert len(executor.relations) == 2
    assert snapshot_counts(exported) == {
        "entity_count": 3, "relation_count": 2, "evidence_count": 2,
    }
    assert audit_checksum(exported) == audit_checksum(_graph())
    assert store.health()["ready"] is True
    assert store.release_counts("release-1") == {
        "entity_count": 3, "relation_count": 2, "evidence_count": 2,
    }


def test_age_neighbors_enforces_hops_top_k_timeout_and_evidence_references_only():
    store, executor = _migrated_store()
    result = store.neighbors(GraphQuery(
        ("measure:liming",), max_hops=2, top_k=1, timeout_ms=73,
    ))
    statement, parameters = next(
        call for call in reversed(executor.calls) if "age.neighbors" in call[0]
    )
    assert "*1..2" in statement and "LIMIT 2" in statement
    assert parameters["_statement_timeout_ms"] == 73
    assert set(text(statement).compile().params) == {"graph_name", "cypher_params"}
    assert len(result.relations) == 1
    assert result.truncated is True
    assert "quote" not in result.evidence_references[0]


def test_dual_read_must_be_exact_and_healthy_before_primary_promotion():
    store, executor = _migrated_store()
    json_store = JsonGraphStore(_graph())
    queries = (
        GraphQuery(("measure:liming",), max_hops=2, top_k=10),
        GraphQuery(("indicator:soil_ph",), relation_types=("characterized_by",), top_k=10),
    )
    passed = compare_graph_stores(json_store, store, queries)
    assert passed["eligible_for_primary"] is True
    executor.relations.pop(next(iter(executor.relations)))
    blocked = compare_graph_stores(json_store, store, queries)
    assert blocked["eligible_for_primary"] is False
    assert blocked["match_ratio"] < 1.0


def test_backup_manifest_verifies_dump_release_counts_and_graph_checksum(tmp_path):
    store, _ = _migrated_store()
    dump = tmp_path / "knowledge.dump"
    dump.write_bytes(b"postgres-age-backup")
    manifest = build_restore_manifest(store, dump, database_name="test_restore")
    report = verify_restored_store(store, manifest, dump)
    assert report["passed"] is True
    assert manifest["counts"] == {
        "entity_count": 3, "relation_count": 2, "evidence_count": 2,
    }
    dump.write_bytes(b"tampered")
    assert verify_restored_store(store, manifest, dump)["issues"] == [
        "dump_checksum_mismatch",
    ]


def test_versioned_upserts_keep_prior_release_intervals():
    store, executor = _migrated_store()
    previous = dict(_graph()["entities"][0])
    store.upsert_entity(
        previous, valid_from_release="release-1", valid_from_sequence=1,
        valid_to_release="release-2", valid_to_sequence=2,
    )
    updated = {**previous, "name": "石灰调酸"}
    store.upsert_entity(
        updated, valid_from_release="release-2", valid_from_sequence=2,
    )
    assert set(executor.entities) >= {"measure:liming|1", "measure:liming|2"}
    assert executor.entities["measure:liming|1"]["valid_to_sequence"] == 2
    assert executor.entities["measure:liming|2"]["name"] == "石灰调酸"


def test_real_v04_migrates_with_exact_counts_and_representative_dual_reads():
    graph = json.loads((
        ROOT / "artifacts/minimal_kg/cultivated_land_minimal_graph_v0.4.json"
    ).read_text(encoding="utf-8"))
    executor = MemoryAgeExecutor()
    store = AgeGraphStore(executor)
    report = migrate_reviewed_graph(
        graph, store, release_id="kg-v0.4-production-candidate-1",
        release_sequence=1, activate=True,
    )
    repeated = migrate_reviewed_graph(
        graph, store, release_id="kg-v0.4-production-candidate-1",
        release_sequence=1, activate=True,
    )
    assert (report.entity_count, report.relation_count, report.evidence_count) == (
        38, 66, 94,
    )
    assert repeated.checksum == report.checksum
    assert len(executor.entities) == 38 and len(executor.relations) == 66

    queries = tuple(GraphQuery((entity_id,), max_hops=2, top_k=100) for entity_id in (
        "obstacle:acidification", "measure:deep_loosening",
        "indicator:organic_matter", "standard:doc-4",
    ))
    comparison = compare_graph_stores(JsonGraphStore(graph), store, queries)
    assert comparison["query_count"] == 4
    assert comparison["match_ratio"] == 1.0
    assert comparison["eligible_for_primary"] is True


def test_restore_requires_explicit_apply_and_runs_post_restore_verification(tmp_path):
    store, _ = _migrated_store()
    dump = tmp_path / "knowledge.dump"
    dump.write_bytes(b"postgres-age-backup")
    manifest = build_restore_manifest(store, dump, database_name="isolated_restore")
    calls = []

    class Result:
        returncode = 0
        stderr = ""

    def runner(command, **_kwargs):
        calls.append(command)
        return Result()

    try:
        restore_postgres_age_backup(
            dsn="postgresql://restore-only", dump_path=dump, manifest=manifest,
            restored_store=store, apply=False, runner=runner,
        )
    except GraphBackupError as exc:
        assert "apply=True" in str(exc)
    else:
        raise AssertionError("restore unexpectedly ran without explicit apply")
    report = restore_postgres_age_backup(
        dsn="postgresql://restore-only", dump_path=dump, manifest=manifest,
        restored_store=store, apply=True, runner=runner,
    )
    assert report["passed"] is True
    assert "--single-transaction" in calls[0]
    assert "--clean" in calls[0]


def test_migration_accepts_current_schema_version():
    from framework.knowledge_graph.age_migration import validate_reviewed_graph
    from framework.knowledge_graph.schema import load_graph_schema
    graph = _graph()
    graph["schema_version"] = load_graph_schema().schema_version
    validate_reviewed_graph(graph)


def test_dedicated_age_engine_reads_separate_database(tmp_path):
    from sqlalchemy import create_engine
    from framework.knowledge_graph.stores import age_engine_for_config
    business = create_engine(f"sqlite:///{tmp_path / 'business.db'}")
    dedicated = age_engine_for_config({"KG_AGE_DATABASE_URI": f"sqlite:///{tmp_path / 'age.db'}"}, business)
    try:
        with business.begin() as connection:
            connection.execute(text("CREATE TABLE probe (value TEXT)"))
            connection.execute(text("INSERT INTO probe VALUES ('business')"))
        with dedicated.begin() as connection:
            connection.execute(text("CREATE TABLE probe (value TEXT)"))
            connection.execute(text("INSERT INTO probe VALUES ('age')"))
        with dedicated.connect() as connection:
            assert connection.execute(text("SELECT value FROM probe")).scalar() == "age"
        assert age_engine_for_config({}, business) is business
    finally:
        dedicated.dispose()
        business.dispose()


def test_real_age_roundtrip_and_release_history():
    """Opt-in integration test: exercise the real AGE parser and persistence."""
    import os
    import uuid
    import pytest
    from sqlalchemy import create_engine
    from framework.knowledge_graph.stores import SqlAlchemyAgeExecutor
    uri = os.environ.get("KG_TEST_AGE_URI")
    if not uri:
        pytest.skip("KG_TEST_AGE_URI is required for real AGE integration")
    engine = create_engine(uri)
    graph_name = "kg_test_" + uuid.uuid4().hex[:16]
    store = AgeGraphStore(SqlAlchemyAgeExecutor(engine), graph_name=graph_name)
    graph = _graph()
    try:
        first = migrate_reviewed_graph(graph, store, release_id="release-1", release_sequence=1, activate=True)
        repeated = migrate_reviewed_graph(graph, store, release_id="release-1", release_sequence=1)
        assert first.checksum == repeated.checksum
        assert compare_graph_stores(JsonGraphStore(graph), store, [GraphQuery(("measure:liming",), max_hops=2, top_k=100)])["passed"]
        key = "addresses|measure:liming|obstacle:acidification"
        store.close_relation(key, valid_to_release="release-2", valid_to_sequence=2)
        relation = dict(graph["relations"][0])
        references = [dict(item) for item in relation["evidence"]]
        references.append({"evidence_id": "evidence:new", "document_id": 7, "page": 3, "quote_sha256": "c" * 64})
        store.upsert_relation(relation, evidence_references=references, valid_from_release="release-2", valid_from_sequence=2)
        store.upsert_release(release_id="release-2", sequence=2, schema_version=graph["schema_version"], checksum="d" * 64, entity_count=3, relation_count=2, evidence_count=3, validated=True)
        store.activate_release("release-2")
        assert snapshot_counts(store.export_snapshot("release-1"))["evidence_count"] == 2
        assert snapshot_counts(store.export_snapshot("release-2"))["evidence_count"] == 3
        assert store.health()["ready"]
    finally:
        with engine.begin() as connection:
            connection.exec_driver_sql("LOAD 'age'")
            connection.execute(text("SELECT ag_catalog.drop_graph(:name, true)"), {"name": graph_name})
        engine.dispose()
