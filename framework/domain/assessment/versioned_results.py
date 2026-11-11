"""Versioned publication layer shared by every thematic model consumer.

Model implementations remain pure owners of their calculation rules.  This
module owns cache identity, immutable publication and retrieval so a map, an
agent and a report cannot accidentally select different executions.
"""

from __future__ import annotations

import hashlib
import json
import logging
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Callable, Mapping

from flask import has_app_context
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

logger = logging.getLogger(__name__)


# Bump the affected value whenever calculation code or its interpretation
# changes.  A new value produces a new immutable result row automatically.
MODEL_RUNTIME_VERSIONS: dict[str, str] = {
    "model-1": "stability-1.2.0",
    "model-2": "quality-grade-2.1.0",
    "model-3": "obstacle-diagnosis-2.1.0",
    "model-4": "acidification-1.1.0",
    "model-5": "organic-matter-1.1.0",
    "model-6": "fertility-1.0.0",
}

COEFFICIENT_VERSIONS: dict[str, str | None] = {
    "model-1": "shaoguan-regions-2026.10.13",
    "model-2": "shaoguan-model2-2026.10.13",
    "model-3": "shaoguan-obstacle-2026.10.13",
    "model-4": "acidification-process-2026.10.13",
    "model-5": "artifact-manifest-2026.10.13",
    "model-6": None,
}

_VOLATILE_INPUT_KEYS = {
    "execution_context", "trace_id", "run_id", "conversation_id", "user_id",
    "question", "guard_passed", "execution_channel", "persisted",
}
# Every deterministic terminal outcome is a versioned publication.  Only a
# genuine execution error is retried without changing inputs/version.
_CACHEABLE_STATUSES = {
    "ok", "success", "rejected", "degraded", "unavailable", "fallback", "partial",
}


def _json_safe(value: Any) -> Any:
    from framework.agents.output_contract import sanitize_json

    return sanitize_json(value)


def _canonical_json(value: Any) -> str:
    return json.dumps(
        _json_safe(value), ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False,
    )


def input_fingerprint(snapshot: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(snapshot).encode("utf-8")).hexdigest()


