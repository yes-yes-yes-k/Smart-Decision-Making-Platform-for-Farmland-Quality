"""Production controls shared by graph-assisted RAG paths.

The module is intentionally dependency-light so health checks and rollout
decisions still work when Chroma or the external model provider is unavailable.
"""
from __future__ import annotations

from collections import Counter, deque
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from threading import Lock
from typing import Any, Mapping, Sequence


ROLLOUT_MODES = {"off", "shadow", "canary", "enabled"}


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def stable_evidence_id(reference: Mapping[str, Any]) -> str:
    """Return a stable identifier independent from Chroma chunk UUIDs."""
    canonical = "|".join((
        str(reference.get("document_id") or ""),
        str(reference.get("document_title") or ""),
        str(reference.get("page") if reference.get("page") is not None else ""),
        " ".join(str(reference.get("quote") or "").split()),
    ))
    return "evidence:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24]


def stable_document_key(title: str) -> str:
    """Content-catalog key that survives database ID changes and re-ingestion."""
    name = Path(str(title or "")).stem.lower()
    normalized = "".join(character for character in name if character.isalnum())
    return "document:" + hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:24]


def rewrite_query_for_retrieval(
    query: str, conversation_history: Sequence[Mapping[str, Any]] | None,
) -> str:
    """Resolve short/pronominal follow-ups without another external LLM call."""
    compact = "".join((query or "").split())
    if not conversation_history or not compact:
        return query
    reference_terms = ("它", "这个", "该指标", "上述", "前者", "后者", "那", "呢", "这种")
    needs_context = len(compact) <= 14 or any(term in compact for term in reference_terms)
    if not needs_context:
        return query
    previous_user = next((
        str(item.get("content") or "").strip()
        for item in reversed(conversation_history)
        if item.get("role") == "user" and str(item.get("content") or "").strip()
    ), "")
    if not previous_user or previous_user == query.strip():
        return query
    intent_hint = ""
    if any(term in compact for term in ("哪一类", "什么类别", "属于哪类")):
        intent_hint = "\n检索意图：判断基础性指标或区域补充性指标。"
    elif any(term in compact for term in ("现场", "实验室", "怎么取值", "怎么赋值")):
        intent_hint = "\n检索意图：判断依据现场踏勘或土壤样品检测结果赋值。"
    return f"上一轮问题：{previous_user}\n当前追问：{query.strip()}{intent_hint}"


def rollout_decision(
    *, mode: str, user_id: int | None, conversation_id: int | None,
    query: str, canary_percent: int, canary_user_ids: Sequence[int] = (),
) -> dict[str, Any]:
    normalized = mode if mode in ROLLOUT_MODES else "off"
    if normalized == "off":
        return {"mode": normalized, "active": False, "shadow": False, "bucket": None, "reason": "disabled"}
    if normalized == "shadow":
        return {"mode": normalized, "active": False, "shadow": True, "bucket": None, "reason": "shadow_only"}
    if normalized == "enabled":
        return {"mode": normalized, "active": True, "shadow": False, "bucket": 0, "reason": "fully_enabled"}
    if user_id is not None and int(user_id) in {int(value) for value in canary_user_ids}:
        return {"mode": normalized, "active": True, "shadow": False, "bucket": 0, "reason": "allowlisted_user"}
    key = f"{user_id or 'anonymous'}|{conversation_id or 'none'}|{query}".encode("utf-8")
    bucket = int(hashlib.sha256(key).hexdigest()[:8], 16) % 100
    active = bucket < max(0, min(100, int(canary_percent)))
    return {
        "mode": normalized, "active": active, "shadow": not active,
        "bucket": bucket, "reason": "percentage_bucket",
    }


def inspect_graph_release(
    graph_path: str | Path, *, manifest_path: str | Path | None = None,
    expected_sha256: str | None = None,
) -> dict[str, Any]:
    path = Path(graph_path)
    result: dict[str, Any] = {
        "ready": False, "graph_path": str(path), "manifest_path": None,
        "schema_version": None, "release_id": None, "sha256": None,
        "errors": [],
    }
    if not path.is_file():
        result["errors"].append("graph_file_missing")
        return result
    try:
        actual_hash = sha256_file(path)
        graph = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        result["errors"].append("graph_file_invalid")
        return result
    result.update({
        "schema_version": graph.get("schema_version"),
        "sha256": actual_hash,
        "entity_count": len(graph.get("entities") or []),
        "relation_count": len(graph.get("relations") or []),
        "evidence_count": sum(len(row.get("evidence") or []) for row in graph.get("relations") or []),
    })
    manifest: dict[str, Any] = {}
    manifest_file = Path(manifest_path) if manifest_path else path.with_suffix(".manifest.json")
    result["manifest_path"] = str(manifest_file)
    if manifest_file.is_file():
        try:
            manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
            result["release_id"] = manifest.get("release_id")
            if manifest.get("sha256") and manifest["sha256"] != actual_hash:
                result["errors"].append("manifest_checksum_mismatch")
            if manifest.get("schema_version") != graph.get("schema_version"):
                result["errors"].append("manifest_schema_mismatch")
        except (OSError, ValueError, TypeError):
            result["errors"].append("manifest_invalid")
    else:
        result["errors"].append("manifest_missing")
    if expected_sha256 and expected_sha256 != actual_hash:
        result["errors"].append("expected_checksum_mismatch")
    if not graph.get("validation", {}).get("passed", True):
        result["errors"].append("graph_validation_failed")
    result["ready"] = not result["errors"]
    return result


class KGMetrics:
    """Small in-process telemetry buffer; safe for multi-threaded Flask workers."""

    def __init__(self, max_events: int = 200):
        self._lock = Lock()
        self._counts: Counter[str] = Counter()
        self._latency_total_ms = 0.0
        self._events: deque[dict[str, Any]] = deque(maxlen=max_events)

    def record(self, event: Mapping[str, Any]) -> None:
        row = dict(event)
        row.setdefault("recorded_at", datetime.now(timezone.utc).isoformat())
        with self._lock:
            self._counts["requests"] += 1
            self._counts[f"mode_{row.get('mode', 'unknown')}"] += 1
            self._counts["active"] += int(bool(row.get("active")))
            self._counts["shadow"] += int(bool(row.get("shadow")))
            self._counts["matched"] += int(bool(row.get("matched")))
            self._counts["graph_result_requests"] += int(bool(row.get("graph_result_count")))
            self._counts["errors"] += int(bool(row.get("error")))
            self._latency_total_ms += float(row.get("latency_ms") or 0.0)
            self._events.append(row)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            requests = self._counts.get("requests", 0)
            return {
                "counts": dict(self._counts),
                "average_latency_ms": round(self._latency_total_ms / requests, 3) if requests else 0.0,
                "recent_events": list(self._events),
            }

    def reset(self) -> None:
        with self._lock:
            self._counts.clear()
            self._latency_total_ms = 0.0
            self._events.clear()


kg_metrics = KGMetrics()
