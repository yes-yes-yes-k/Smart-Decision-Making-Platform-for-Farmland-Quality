"""Administrative APIs for graph jobs, candidates, evidence and reviews."""
from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from sqlalchemy import or_

from framework.knowledge_graph.contracts import stable_digest
from framework.knowledge_graph.jobs import (
    DEFAULT_BACKEND_NAME,
    DEFAULT_EXTRACTOR_VERSION,
    document_is_graph_eligible,
    utcnow_naive,
)
from framework.knowledge_graph.review import KnowledgeGraphReviewService, ReviewError
from framework.knowledge_graph.release_platform import (
    KnowledgeGraphReleaseService,
    ReleaseError,
)
from framework.knowledge_graph.query import SafeGraphQueryService
from framework.knowledge_graph.schema import load_graph_schema
from framework.models.document import Document
from framework.models.knowledge_graph import (
    KnowledgeGraphCandidateEvidence,
    KnowledgeGraphClaimCandidate,
    KnowledgeGraphClaimEvidence,
    KnowledgeGraphEntityCandidate,
    KnowledgeGraphExtractionJob,
    KnowledgeGraphRelationCandidate,
    KnowledgeGraphRelease,
    KnowledgeGraphRollbackAudit,
    KnowledgeGraphReviewDecision,
)
from framework.models.user import User, db
from framework.vector_store.chroma_store import vector_store


knowledge_graph_bp = Blueprint("knowledge_graph_admin", __name__)
REVIEWER_ROLES = {"admin", "domain_reviewer"}
JOB_STATES = {"pending", "running", "retry", "completed", "dead_letter"}
CANDIDATE_KINDS = {"entity", "relation", "claim"}


def _error(code, message, status):
    return jsonify({"status": "error", "error_code": code, "message": message}), status


def _actor(*, admin=False):
    user = db.session.get(User, int(get_jwt_identity()))
    if user is None:
        return None
    if admin:
        return user if user.is_admin() else None
    return user if user.role in REVIEWER_ROLES else None


def _page_args():
    page = max(1, request.args.get("page", 1, type=int))
    page_size = request.args.get("page_size", 20, type=int)
    return page, max(1, min(page_size, 100))


def _iso(value):
    return value.isoformat() if value else None


def _job_payload(row, *, detail=False):
    data = {
        "id": row.id, "document_id": row.document_id,
        "content_sha256": row.content_sha256,
        "schema_version": row.schema_version,
        "backend_name": row.backend_name,
        "extractor_version": row.extractor_version,
        "state": row.state, "priority": row.priority,
        "attempt_count": row.attempt_count, "max_attempts": row.max_attempts,
        "retryable": bool(row.retryable), "failure_code": row.failure_code,
        "available_at": _iso(row.available_at), "started_at": _iso(row.started_at),
        "finished_at": _iso(row.finished_at), "updated_at": _iso(row.updated_at),
    }
    if detail:
        data.update({
            "result_digest": row.result_digest,
            "raw_output_fingerprint": row.raw_output_fingerprint,
            "candidate_counts": {
                "entities": KnowledgeGraphEntityCandidate.query.filter_by(job_id=row.id).count(),
                "relations": KnowledgeGraphRelationCandidate.query.filter_by(job_id=row.id).count(),
                "claims": KnowledgeGraphClaimCandidate.query.filter_by(job_id=row.id).count(),
            },
        })
    return data


def _entity_payload(row):
    return {
        "kind": "entity", "id": row.id, "job_id": row.job_id,
        "candidate_key": row.candidate_key, "entity_type": row.entity_type,
        "mention": row.mention, "canonical_entity_id": row.canonical_entity_id,
        "canonical_name": row.canonical_name,
        "resolution_status": row.resolution_status,
        "risk_level": row.risk_level, "review_status": row.review_status,
        "confidence": row.confidence, "candidate_payload": row.candidate_payload,
    }


