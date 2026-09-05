from __future__ import annotations

import logging
from copy import deepcopy
from hashlib import sha1
from numbers import Real
from typing import Any, Mapping

from .overview import _normalize_area_code, get_county_overview


logger = logging.getLogger(__name__)

ADVISORY_RESULT_KIND = "advisory_only"
UNAVAILABLE_PREDICTION = "validated_prediction_unavailable"
UNAVAILABLE_STATISTICS = "validated_statistics_unavailable"
UNAVAILABLE_PRICE = "price_basis_unavailable"

_METRIC_META_KEYS = {
    "status",
    "reason",
    "unit",
    "source",
    "method",
    "model_version",
    "calculated_at",
    "scope",
}
_QUANTITATIVE_COLLECTIONS = {
    "problems": ("percent",),
    "problem_distribution": ("percent",),
    "measures": ("cost", "improve", "period"),
    "treatments": ("cost", "improve", "period"),
    "regions": ("weight", "effect"),
    "base_data": ("weight", "effect"),
}


class DiagnosisContractError(ValueError):
    """Raised when a county diagnosis violates the quantitative safety contract."""


TOPIC_RULES: dict[str, dict[str, Any]] = {
    "acidification": {
        "name": "酸化诊断",
        "recommended_layers": ["acidification-risk", "soil_points"],
        "summary": "当前仅提供酸化相关的定性核验方向，不提供治理时效、提升幅度或成本预测。",
        "evidence": [
            "三普表层土点位和测土配方点数据可作为后续酸化诊断候选输入。",
            "当前县域接口尚未接入可验证的治理效果预测或县域统计结果。",
        ],
        "recommendations": [
            "先核验 pH、有机质、CEC、交换性氢和交换性铝等字段及数据时间。",
            "需要具体施用量时使用正式酸化改良模型并保留模型版本与输入来源。",
        ],
    },
    "quality": {
        "name": "耕地质量总览",
        "recommended_layers": ["quality-overview", "cropland", "soil_points"],
        "summary": "当前仅提供耕地质量核验方向和推荐图层，不提供无统计依据的问题占比或区域排序。",
        "evidence": [
            "行政边界、耕地掩膜和土壤点位已纳入基础数据目录。",
            "当前县域接口尚未接入可验证的县域质量等级与障碍统计结果。",
        ],
        "recommendations": [
            "先核验区域、图层元数据和土壤指标覆盖范围。",
            "需要质量等级或障碍占比时调用正式专业模型并使用真实统计结果。",
        ],
    },
    "improvement": {
        "name": "治理提升建议",
        "recommended_layers": ["quality-overview", "acidification-risk", "organic-matter"],
        "summary": "当前仅提供治理工作的定性组织建议，不提供周期、投资、提升率或效果预测。",
        "evidence": [
            "酸化风险、有机质水平和质量总览是治理前应优先核验的候选图层。",
            "当前县域接口没有治理响应曲线、价格口径或长期监测数据。",
        ],
        "recommendations": [
            "按数据核验、专业模型计算、空间分区和监测复核组织治理工作。",
            "在获得模型结果和现场价格依据前，不展示定量周期、成本或效果。",
        ],
    },
}

_PROBLEM_GUIDANCE: dict[str, list[tuple[str, str]]] = {
    "quality": [
        ("土壤有机质状况待核验", "#f5222d"),
        ("耕层条件待核验", "#fa8c16"),
        ("土壤酸化风险待核验", "#fadb14"),
        ("灌溉排水条件待核验", "#52c41a"),
        ("障碍因子组合待专业模型确认", "#40a9ff"),
    ],
    "acidification": [
        ("土壤酸化风险待核验", "#f5222d"),
        ("交换性酸指标待核验", "#fa8c16"),
        ("土壤缓冲能力待核验", "#fadb14"),
        ("有机质协同条件待核验", "#52c41a"),
        ("空间分布待真实数据统计", "#40a9ff"),
    ],
    "improvement": [
        ("治理对象与基础指标待核验", "#f5222d"),
        ("专业模型结果待接入", "#fa8c16"),
        ("措施适用范围待确认", "#fadb14"),
        ("成本与时效暂无可靠估计", "#52c41a"),
        ("长期监测机制待建立", "#40a9ff"),
    ],
}

