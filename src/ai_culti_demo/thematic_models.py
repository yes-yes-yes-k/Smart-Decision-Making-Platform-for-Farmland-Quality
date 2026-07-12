from __future__ import annotations

from typing import Any

from .overview import get_county_overview


ModelSpec = dict[str, Any]


MODEL_SPECS: dict[str, ModelSpec] = {
    "spatial-structure-analysis": {
        "model_id": "spatial-structure-analysis",
        "name": "耕地质量空间结构解析模型",
        "purpose": "按区域、类型和图层组织县域耕地质量空间结构，用于总览和空间分区研判。",
        "minimum_inputs": ["area_code"],
        "recommended_layers": ["boundary", "cropland", "quality-overview"],
        "findings": [
            {"title": "空间组织", "content": "首版按县域整体组织空间结构，后续可细化到镇域或格网。"},
            {"title": "图层联动", "content": "行政边界、耕地范围和质量总览图层可作为空间结构解析的首批展示底图。"},
        ],
        "recommendations": [
            "先按县域和镇域两级组织空间结果。",
            "后续补入真实分区指标后再下钻到更细粒度。",
        ],
    },
    "soil-indicator-analysis": {
        "model_id": "soil-indicator-analysis",
        "name": "土壤关键指标多维解析模型",
        "purpose": "围绕 pH、有机质和养分等关键指标做多维占位解析，用于支撑专题判断。",
        "minimum_inputs": ["area_code"],
        "recommended_layers": ["soil_points", "organic-matter", "acidification-risk"],
        "findings": [
            {"title": "关键指标", "content": "Demo 重点关注 pH、有机质和养分三类指标，用于后续主题模型共享。"},
            {"title": "多维解析", "content": "当前以结构化占位方式表达指标关联，后续可替换为真实统计分析。"},
        ],
        "recommendations": [
            "优先核验 pH、有机质和主要养分字段映射。",
            "在真实模型接入前，保持指标字段名和单位约定稳定。",
        ],
        "fallback_fields": ["indicators"],
    },
    "obstacle-factor-identification": {
        "model_id": "obstacle-factor-identification",
        "name": "耕地质量主要障碍因素识别模型",
        "purpose": "识别限制耕地质量提升的主要障碍因素，并输出分级治理方向。",
        "minimum_inputs": ["area_code"],
        "recommended_layers": ["quality-overview", "acidification-risk", "organic-matter"],
        "findings": [
            {"title": "障碍识别", "content": "首版重点识别酸化风险、有机质不足和综合质量薄弱三类占位障碍。"},
            {"title": "治理方向", "content": "结果用于支撑后续单项治理和协同提升模型调用。"},
        ],
        "recommendations": [
            "先按主要障碍类型组织问题清单，再匹配治理措施。",
            "在真实模型替换前保留障碍类别字段和建议结构。",
        ],
        "fallback_fields": ["longitude", "latitude"],
    },
    "acidification-governance": {
        "model_id": "acidification-governance",
        "name": "土壤酸化治理模型",
        "purpose": "对酸化问题进行占位识别、治理需求分析和措施匹配。",
        "minimum_inputs": ["area_code"],
        "recommended_layers": ["acidification-risk", "soil_points"],
        "findings": [
            {"title": "问题识别", "content": "酸化治理模型以酸化风险图层和样点来源为基础返回结构化占位结论。"},
            {"title": "措施匹配", "content": "当前建议聚焦 pH 核验、区域复核和治理措施分层组织。"},
        ],
        "recommendations": [
            "优先核验酸化相关字段与分级阈值映射。",
            "在重点片区先做 pH 复核，再安排分区治理措施。",
        ],
        "fallback_fields": ["longitude", "latitude"],
    },
    "organic-matter-improvement": {
        "model_id": "organic-matter-improvement",
        "name": "土壤有机质提升模型",
        "purpose": "对有机质不足问题进行占位识别、提升需求分析和措施匹配。",
        "minimum_inputs": ["area_code"],
        "recommended_layers": ["organic-matter", "soil_points", "cropland"],
        "findings": [
            {"title": "问题识别", "content": "有机质提升模型以样点和有机质图层为基础返回结构化占位判断。"},
            {"title": "提升方向", "content": "当前建议围绕培肥、秸秆还田和区域复核三类措施组织。"},
        ],
        "recommendations": [
            "先确认有机质水平图层与样点表字段映射。",
            "将提升建议拆分为核验、培肥和持续监测三类动作。",
        ],
        "fallback_fields": ["longitude", "latitude"],
    },
    "multi-factor-collaborative-improvement": {
        "model_id": "multi-factor-collaborative-improvement",
        "name": "耕地质量多项协同提升模型",
        "purpose": "综合多个专题模型的占位结果，形成分区分类的综合提升建议。",
        "minimum_inputs": ["area_code"],
        "recommended_layers": ["quality-overview", "acidification-risk", "organic-matter"],
        "findings": [
            {"title": "协同组合", "content": "协同提升模型综合酸化治理、障碍识别和有机质提升等专题结果生成总建议。"},
            {"title": "分区分类", "content": "首版按全县重点治理区、常规提升区和持续监测区三类输出综合方向。"},
        ],
        "recommendations": [
            "先按主要障碍与提升主题划分重点治理区。",
            "后续可在镇域或格网尺度叠加真实模型输出做精细分区。",
        ],
        "dependent_models": [
            "acidification-governance",
            "organic-matter-improvement",
            "obstacle-factor-identification",
        ],
        "zoning_recommendations": [
            {
                "zone": "重点治理区",
                "focus": "酸化风险与综合障碍叠加区域优先核验并治理。",
            },
            {
                "zone": "常规提升区",
                "focus": "以有机质提升和耕地培肥措施为主，保持常态化改良。",
            },
            {
                "zone": "持续监测区",
                "focus": "维持监测和图层复核，为后续真实模型替换保留比对基线。",
            },
        ],
        "fallback_fields": ["longitude", "latitude", "indicators"],
    },
}


