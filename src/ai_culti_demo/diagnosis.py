from __future__ import annotations

from hashlib import sha1
from typing import Any

from .overview import get_county_overview


TOPIC_RULES: dict[str, dict[str, Any]] = {
    "acidification": {
        "name": "酸化诊断",
        "recommended_layers": ["acidification-risk", "soil_points"],
        "summary": "乐昌市酸化诊断接口已返回结构化占位结论，后续可接入真实酸化模型替换规则结果。",
        "evidence": [
            "三普表层土点位和测土配方点数据可作为酸化诊断候选输入。",
            "当前 change 仅验证接口契约与来源追溯，不宣称生产级酸化等级。",
        ],
        "recommendations": [
            "优先核验 pH、有机质、CEC 等字段映射。",
            "后续接入酸化模型时保留当前响应结构。",
        ],
    },
    "quality": {
        "name": "耕地质量总览",
        "recommended_layers": ["quality-overview", "cropland", "soil_points"],
        "summary": "乐昌市耕地质量总览接口已返回区域、图层和来源信息，可供未来 Agent 组合分析。",
        "evidence": [
            "行政边界、耕地掩膜和土壤点位已纳入基础数据目录。",
            "当前结果用于总览能力验证，质量等级需后续模型或规则补充。",
        ],
        "recommendations": [
            "先稳定区域与图层元数据，再扩展真实质量评价模型。",
            "对外输出时同步展示来源和可靠性标记。",
        ],
    },
    "improvement": {
        "name": "治理提升建议",
        "recommended_layers": ["quality-overview", "acidification-risk", "organic-matter"],
        "summary": "治理提升接口已基于当前可用图层返回结构化建议，适合后续报告整理与 Agent 二次加工。",
        "evidence": [
            "酸化风险、有机质水平和质量总览是首版治理建议的核心候选图层。",
            "当前建议来自规则模板，待真实诊断模型接入后增强。",
        ],
        "recommendations": [
            "按酸化、有机质和耕地范围三类图层组织治理优先级。",
            "将建议拆分为核验、分区、措施和报告四类后续行动。",
        ],
    },
}


def _diagnosis_id(payload: dict[str, Any]) -> str:
    raw = repr(sorted(payload.items())).encode("utf-8")
    return "diag_" + sha1(raw).hexdigest()[:12]


def diagnose_county(payload: dict[str, Any]) -> dict[str, Any]:
    """执行县域结构化诊断，首版使用可替换的规则结果。"""

    topic = payload.get("topic", "quality")
    area_code = payload.get("area_code", "lechang")
    if topic not in TOPIC_RULES:
        return {
            "status": "error",
            "error": {
                "code": "INVALID_TOPIC",
                "message": "topic 仅支持 acidification、quality、improvement",
            },
            "fallback": {"used": False, "fields": []},
        }

    overview = get_county_overview(area_code)
    if overview.get("status") != "ok":
        return overview

    rule = TOPIC_RULES[topic]
    missing_location = "longitude" not in payload or "latitude" not in payload
    fallback_fields = []
    if missing_location:
        fallback_fields.extend(["longitude", "latitude"])

    result = {
        "status": "ok",
        "diagnosis_id": _diagnosis_id(payload),
        "topic": {"id": topic, "name": rule["name"]},
        "area": overview["area"],
        "summary": rule["summary"],
        "evidence": rule["evidence"],
        "key_areas": [
            {
                "name": "乐昌市县域范围",
                "level": "county",
                "reason": "首版按县域整体返回，后续可接入镇界或格网分区。",
            }
        ],
        "recommended_layers": rule["recommended_layers"],
        "recommendations": rule["recommendations"],
        "fallback": {
            "used": bool(fallback_fields),
            "fields": fallback_fields,
            "strategy": "缺少坐标时使用县域级诊断；缺少模型字段时后续按最近邻或模板补齐。",
        },
        "lineage": {
            "overview_catalog": "data/lechang/catalog.json",
            "referenced_assets": [
                "external/AcidMap",
                "external/AcidificationModel/api",
            ],
            "runtime_dependency": "none",
        },
        "reliability": {
            "level": "demo_stub",
            "message": "当前诊断为结构化规则占位，目标是验证未来 Agent 调用契约。",
        },
    }
    return result