_MEASURE_GUIDANCE = [
    {
        "name": "有机质培肥措施",
        "apply": "适用于经检测和专业模型确认的有机质不足地块",
        "icon": "TrendCharts",
        "icon_bg": "#f6ffed",
        "icon_color": "#52c41a",
    },
    {
        "name": "土壤酸化改良措施",
        "apply": "适用于经检测和专业模型确认的酸化地块",
        "icon": "DataLine",
        "icon_bg": "#e6f7ff",
        "icon_color": "#1890ff",
    },
    {
        "name": "灌溉排水条件改善",
        "apply": "适用于经现场核验存在灌排限制的地块",
        "icon": "Location",
        "icon_bg": "#e6f7ff",
        "icon_color": "#13c2c2",
    },
    {
        "name": "耕层条件改良措施",
        "apply": "适用于经现场核验存在耕层限制的地块",
        "icon": "Warning",
        "icon_bg": "#fff7e6",
        "icon_color": "#fa8c16",
    },
]


def _diagnosis_id(payload: dict[str, Any]) -> str:
    raw = repr(sorted(payload.items())).encode("utf-8")
    return "diag_" + sha1(raw).hexdigest()[:12]


def unavailable_metric(
    reason: str,
    *,
    unit: str | None,
    scope: Mapping[str, Any],
) -> dict[str, Any]:
    """Build complete metadata for a quantitative field that is unavailable."""

    return {
        "status": "unavailable",
        "reason": reason,
        "unit": unit,
        "source": None,
        "method": None,
        "model_version": None,
        "calculated_at": None,
        "scope": dict(scope),
    }


def _validate_metric(item: Mapping[str, Any], field: str, path: str) -> bool:
    meta_by_field = item.get("metric_meta")
    if not isinstance(meta_by_field, Mapping):
        raise DiagnosisContractError(f"{path}.{field} 缺少 metric_meta")

    meta = meta_by_field.get(field)
    if not isinstance(meta, Mapping):
        raise DiagnosisContractError(f"{path}.{field} 缺少字段级依据")

    missing_keys = _METRIC_META_KEYS - set(meta)
    if missing_keys:
        missing = ", ".join(sorted(missing_keys))
        raise DiagnosisContractError(f"{path}.{field} 元数据缺少字段: {missing}")

    value = item.get(field)
    status = meta.get("status")
    if status == "unavailable":
        if value is not None:
            raise DiagnosisContractError(f"{path}.{field} 不可用时值必须为 null")
        if not meta.get("reason"):
            raise DiagnosisContractError(f"{path}.{field} 不可用时必须说明原因")
        return False

    if status != "available":
        raise DiagnosisContractError(f"{path}.{field} 使用未知状态: {status!r}")
    if value is None:
        raise DiagnosisContractError(f"{path}.{field} 标记可用时值不能为空")
    if field != "period" and (isinstance(value, bool) or not isinstance(value, Real)):
        raise DiagnosisContractError(f"{path}.{field} 必须是数值")

    for key in ("source", "method", "calculated_at"):
        if not meta.get(key):
            raise DiagnosisContractError(f"{path}.{field} 可用时缺少 {key}")
    if not isinstance(meta.get("scope"), Mapping) or not meta["scope"]:
        raise DiagnosisContractError(f"{path}.{field} 可用时缺少 scope")
    return True


def validate_diagnosis_response(result: Mapping[str, Any]) -> None:
    """Validate all county-diagnosis aliases before the response is exposed."""

    available_metrics = 0
    for collection, fields in _QUANTITATIVE_COLLECTIONS.items():
        items = result.get(collection, [])
        if not isinstance(items, list):
            raise DiagnosisContractError(f"{collection} 必须是数组")
        for index, item in enumerate(items):
            if not isinstance(item, Mapping):
                raise DiagnosisContractError(f"{collection}[{index}] 必须是对象")
            for field in fields:
                if field in item:
                    available_metrics += int(
                        _validate_metric(item, field, f"{collection}[{index}]")
                    )

    reliability = result.get("reliability")
    if isinstance(reliability, Mapping):
        declared_availability = reliability.get("quantitative_available")
        if declared_availability is not bool(available_metrics):
            raise DiagnosisContractError(
                "顶层 quantitative_available 与字段级定量状态不一致"
            )

    if result.get("result_kind") == ADVISORY_RESULT_KIND:
        if result.get("status") != "degraded":
            raise DiagnosisContractError("advisory_only 必须使用 degraded 状态")
        if not isinstance(reliability, Mapping):
            raise DiagnosisContractError("advisory_only 缺少 reliability")
        if reliability.get("predictive") is not False:
            raise DiagnosisContractError("advisory_only 必须标记 predictive=false")
        if reliability.get("quantitative_available") is not False:
            raise DiagnosisContractError(
                "advisory_only 必须标记 quantitative_available=false"
            )
        if available_metrics:
            raise DiagnosisContractError("advisory_only 不得包含可用定量指标")


def _problem(name: str, color: str, scope: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "name": name,
        "percent": None,
        "color": color,
        "advisory_only": True,
        "basis": "template_guidance",
        "metric_meta": {
            "percent": unavailable_metric(
                UNAVAILABLE_STATISTICS,
                unit="%",
                scope=scope,
            )
        },
    }