def _relation_payload(row):
    return {
        "kind": "relation", "id": row.id, "job_id": row.job_id,
        "candidate_key": row.candidate_key, "relation_type": row.relation_type,
        "source_candidate_id": row.source_candidate_id,
        "target_candidate_id": row.target_candidate_id,
        "canonical_source_id": row.canonical_source_id,
        "canonical_target_id": row.canonical_target_id,
        "risk_level": row.risk_level, "validation_status": row.validation_status,
        "review_status": row.review_status, "confidence": row.confidence,
        "support_document_count": row.support_document_count,
    }


def _claim_payload(row):
    return {
        "kind": "claim", "id": row.id, "job_id": row.job_id,
        "candidate_key": row.candidate_key, "claim_type": row.claim_type,
        "subject_candidate_id": row.subject_candidate_id,
        "object_candidate_id": row.object_candidate_id,
        "canonical_subject_id": row.canonical_subject_id,
        "canonical_object_id": row.canonical_object_id,
        "statement": row.statement, "risk_level": row.risk_level,
        "validation_status": row.validation_status,
        "review_status": row.review_status, "confidence": row.confidence,
    }


def _evidence_payload(row, kind):
    return {
        "kind": kind, "id": row.id, "evidence_key": row.evidence_key,
        "candidate_id": (
            row.relation_candidate_id if kind == "relation" else row.claim_candidate_id
        ),
        "document_id": row.document_id, "content_sha256": row.content_sha256,
        "chunk_index": row.chunk_index, "page": row.page,
        "span_start": row.span_start, "span_end": row.span_end,
        "quote": row.quote, "quote_sha256": row.quote_sha256,
        "schema_version": row.schema_version, "backend_name": row.backend_name,
        "extractor_version": row.extractor_version,
        "validation_status": row.validation_status,
        "review_status": row.review_status, "is_active": bool(row.is_active),
    }


def _candidate(kind, candidate_id):
    model = {
        "entity": KnowledgeGraphEntityCandidate,
        "relation": KnowledgeGraphRelationCandidate,
        "claim": KnowledgeGraphClaimCandidate,
    }.get(kind)
    return db.session.get(model, candidate_id) if model else None


def _candidate_payload(kind, row):
    return {
        "entity": _entity_payload,
        "relation": _relation_payload,
        "claim": _claim_payload,
    }[kind](row)


def _audit_payload(row):
    return {
        "id": row.id, "idempotency_key": row.idempotency_key,
        "subject_type": row.subject_type, "subject_id": row.subject_id,
        "decision": row.decision, "reason": row.reason,
        "reviewer_id": row.reviewer_id, "schema_version": row.schema_version,
        "backend_name": row.backend_name,
        "extractor_version": row.extractor_version,
        "reviewed_value": row.reviewed_value, "created_at": _iso(row.created_at),
    }


def _release_payload(row):
    return {
        "release_id": row.release_id, "sequence_no": row.sequence_no,
        "parent_release_id": row.parent_release_id,
        "schema_version": row.schema_version, "state": row.state,
        "change_checksum": row.change_checksum,
        "diff_summary": row.diff_summary,
        "validation_report": row.validation_report,
        "created_by": row.created_by, "validated_at": _iso(row.validated_at),
        "published_at": _iso(row.published_at), "created_at": _iso(row.created_at),
    }


def _release_service():
    store = current_app.extensions.get("knowledge_graph_store")
    if store is None:
        raise ReleaseError("graph_store_unavailable", "图存储当前不可用", 503)
    return KnowledgeGraphReleaseService(db.session, store)


