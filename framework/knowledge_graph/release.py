"""Versioned, reproducible knowledge-graph artifact publication."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

from framework.rag.kg_runtime import sha256_file, stable_document_key, stable_evidence_id


def prepare_graph_release(
    graph: dict[str, Any], *, release_id: str, reviewed_by: str,
) -> dict[str, Any]:
    prepared = json.loads(json.dumps(graph, ensure_ascii=False))
    relations = prepared.get("relations") or []
    if not prepared.get("schema_version") or not relations:
        raise ValueError("graph schema_version and relations are required")
    if not prepared.get("validation", {}).get("passed", True):
        raise ValueError("graph validation must pass before release")
    for relation in relations:
        evidence_rows = relation.get("evidence") or []
        if not evidence_rows:
            raise ValueError(f"relation without evidence: {relation.get('id')}")
        for evidence in evidence_rows:
            quote = " ".join(str(evidence.get("quote") or "").split())
            evidence["evidence_id"] = evidence.get("evidence_id") or stable_evidence_id(evidence)
            evidence["document_key"] = evidence.get("document_key") or stable_document_key(
                str(evidence.get("document_title") or "")
            )
            evidence["quote_sha256"] = hashlib.sha256(quote.encode("utf-8")).hexdigest()
    prepared["release"] = {
        "release_id": release_id,
        "reviewed_by": reviewed_by,
        "released_at": datetime.now(timezone.utc).isoformat(),
        "rollback_schema_version": prepared.get("lineage", {}).get("base_schema_version"),
    }
    return prepared


def publish_graph_release(
    graph_path: str | Path, *, output_path: str | Path | None = None,
    manifest_path: str | Path | None = None, release_id: str,
    reviewed_by: str,
) -> dict[str, Any]:
    source = Path(graph_path)
    output = Path(output_path) if output_path else source
    manifest = Path(manifest_path) if manifest_path else output.with_suffix(".manifest.json")
    graph = json.loads(source.read_text(encoding="utf-8"))
    prepared = prepare_graph_release(
        graph, release_id=release_id, reviewed_by=reviewed_by,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(
        json.dumps(prepared, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    temporary.replace(output)
    checksum = sha256_file(output)
    relation_count = len(prepared.get("relations") or [])
    evidence_count = sum(len(row.get("evidence") or []) for row in prepared.get("relations") or [])
    payload = {
        "manifest_schema_version": "knowledge-graph-release-manifest-v1",
        "release_id": release_id,
        "schema_version": prepared["schema_version"],
        "sha256": checksum,
        "artifact": output.name,
        "entity_count": len(prepared.get("entities") or []),
        "relation_count": relation_count,
        "evidence_count": evidence_count,
        "reviewed_by": reviewed_by,
        "released_at": prepared["release"]["released_at"],
        "rollback": {
            "schema_version": prepared["release"].get("rollback_schema_version"),
            "procedure": "set KG_GRAPH_PATH/KG_MANIFEST_PATH to the previous release or set KG_ROLLOUT_MODE=off",
        },
    }
    manifest.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload
