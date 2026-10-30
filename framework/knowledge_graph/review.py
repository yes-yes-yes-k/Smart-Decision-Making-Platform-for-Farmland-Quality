"""Domain review rules and immutable audit recording for graph candidates."""
from __future__ import annotations

from framework.models.knowledge_graph import (
    KnowledgeGraphCandidateEvidence,
    KnowledgeGraphClaimCandidate,
    KnowledgeGraphClaimEvidence,
    KnowledgeGraphEntityCandidate,
    KnowledgeGraphExtractionJob,
    KnowledgeGraphRelationCandidate,
    KnowledgeGraphReviewDecision,
)

from .schema import GraphSchema, load_graph_schema


class ReviewError(ValueError):
    def __init__(self, code: str, message: str, status_code: int = 409):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code

    def __str__(self) -> str:
        return self.message


class KnowledgeGraphReviewService:
    CANDIDATE_MODELS = {
        "entity": KnowledgeGraphEntityCandidate,
        "relation": KnowledgeGraphRelationCandidate,
        "claim": KnowledgeGraphClaimCandidate,
    }
    EVIDENCE_MODELS = {
        "relation": KnowledgeGraphCandidateEvidence,
        "claim": KnowledgeGraphClaimEvidence,
    }

    def __init__(self, session, schema: GraphSchema | None = None):
        self.session = session
        self.schema = schema or load_graph_schema()

    def resolve_entity(
        self, entity_id: int, *, canonical_id: str, canonical_name: str,
        reason: str, reviewer_id: int, idempotency_key: str,
    ) -> tuple[KnowledgeGraphEntityCandidate, KnowledgeGraphReviewDecision, bool]:
        self._validate_metadata(reason, idempotency_key)
        replay = self._replay(idempotency_key)
        if replay:
            self._validate_replay(replay, "entity_resolution", entity_id, "resolve")
            row = self.session.get(KnowledgeGraphEntityCandidate, entity_id)
            return row, replay, True
        entity = self.session.get(KnowledgeGraphEntityCandidate, entity_id)
        if entity is None:
            raise ReviewError("candidate_not_found", "实体候选不存在", 404)
        if entity.review_status in {"approved", "rejected"}:
            raise ReviewError("review_already_finalized", "实体审核结果已终结")
        canonical_id = str(canonical_id or "").strip()
        canonical_name = str(canonical_name or "").strip()
        if not canonical_id.startswith(f"{entity.entity_type}:") or not canonical_name:
            raise ReviewError(
                "invalid_canonical_entity", "规范 ID 必须使用实体类型命名空间且规范名非空", 422,
            )
        job = self._job_for_candidate(entity)
        before = self._entity_snapshot(entity)
        entity.canonical_entity_id = canonical_id
        entity.canonical_name = canonical_name
        entity.resolution_status = "resolved"
        entity.risk_level = "new_entity" if entity.risk_level == "new_entity" else "resolved_entity"
        entity.review_status = "pending"
        self._refresh_relation_endpoints(entity)
        decision = self._decision(
            subject_type="entity_resolution", subject_id=entity.id,
            decision="resolve", reason=reason, reviewer_id=reviewer_id,
            idempotency_key=idempotency_key, job=job,
            reviewed_value={"before": before, "after": self._entity_snapshot(entity)},
        )
        self.session.flush()
        return entity, decision, False

    def review_candidate(
        self, kind: str, candidate_id: int, *, decision: str, reason: str,
        reviewer_id: int, idempotency_key: str,
    ):
        model = self.CANDIDATE_MODELS.get(kind)
        if model is None:
            raise ReviewError("invalid_candidate_type", "不支持的候选类型", 422)
        replay = self._replay(idempotency_key)
        if replay:
            self._validate_replay(
                replay, f"{kind}_candidate", candidate_id, decision,
            )
            row = self.session.get(model, candidate_id)
            return row, replay, True
        row = self.session.get(model, candidate_id)
        if row is None:
            raise ReviewError("candidate_not_found", "候选不存在", 404)
        self._validate_decision(decision, reason, idempotency_key)
        if row.review_status in {"approved", "rejected"}:
            raise ReviewError("review_already_finalized", "候选审核结果已终结")
        if decision == "approve":
            self._assert_candidate_approvable(kind, row)
        before = self._candidate_snapshot(kind, row)
        row.review_status = "approved" if decision == "approve" else "rejected"
        job = self._job_for_candidate(row)
        audit = self._decision(
            subject_type=f"{kind}_candidate", subject_id=row.id,
            decision=decision, reason=reason, reviewer_id=reviewer_id,
            idempotency_key=idempotency_key, job=job,
            reviewed_value={"before": before, "after": self._candidate_snapshot(kind, row)},
        )
        self.session.flush()
        return row, audit, False

    def review_evidence(
        self, kind: str, evidence_id: int, *, decision: str, reason: str,
        reviewer_id: int, idempotency_key: str,
    ):
        model = self.EVIDENCE_MODELS.get(kind)
        if model is None:
            raise ReviewError("invalid_evidence_type", "不支持的证据类型", 422)
        replay = self._replay(idempotency_key)
        if replay:
            self._validate_replay(
                replay, f"{kind}_evidence", evidence_id, decision,
            )
            row = self.session.get(model, evidence_id)
            return row, replay, True
        row = self.session.get(model, evidence_id)
        if row is None:
            raise ReviewError("evidence_not_found", "证据不存在", 404)
        self._validate_decision(decision, reason, idempotency_key)
        if row.review_status in {"approved", "rejected"}:
            raise ReviewError("review_already_finalized", "证据审核结果已终结")
        if decision == "approve" and (
            row.validation_status != "validated" or not row.is_active
        ):
            raise ReviewError("evidence_not_approvable", "证据无效或已失效")
        before = self._evidence_snapshot(row)
        row.review_status = "approved" if decision == "approve" else "rejected"
        job = self._job_for_evidence(kind, row)
        audit = self._decision(
            subject_type=f"{kind}_evidence", subject_id=row.id,
            decision=decision, reason=reason, reviewer_id=reviewer_id,
            idempotency_key=idempotency_key, job=job,
            reviewed_value={"before": before, "after": self._evidence_snapshot(row)},
        )
        self.session.flush()
        return row, audit, False

    def _assert_candidate_approvable(self, kind, row) -> None:
        if kind == "entity":
            if row.resolution_status not in {"resolved", "new_entity"}:
                raise ReviewError("entity_resolution_required", "实体尚未完成消歧")
            if not row.canonical_entity_id or not row.canonical_name:
                raise ReviewError("entity_resolution_required", "实体缺少规范 ID 或规范名")
            return
        if row.validation_status != "validated":
            raise ReviewError("candidate_not_validated", "候选未通过结构与证据校验")
        endpoint_ids = (
            (row.source_candidate_id, row.target_candidate_id)
            if kind == "relation"
            else tuple(value for value in (
                row.subject_candidate_id, row.object_candidate_id,
            ) if value is not None)
        )
        endpoints = [self.session.get(KnowledgeGraphEntityCandidate, value) for value in endpoint_ids]
        if any(item is None or item.review_status != "approved" for item in endpoints):
            raise ReviewError("endpoint_review_required", "所有关系端点必须先审核通过")
        evidence_model = (
            KnowledgeGraphCandidateEvidence if kind == "relation"
            else KnowledgeGraphClaimEvidence
        )
        foreign_key = (
            evidence_model.relation_candidate_id if kind == "relation"
            else evidence_model.claim_candidate_id
        )
        evidence = self.session.query(evidence_model).filter(
            foreign_key == row.id, evidence_model.is_active.is_(True),
        ).all()
        if not evidence or any(item.review_status != "approved" for item in evidence):
            raise ReviewError("evidence_review_required", "所有有效证据必须先审核通过")

    def _refresh_relation_endpoints(self, entity) -> None:
        source_rows = self.session.query(KnowledgeGraphRelationCandidate).filter_by(
            source_candidate_id=entity.id,
        ).all()
        target_rows = self.session.query(KnowledgeGraphRelationCandidate).filter_by(
            target_candidate_id=entity.id,
        ).all()
        for row in source_rows:
            row.canonical_source_id = entity.canonical_entity_id
            self._refresh_relation_validation(row)
        for row in target_rows:
            row.canonical_target_id = entity.canonical_entity_id
            self._refresh_relation_validation(row)
        subject_rows = self.session.query(KnowledgeGraphClaimCandidate).filter_by(
            subject_candidate_id=entity.id,
        ).all()
        object_rows = self.session.query(KnowledgeGraphClaimCandidate).filter_by(
            object_candidate_id=entity.id,
        ).all()
        for row in subject_rows:
            row.canonical_subject_id = entity.canonical_entity_id
            self._refresh_claim_validation(row)
        for row in object_rows:
            row.canonical_object_id = entity.canonical_entity_id
            self._refresh_claim_validation(row)

    def _refresh_relation_validation(self, row) -> None:
        source = self.session.get(KnowledgeGraphEntityCandidate, row.source_candidate_id)
        target = self.session.get(KnowledgeGraphEntityCandidate, row.target_candidate_id)
        if (
            source and target and source.canonical_entity_id and target.canonical_entity_id
            and self.schema.allows(row.relation_type, source.entity_type, target.entity_type)
        ):
            row.canonical_source_id = source.canonical_entity_id
            row.canonical_target_id = target.canonical_entity_id
            row.validation_status = "validated"
            if row.review_status == "blocked":
                row.review_status = "pending"

    @staticmethod
    def _refresh_claim_validation(row) -> None:
        if row.canonical_subject_id and (
            row.object_candidate_id is None or row.canonical_object_id
        ):
            row.validation_status = "validated"
            if row.review_status == "blocked":
                row.review_status = "pending"

    def _replay(self, idempotency_key):
        if not str(idempotency_key or "").strip():
            raise ReviewError("idempotency_key_required", "审核必须提供 idempotency_key", 422)
        return self.session.query(KnowledgeGraphReviewDecision).filter_by(
            idempotency_key=str(idempotency_key).strip(),
        ).one_or_none()

    @staticmethod
    def _validate_replay(audit, subject_type, subject_id, decision) -> None:
        if (
            audit.subject_type != subject_type
            or audit.subject_id != subject_id
            or audit.decision != decision
        ):
            raise ReviewError(
                "idempotency_key_conflict",
                "idempotency_key 已用于其他审核操作",
                409,
            )

    @staticmethod
    def _validate_metadata(reason, idempotency_key) -> None:
        if not str(reason or "").strip():
            raise ReviewError("review_reason_required", "审核理由不能为空", 422)
        if not str(idempotency_key or "").strip():
            raise ReviewError("idempotency_key_required", "审核必须提供 idempotency_key", 422)
        if len(str(reason)) > 2000 or len(str(idempotency_key)) > 128:
            raise ReviewError("invalid_review_metadata", "审核元数据长度超限", 422)

    @staticmethod
    def _validate_decision(decision, reason, idempotency_key) -> None:
        if decision not in {"approve", "reject"}:
            raise ReviewError("invalid_review_decision", "decision 仅支持 approve/reject", 422)
        KnowledgeGraphReviewService._validate_metadata(reason, idempotency_key)

    def _decision(
        self, *, subject_type, subject_id, decision, reason, reviewer_id,
        idempotency_key, job, reviewed_value,
    ):
        row = KnowledgeGraphReviewDecision(
            idempotency_key=str(idempotency_key).strip(),
            subject_type=subject_type,
            subject_id=subject_id,
            decision=decision,
            reason=str(reason).strip(),
            reviewer_id=reviewer_id,
            schema_version=job.schema_version,
            backend_name=job.backend_name,
            extractor_version=job.extractor_version,
            reviewed_value=reviewed_value,
        )
        self.session.add(row)
        return row

    def _job_for_candidate(self, row):
        return self.session.get(KnowledgeGraphExtractionJob, row.job_id)

    def _job_for_evidence(self, kind, row):
        candidate = self.session.get(
            KnowledgeGraphRelationCandidate if kind == "relation" else KnowledgeGraphClaimCandidate,
            row.relation_candidate_id if kind == "relation" else row.claim_candidate_id,
        )
        return self._job_for_candidate(candidate)

    @staticmethod
    def _entity_snapshot(row):
        return {
            "id": row.id, "entity_type": row.entity_type, "mention": row.mention,
            "canonical_entity_id": row.canonical_entity_id,
            "canonical_name": row.canonical_name,
            "resolution_status": row.resolution_status,
            "review_status": row.review_status,
        }

    def _candidate_snapshot(self, kind, row):
        if kind == "entity":
            return self._entity_snapshot(row)
        common = {
            "id": row.id, "review_status": row.review_status,
            "validation_status": row.validation_status, "risk_level": row.risk_level,
        }
        if kind == "relation":
            common.update({
                "relation_type": row.relation_type,
                "canonical_source_id": row.canonical_source_id,
                "canonical_target_id": row.canonical_target_id,
            })
        else:
            common.update({
                "claim_type": row.claim_type,
                "canonical_subject_id": row.canonical_subject_id,
                "canonical_object_id": row.canonical_object_id,
                "statement": row.statement,
            })
        return common

    @staticmethod
    def _evidence_snapshot(row):
        return {
            "id": row.id, "evidence_key": row.evidence_key,
            "document_id": row.document_id, "content_sha256": row.content_sha256,
            "chunk_index": row.chunk_index, "page": row.page,
            "span_start": row.span_start, "span_end": row.span_end,
            "quote_sha256": row.quote_sha256,
            "validation_status": row.validation_status,
            "review_status": row.review_status, "is_active": bool(row.is_active),
        }