@knowledge_graph_bp.get("/jobs")
@jwt_required()
def list_jobs():
    if not _actor(admin=True):
        return _error("forbidden", "只有管理员可以查询图谱任务", 403)
    query = KnowledgeGraphExtractionJob.query
    state = request.args.get("state")
    if state:
        if state not in JOB_STATES:
            return _error("invalid_job_state", "无效任务状态", 422)
        query = query.filter_by(state=state)
    for field in ("backend_name", "extractor_version"):
        value = request.args.get(field)
        if value:
            query = query.filter(getattr(KnowledgeGraphExtractionJob, field) == value)
    document_id = request.args.get("document_id", type=int)
    if document_id:
        query = query.filter_by(document_id=document_id)
    page, page_size = _page_args()
    result = query.order_by(
        KnowledgeGraphExtractionJob.created_at.desc(),
        KnowledgeGraphExtractionJob.id.desc(),
    ).paginate(page=page, per_page=page_size, error_out=False)
    return jsonify({"status": "ok", "data": {
        "list": [_job_payload(item) for item in result.items],
        "total": result.total, "page": page, "page_size": page_size,
    }})


@knowledge_graph_bp.get("/jobs/<int:job_id>")
@jwt_required()
def get_job(job_id):
    if not _actor(admin=True):
        return _error("forbidden", "只有管理员可以查询图谱任务", 403)
    row = db.session.get(KnowledgeGraphExtractionJob, job_id)
    return (
        jsonify({"status": "ok", "data": _job_payload(row, detail=True)})
        if row else _error("not_found", "图谱任务不存在", 404)
    )


def _reset_job(row):
    row.state = "pending"
    row.attempt_count = 0
    row.available_at = utcnow_naive()
    row.lease_owner = None
    row.lease_expires_at = None
    row.heartbeat_at = None
    row.started_at = None
    row.finished_at = None
    row.failure_code = None
    row.failure_message = None
    row.retryable = False
    row.result_digest = None
    row.raw_output_fingerprint = None


@knowledge_graph_bp.post("/jobs/<int:job_id>/retry")
@jwt_required()
def retry_job(job_id):
    if not _actor(admin=True):
        return _error("forbidden", "只有管理员可以重试图谱任务", 403)
    row = db.session.get(KnowledgeGraphExtractionJob, job_id)
    if not row:
        return _error("not_found", "图谱任务不存在", 404)
    if row.state not in {"retry", "dead_letter"}:
        return _error("job_not_retryable", "当前任务不是失败或待重试状态", 409)
    _reset_job(row)
    db.session.commit()
    return jsonify({"status": "ok", "data": _job_payload(row)}), 202


@knowledge_graph_bp.post("/documents/<int:document_id>/rerun")
@jwt_required()
def rerun_document(document_id):
    if not _actor(admin=True):
        return _error("forbidden", "只有管理员可以重跑图谱任务", 403)
    document = db.session.get(Document, document_id)
    if not document or not document_is_graph_eligible(document):
        return _error("document_not_eligible", "文档尚未审核发布或不支持图谱抽取", 409)
    payload = request.get_json(silent=True) or {}
    schema_version = str(payload.get("schema_version") or load_graph_schema().schema_version)
    backend_name = str(payload.get("backend_name") or DEFAULT_BACKEND_NAME)
    extractor_version = str(payload.get("extractor_version") or DEFAULT_EXTRACTOR_VERSION)
    from framework.knowledge_graph.extraction_config import backend_config_digest
    config_digest = str(payload.get("backend_config_digest") or backend_config_digest(
        backend_name, extractor_version, schema_version,
    ))
    row = KnowledgeGraphExtractionJob.query.filter_by(
        document_id=document.id, content_sha256=document.file_hash,
        schema_version=schema_version, backend_name=backend_name,
        extractor_version=extractor_version,
    ).one_or_none()
    created = row is None
    if row is None:
        row = KnowledgeGraphExtractionJob(
            document_id=document.id, content_sha256=document.file_hash,
            schema_version=schema_version, backend_name=backend_name,
            extractor_version=extractor_version,
            backend_config_digest=config_digest,
        )
        db.session.add(row)
    else:
        if row.state == "running":
            return _error("job_running", "图谱任务正在运行", 409)
        if row.backend_config_digest != config_digest:
            # Existing candidate provenance must remain immutable.
            if KnowledgeGraphEntityCandidate.query.filter_by(job_id=row.id).first():
                return _error("backend_config_conflict", "已有候选的任务不能更改抽取配置", 409)
            row.backend_config_digest = config_digest
        _reset_job(row)
    db.session.commit()
    return jsonify({
        "status": "ok", "data": _job_payload(row), "created": created,
    }), 202