def _lineage_for_model(model: ModelSpec) -> dict[str, Any]:
    return {
        "catalog": "data/lechang/catalog.json",
        "referenced_assets": [
            "D:\\work\\AcidMap",
            "D:\\work\\suan\\AcidificationModel\\api",
        ],
        "runtime_dependency": "none",
        "recommended_layers": model["recommended_layers"],
    }


def _reliability() -> dict[str, str]:
    return {
        "level": "demo_stub",
        "message": "当前专题模型结果仅用于 Demo 演示多模型调用契约，不代表真实专业模型结论。",
    }


def _base_model_descriptor(model: ModelSpec) -> dict[str, Any]:
    descriptor = {
        "model_id": model["model_id"],
        "name": model["name"],
        "purpose": model["purpose"],
        "minimum_inputs": model["minimum_inputs"],
        "recommended_layers": model["recommended_layers"],
    }
    if model.get("dependent_models"):
        descriptor["dependent_models"] = model["dependent_models"]
    return descriptor


def list_thematic_models(area_code: str = "lechang") -> dict[str, Any]:
    """返回可供大模型或 Agent 列举的专题模型目录。"""

    overview = get_county_overview(area_code)
    if overview.get("status") != "ok":
        return overview

    return {
        "status": "ok",
        "area": overview["area"],
        "models": [_base_model_descriptor(model) for model in MODEL_SPECS.values()],
        "lineage": {
            "catalog": "data/lechang/catalog.json",
            "runtime_dependency": "none",
        },
        "reliability": _reliability(),
    }


def _fallback_for_payload(payload: dict[str, Any], model: ModelSpec) -> dict[str, Any]:
    fields: list[str] = []
    if payload.get("longitude") is None:
        fields.append("longitude")
    if payload.get("latitude") is None:
        fields.append("latitude")
    if "indicators" in model.get("fallback_fields", []) and not payload.get("indicators"):
        fields.append("indicators")

    unique_fields = list(dict.fromkeys(fields))
    return {
        "used": bool(unique_fields),
        "fields": unique_fields,
        "strategy": "缺少坐标时按县域级占位结果返回；缺少指标时使用 Demo 默认上下文补齐。",
    }


def _single_model_result(payload: dict[str, Any], model: ModelSpec, area: dict[str, Any]) -> dict[str, Any]:
    result = {
        "status": "ok",
        "model": _base_model_descriptor(model),
        "area": area,
        "summary": f"{model['name']} 已返回结构化 Demo 结果，可供大模型继续编排调用。",
        "findings": model["findings"],
        "recommended_layers": model["recommended_layers"],
        "recommendations": model["recommendations"],
        "lineage": _lineage_for_model(model),
        "reliability": _reliability(),
        "fallback": _fallback_for_payload(payload, model),
    }
    if payload.get("context"):
        result["context"] = payload["context"]
    return result


def _collaborative_result(payload: dict[str, Any], model: ModelSpec, area: dict[str, Any]) -> dict[str, Any]:
    result = _single_model_result(payload, model, area)
    result["dependent_models"] = model["dependent_models"]
    result["zoning_recommendations"] = model["zoning_recommendations"]
    result["summary"] = "多项协同提升模型已综合多个专题模型的 Demo 结果，形成分区分类的综合建议。"
    return result


def run_thematic_model(payload: dict[str, Any]) -> dict[str, Any]:
    """执行单个模拟专题模型。"""

    model_id = payload.get("model_id")
    if not model_id:
        return {
            "status": "error",
            "error": {
                "code": "MISSING_MODEL_ID",
                "message": "调用专题模型时必须提供 model_id",
            },
        }

    model = MODEL_SPECS.get(model_id)
    if model is None:
        return {
            "status": "error",
            "error": {
                "code": "INVALID_MODEL_ID",
                "message": "model_id 不在当前已注册的 6 个模拟专题模型目录中",
            },
            "supported_model_ids": list(MODEL_SPECS.keys()),
        }

    area_code = payload.get("area_code", "lechang")
    overview = get_county_overview(area_code)
    if overview.get("status") != "ok":
        return overview

    if model_id == "multi-factor-collaborative-improvement":
        return _collaborative_result(payload, model, overview["area"])
    return _single_model_result(payload, model, overview["area"])
