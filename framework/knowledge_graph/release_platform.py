"""Append-only graph releases, validation gates, rollback and audit exports."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import time
from typing import Any, Mapping

from sqlalchemy import func

from framework.models.knowledge_graph import (
    KnowledgeGraphAuditExport,
    KnowledgeGraphCandidateEvidence,
    KnowledgeGraphClaimCandidate,
    KnowledgeGraphControl,
    KnowledgeGraphEntityCandidate,
    KnowledgeGraphOutboxEvent,
    KnowledgeGraphRelationCandidate,
    KnowledgeGraphRelease,
    KnowledgeGraphReleaseChange,
    KnowledgeGraphRollbackAudit,
)

from .contracts import GraphQuery
from .contracts import stable_digest
from .schema import GraphSchema, load_graph_schema
from .stores import JsonGraphStore, _evidence_reference


def utcnow_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class ReleaseError(ValueError):
    def __init__(self, code: str, message: str, status_code: int = 409):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


@dataclass(frozen=True, slots=True)
class ReleasePreview:
    parent_release_id: str | None
    schema_version: str
    graph: Mapping[str, Any]
    changes: tuple[Mapping[str, Any], ...]
    diff_summary: Mapping[str, int]
    change_checksum: str
    validation_report: Mapping[str, Any]

    def to_dict(self, *, include_graph: bool = False) -> dict[str, Any]:
        payload = {
            "parent_release_id": self.parent_release_id,
            "schema_version": self.schema_version,
            "changes": [dict(item) for item in self.changes],
            "diff_summary": dict(self.diff_summary),
            "change_checksum": self.change_checksum,
            "validation_report": dict(self.validation_report),
        }
        if include_graph:
            payload["graph"] = dict(self.graph)
        return payload


class KnowledgeGraphReleaseService:
    """Build and activate releases from explicitly approved relational candidates."""

    def __init__(self, session, graph_store, *, schema: GraphSchema | None = None):
        self.session = session
        self.graph_store = graph_store
        self.schema = schema or load_graph_schema()

    def _control(self) -> KnowledgeGraphControl:
        row = self.session.get(KnowledgeGraphControl, "active")
        if row is None:
            row = KnowledgeGraphControl(control_id="active")
            self.session.add(row)
            self.session.flush()
        if not row.active_release_id:
            active = getattr(self.graph_store, "active_release", lambda: None)()
            if active:
                row.active_release_id = str(active)
                export = getattr(self.graph_store, "export_snapshot", None)
                if callable(export):
                    try:
                        snapshot = export(str(active))
                        row.active_sequence_no = int(
                            (snapshot.get("release") or {}).get("sequence") or 0
                        ) or None
                    except (TypeError, ValueError, KeyError):
                        pass
        return row

    def _current_snapshot(self, active_release: str | None) -> dict[str, Any]:
        if not active_release:
            return {
                "schema_version": self.schema.schema_version,
                "entities": [], "relations": [],
            }
        export = getattr(self.graph_store, "export_snapshot", None)
        if not callable(export):
            raise ReleaseError(
                "active_snapshot_unavailable",
                "当前图存储不能导出活动版本，无法计算追加差异",
                503,
            )
        try:
            snapshot = dict(export(active_release))
        except Exception as exc:
            raise ReleaseError(
                "active_snapshot_unavailable", "无法读取当前活动图谱版本", 503,
            ) from exc
        return snapshot

    @staticmethod
    def _relation_key(row: Mapping[str, Any]) -> str:
        return "|".join((
            str(row.get("type") or ""), str(row.get("source") or ""),
            str(row.get("target") or ""),
        ))

    def preview(self) -> ReleasePreview:
        control = self._control()
        parent = control.active_release_id
        current = self._current_snapshot(parent)
        compatible_versions = {
            self.schema.schema_version, *self.schema.compatible_graph_versions,
        }
        if current.get("schema_version") not in {None, *compatible_versions}:
            raise ReleaseError("schema_incompatible", "活动版本与当前 schema 不兼容")

        entities = {
            str(item["id"]): dict(item) for item in current.get("entities") or []
        }
        current_entity_ids = set(entities)
        for row in KnowledgeGraphEntityCandidate.query.filter_by(
            review_status="approved",
        ).order_by(KnowledgeGraphEntityCandidate.id).all():
            if not row.canonical_entity_id or not row.canonical_name:
                continue
            entities[row.canonical_entity_id] = {
                "id": row.canonical_entity_id,
                "type": row.entity_type,
                "name": row.canonical_name,
                "candidate_id": row.id,
            }

        inactive_evidence_ids = {
            str(value) for (value,) in self.session.query(
                KnowledgeGraphCandidateEvidence.evidence_key,
            ).filter_by(is_active=False).all()
        }
        relations = {}
        current_evidence: dict[str, set[str]] = {}
        for item in current.get("relations") or []:
            relation = dict(item)
            key = self._relation_key(relation)
            original_refs = list(relation.get("evidence") or [])
            relation["evidence"] = [
                value for value in original_refs
                if str(value.get("evidence_id") or value.get("evidence_key") or "")
                not in inactive_evidence_ids
            ]
            relations[key] = relation
            current_evidence[key] = {
                str(value.get("evidence_id") or value.get("evidence_key") or "")
                for value in original_refs
            }

        approved_relation_rows = KnowledgeGraphRelationCandidate.query.filter_by(
            review_status="approved",
        ).order_by(KnowledgeGraphRelationCandidate.id).all()
        candidate_relation_keys: dict[str, int] = {}
        for row in approved_relation_rows:
            key = "|".join((
                row.relation_type, str(row.canonical_source_id or ""),
                str(row.canonical_target_id or ""),
            ))
            evidence_rows = KnowledgeGraphCandidateEvidence.query.filter_by(
                relation_candidate_id=row.id, review_status="approved", is_active=True,
            ).order_by(KnowledgeGraphCandidateEvidence.id).all()
            refs = []
            for evidence in evidence_rows:
                source = {
                    "evidence_id": evidence.evidence_key,
                    "document_id": evidence.document_id,
                    "content_sha256": evidence.content_sha256,
                    "chunk_index": evidence.chunk_index,
                    "page": evidence.page,
                    "span_start": evidence.span_start,
                    "span_end": evidence.span_end,
                    "quote_sha256": evidence.quote_sha256,
                }
                refs.append(_evidence_reference(source, key))
            existing = relations.get(key, {})
            merged_evidence = {
                str(item.get("evidence_id")): dict(item)
                for item in existing.get("evidence") or []
            }
            merged_evidence.update({str(item["evidence_id"]): item for item in refs})
            relations[key] = {
                "id": str(existing.get("id") or key),
                "type": row.relation_type,
                "source": row.canonical_source_id,
                "target": row.canonical_target_id,
                "candidate_id": row.id,
                "evidence": [merged_evidence[item] for item in sorted(merged_evidence)],
            }
            candidate_relation_keys[key] = row.id

        graph = {
            "schema_version": self.schema.schema_version,
            "release": {"release_id": "preview"},
            "entities": [entities[key] for key in sorted(entities)],
            "relations": [relations[key] for key in sorted(relations)],
        }
        changes: list[dict[str, Any]] = []
        for entity_id in sorted(set(entities) - current_entity_ids):
            changes.append({
                "change_type": "add_entity", "subject_type": "entity",
                "subject_key": entity_id, "payload": entities[entity_id],
            })
        current_relation_keys = {
            self._relation_key(item) for item in current.get("relations") or []
        }
        for key in sorted(relations):
            if key not in current_relation_keys:
                changes.append({
                    "change_type": "add_relation", "subject_type": "relation",
                    "subject_key": key, "payload": relations[key],
                })
                continue
            new_refs = [
                item for item in relations[key].get("evidence") or []
                if str(item.get("evidence_id") or "") not in current_evidence.get(key, set())
            ]
            for evidence in new_refs:
                changes.append({
                    "change_type": "append_evidence", "subject_type": "evidence",
                    "subject_key": str(evidence.get("evidence_id")),
                    "payload": {"relation_key": key, "evidence": evidence},
                })
            removed_refs = current_evidence.get(key, set()) - {
                str(item.get("evidence_id") or item.get("evidence_key") or "")
                for item in relations[key].get("evidence") or []
            }
            for evidence_id in sorted(removed_refs):
                changes.append({
                    "change_type": "remove_evidence", "subject_type": "evidence",
                    "subject_key": evidence_id,
                    "payload": {"relation_key": key, "evidence_id": evidence_id},
                })

        for row in KnowledgeGraphClaimCandidate.query.filter_by(
            review_status="approved",
        ).order_by(KnowledgeGraphClaimCandidate.id).all():
            already = self.session.query(KnowledgeGraphReleaseChange.id).filter_by(
                subject_type="claim", subject_key=f"claim:{row.id}",
            ).first()
            if not already:
                changes.append({
                    "change_type": "add_claim", "subject_type": "claim",
                    "subject_key": f"claim:{row.id}",
                    "payload": {
                        "candidate_id": row.id, "claim_type": row.claim_type,
                        "subject": row.canonical_subject_id,
                        "object": row.canonical_object_id,
                        "statement": row.statement,
                    },
                })

        normalized = tuple(
            {**item, "change_checksum": stable_digest(item)} for item in changes
        )
        checksum = stable_digest(list(normalized))
        validation = self._validate(
            graph, checksum=checksum, changes=normalized,
            candidate_relation_keys=candidate_relation_keys,
        )
        counts: dict[str, int] = {}
        for item in normalized:
            key = str(item["change_type"])
            counts[key] = counts.get(key, 0) + 1
        counts.update({
            "total": len(normalized),
            "entity_count": len(graph["entities"]),
            "relation_count": len(graph["relations"]),
            "evidence_count": sum(
                len(item.get("evidence") or []) for item in graph["relations"]
            ),
        })
        return ReleasePreview(
            parent_release_id=parent, schema_version=self.schema.schema_version,
            graph=graph, changes=normalized, diff_summary=counts,
            change_checksum=checksum, validation_report=validation,
        )

    def _validate(self, graph, *, checksum, changes, candidate_relation_keys):
        gates: dict[str, dict[str, Any]] = {}

        def gate(name, issues):
            values = sorted(set(str(item) for item in issues if item))
            gates[name] = {"passed": not values, "issues": values}

        gate("schema_compatible", [] if graph.get("schema_version") == self.schema.schema_version else ["schema_version"])
        entity_map = {str(item.get("id")): item for item in graph.get("entities") or []}
        relation_keys = []
        endpoint_issues = []
        direction_issues = []
        evidence_issues = []
        duplicate_evidence = []
        connected = set()
        for relation in graph.get("relations") or []:
            key = self._relation_key(relation)
            relation_keys.append(key)
            source = entity_map.get(str(relation.get("source")))
            target = entity_map.get(str(relation.get("target")))
            if not source or not target:
                endpoint_issues.append(key)
                continue
            connected.update((str(relation["source"]), str(relation["target"])))
            if not self.schema.allows(
                str(relation.get("type")), str(source.get("type")), str(target.get("type")),
            ):
                direction_issues.append(key)
            evidence_ids = []
            for evidence in relation.get("evidence") or []:
                evidence_id = str(evidence.get("evidence_id") or "")
                evidence_ids.append(evidence_id)
                required = (
                    "evidence_id", "document_id", "content_sha256", "chunk_index",
                    "page", "span_start", "span_end", "quote_sha256",
                )
                if any(evidence.get(field) in (None, "") for field in required):
                    evidence_issues.append(f"{key}:{evidence_id or 'missing'}")
            if not evidence_ids:
                evidence_issues.append(f"{key}:none")
            if len(evidence_ids) != len(set(evidence_ids)):
                duplicate_evidence.append(key)
        gate("endpoints", endpoint_issues)
        gate("direction", direction_issues)
        gate("valid_evidence", evidence_issues)
        gate("duplicates", (
            (["duplicate_relation"] if len(relation_keys) != len(set(relation_keys)) else [])
            + duplicate_evidence
        ))
        gate("no_orphan_entities", sorted(set(entity_map) - connected))

        review_issues = []
        for key, candidate_id in candidate_relation_keys.items():
            row = self.session.get(KnowledgeGraphRelationCandidate, candidate_id)
            if not row or row.review_status != "approved":
                review_issues.append(key)
            for endpoint_id in (
                getattr(row, "source_candidate_id", None),
                getattr(row, "target_candidate_id", None),
            ):
                endpoint = self.session.get(KnowledgeGraphEntityCandidate, endpoint_id)
                if endpoint is None or endpoint.review_status != "approved":
                    review_issues.append(f"{key}:endpoint")
        gate("review_coverage", review_issues)

        representative_issues = []
        if graph.get("entities") and graph.get("relations"):
            try:
                probe = json.loads(json.dumps(graph, ensure_ascii=False))
                probe["release"] = {"release_id": "validation-preview"}
                store = JsonGraphStore(probe)
                seed = str(probe["relations"][0]["source"])
                store.neighbors(GraphQuery((seed,), max_hops=2, top_k=10))
            except Exception:
                representative_issues.append("representative_query_failed")
        else:
            representative_issues.append("empty_graph")
        gate("representative_queries", representative_issues)
        gate("change_checksum", [] if checksum == stable_digest(list(changes)) else ["checksum_mismatch"])
        issues = [
            f"{name}:{issue}"
            for name, result in gates.items()
            for issue in result["issues"]
        ]
        return {"passed": not issues, "gates": gates, "issues": issues}

    def publish(self, *, release_id: str, created_by: int) -> KnowledgeGraphRelease:
        release_id = str(release_id or "").strip()
        if not release_id or len(release_id) > 128:
            raise ReleaseError("invalid_release_id", "release_id 不能为空且最长 128 字符", 422)
        existing = KnowledgeGraphRelease.query.filter_by(release_id=release_id).one_or_none()
        if existing:
            return existing
        preview = self.preview()
        if not preview.changes:
            raise ReleaseError("empty_release", "没有新的已批准变更")
        if not preview.validation_report.get("passed"):
            raise ReleaseError("release_validation_failed", "发布门禁未全部通过", 422)
        control = self._control()
        sequence = max(int(control.active_sequence_no or 0), int(self.session.query(
            func.coalesce(func.max(KnowledgeGraphRelease.sequence_no), 0),
        ).scalar())) + 1
        release = KnowledgeGraphRelease(
            release_id=release_id, sequence_no=sequence,
            parent_release_id=preview.parent_release_id,
            schema_version=preview.schema_version, state="validated",
            change_checksum=preview.change_checksum,
            diff_summary=dict(preview.diff_summary),
            validation_report=dict(preview.validation_report),
            created_by=created_by, validated_at=utcnow_naive(),
        )
        self.session.add(release)
        for index, item in enumerate(preview.changes, 1):
            previous_changes = KnowledgeGraphReleaseChange.query.filter_by(
                subject_type=item["subject_type"],
                subject_key=item["subject_key"],
                valid_to_release=None,
            ).all()
            for previous in previous_changes:
                previous.valid_to_release = release_id
            self.session.add(KnowledgeGraphReleaseChange(
                release_id=release_id, sequence_no=index,
                change_type=item["change_type"], subject_type=item["subject_type"],
                subject_key=item["subject_key"], change_payload=item["payload"],
                change_checksum=item["change_checksum"],
                valid_from_release=release_id,
            ))
        self.session.flush()
        self._apply_to_store(release, preview)
        control.active_release_id = release_id
        control.active_sequence_no = sequence
        control.updated_by = created_by
        release.state = "published"
        release.published_at = utcnow_naive()
        for format_name in ("json", "parquet"):
            export = KnowledgeGraphAuditExport(
                release_id=release_id, format=format_name, state="pending",
            )
            event_key = f"kg-release-export:{release_id}:{format_name}"
            event = KnowledgeGraphOutboxEvent(
                event_key=event_key,
                event_type="knowledge_graph_release_export_requested",
                aggregate_type="kg_release", aggregate_id=release_id,
                payload={"release_id": release_id, "format": format_name},
                state="pending",
            )
            self.session.add_all([export, event])
        self.session.flush()
        return release

    def _apply_to_store(self, release, preview):
        graph = preview.graph
        required = ("upsert_release", "upsert_entity", "upsert_relation", "activate_release")
        if any(not callable(getattr(self.graph_store, name, None)) for name in required):
            raise ReleaseError("graph_store_read_only", "当前图存储不支持增量发布", 503)
        previous_release = None
        try:
            previous_release = self.graph_store.active_release()
            counts = {
                "entity_count": len(graph.get("entities") or []),
                "relation_count": len(graph.get("relations") or []),
                "evidence_count": sum(
                    len(item.get("evidence") or []) for item in graph.get("relations") or []
                ),
            }
            self.graph_store.upsert_release(
                release_id=release.release_id, sequence=release.sequence_no,
                schema_version=release.schema_version,
                checksum=release.change_checksum, validated=False, **counts,
            )
            entities = {
                str(item.get("id")): item for item in graph.get("entities") or []
            }
            relations = {
                self._relation_key(item): item for item in graph.get("relations") or []
            }
            new_entity_ids = {
                str(item["subject_key"]) for item in preview.changes
                if item["change_type"] == "add_entity"
            }
            added_relation_keys = {
                str(item["subject_key"]) for item in preview.changes
                if item["change_type"] == "add_relation"
            }
            evidence_relation_keys = {
                str(item["payload"]["relation_key"]) for item in preview.changes
                if item["change_type"] in {"append_evidence", "remove_evidence"}
            }
            for entity_id in sorted(new_entity_ids):
                entity = entities[entity_id]
                self.graph_store.upsert_entity(
                    entity, valid_from_release=release.release_id,
                    valid_from_sequence=release.sequence_no,
                )
            close_relation = getattr(self.graph_store, "close_relation", None)
            for relation_key in sorted(evidence_relation_keys - added_relation_keys):
                if not callable(close_relation):
                    raise RuntimeError("graph store cannot version updated relations")
                close_relation(
                    relation_key, valid_to_release=release.release_id,
                    valid_to_sequence=release.sequence_no,
                )
            for relation_key in sorted(added_relation_keys | evidence_relation_keys):
                relation = relations[relation_key]
                self.graph_store.upsert_relation(
                    relation, evidence_references=list(relation.get("evidence") or []),
                    valid_from_release=release.release_id,
                    valid_from_sequence=release.sequence_no,
                )
            self.graph_store.upsert_release(
                release_id=release.release_id, sequence=release.sequence_no,
                schema_version=release.schema_version,
                checksum=release.change_checksum, validated=True, **counts,
            )
            self.graph_store.activate_release(release.release_id)
            health = dict(self.graph_store.health())
            if not health.get("ready") or health.get("active_release") != release.release_id:
                raise RuntimeError("activated store failed health verification")
        except Exception as exc:
            try:
                if previous_release and self.graph_store.active_release() != previous_release:
                    self.graph_store.activate_release(previous_release)
            except Exception:
                pass
            raise ReleaseError(
                "graph_store_activation_failed", "图存储写入或活动版本切换失败", 503,
            ) from exc

    def rollback(
        self, *, target_release_id: str, operator_id: int,
        reason: str, idempotency_key: str,
    ) -> tuple[KnowledgeGraphRollbackAudit, bool]:
        reason = str(reason or "").strip()
        key = str(idempotency_key or "").strip()
        if not reason or not key:
            raise ReleaseError("rollback_metadata_required", "回滚原因和幂等键不能为空", 422)
        if len(reason) > 2000 or len(key) > 128:
            raise ReleaseError("rollback_metadata_invalid", "回滚元数据长度超限", 422)
        replay = KnowledgeGraphRollbackAudit.query.filter_by(
            idempotency_key=key,
        ).one_or_none()
        if replay:
            if replay.target_release_id != target_release_id:
                raise ReleaseError("idempotency_key_conflict", "幂等键已用于其他回滚")
            return replay, True
        target = KnowledgeGraphRelease.query.filter_by(
            release_id=target_release_id,
        ).one_or_none()
        if (
            target is None or target.state not in {"validated", "published", "superseded"}
            or not (target.validation_report or {}).get("passed")
            or target.schema_version not in {
                self.schema.schema_version, *self.schema.compatible_graph_versions,
            }
        ):
            raise ReleaseError("rollback_target_invalid", "目标版本不存在、未验证或不兼容", 422)
        control = self._control()
        source = control.active_release_id
        started = time.monotonic()
        try:
            self.graph_store.activate_release(target.release_id)
            health = dict(self.graph_store.health())
            if not health.get("ready") or health.get("active_release") != target.release_id:
                raise RuntimeError("rollback health verification failed")
        except Exception as exc:
            raise ReleaseError("rollback_activation_failed", "图存储回滚切换失败", 503) from exc
        duration_ms = int((time.monotonic() - started) * 1000)
        control.active_release_id = target.release_id
        control.active_sequence_no = target.sequence_no
        control.updated_by = operator_id
        audit = KnowledgeGraphRollbackAudit(
            idempotency_key=key, source_release_id=source,
            target_release_id=target.release_id, operator_id=operator_id,
            reason=reason, duration_ms=duration_ms,
        )
        self.session.add(audit)
        self.session.flush()
        return audit, False


class ReleaseAuditExporter:
    """Process post-publication export rows; publishing never waits for this worker."""

    def __init__(self, session, graph_store, output_dir: str | Path):
        self.session = session
        self.graph_store = graph_store
        self.output_dir = Path(output_dir)

    def process_pending(self, *, limit: int = 10) -> dict[str, int]:
        rows = KnowledgeGraphAuditExport.query.filter_by(state="pending").order_by(
            KnowledgeGraphAuditExport.id,
        ).limit(max(1, min(int(limit), 100))).all()
        result = {"selected": len(rows), "completed": 0, "failed": 0}
        for row in rows:
            row.state = "running"
            try:
                snapshot = self.graph_store.export_snapshot(row.release_id)
                path = self._write(snapshot, row.release_id, row.format)
                row.artifact_path = str(path)
                row.artifact_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
                row.state = "completed"
                row.completed_at = utcnow_naive()
                event = KnowledgeGraphOutboxEvent.query.filter_by(
                    event_key=f"kg-release-export:{row.release_id}:{row.format}",
                ).one_or_none()
                if event:
                    event.state = "published"
                    event.published_at = row.completed_at
                result["completed"] += 1
            except Exception as exc:
                row.state = "failed"
                row.error_code = (
                    "parquet_dependency_missing"
                    if row.format == "parquet" and isinstance(exc, ImportError)
                    else "audit_export_failed"
                )
                event = KnowledgeGraphOutboxEvent.query.filter_by(
                    event_key=f"kg-release-export:{row.release_id}:{row.format}",
                ).one_or_none()
                if event:
                    event.state = "retry"
                    event.attempt_count += 1
                    event.last_error_code = row.error_code
                result["failed"] += 1
        self.session.flush()
        return result

    def _write(self, snapshot, release_id, format_name) -> Path:
        safe_id = "".join(
            char for char in str(release_id) if char.isalnum() or char in "-_."
        )
        if not safe_id:
            raise ValueError("invalid release id")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        if format_name == "json":
            path = self.output_dir / f"{safe_id}.json"
            temporary = path.with_suffix(".json.tmp")
            temporary.write_text(
                json.dumps(snapshot, ensure_ascii=False, sort_keys=True, indent=2),
                encoding="utf-8",
            )
            temporary.replace(path)
            return path
        if format_name == "parquet":
            try:
                import pandas as pd
            except ImportError as exc:
                raise ImportError("pandas/pyarrow is required for Parquet export") from exc
            rows = [
                {"record_type": "entity", "record_id": item.get("id"),
                 "payload_json": json.dumps(item, ensure_ascii=False, sort_keys=True)}
                for item in snapshot.get("entities") or []
            ] + [
                {"record_type": "relation", "record_id": item.get("id"),
                 "payload_json": json.dumps(item, ensure_ascii=False, sort_keys=True)}
                for item in snapshot.get("relations") or []
            ]
            path = self.output_dir / f"{safe_id}.parquet"
            temporary = path.with_suffix(".parquet.tmp")
            try:
                pd.DataFrame(rows).to_parquet(temporary, index=False)
            except (ImportError, ModuleNotFoundError) as exc:
                raise ImportError("pyarrow is required for Parquet export") from exc
            temporary.replace(path)
            return path
        raise ValueError("unsupported export format")
