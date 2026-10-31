"""Cd 双模型数据库后端：输入适配 → 批量推理 → 地块级覆盖写库 → 读取还原。

对应 openspec change ``add-heavy-metal-cd-database-backend``：

- 输入适配只启用语义与单位已确认的映射，其余进 ``missing_fields``，不填零/区域均值（design 决策 5）；
- ``solution`` / ``cdsolution`` 由上游 MSM 提供，缺失即拒绝整批、不以降级值入库（design 决策 9）；
- 写库按地块覆盖：``DELETE WHERE parcel_id IN (...)`` + 分批 ``bulk_insert_mappings`` + 单事务（design 决策 2）；
- 结果只存自然对数值（design 决策 1）。

由于当前库输入覆盖率为 0（``docs/cd-input-coverage-report.md``），主通道是
``rows=``：调用方直接提供完整特征行（design 决策 10）。``parcel_ids=`` 是可选通道，
只对能凑齐全部特征的地块生效，否则整批拒绝并列明缺口。
"""
from __future__ import annotations

import logging
import math
from typing import Any, Iterable, Mapping, Sequence

from framework.domain.other_models.heavy_metal_cd import _API_FIELDS, predict

LOG = logging.getLogger(__name__)

BATCH_SIZE = 5000

#: 唯一启用的映射：模型特征 ← ``parcel_info.soil_indicators`` 的键。
#: 只放语义与单位都已确认的一对一映射（design 决策 5）。
CONFIRMED_INDICATOR_MAP: dict[str, str] = {
    "available_potassium": "available_potassium",
    "available_phosphorus": "available_phosphorus",
    "total_nitrogen": "total_n",
}

#: 明确禁止的映射来源：交换态 ≠ 全量（design 决策 5、spec「交换态与全量语义不得混用」）。
FORBIDDEN_SOURCES: tuple[str, ...] = (
    "exchangeable_ca",
    "exchangeable_mg",
    "exchangeable_k",
    "exchangeable_na",
)

#: model_id → (ORM 模型, ln 列名)
_RESULT_COLUMNS: dict[str, str] = {"crop_cd": "ln_crop_cd", "effective_cd": "ln_eff_cd"}


class CdDatabaseError(RuntimeError):
    """数据库后端的输入或执行错误。"""


def _result_models() -> dict[str, Any]:
    """延迟导入 ORM 模型，避免在无 Flask app 的纯逻辑测试里引入 db 绑定。"""
    from framework.models.cd_prediction import (  # noqa: WPS433
        CdCropPredictionResult,
        CdEffectivePredictionResult,
    )

    return {"crop_cd": CdCropPredictionResult, "effective_cd": CdEffectivePredictionResult}


def _require_app_context() -> None:
    from flask import has_app_context

    if not has_app_context():
        raise CdDatabaseError("no_app_context")


def map_indicators(indicators: Mapping[str, Any] | None, model_id: str) -> dict[str, Any]:
    """把 ``parcel_info.soil_indicators`` 映射为模型特征（纯函数，不查库）。"""
    if model_id not in _API_FIELDS:
        raise CdDatabaseError("unknown_model")
    fields = _API_FIELDS[model_id]
    stored = dict((indicators or {}).get("provenance") or {})
    data: dict[str, Any] = {}
    provenance: dict[str, str] = {}
    missing: list[str] = []
    for field in fields:
        key = CONFIRMED_INDICATOR_MAP.get(field)
        value = (indicators or {}).get(key) if key else None
        if value is None:
            missing.append(field)
            continue
        data[field] = value
        provenance[field] = stored.get(key, "unknown")
    return {
        "status": "ready" if not missing else "need_input",
        "model_id": model_id,
        "data": data,
        "provenance": provenance,
        "missing_fields": missing,
        "sample_granularity": "parcel",
    }


def build_inputs(parcel_id: str, model_id: str) -> dict[str, Any]:
    """按地块编号从当前库读取输入（可选通道）。"""
    _require_app_context()
    from framework.models import ParcelInfo

    row = ParcelInfo.query.filter_by(parcel_id=str(parcel_id)).first()
    if row is None:
        return {
            "status": "parcel_not_found",
            "model_id": model_id,
            "data": {},
            "provenance": {},
            "missing_fields": list(_API_FIELDS.get(model_id, ())),
            "sample_granularity": "parcel",
        }
    return map_indicators(row.soil_indicators, model_id)


def build_inputs_from_row(row: Mapping[str, Any], model_id: str) -> dict[str, Any]:
    """从完整特征行构建输入（主通道）：``{parcel_id, sample_id, **features}``。"""
    if model_id not in _API_FIELDS:
        raise CdDatabaseError("unknown_model")
    fields = _API_FIELDS[model_id]
    data: dict[str, Any] = {}
    missing: list[str] = []
    for field in fields:
        value = row.get(field)
        if value is None:
            missing.append(field)
        else:
            data[field] = value
    return {
        "status": "ready" if not missing else "need_input",
        "model_id": model_id,
        "data": data,
        "provenance": {f: "provided" for f in data},
        "missing_fields": missing,
        "sample_granularity": "sample",
    }