@knowledge_graph_bp.get("/candidates")
@jwt_required()
def list_candidates():
    if not _actor():
        return _error("forbidden", "需要管理员或领域审核员权限", 403)
    kind = request.args.get("kind", "relation")
    if kind not in CANDIDATE_KINDS:
        return _error("invalid_candidate_type", "kind 仅支持 entity/relation/claim", 422)
    model = {
        "entity": KnowledgeGraphEntityCandidate,
        "relation": KnowledgeGraphRelationCandidate,
        "claim": KnowledgeGraphClaimCandidate,
    }[kind]
    query = model.query
    review_status = request.args.get("review_status")
    risk_level = request.args.get("risk_level")
    if review_status:
        query = query.filter(model.review_status == review_status)
    if risk_level:
        query = query.filter(model.risk_level == risk_level)
    relation_type = request.args.get("relation_type")
    if relation_type:
        if kind != "relation":
            return _error("invalid_filter", "relation_type 仅适用于关系候选", 422)
        query = query.filter(model.relation_type == relation_type)
    document_id = request.args.get("document_id", type=int)
    if document_id:
        originating_document = model.job_id.in_(
            db.session.query(KnowledgeGraphExtractionJob.id).filter_by(
                document_id=document_id,
            )
        )
        if kind == "relation":
            evidence_document = model.id.in_(
                db.session.query(KnowledgeGraphCandidateEvidence.relation_candidate_id)
                .filter_by(document_id=document_id)
            )
            query = query.filter(or_(originating_document, evidence_document))
        elif kind == "claim":
            evidence_document = model.id.in_(
                db.session.query(KnowledgeGraphClaimEvidence.claim_candidate_id)
                .filter_by(document_id=document_id)
            )
            query = query.filter(or_(originating_document, evidence_document))
        else:
            query = query.filter(originating_document)
    page, page_size = _page_args()
    result = query.order_by(model.id.desc()).paginate(
        page=page, per_page=page_size, error_out=False,
    )
    return jsonify({"status": "ok", "data": {
        "list": [_candidate_payload(kind, item) for item in result.items],
        "total": result.total, "page": page, "page_size": page_size,
    }})


@knowledge_graph_bp.get("/candidates/<kind>/<int:candidate_id>")
@jwt_required()
def get_candidate(kind, candidate_id):
    if not _actor():
        return _error("forbidden", "需要管理员或领域审核员权限", 403)
    row = _candidate(kind, candidate_id)
    if row is None:
        return _error("candidate_not_found", "候选不存在", 404)
    data = _candidate_payload(kind, row)
    evidence = []
    if kind == "relation":
        evidence = KnowledgeGraphCandidateEvidence.query.filter_by(
            relation_candidate_id=row.id,
        ).order_by(KnowledgeGraphCandidateEvidence.id).all()
    elif kind == "claim":
        evidence = KnowledgeGraphClaimEvidence.query.filter_by(
            claim_candidate_id=row.id,
        ).order_by(KnowledgeGraphClaimEvidence.id).all()
    data["evidence"] = [_evidence_payload(item, kind) for item in evidence]
    subject_types = [f"{kind}_candidate"]
    if kind == "entity":
        subject_types.append("entity_resolution")
    data["review_history"] = [_audit_payload(item) for item in (
        KnowledgeGraphReviewDecision.query.filter(
            KnowledgeGraphReviewDecision.subject_id == row.id,
            KnowledgeGraphReviewDecision.subject_type.in_(subject_types),
        ).order_by(KnowledgeGraphReviewDecision.id).all()
    )]
    return jsonify({"status": "ok", "data": data})


