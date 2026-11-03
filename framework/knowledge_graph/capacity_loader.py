"""Streaming loader for namespace-isolated synthetic AGE capacity datasets."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from itertools import groupby
import json
from pathlib import Path
from time import perf_counter
from typing import Any, Iterator, Mapping

from .contracts import stable_digest
from .schema import load_graph_schema
from .stores import AgeGraphStore, _evidence_reference
from .synthetic import MARKER


class SyntheticLoadError(ValueError):
    pass


def _rows(path: Path, hasher: Any) -> Iterator[dict[str, Any]]:
    with path.open("rb") as handle:
        for line_number, raw in enumerate(handle, 1):
            hasher.update(raw)
            if not raw.strip():
                continue
            try:
                row = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise SyntheticLoadError(f"invalid JSONL at {path.name}:{line_number}") from exc
            if not isinstance(row, dict):
                raise SyntheticLoadError(f"JSON object required at {path.name}:{line_number}")
            yield row


def _scan_synthetic(path: Path, hasher: Any) -> int:
    count = 0
    for row in _rows(path, hasher):
        if row.get("synthetic") is not True:
            raise SyntheticLoadError(f"non-synthetic row in {path.name}")
        count += 1
    return count


def _validate_evidence(row: Mapping[str, Any], relation_id: str, documents: int) -> None:
    if row.get("synthetic") is not True or row.get("relation_id") != relation_id:
        raise SyntheticLoadError("evidence namespace or relation identity mismatch")
    document_id = row.get("document_id")
    if not isinstance(document_id, int) or isinstance(document_id, bool) or not 1 <= document_id <= documents:
        raise SyntheticLoadError("evidence document is outside the generated dataset")
    quote = str(row.get("quote") or "")
    start, end = row.get("span_start"), row.get("span_end")
    if start != 0 or end != len(quote) or not quote:
        raise SyntheticLoadError("evidence span is invalid")
    if hashlib.sha256(quote.encode()).hexdigest() != row.get("quote_sha256"):
        raise SyntheticLoadError("evidence quote hash is invalid")


def load_synthetic_dataset(
    dataset_root: str | Path,
    store: AgeGraphStore,
    *,
    release_id: str,
    release_sequence: int,
    activate: bool = False,
    rollback_release_id: str | None = None,
) -> dict[str, Any]:
    """Load entities/relations with bounded evidence memory and verify AGE counts."""
    root = Path(dataset_root).resolve()
    marker_path = root / MARKER
    manifest_path = root / "manifest.json"
    try:
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SyntheticLoadError("valid synthetic marker and manifest are required") from exc
    if marker.get("synthetic_only") is not True or manifest.get("synthetic_only") is not True:
        raise SyntheticLoadError("refusing to load a non-synthetic dataset")
    if marker.get("namespace") != manifest.get("namespace") or root.name != marker.get("namespace"):
        raise SyntheticLoadError("synthetic namespace does not match its directory")
    if not release_id.startswith("synthetic-"):
        raise SyntheticLoadError("synthetic release_id must start with synthetic-")
    if rollback_release_id is not None and (
        not rollback_release_id.startswith("synthetic-")
        or rollback_release_id == release_id
    ):
        raise SyntheticLoadError("rollback_release_id must be a distinct synthetic release")
    if release_sequence <= 0:
        raise SyntheticLoadError("release_sequence must be positive")

    expected = dict(manifest.get("counts") or {})
    hashers = {
        name: hashlib.sha256() for name in (
            "documents", "entities", "relations", "evidence", "jobs",
        )
    }
    started_at = datetime.now(timezone.utc)
    started = perf_counter()
    store.ensure_graph()
    indexes = store.ensure_schema_indexes()

    document_count = _scan_synthetic(root / "documents.jsonl", hashers["documents"])
    job_count = _scan_synthetic(root / "jobs.jsonl", hashers["jobs"])
    entity_types: dict[str, str] = {}
    entity_count = 0
    for entity in _rows(root / "entities.jsonl", hashers["entities"]):
        if entity.get("synthetic") is not True:
            raise SyntheticLoadError("non-synthetic entity row")
        entity_id = str(entity.get("id") or "")
        entity_type = str(entity.get("type") or "")
        if not entity_id.startswith(f"{marker['namespace']}:") or entity_id in entity_types:
            raise SyntheticLoadError("entity identity is invalid or duplicated")
        entity_types[entity_id] = entity_type
        store.upsert_entity(
            entity, valid_from_release=release_id,
            valid_from_sequence=release_sequence,
        )
        entity_count += 1

    evidence_rows = _rows(root / "evidence.jsonl", hashers["evidence"])
    evidence_groups = groupby(evidence_rows, key=lambda row: str(row.get("relation_id") or ""))
    current_group = next(evidence_groups, None)
    schema = load_graph_schema()
    relation_count = 0
    evidence_count = 0
    peak_relation_evidence = 0
    seen_relations: set[str] = set()
    for relation in _rows(root / "relations.jsonl", hashers["relations"]):
        relation_id = str(relation.get("id") or "")
        if relation.get("synthetic") is not True or relation_id in seen_relations:
            raise SyntheticLoadError("relation identity is invalid or duplicated")
        seen_relations.add(relation_id)
        source_type = entity_types.get(str(relation.get("source") or ""))
        target_type = entity_types.get(str(relation.get("target") or ""))
        if source_type is None or target_type is None or not schema.allows(
            str(relation.get("type") or ""), source_type, target_type,
        ):
            raise SyntheticLoadError("relation endpoints or direction are invalid")
        if current_group is None or current_group[0] != relation_id:
            raise SyntheticLoadError("relations and grouped evidence are not aligned")
        grouped = []
        for evidence in current_group[1]:
            _validate_evidence(evidence, relation_id, document_count)
            grouped.append(_evidence_reference(evidence, relation_id))
        current_group = next(evidence_groups, None)
        peak_relation_evidence = max(peak_relation_evidence, len(grouped))
        evidence_count += len(grouped)
        store.upsert_relation(
            relation, evidence_references=grouped,
            valid_from_release=release_id,
            valid_from_sequence=release_sequence,
        )
        relation_count += 1
    if current_group is not None:
        raise SyntheticLoadError("evidence references an unknown or out-of-order relation")

    actual = {
        "documents": document_count,
        "entities": entity_count,
        "relations": relation_count,
        "evidence": evidence_count,
        "jobs": job_count,
    }
    if actual != expected:
        raise SyntheticLoadError(f"dataset count mismatch: expected={expected}, actual={actual}")
    file_sha256 = {name: hasher.hexdigest() for name, hasher in hashers.items()}
    checksum = stable_digest(file_sha256)
    age_expected = {
        "entity_count": entity_count,
        "relation_count": relation_count,
        "evidence_count": evidence_count,
    }
    store.upsert_release(
        release_id=release_id, sequence=release_sequence,
        schema_version=schema.schema_version, checksum=checksum,
        **age_expected, validated=False,
    )
    observed = store.release_counts(release_id)
    if observed != age_expected:
        raise SyntheticLoadError(
            f"AGE count verification failed: expected={age_expected}, observed={observed}"
        )
    store.upsert_release(
        release_id=release_id, sequence=release_sequence,
        schema_version=schema.schema_version, checksum=checksum,
        **age_expected, validated=True,
    )
    if rollback_release_id:
        # An alias release points at the exact same immutable sequence.  It is
        # sufficient for measuring control-plane activation/rollback without
        # duplicating 100k entity and relation versions.
        store.upsert_release(
            release_id=rollback_release_id, sequence=release_sequence,
            schema_version=schema.schema_version, checksum=checksum,
            **age_expected, validated=True,
        )
    if activate:
        store.activate_release(rollback_release_id or release_id)
    elapsed = perf_counter() - started
    finished_at = datetime.now(timezone.utc)
    return {
        "schema": "knowledge-platform-synthetic-age-load-v1",
        "status": "completed",
        "synthetic_only": True,
        "namespace": marker["namespace"],
        "release_id": release_id,
        "release_sequence": release_sequence,
        "activated": activate,
        "activated_release": (rollback_release_id or release_id) if activate else None,
        "rollback_release_id": rollback_release_id,
        "counts": actual,
        "age_counts": observed,
        "dataset_checksum": checksum,
        "file_sha256": file_sha256,
        "indexes": list(indexes),
        "peak_relation_evidence_in_memory": peak_relation_evidence,
        "elapsed_seconds": elapsed,
        "entities_per_second": entity_count / elapsed if elapsed else None,
        "relations_per_second": relation_count / elapsed if elapsed else None,
        "evidence_per_second": evidence_count / elapsed if elapsed else None,
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
    }
