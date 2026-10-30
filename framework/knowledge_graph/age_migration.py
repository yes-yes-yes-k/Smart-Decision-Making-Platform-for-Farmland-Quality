"""Validated, idempotent migration of reviewed JSON releases into Apache AGE."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .contracts import stable_digest
from .schema import GraphSchema, load_graph_schema
from .stores import AgeGraphStore, _evidence_reference


class GraphMigrationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class GraphMigrationReport:
    release_id: str
    checksum: str
    entity_count: int
    relation_count: int
    evidence_count: int
    activated: bool
    verified: bool


def validate_reviewed_graph(
    graph: Mapping[str, Any], schema: GraphSchema | None = None,
) -> None:
    schema = schema or load_graph_schema()
    graph_version = str(graph.get("schema_version") or "")
    if graph_version not in schema.compatible_graph_versions:
        raise GraphMigrationError(f"graph version is not compatible: {graph_version}")
    entities = list(graph.get("entities") or [])
    relations = list(graph.get("relations") or [])
    if not entities or not relations:
        raise GraphMigrationError("reviewed graph requires entities and relations")
    entity_index: dict[str, Mapping[str, Any]] = {}
    for entity in entities:
        entity_id = str(entity.get("id") or "")
        entity_type = str(entity.get("type") or "")
        if not entity_id or entity_id in entity_index:
            raise GraphMigrationError("entity ids must be present and unique")
        if entity_type not in schema.entity_type_ids:
            raise GraphMigrationError(f"unknown entity type: {entity_type}")
        if not entity_id.startswith(f"{entity_type}:"):
            raise GraphMigrationError(f"entity id namespace mismatch: {entity_id}")
        entity_index[entity_id] = entity
    triples = set()
    for relation in relations:
        triple = (
            str(relation.get("type") or ""), str(relation.get("source") or ""),
            str(relation.get("target") or ""),
        )
        if triple in triples:
            raise GraphMigrationError(f"duplicate relation triple: {triple}")
        triples.add(triple)
        source = entity_index.get(triple[1])
        target = entity_index.get(triple[2])
        if source is None or target is None:
            raise GraphMigrationError(f"relation endpoint is missing: {triple}")
        if not schema.allows(triple[0], str(source["type"]), str(target["type"])):
            raise GraphMigrationError(f"relation direction is invalid: {triple}")
        evidence = relation.get("evidence") or []
        if not evidence:
            raise GraphMigrationError(f"relation has no evidence: {triple}")
        for reference in evidence:
            if not reference.get("evidence_id") or reference.get("page") is None:
                raise GraphMigrationError("evidence id and page are required")
            if not reference.get("quote_sha256"):
                raise GraphMigrationError("evidence quote hash is required")


def canonical_audit_snapshot(graph: Mapping[str, Any]) -> dict[str, Any]:
    """Canonicalize only AGE-owned graph data; raw evidence text remains relational."""
    entities = sorted(
        (dict(item) for item in graph.get("entities") or []),
        key=lambda item: str(item.get("id") or ""),
    )
    relations = []
    for relation in graph.get("relations") or []:
        payload = {key: value for key, value in relation.items() if key != "evidence"}
        relation_id = str(payload.get("id") or "")
        payload["evidence"] = sorted(
            (_evidence_reference(item, relation_id) for item in relation.get("evidence") or []),
            key=lambda item: (
                str(item.get("evidence_id") or ""), int(item.get("document_id") or 0),
                int(item.get("page") or 0), int(item.get("chunk_index") or -1),
            ),
        )
        relations.append(payload)
    relations.sort(key=lambda item: (
        str(item.get("type") or ""), str(item.get("source") or ""),
        str(item.get("target") or ""),
    ))
    return {"entities": entities, "relations": relations}


def audit_checksum(graph: Mapping[str, Any]) -> str:
    return stable_digest(canonical_audit_snapshot(graph))


def snapshot_counts(graph: Mapping[str, Any]) -> dict[str, int]:
    relations = list(graph.get("relations") or [])
    return {
        "entity_count": len(graph.get("entities") or []),
        "relation_count": len(relations),
        "evidence_count": sum(len(item.get("evidence") or []) for item in relations),
    }


def migrate_reviewed_graph(
    graph: Mapping[str, Any],
    store: AgeGraphStore,
    *,
    release_id: str,
    release_sequence: int,
    activate: bool = False,
    schema: GraphSchema | None = None,
) -> GraphMigrationReport:
    """Upsert one release, verify reverse export, then optionally activate it."""
    validate_reviewed_graph(graph, schema)
    expected = canonical_audit_snapshot(graph)
    counts = snapshot_counts(expected)
    checksum = stable_digest(expected)
    store.ensure_graph()
    store.ensure_schema_indexes()
    release_values = {
        "release_id": release_id,
        "sequence": int(release_sequence),
        "schema_version": str(graph["schema_version"]),
        "checksum": checksum,
        **counts,
    }
    store.upsert_release(**release_values, validated=False)
    for entity in expected["entities"]:
        store.upsert_entity(
            entity,
            valid_from_release=release_id,
            valid_from_sequence=release_sequence,
        )
    for relation in expected["relations"]:
        store.upsert_relation(
            relation,
            evidence_references=list(relation.get("evidence") or []),
            valid_from_release=release_id,
            valid_from_sequence=release_sequence,
        )
    exported = store.export_snapshot(release_id)
    observed = canonical_audit_snapshot(exported)
    observed_counts = snapshot_counts(observed)
    if observed_counts != counts:
        raise GraphMigrationError(
            f"AGE count verification failed: expected={counts}, observed={observed_counts}"
        )
    if stable_digest(observed) != checksum:
        raise GraphMigrationError("AGE reverse-export checksum verification failed")
    store.upsert_release(**release_values, validated=True)
    if activate:
        store.activate_release(release_id)
    return GraphMigrationReport(
        release_id=release_id,
        checksum=checksum,
        entity_count=counts["entity_count"],
        relation_count=counts["relation_count"],
        evidence_count=counts["evidence_count"],
        activated=activate,
        verified=True,
    )