@knowledge_graph_bp.get("/evidence/<kind>/<int:evidence_id>")
@jwt_required()
def get_evidence(kind, evidence_id):
    if not _actor():
        return _error("forbidden", "需要管理员或领域审核员权限", 403)
    model = {
        "relation": KnowledgeGraphCandidateEvidence,
        "claim": KnowledgeGraphClaimEvidence,
    }.get(kind)
    row = db.session.get(model, evidence_id) if model else None
    if row is None:
        return _error("evidence_not_found", "证据不存在", 404)
    return jsonify({"status": "ok", "data": _evidence_payload(row, kind)})


def _review_request():
    payload = request.get_json(silent=True) or {}
    return payload, {
        "decision": str(payload.get("decision") or "").strip().lower(),
        "reason": str(payload.get("reason") or "").strip(),
        "idempotency_key": str(payload.get("idempotency_key") or "").strip(),
    }


@knowledge_graph_bp.post("/entities/<int:entity_id>/resolve")
@jwt_required()
def resolve_entity(entity_id):
    actor = _actor()
    if not actor:
        return _error("forbidden", "需要管理员或领域审核员权限", 403)
    payload = request.get_json(silent=True) or {}
    try:
        row, audit, replayed = KnowledgeGraphReviewService(db.session).resolve_entity(
            entity_id,
            canonical_id=str(payload.get("canonical_id") or ""),
            canonical_name=str(payload.get("canonical_name") or ""),
            reason=str(payload.get("reason") or ""), reviewer_id=actor.id,
            idempotency_key=str(payload.get("idempotency_key") or ""),
        )
        db.session.commit()
    except ReviewError as exc:
        db.session.rollback()
        return _error(exc.code, exc.message, exc.status_code)
    return jsonify({"status": "ok", "data": {
        "candidate": _entity_payload(row), "audit": _audit_payload(audit),
        "replayed": replayed,
    }})


@knowledge_graph_bp.post("/candidates/<kind>/<int:candidate_id>/review")
@jwt_required()
def review_candidate(kind, candidate_id):
    actor = _actor()
    if not actor:
        return _error("forbidden", "需要管理员或领域审核员权限", 403)
    _, values = _review_request()
    try:
        row, audit, replayed = KnowledgeGraphReviewService(db.session).review_candidate(
            kind, candidate_id, reviewer_id=actor.id, **values,
        )
        db.session.commit()
    except ReviewError as exc:
        db.session.rollback()
        return _error(exc.code, exc.message, exc.status_code)
    return jsonify({"status": "ok", "data": {
        "candidate": _candidate_payload(kind, row), "audit": _audit_payload(audit),
        "replayed": replayed,
    }})


@knowledge_graph_bp.post("/evidence/<kind>/<int:evidence_id>/review")
@jwt_required()
def review_evidence(kind, evidence_id):
    actor = _actor()
    if not actor:
        return _error("forbidden", "需要管理员或领域审核员权限", 403)
    _, values = _review_request()
    try:
        row, audit, replayed = KnowledgeGraphReviewService(db.session).review_evidence(
            kind, evidence_id, reviewer_id=actor.id, **values,
        )
        db.session.commit()
    except ReviewError as exc:
        db.session.rollback()
        return _error(exc.code, exc.message, exc.status_code)
    return jsonify({"status": "ok", "data": {
        "evidence": _evidence_payload(row, kind), "audit": _audit_payload(audit),
        "replayed": replayed,
    }})


@knowledge_graph_bp.post("/production-relations")
@jwt_required()
def forbid_direct_production_relation():
    if not _actor():
        return _error("forbidden", "需要管理员或领域审核员权限", 403)
    return _error(
        "direct_production_write_forbidden",
        "生产关系只能由已批准候选通过版本发布流程生成",
        405,
    )