def _write_results(model_id: str, records: Sequence[dict[str, Any]]) -> int:
    """地块级覆盖写入：先按 parcel_id 删除旧行，再分批插入，单事务提交。"""
    _require_app_context()
    from framework.models.user import db

    table = _result_models()[model_id]
    parcel_ids = sorted({r["parcel_id"] for r in records})
    try:
        db.session.query(table).filter(table.parcel_id.in_(parcel_ids)).delete(
            synchronize_session=False
        )
        for start in range(0, len(records), BATCH_SIZE):
            db.session.bulk_insert_mappings(table, list(records[start : start + BATCH_SIZE]))
        db.session.commit()
    except Exception as exc:  # noqa: BLE001 - 统一回滚并转为可诊断错误
        db.session.rollback()
        LOG.exception("Cd 结果写入失败，已回滚")
        raise CdDatabaseError(f"write_failed: {exc}") from exc
    return len(records)


def run(
    model_id: str,
    *,
    rows: Iterable[Mapping[str, Any]] | None = None,
    parcel_ids: Iterable[str] | None = None,
    apply: bool = False,
) -> dict[str, Any]:
    """执行一次批量预测。

    ``rows`` 与 ``parcel_ids`` 二选一：前者是完整特征行（主通道），后者走当前库映射。
    预检有任何缺失则整批拒绝、不写库。``apply=False`` 时只返回预览（dry-run）。
    """
    if model_id not in _API_FIELDS:
        raise CdDatabaseError("unknown_model")
    has_rows = rows is not None
    has_parcels = parcel_ids is not None
    if has_rows == has_parcels:
        raise CdDatabaseError("exactly_one_input_source_required")

    items: list[tuple[str, str, dict[str, Any]]] = []
    if has_rows:
        for row in rows or []:
            parcel_id = str(row.get("parcel_id") or "").strip()
            if not parcel_id:
                raise CdDatabaseError("row_missing_parcel_id")
            sample_id = str(row.get("sample_id") or parcel_id).strip()
            items.append((parcel_id, sample_id, build_inputs_from_row(row, model_id)))
    else:
        for raw in parcel_ids or []:
            parcel_id = str(raw).strip()
            if not parcel_id:
                raise CdDatabaseError("empty_parcel_id")
            items.append((parcel_id, parcel_id, build_inputs(parcel_id, model_id)))

    if not items:
        raise CdDatabaseError("no_items")

    # 预检：任何地块缺输入 → 整批拒绝，不写库
    rejected = [
        {
            "parcel_id": parcel_id,
            "sample_id": sample_id,
            "status": inputs["status"],
            "missing_fields": inputs["missing_fields"],
        }
        for parcel_id, sample_id, inputs in items
        if inputs["status"] != "ready"
    ]
    if rejected:
        return {
            "status": "rejected",
            "model_id": model_id,
            "reason": "incomplete_inputs",
            "requested": len(items),
            "applied": False,
            "stored": 0,
            "rejected": rejected,
        }

    column = _RESULT_COLUMNS[model_id]
    records: list[dict[str, Any]] = []
    degraded = 0
    preview: list[dict[str, Any]] = []
    for parcel_id, sample_id, inputs in items:
        result = predict(model_id, inputs["data"])
        status = result.get("status")
        if status not in ("success", "degraded"):
            return {
                "status": "rejected",
                "model_id": model_id,
                "reason": result.get("reason") or status or "prediction_failed",
                "requested": len(items),
                "applied": False,
                "stored": 0,
                "rejected": [
                    {
                        "parcel_id": parcel_id,
                        "sample_id": sample_id,
                        "status": status,
                        "missing_fields": result.get("missing_fields") or [],
                    }
                ],
            }
        if status == "degraded":
            degraded += 1
        log_value = result.get("log_prediction")
        if log_value is None:
            log_value = math.log(result["prediction"])
        records.append({"parcel_id": parcel_id, "sample_id": sample_id, column: float(log_value)})
        preview.append(
            {
                "parcel_id": parcel_id,
                "sample_id": sample_id,
                column: float(log_value),
                "value": float(result["prediction"]),
                "status": status,
            }
        )

    stored = _write_results(model_id, records) if apply else 0
    return {
        "status": "ok",
        "model_id": model_id,
        "requested": len(items),
        "applied": bool(apply),
        "stored": stored,
        "degraded": degraded,
        "sample_granularity": items[0][2]["sample_granularity"],
        "results": preview,
    }


def read_results(
    model_id: str,
    parcel_ids: Iterable[str] | None = None,
) -> list[dict[str, Any]]:
    """读取结果并把自然对数值还原为 mg/kg。

    单位标注为 ``mg/kg``；``unit_status`` 保持 ``unverified``
    （``exp(LnEffCd)`` 实测量级待核，见 design 决策 6）。
    """
    if model_id not in _API_FIELDS:
        raise CdDatabaseError("unknown_model")
    _require_app_context()
    from framework.models.user import db

    table = _result_models()[model_id]
    column = _RESULT_COLUMNS[model_id]
    query = db.session.query(table)
    if parcel_ids is not None:
        query = query.filter(table.parcel_id.in_([str(p) for p in parcel_ids]))
    rows = query.order_by(table.parcel_id, table.sample_id).all()
    payload = []
    for row in rows:
        log_value = float(getattr(row, column))
        payload.append(
            {
                "parcel_id": row.parcel_id,
                "sample_id": row.sample_id,
                column: log_value,
                "value": math.exp(log_value),
                "unit": "mg/kg",
                "unit_status": "unverified",
            }
        )
    return payload