def _payload_inputs(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Keep calculation inputs while removing request/trace-only fields."""
    return {
        str(key): value
        for key, value in payload.items()
        if key not in _VOLATILE_INPUT_KEYS and not str(key).startswith("_")
    }


def build_input_snapshot(agent_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    """Build the complete canonical source snapshot used by one model run.

    Spatial calculations prefer the authoritative parcel row.  Model-1 also
    includes history and a conservative parcel-update clock because its result
    depends on temporal and neighbouring parcels.
    """
    supplied = _payload_inputs(payload)
    parcel_id = supplied.get("parcel_id") or supplied.get("parcel_code")
    snapshot: dict[str, Any] = {
        "agent_id": agent_id,
        "model_version": MODEL_RUNTIME_VERSIONS.get(agent_id, "unknown"),
        "coefficient_version": COEFFICIENT_VERSIONS.get(agent_id),
        "request_inputs": supplied,
    }
    if not parcel_id or not has_app_context():
        return _json_safe(snapshot)

    try:
        from framework.models import ParcelHistorySnapshot, ParcelInfo, db

        parcel = ParcelInfo.query.filter_by(parcel_id=str(parcel_id)).first()
        if parcel is None:
            return _json_safe(snapshot)
        snapshot["parcel"] = {
            "parcel_id": parcel.parcel_id,
            "legacy_parcel_code": parcel.legacy_parcel_code,
            "area_code": parcel.area_code,
            "land_type": parcel.land_type,
            "fertilizer_type": parcel.fertilizer_type,
            "target_ph": parcel.target_ph,
            "soil_indicators": dict(parcel.soil_indicators or {}),
            "updated_at": parcel.updated_at,
        }
        # Spatial mode calculates from the authoritative row, not arbitrary
        # request values.  Retain only explicit scenario overrides.
        if supplied.get("calculation_mode") != "scenario":
            snapshot["request_inputs"] = {
                "parcel_id": parcel.parcel_id,
                "calculation_mode": "spatial",
            }

        if agent_id == "model-1":
            # Stability is defined relative to the currently published quality
            # assessment.  Materialise Model-2 first and include its immutable
            # identity in this model's own input hash.
            from framework.agents.specialized.grade_agent import FarmlandGradeAgent
            grade_execution = FarmlandGradeAgent().execute({
                "parcel_id": parcel.parcel_id,
                "area_code": parcel.area_code,
            })
            dependency = grade_execution.get("versioned_result") or {}
            snapshot["dependencies"] = {"model-2": {
                key: dependency.get(key)
                for key in (
                    "resultId", "modelVersion", "coefficientVersion",
                    "inputHash", "calculatedAt",
                )
            }}
            histories = (
                ParcelHistorySnapshot.query
                .filter_by(parcel_id=str(parcel_id))
                .order_by(ParcelHistorySnapshot.survey_year)
                .all()
            )
            snapshot["history"] = [
                {
                    "survey_year": row.survey_year,
                    "soil_indicators": row.soil_indicators,
                    "quality_grade": row.quality_grade,
                    "composite_index": row.composite_index,
                    "created_at": row.created_at,
                }
                for row in histories
            ]
            snapshot["neighbour_source_clock"] = db.session.query(
                db.func.max(ParcelInfo.updated_at)
            ).scalar()
    except (SQLAlchemyError, RuntimeError) as exc:
        logger.warning("构建版本化模型输入快照失败 agent=%s: %s", agent_id, exc)
        try:
            from framework.models import db
            db.session.rollback()
        except Exception:
            pass
    return _json_safe(snapshot)


def _subject(snapshot: Mapping[str, Any], payload: Mapping[str, Any], digest: str) -> tuple[str, str, str | None]:
    parcel = snapshot.get("parcel") if isinstance(snapshot.get("parcel"), Mapping) else {}
    parcel_id = parcel.get("parcel_id") or payload.get("parcel_id") or payload.get("parcel_code")
    area_code = parcel.get("area_code") or payload.get("area_code")
    if parcel_id:
        return "parcel", str(parcel_id), str(area_code) if area_code else None
    if area_code:
        return "region", str(area_code), str(area_code)
    return "scenario", digest, None


def _metadata(row: Any, *, cache_hit: bool) -> dict[str, Any]:
    return {
        "resultId": row.id,
        "agentId": row.agent_id,
        "modelVersion": row.model_version,
        "coefficientVersion": row.coefficient_version,
        "inputHash": row.input_hash,
        "calculatedAt": row.calculated_at.isoformat() if row.calculated_at else None,
        "cacheHit": cache_hit,
    }


def _with_metadata(payload: Mapping[str, Any], row: Any, *, cache_hit: bool) -> dict[str, Any]:
    result = deepcopy(dict(payload))
    result["versioned_result"] = _metadata(row, cache_hit=cache_hit)
    return result


def _find_exact(agent_id: str, subject_type: str, subject_id: str, version: str, digest: str):
    from framework.models import VersionedModelResult

    return VersionedModelResult.query.filter_by(
        agent_id=agent_id,
        subject_type=subject_type,
        subject_id=subject_id,
        model_version=version,
        input_hash=digest,
        is_current=True,
    ).first()


def get_current_result(agent_id: str, subject_id: str, subject_type: str = "parcel"):
    """Return the single published row for a consumer, newest first."""
    if not has_app_context():
        return None
    try:
        from framework.models import VersionedModelResult
        return (
            VersionedModelResult.query
            .filter_by(
                agent_id=agent_id,
                subject_type=subject_type,
                subject_id=str(subject_id),
                is_current=True,
            )
            .order_by(VersionedModelResult.calculated_at.desc(), VersionedModelResult.id.desc())
            .first()
        )
    except (SQLAlchemyError, RuntimeError):
        try:
            from framework.models import db
            db.session.rollback()
        except Exception:
            pass
        return None


def _publish(
    *, agent: Any, execution: Mapping[str, Any], snapshot: Mapping[str, Any],
    digest: str, subject_type: str, subject_id: str, area_code: str | None,
):
    from framework.models import VersionedModelResult, db

    agent_id = agent.agent_id
    version = MODEL_RUNTIME_VERSIONS.get(agent_id, "unknown")
    status = str(execution.get("status") or "error")
    now = datetime.now(timezone.utc)
    current = status in _CACHEABLE_STATUSES
    try:
        existing = VersionedModelResult.query.filter_by(
            agent_id=agent_id,
            subject_type=subject_type,
            subject_id=subject_id,
            model_version=version,
            input_hash=digest,
        ).first()
        if current:
            VersionedModelResult.query.filter_by(
                agent_id=agent_id,
                subject_type=subject_type,
                subject_id=subject_id,
                is_current=True,
            ).update({"is_current": False}, synchronize_session=False)
        if existing is None:
            existing = VersionedModelResult(
                agent_id=agent_id,
                model_id=agent.model_id,
                subject_type=subject_type,
                subject_id=subject_id,
                area_code=area_code,
                model_version=version,
                coefficient_version=COEFFICIENT_VERSIONS.get(agent_id),
                input_hash=digest,
                input_snapshot=_json_safe(snapshot),
                result_payload=_json_safe(dict(execution)),
                status=status,
                is_current=current,
                calculated_at=now,
            )
            db.session.add(existing)
        else:
            # Execution errors are deliberately excluded from the cache.  A
            # later retry has the same unique identity, so keeping the old
            # payload here would make a transient failure permanent even
            # after ``calculate`` succeeds.  Only successful/deterministic
            # publications are immutable; refresh a prior non-cacheable row
            # with the latest retry outcome.
            if str(existing.status or "error") not in _CACHEABLE_STATUSES:
                existing.area_code = area_code
                existing.coefficient_version = COEFFICIENT_VERSIONS.get(agent_id)
                existing.input_snapshot = _json_safe(snapshot)
                existing.result_payload = _json_safe(dict(execution))
                existing.status = status
                existing.calculated_at = now
            existing.is_current = current
        db.session.commit()
        return existing
    except IntegrityError:
        db.session.rollback()
        return VersionedModelResult.query.filter_by(
            agent_id=agent_id,
            subject_type=subject_type,
            subject_id=subject_id,
            model_version=version,
            input_hash=digest,
        ).first()


def _try_push_app_context() -> Any | None:
    """在无 Flask 上下文的执行路径（如 SSE 流式生成器）临时提供应用上下文。

    与 BaseAgent._persist_result 使用同一模式：对话/报告路径一旦执行模型，
    就必须产出带版本化元数据的可发布结果；缺失上下文时 execute_versioned
    会退回裸计算，导致字段直查误报「暂无可发布的已验证模型结果」。
    推送失败返回 None，调用方按原逻辑回退。
    """
    app_ctx = None
    try:
        if has_app_context():
            return None
        from framework.api.app import create_app
        app_ctx = create_app("default").app_context()
        app_ctx.push()
        return app_ctx
    except Exception:
        return None


def execute_versioned(
    agent: Any,
    payload: Mapping[str, Any] | None,
    calculate: Callable[[], Mapping[str, Any]],
) -> dict[str, Any]:
    """Get or calculate one result for every Model-1..6 execution path."""
    request = dict(payload or {})
    temp_ctx = None
    if not has_app_context():
        temp_ctx = _try_push_app_context()
        if temp_ctx is None and not has_app_context():
            return dict(calculate())
    try:
        agent_id = agent.agent_id
        snapshot = build_input_snapshot(agent_id, request)
        digest = input_fingerprint(snapshot)
        subject_type, subject_id, area_code = _subject(snapshot, request, digest)
        version = MODEL_RUNTIME_VERSIONS.get(agent_id, "unknown")
        try:
            row = _find_exact(agent_id, subject_type, subject_id, version, digest)
            if row is not None:
                return _with_metadata(row.result_payload or {}, row, cache_hit=True)
        except (SQLAlchemyError, RuntimeError) as exc:
            logger.warning("读取版本化结果失败，执行现场计算 agent=%s: %s", agent_id, exc)
            try:
                from framework.models import db
                db.session.rollback()
            except Exception:
                pass

        execution = dict(calculate())
        try:
            row = _publish(
                agent=agent,
                execution=execution,
                snapshot=snapshot,
                digest=digest,
                subject_type=subject_type,
                subject_id=subject_id,
                area_code=area_code,
            )
            if row is not None:
                # Reactivating a historical row must return that row's immutable
                # payload, not a separately recalculated in-memory value.
                return _with_metadata(row.result_payload or execution, row, cache_hit=False)
        except (SQLAlchemyError, RuntimeError) as exc:
            logger.warning("发布版本化结果失败 agent=%s: %s", agent_id, exc)
            try:
                from framework.models import db
                db.session.rollback()
            except Exception:
                pass
        return execution
    finally:
        if temp_ctx is not None:
            try:
                temp_ctx.pop()
            except Exception:
                pass


def business_result(row_or_execution: Any) -> dict[str, Any]:
    """Extract a model's business payload from a row or execution envelope."""
    payload = getattr(row_or_execution, "result_payload", row_or_execution) or {}
    if not isinstance(payload, Mapping):
        return {}
    nested = payload.get("result")
    return dict(nested) if isinstance(nested, Mapping) else dict(payload)
