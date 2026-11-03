"""Deterministic, namespace-isolated synthetic capacity dataset generation."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import shutil
from typing import Iterator


MARKER = ".knowledge-platform-synthetic.json"
ENTITY_TYPES = ("measure", "obstacle", "indicator", "standard")
RELATION_PATTERNS = (
    ("addresses", "measure", "obstacle"),
    ("improves_indicator", "measure", "indicator"),
    ("characterized_by", "obstacle", "indicator"),
    ("includes_indicator", "standard", "indicator"),
    ("prescribes_measurement", "standard", "indicator"),
    ("assessment_basis", "standard", "obstacle"),
    ("classifies_basic_indicator", "standard", "indicator"),
    ("classifies_regional_supplementary_indicator", "standard", "indicator"),
    ("assigns_by_field_survey", "standard", "indicator"),
    ("assigns_by_laboratory_test", "standard", "indicator"),
)


@dataclass(frozen=True, slots=True)
class SyntheticScale:
    documents: int
    entities: int
    evidence: int
    jobs: int

    def __post_init__(self):
        if min(self.documents, self.entities, self.evidence, self.jobs) < 0:
            raise ValueError("synthetic counts cannot be negative")


def _safe_namespace(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if not normalized.startswith("synthetic-") or not all(
        char.isalnum() or char in "-_" for char in normalized
    ):
        raise ValueError("namespace must start with synthetic- and use safe characters")
    return normalized


def _write_jsonl(path: Path, rows: Iterator[dict]) -> int:
    count = 0
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
            count += 1
    return count


def _type_count(entity_count: int, entity_type: str) -> int:
    offset = ENTITY_TYPES.index(entity_type)
    return max(0, (entity_count - offset + len(ENTITY_TYPES) - 1) // len(ENTITY_TYPES))


def _entity_index(entity_count: int, entity_type: str, ordinal: int) -> int:
    count = _type_count(entity_count, entity_type)
    if count <= 0:
        raise ValueError(f"synthetic entity distribution has no {entity_type}")
    return ENTITY_TYPES.index(entity_type) + len(ENTITY_TYPES) * (ordinal % count)


def _document_sha(prefix: str, index: int) -> str:
    return hashlib.sha256(f"{prefix}document:{index}".encode()).hexdigest()


def _synthetic_relation_row(
    prefix: str, entity_count: int, index: int,
    patterns: tuple[tuple[str, str, str], ...],
) -> dict:
    pattern = patterns[index % len(patterns)]
    ordinal = index // len(patterns)
    target_count = _type_count(entity_count, pattern[2])
    source_index = _entity_index(entity_count, pattern[1], ordinal // target_count)
    target_index = _entity_index(entity_count, pattern[2], ordinal % target_count)
    return {
        "id": f"{prefix}relation:{index}", "synthetic": True,
        "type": pattern[0],
        "source": f"{prefix}entity:{source_index}",
        "target": f"{prefix}entity:{target_index}",
    }


def generate_synthetic_dataset(
    output_root: str | Path, *, namespace: str, scale: SyntheticScale,
) -> dict:
    namespace = _safe_namespace(namespace)
    available_patterns = tuple(
        pattern for pattern in RELATION_PATTERNS
        if _type_count(scale.entities, pattern[1])
        and _type_count(scale.entities, pattern[2])
    )
    if scale.evidence and scale.documents <= 0:
        raise ValueError("synthetic evidence requires at least one document")
    if scale.evidence and not available_patterns:
        raise ValueError("synthetic evidence requires entities with a valid relation direction")
    round_robin_capacity = min(
        _type_count(scale.entities, pattern[1]) * _type_count(scale.entities, pattern[2])
        for pattern in available_patterns
    ) * len(available_patterns) if available_patterns else 0
    relation_count = min(scale.entities, scale.evidence, round_robin_capacity)
    root = Path(output_root).resolve()
    target = (root / namespace).resolve()
    if target.parent != root or target == root:
        raise ValueError("synthetic target must be a direct child of output_root")
    if target.exists():
        raise FileExistsError(f"synthetic namespace already exists: {namespace}")
    target.mkdir(parents=True)
    marker = {
        "schema": "knowledge-platform-synthetic-marker-v1",
        "namespace": namespace, "synthetic_only": True,
    }
    (target / MARKER).write_text(
        json.dumps(marker, sort_keys=True) + "\n", encoding="utf-8",
    )
    prefix = f"{namespace}:"
    counts = {}
    counts["documents"] = _write_jsonl(target / "documents.jsonl", (
        {
            "id": f"{prefix}document:{index}", "synthetic": True,
            "content_sha256": _document_sha(prefix, index),
        }
        for index in range(scale.documents)
    ))
    counts["entities"] = _write_jsonl(target / "entities.jsonl", (
        {
            "id": f"{prefix}entity:{index}", "synthetic": True,
            "type": ENTITY_TYPES[index % len(ENTITY_TYPES)],
            "name": f"Synthetic entity {index}",
        }
        for index in range(scale.entities)
    ))
    counts["relations"] = _write_jsonl(target / "relations.jsonl", (
        _synthetic_relation_row(prefix, scale.entities, index, available_patterns)
        for index in range(relation_count)
    ))
    counts["evidence"] = _write_jsonl(target / "evidence.jsonl", (
        _synthetic_evidence_row(prefix, scale, relation_count, index)
        for index in range(scale.evidence)
    ))
    counts["jobs"] = _write_jsonl(target / "jobs.jsonl", (
        {
            "job_id": f"{prefix}job:{index}", "synthetic": True,
            "document_index": index % max(1, scale.documents), "state": "pending",
        }
        for index in range(scale.jobs)
    ))
    manifest = {
        **marker, "counts": counts,
        "files": [
            "documents.jsonl", "entities.jsonl", "relations.jsonl",
            "evidence.jsonl", "jobs.jsonl",
        ],
    }
    (target / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8",
    )
    return {**manifest, "path": str(target)}


def _synthetic_evidence_row(
    prefix: str, scale: SyntheticScale, relation_count: int, index: int,
) -> dict:
    if relation_count <= 0:
        raise ValueError("evidence generation requires at least one valid relation")
    document_index = index % max(1, scale.documents)
    # Relation-major ordering lets a capacity loader group evidence while
    # reading one line at a time instead of retaining the full 1m rows.
    relation_index = min(
        relation_count - 1,
        (index * relation_count) // max(1, scale.evidence),
    )
    quote = f"Synthetic evidence {index} for relation {relation_index}."
    return {
        "evidence_id": f"{prefix}evidence:{index}",
        "synthetic": True,
        "document_id": document_index + 1,
        "document_key": f"{prefix}document:{document_index}",
        "content_sha256": _document_sha(prefix, document_index),
        "relation_id": f"{prefix}relation:{relation_index}",
        "relation_index": relation_index,
        "chunk_index": index % 20,
        "page": index % 100 + 1,
        "span_start": 0,
        "span_end": len(quote),
        "quote": quote,
        "quote_sha256": hashlib.sha256(quote.encode()).hexdigest(),
    }


def cleanup_synthetic_dataset(output_root: str | Path, *, namespace: str) -> bool:
    namespace = _safe_namespace(namespace)
    root = Path(output_root).resolve()
    target = (root / namespace).resolve()
    if target.parent != root or not target.is_dir():
        return False
    marker_path = target / MARKER
    try:
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise ValueError("refusing cleanup without a valid synthetic marker")
    if marker.get("namespace") != namespace or marker.get("synthetic_only") is not True:
        raise ValueError("refusing cleanup of an unverified directory")
    shutil.rmtree(target)
    return True