def _measure(template: Mapping[str, Any], scope: Mapping[str, Any]) -> dict[str, Any]:
    return {
        **template,
        "cost": None,
        "improve": None,
        "period": None,
        "advisory_only": True,
        "basis": "template_guidance",
        "metric_meta": {
            "cost": unavailable_metric(
                UNAVAILABLE_PRICE,
                unit=None,
                scope=scope,
            ),
            "improve": unavailable_metric(
                UNAVAILABLE_PREDICTION,
                unit="ratio",
                scope=scope,
            ),
            "period": unavailable_metric(
                UNAVAILABLE_PREDICTION,
                unit=None,
                scope=scope,
            ),
        },
    }


def diagnose_county(payload: dict[str, Any]) -> dict[str, Any]:
    """Return safe county-level qualitative guidance with explicit evidence limits."""

    topic = payload.get("topic", "quality")
    raw_area_code = payload.get("area_code", "lechang")
    area_code = _normalize_area_code(raw_area_code)
    payload = {**payload, "area_code": area_code}
    if topic not in TOPIC_RULES:
        return {
            "status": "error",
            "message": "topic 仅支持 acidification、quality、improvement",
            "error": {
                "code": "INVALID_TOPIC",
                "message": "topic 仅支持 acidification、quality、improvement",
            },
            "fallback": {"used": False, "fields": []},
        }

    overview = get_county_overview(area_code)
    if overview.get("status") != "ok":
        err = overview.get("error") or {}
        overview.setdefault("message", err.get("message", "区域暂不支持"))
        return overview

    rule = TOPIC_RULES[topic]
    scope = {"type": "county", "id": area_code}
    fallback_fields = ["validated_quantitative_results"]
    if "longitude" not in payload or "latitude" not in payload:
        fallback_fields.extend(["longitude", "latitude"])

    problems = [
        _problem(name, color, scope)
        for name, color in _PROBLEM_GUIDANCE[topic]
    ]
    measures = [_measure(item, scope) for item in _MEASURE_GUIDANCE]
    if topic == "acidification":
        measures = [
            item
            for item in measures
            if "酸化" in item["name"] or "有机质" in item["name"]
        ]

    result: dict[str, Any] = {
        "status": "degraded",
        "result_kind": ADVISORY_RESULT_KIND,
        "diagnosis_id": _diagnosis_id(payload),
        "topic": {"id": topic, "name": rule["name"]},
        "area": overview["area"],
        "summary": rule["summary"],
        "evidence": rule["evidence"],
        "key_areas": [
            {
                "name": "乐昌市县域范围",
                "level": "county",
                "reason": "当前仅用于指向县域范围，不代表重点区域排序。",
                "advisory_only": True,
                "basis": "template_guidance",
            }
        ],
        "recommended_layers": rule["recommended_layers"],
        "recommendations": rule["recommendations"],
        "problems": problems,
        "problem_distribution": deepcopy(problems),
        "measures": measures,
        "treatments": deepcopy(measures),
        "regions": [],
        "base_data": [],
        "regions_status": {
            "status": "unavailable",
            "reason": UNAVAILABLE_STATISTICS,
            "message": "当前没有可验证的县域重点区域、权重或治理效果排序。",
        },
        "quantitative_estimates": {
            "status": "unavailable",
            "reason": "validated_quantitative_results_unavailable",
            "fields": ["percent", "cost", "improve", "period", "weight", "effect"],
        },
        "fallback": {
            "used": True,
            "fields": fallback_fields,
            "strategy": (
                "当前仅返回县域级定性建议；缺少坐标或专业模型结果时，"
                "不会使用模板值补齐定量结论。"
            ),
        },
        "lineage": {
            "overview_catalog": "data/lechang/catalog.json",
            "guidance_source": "template_guidance",
            "referenced_assets": [
                "external/AcidMap",
                "external/AcidificationModel/api",
            ],
            "runtime_dependency": "none",
        },
        "reliability": {
            "level": "insufficient_evidence",
            "predictive": False,
            "quantitative_available": False,
            "message": (
                "当前结果仅为定性核验与治理方向，不包含可靠的周期、提升率、"
                "治理效果、成本或问题占比。"
            ),
        },
    }

    try:
        validate_diagnosis_response(result)
    except DiagnosisContractError as exc:
        logger.error("县域诊断响应契约校验失败: %s", exc)
        return {
            "status": "error",
            "message": "县域诊断响应未通过安全校验",
            "error": {
                "code": "DIAGNOSIS_CONTRACT_ERROR",
                "message": str(exc),
            },
            "fallback": {"used": False, "fields": []},
        }
    return result