@knowledge_graph_bp.get("/releases")
@jwt_required()
def list_releases():
    if not _actor(admin=True):
        return _error("forbidden", "只有管理员可以查询发布版本", 403)
    page, page_size = _page_args()
    result = KnowledgeGraphRelease.query.order_by(
        KnowledgeGraphRelease.sequence_no.desc(),
    ).paginate(page=page, per_page=page_size, error_out=False)
    return jsonify({"status": "ok", "data": {
        "list": [_release_payload(item) for item in result.items],
        "total": result.total, "page": page, "page_size": page_size,
    }})


@knowledge_graph_bp.get("/releases/preview")
@jwt_required()
def preview_release():
    if not _actor(admin=True):
        return _error("forbidden", "只有管理员可以预览发布", 403)
    try:
        preview = _release_service().preview()
    except ReleaseError as exc:
        return _error(exc.code, exc.message, exc.status_code)
    return jsonify({"status": "ok", "data": preview.to_dict()})


@knowledge_graph_bp.post("/releases")
@jwt_required()
def publish_release():
    actor = _actor(admin=True)
    if not actor:
        return _error("forbidden", "只有管理员可以发布图谱", 403)
    payload = request.get_json(silent=True) or {}
    try:
        row = _release_service().publish(
            release_id=str(payload.get("release_id") or ""),
            created_by=actor.id,
        )
        db.session.commit()
    except ReleaseError as exc:
        db.session.rollback()
        return _error(exc.code, exc.message, exc.status_code)
    return jsonify({"status": "ok", "data": _release_payload(row)}), 201


@knowledge_graph_bp.post("/releases/<release_id>/rollback")
@jwt_required()
def rollback_release(release_id):
    actor = _actor(admin=True)
    if not actor:
        return _error("forbidden", "只有管理员可以回滚图谱", 403)
    payload = request.get_json(silent=True) or {}
    try:
        audit, replayed = _release_service().rollback(
            target_release_id=release_id, operator_id=actor.id,
            reason=str(payload.get("reason") or ""),
            idempotency_key=str(payload.get("idempotency_key") or ""),
        )
        db.session.commit()
    except ReleaseError as exc:
        db.session.rollback()
        return _error(exc.code, exc.message, exc.status_code)
    return jsonify({"status": "ok", "data": {
        "id": audit.id, "source_release_id": audit.source_release_id,
        "target_release_id": audit.target_release_id,
        "operator_id": audit.operator_id, "reason": audit.reason,
        "duration_ms": audit.duration_ms, "created_at": _iso(audit.created_at),
        "replayed": replayed,
    }})


@knowledge_graph_bp.post("/query")
@jwt_required()
def query_graph():
    user = db.session.get(User, int(get_jwt_identity()))
    if user is None or not user.status:
        return _error("forbidden", "用户不可用", 403)
    store = current_app.extensions.get("knowledge_graph_store")
    if store is None:
        return jsonify({"status": "ok", "data": {
            "status": "degraded", "failure_code": "graph_query_unavailable",
            "active_release": None, "entities": [], "relations": [],
            "evidence": [], "truncated": False,
        }})
    payload = request.get_json(silent=True) or {}
    filters = {"$or": [
        {"visibility_scope": "public"}, {"owner_id": user.id},
    ]}
    try:
        data = SafeGraphQueryService(store, vector_store).query(
            entity_ids=payload.get("entity_ids") or (),
            relation_types=payload.get("relation_types") or (),
            direction=payload.get("direction", "both"),
            max_hops=payload.get("max_hops", 1),
            top_k=payload.get("top_k", 20),
            timeout_ms=payload.get("timeout_ms", 1000),
            max_result_bytes=payload.get("max_result_bytes", 262_144),
            filters=filters, category=payload.get("category"),
        )
    except (TypeError, ValueError) as exc:
        return _error("invalid_graph_query", str(exc), 422)
    return jsonify({"status": "ok", "data": data})
