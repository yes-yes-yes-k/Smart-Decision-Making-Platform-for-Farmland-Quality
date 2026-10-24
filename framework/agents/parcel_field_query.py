"""Deterministic single-parcel field lookup for chat questions.

Professional models return derived diagnoses and prescriptions.  They are not a
reliable source for questions such as "这块地的 pH 是多少" because their compact
chat projection deliberately omits most raw inputs.  This module resolves those
questions against the authoritative ``parcel_info`` snapshot before the model
answer is composed.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import math
from typing import Any, Iterable
from collections.abc import Mapping

from framework.domain.data.parcel_data_accessor import (
    ParcelDataAccessor,
    ParcelDataSnapshot,
)
from framework.domain.statistics.indicator_definitions import (
    INDICATOR_DEFINITIONS,
)


@dataclass(frozen=True)
class ParcelField:
    key: str
    source_field: str
    label: str
    unit: str = ""
    decimals: int = 2
    aliases: tuple[str, ...] = ()
    category: str = "measured_indicator"
    source_kind: str = "indicator"
    attribute_name: str | None = None
    fallback_source_field: str | None = None
    model_agent_id: str | None = None


FIELD_CATEGORY_PRECONDITIONS: dict[str, tuple[str, ...]] = {
    "measured_indicator": (
        "已解析到权威地块快照",
        "soil_indicators 中存在非空且有限的字段值",
    ),
    "management_context": (
        "只读取 parcel_info 顶层规范字段",
        "soil_indicators 不得保存同名管理字段",
    ),
    "derived_model_result": (
        "结果来自本次请求调用的 Model-2",
        "模型状态为 ok 且不是模拟结果",
        "地块标识与当前分析对象一致",
        "结果具备发布记录、模型版本、输入哈希和计算时间",
    ),
    "indicator_provenance": (
        "用户必须明确点名一个或多个指标",
        "元数据必须来自该指标自己的 indicator_provenance 记录",
    ),
}


_FIELDS: tuple[ParcelField, ...] = (
    ParcelField(
        "soil_ph", "soil_ph", "土壤酸碱度（pH）", "", 2,
        ("土壤酸碱度", "酸碱度", "ph值", "ph 值", "ph"),
    ),
    ParcelField(
        "effective_soil_depth", "topsoil_thickness", "有效土层厚度", "cm", 2,
        ("有效土层厚度", "土层厚度"),
    ),
    ParcelField(
        "plow_layer_thickness", "plow_layer_thickness", "耕层厚度", "cm", 2,
        ("耕作层厚度", "耕层厚度"),
    ),
    ParcelField(
        "organic_matter", "organic_matter", "有机质含量", "g/kg", 2,
        ("土壤有机质", "有机质含量", "有机质"),
    ),
    ParcelField(
        "available_phosphorus", "available_phosphorus", "有效磷含量", "mg/kg", 2,
        ("有效磷含量", "有效磷"),
    ),
    ParcelField(
        "available_potassium", "available_potassium", "速效钾含量", "mg/kg", 2,
        ("速效钾含量", "有效钾", "速效钾"),
    ),
    ParcelField(
        "bulk_density", "bulk_density", "土壤容重", "g/cm³", 2,
        ("土壤容重", "容重"),
    ),
    ParcelField(
        "exchangeable_hydrogen", "exchangeable_hydrogen", "交换性氢", "cmol/kg", 2,
        ("交换性氢离子", "可交换氢", "交换性氢"),
    ),
    ParcelField(
        "exchangeable_aluminum", "exchangeable_aluminum", "交换性铝", "cmol/kg", 2,
        ("交换性铝离子", "交换性铝"),
    ),
    ParcelField(
        "total_nitrogen", "total_nitrogen", "全氮", "g/kg", 2,
        ("总氮", "全氮"),
    ),
    ParcelField(
        "total_phosphorus", "total_phosphorus", "全磷", "g/kg", 2,
        ("总磷", "全磷"),
    ),
    ParcelField(
        "total_potassium", "total_potassium", "全钾", "g/kg", 2,
        ("总钾", "全钾"),
    ),
    ParcelField(
        "soil_texture", "soil_texture", "耕层质地", "", 0,
        ("土壤质地", "耕层质地", "质地"),
    ),
    ParcelField(
        "irrigation_condition", "irrigation_condition", "灌溉能力", "", 0,
        ("灌溉条件", "灌溉能力"),
    ),
    ParcelField(
        "drainage_capacity", "drainage_capacity", "排水能力", "", 0,
        ("排水条件", "排水能力"),
    ),
    ParcelField(
        "terrain_position", "terrain_position", "地形部位", "", 0,
        ("地形位置", "地形部位"),
    ),
    ParcelField(
        "soil_structure", "soil_structure", "质地构型", "", 0,
        ("土壤结构", "质地构型"),
    ),
    ParcelField(
        "land_type", "land_type", "土地利用类型", "", 0,
        ("土地利用类型", "农田类型", "地类"),
        category="management_context", source_kind="attribute",
        attribute_name="land_type",
    ),
    ParcelField(
        "fertilizer_type", "fertilizer_type", "肥料类型", "", 0,
        ("施肥类型", "肥料类型"),
        category="management_context", source_kind="attribute",
        attribute_name="fertilizer_type",
    ),
    ParcelField(
        "target_ph", "target_ph", "目标 pH", "", 2,
        ("目标土壤酸碱度", "目标酸碱度", "目标ph值", "目标 ph", "目标ph", "目标pH"),
        category="management_context", source_kind="attribute",
        attribute_name="target_ph",
    ),
    ParcelField(
        "cation_exchange_capacity", "cation_exchange_capacity", "阳离子交换量", "cmol/kg", 2,
        ("阳离子交换容量", "阳离子交换量", "cec"),
    ),
    ParcelField(
        "exchangeable_acid_total", "exchangeable_acid_total", "交换性酸总量", "cmol/kg", 2,
        ("交换性总酸", "交换性酸总量", "交换性酸"),
    ),
    ParcelField(
        "hydrolytic_total_acidity", "hydrolytic_total_acidity", "水解性总酸度", "cmol/kg", 2,
        ("水解性总酸度", "水解性总酸", "水解酸度"),
    ),
    ParcelField(
        "quality_grade", "quality_grade", "耕地质量等级", "等", 0,
        ("耕地质量等级", "质量等级"),
        category="derived_model_result", source_kind="model",
        model_agent_id="model-2",
    ),
    ParcelField(
        "composite_index", "composite_index", "耕地质量综合指数", "", 4,
        ("耕地质量综合指数", "质量综合指数", "综合指数"),
        category="derived_model_result", source_kind="model",
        model_agent_id="model-2",
    ),
)


_METADATA_ALIASES: dict[str, tuple[str, ...]] = {
    "measurement_year": ("测量年份", "检测年份", "采样年份", "哪年测", "哪一年测"),
    "data_source": ("数据来源", "数据源", "来源"),
    "is_imputed": ("是否插补", "是否推算", "插补", "推算值"),
    "quality_flag": ("质量标记", "质量标签", "质量状态"),
    "model_version": ("模型版本",),
    "coefficient_version": ("系数版本", "参数版本"),
    "calculated_at": ("计算时间", "评价时间", "评定时间"),
}

_ENUM_LABELS: dict[str, dict[str, str]] = {
    "land_type": {"upland": "旱地", "paddy": "水田"},
    "fertilizer_type": {
        "compound": "复合肥", "urea": "尿素", "single": "单质肥",
    },
}

_SOURCE_LABELS = {
    "model1_shapefile": "模型1地块数据",
    "db": "地块数据库",
    "database": "地块数据库",
    "csv": "模型数据文件",
}

_QUALITY_FLAG_LABELS = {
    "source_unverified": "来源未核验",
    "low_variability": "低变异性",
    "verified": "已核验",
}


def requested_parcel_fields(question: str) -> tuple[ParcelField, ...]:
    """Return explicitly mentioned parcel fields, preserving registry order."""
    folded = str(question or "").casefold()
    matched: list[ParcelField] = []
    for field in _FIELDS:
        aliases = sorted(field.aliases, key=len, reverse=True)
        if any(alias.casefold() in folded for alias in aliases):
            matched.append(field)
    # "目标 pH" is a management target, not a request for the current pH.
    if any(field.key == "target_ph" for field in matched):
        matched = [field for field in matched if field.key != "soil_ph"]
    return tuple(matched)


def requested_metadata_fields(question: str) -> tuple[str, ...]:
    """Return requested provenance/model metadata keys."""
    folded = str(question or "").casefold()
    return tuple(
        key for key, aliases in _METADATA_ALIASES.items()
        if any(alias.casefold() in folded for alias in aliases)
    )


def _is_missing(value: Any) -> bool:
    if value is None or isinstance(value, bool):
        return value is None
    if isinstance(value, float):
        return not math.isfinite(value)
    return isinstance(value, str) and not value.strip()


def _model_field_value(
    snapshot: ParcelDataSnapshot,
    field: ParcelField,
    professional_results: Mapping[str, Any] | None,
) -> tuple[Any, str | None, dict[str, Any], str | None]:
    models = (
        professional_results.get("models", {})
        if isinstance(professional_results, Mapping) else {}
    )
    envelope = models.get(field.model_agent_id or "") if isinstance(models, Mapping) else None
    if not isinstance(envelope, Mapping):
        return None, None, {}, "model_result_missing"
    if envelope.get("status") != "ok":
        return None, None, {}, "model_status_not_ok"
    subject = envelope.get("subject") if isinstance(envelope.get("subject"), Mapping) else {}
    if subject.get("type") != "parcel" or str(subject.get("id")) != snapshot.parcel_id:
        return None, None, {}, "model_subject_mismatch"
    meta = envelope.get("meta") if isinstance(envelope.get("meta"), Mapping) else {}
    required_meta = (
        "model_version", "calculation_result_id", "input_hash", "calculated_at",
    )
    if meta.get("simulated") or any(_is_missing(meta.get(key)) for key in required_meta):
        return None, None, dict(meta), "model_provenance_incomplete"
    if str(meta.get("model_version")).strip().lower() == "unknown":
        return None, None, dict(meta), "model_provenance_incomplete"
    result = envelope.get("result") if isinstance(envelope.get("result"), Mapping) else {}
    value = result.get(field.source_field)
    if _is_missing(value):
        return None, None, dict(meta), "model_value_missing"
    provenance = {
        "data_source": meta.get("data_source"),
        "model_version": meta.get("model_version"),
        "coefficient_version": meta.get("coefficient_version"),
        "calculation_result_id": meta.get("calculation_result_id"),
        "input_hash": meta.get("input_hash"),
        "calculated_at": meta.get("calculated_at"),
        "simulated": False,
    }
    return value, f"{field.model_agent_id}.result.{field.source_field}", provenance, None


def _indicator_provenance(snapshot: ParcelDataSnapshot, field: ParcelField) -> dict[str, Any]:
    all_provenance = snapshot.indicators.get("indicator_provenance")
    if not isinstance(all_provenance, Mapping):
        return {}
    candidates = (field.source_field, field.key, field.fallback_source_field)
    for key in candidates:
        item = all_provenance.get(key) if key else None
        if isinstance(item, Mapping):
            return dict(item)
    return {}


def _field_value(
    snapshot: ParcelDataSnapshot,
    field: ParcelField,
    professional_results: Mapping[str, Any] | None,
) -> tuple[Any, str | None, dict[str, Any], str | None]:
    if field.source_kind == "model":
        return _model_field_value(snapshot, field, professional_results)

    if field.source_kind == "attribute":
        value = getattr(snapshot, field.attribute_name or field.source_field, None)
        if not _is_missing(value):
            return value, f"parcel_info.{field.attribute_name or field.source_field}", {}, None
        return None, None, {}, "field_value_missing"

    value = snapshot.indicators.get(field.source_field)
    provenance = _indicator_provenance(snapshot, field)
    if _is_missing(value):
        return None, f"parcel_info.soil_indicators.{field.source_field}", provenance, "field_value_missing"
    return value, f"parcel_info.soil_indicators.{field.source_field}", provenance, None


def _classification(field: ParcelField, value: Any) -> tuple[str | None, str | None]:
    if field.source_kind != "indicator":
        return None, None
    definition = INDICATOR_DEFINITIONS.get(field.key)
    if definition is None:
        return None, None
    bucket = definition.classify(value)
    if bucket is None:
        return None, None
    return bucket.label, bucket.range_label


def _format_value(value: Any, decimals: int, key: str | None = None) -> str:
    enum_label = _ENUM_LABELS.get(key or "", {}).get(str(value).casefold())
    if enum_label is not None:
        return enum_label
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, (int, float)):
        rendered = f"{float(value):.{decimals}f}"
        return rendered.rstrip("0").rstrip(".") if "." in rendered else rendered
    return str(value)


def _public_metadata_value(key: str, value: Any) -> str:
    if key == "measurement_year":
        return f"{value}年"
    if key == "data_source":
        return _SOURCE_LABELS.get(str(value), str(value))
    if key == "is_imputed":
        return "是" if bool(value) else "否"
    if key == "quality_flag":
        return _QUALITY_FLAG_LABELS.get(str(value), str(value))
    if key == "calculated_at" and isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _metadata_clauses(item: Mapping[str, Any], requested: Iterable[str]) -> list[str]:
    labels = {
        "measurement_year": "测量年份",
        "data_source": "数据来源",
        "is_imputed": "是否插补",
        "quality_flag": "质量标记",
        "model_version": "模型版本",
        "coefficient_version": "系数版本",
        "calculated_at": "计算时间",
    }
    provenance = item.get("provenance") if isinstance(item.get("provenance"), Mapping) else {}
    clauses: list[str] = []
    for key in requested:
        value = provenance.get(key)
        if _is_missing(value):
            clauses.append(f"{labels[key]}暂无记录")
        else:
            clauses.append(f"{labels[key]}为{_public_metadata_value(key, value)}")
    return clauses


def format_field_query_answer(field_query: dict[str, Any]) -> str:
    """Build the exact, non-LLM answer prefix used by HTTP and SSE paths."""
    parcel_id = field_query.get("parcel_id") or "当前地块"
    if field_query.get("status") == "parcel_not_found":
        return f"未找到地块 {parcel_id} 的指标快照。"
    if field_query.get("status") == "needs_indicator_for_metadata":
        return "请明确需要查询哪个指标的测量年份、数据来源、插补状态或质量标记。"

    clauses: list[str] = []
    requested_metadata = field_query.get("requested_metadata", [])
    for item in field_query.get("fields", []):
        label = item["label"]
        value = item.get("value")
        if value is None:
            if item.get("category") == "derived_model_result":
                clause = f"{label}暂无可发布的已验证模型结果"
            else:
                clause = f"{label}暂无记录"
            metadata = _metadata_clauses(item, requested_metadata)
            clauses.append("，".join([clause, *metadata]))
            continue
        rendered = _format_value(
            value, int(item.get("decimals", 2)), str(item.get("key") or ""),
        )
        unit = item.get("unit") or ""
        if unit and rendered.endswith(unit):
            unit = ""
        classification = item.get("classification")
        suffix = f"（{classification}）" if classification else ""
        clause = f"{label}为 {rendered}{unit}{suffix}"
        metadata = _metadata_clauses(item, requested_metadata)
        clauses.append("，".join([clause, *metadata]))
    return f"地块 {parcel_id}：" + "；".join(clauses) + "。"


def query_requested_parcel_fields(
    question: str,
    parcel_id: str | None,
    *,
    accessor: ParcelDataAccessor | None = None,
    professional_results: Mapping[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Resolve explicitly requested fields from one authoritative parcel row.

    ``None`` means the question does not ask for a supported raw field.  A
    structured result is returned even when the parcel or a field value is
    missing so the answer never silently falls back to "the model did not
    provide that value".
    """
    fields = requested_parcel_fields(question)
    metadata_fields = requested_metadata_fields(question)
    if (not fields and not metadata_fields) or not parcel_id:
        return None

    snapshot = (accessor or ParcelDataAccessor()).get_parcel_snapshot(str(parcel_id))
    if snapshot is None:
        result: dict[str, Any] = {
            "status": "parcel_not_found",
            "parcel_id": str(parcel_id),
            "fields": [],
            "source": "parcel_info",
        }
        result["answer"] = format_field_query_answer(result)
        return result

    if metadata_fields and not fields:
        result = {
            "status": "needs_indicator_for_metadata",
            "parcel_id": snapshot.parcel_id,
            "fields": [],
            "requested_metadata": list(metadata_fields),
            "preconditions": {
                "indicator_provenance": {
                    "met": False,
                    "rules": list(FIELD_CATEGORY_PRECONDITIONS["indicator_provenance"]),
                },
            },
            "source": "parcel_info.soil_indicators.indicator_provenance",
            "source_version": snapshot.source_version,
        }
        result["answer"] = format_field_query_answer(result)
        return result

    items: list[dict[str, Any]] = []
    for field in fields:
        value, value_source, provenance, unavailable_reason = _field_value(
            snapshot, field, professional_results,
        )
        classification, range_label = _classification(field, value)
        provenance = {**provenance, "snapshot_version": snapshot.source_version}
        items.append({
            "key": field.key,
            "source_field": field.source_field,
            "label": field.label,
            "value": value,
            "unit": field.unit,
            "decimals": field.decimals,
            "classification": classification,
            "classification_range": range_label,
            "category": field.category,
            "value_source": value_source,
            "preconditions_met": unavailable_reason is None,
            "preconditions": list(FIELD_CATEGORY_PRECONDITIONS[field.category]),
            "unavailable_reason": unavailable_reason,
            "provenance": provenance,
        })

    categories = dict.fromkeys(field.category for field in fields)
    result = {
        "status": "ok" if any(item["value"] is not None for item in items) else "missing",
        "parcel_id": snapshot.parcel_id,
        "fields": items,
        "requested_metadata": list(metadata_fields),
        "preconditions": {
            category: {
                "met": all(
                    item["preconditions_met"] for item in items
                    if item["category"] == category
                ),
                "rules": list(FIELD_CATEGORY_PRECONDITIONS[category]),
            }
            for category in categories
        },
        "source": "parcel_info + verified professional model results",
        "source_version": snapshot.source_version,
    }
    if metadata_fields:
        result["preconditions"]["indicator_provenance"] = {
            "met": all(
                all(not _is_missing(item["provenance"].get(key)) for key in metadata_fields)
                for item in items
            ),
            "rules": list(FIELD_CATEGORY_PRECONDITIONS["indicator_provenance"]),
        }
    result["answer"] = format_field_query_answer(result)
    return result


def prepend_field_answer(field_query: dict[str, Any] | None, answer: str | None) -> str:
    """Prepend the authoritative field sentence once to a generated answer."""
    field_answer = str((field_query or {}).get("answer") or "").strip()
    body = str(answer or "").strip()
    if not field_answer:
        return body
    if not body or body.startswith(field_answer):
        return field_answer if not body else body
    return f"{field_answer}\n\n{body}"


__all__: Iterable[str] = (
    "ParcelField",
    "format_field_query_answer",
    "prepend_field_answer",
    "query_requested_parcel_fields",
    "requested_metadata_fields",
    "requested_parcel_fields",
)
