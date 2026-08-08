from __future__ import annotations

from typing import Any

from .overview import get_county_overview
from framework.agents.capabilities import (
    LEGACY_MODEL_ALIASES,
    PROFESSIONAL_CAPABILITIES,
    get_capability_by_model_id,
    public_capability_descriptor,
)

try:
    from .farmland_diagnosis import query_parcel, query_acidification, DiagnosisStorage
    DIAGNOSIS_MODEL_AVAILABLE = True
except ImportError:
    DIAGNOSIS_MODEL_AVAILABLE = False
    query_parcel = None
    query_acidification = None
    DiagnosisStorage = None

try:
    from .farmland_stability import StabilityStorage, get_parcel_result
    STABILITY_MODEL_AVAILABLE = True
except ImportError:
    STABILITY_MODEL_AVAILABLE = False
    StabilityStorage = None
    get_parcel_result = None

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
        "purpose": "基于耕地质量评价结果，识别限制耕地质量提升的主要障碍因素，判定障碍类型（单一障碍/多障碍），并输出分级治理方向。",
        "minimum_inputs": ["parcel_id"],
        "recommended_layers": ["quality-overview", "acidification-risk", "organic-matter"],
        "findings": [
            {"title": "障碍识别", "content": "基于隶属度评价结果，识别障碍因子并判定障碍程度（轻度/中度/重度）。"},
            {"title": "障碍类型判定", "content": "根据障碍度阈值判定障碍类型：单一障碍（仅一个主要障碍）、多障碍（多个障碍因子叠加）。"},
            {"title": "治理方向", "content": "结果用于支撑后续单项治理和协同提升模型调用。"},
        ],
        "recommendations": [
            "先按主要障碍类型组织问题清单，再匹配治理措施。",
            "在真实模型替换前保留障碍类别字段和建议结构。",
        ],
        "fallback_fields": ["longitude", "latitude", "parcel_id"],
        "real_model": "farmland_diagnosis",
    },
    "acidification-governance": {
        "model_id": "acidification-governance",
        "name": "土壤酸化治理模型",
        "purpose": "对酸化问题进行分区识别、治理需求分析和改良措施匹配，生成针对性的酸化改良方案。",
        "minimum_inputs": ["parcel_id"],
        "recommended_layers": ["acidification-risk", "soil_points"],
        "findings": [
            {"title": "酸化分区", "content": "基于 pH 值进行酸化程度分区：强酸性(pH<4.5)、酸性(4.5≤pH<5.5)、微酸性(5.5≤pH<6.5)、中性(6.5≤pH<7.5)、碱性(pH≥7.5)。"},
            {"title": "改良方案", "content": "根据酸化程度和有机质含量生成针对性改良方案，包括石灰施用量、有机肥建议等。"},
            {"title": "措施匹配", "content": "当前建议聚焦 pH 核验、区域复核和治理措施分层组织。"},
        ],
        "recommendations": [
            "优先核验酸化相关字段与分级阈值映射。",
            "在重点片区先做 pH 复核，再安排分区治理措施。",
            "结合有机质含量调整改良方案，有机质不足时增加有机肥施用量。",
        ],
        "fallback_fields": ["longitude", "latitude", "parcel_id"],
        "real_model": "farmland_acidification",
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
    "stability-risk-evaluation": {
        "model_id": "stability-risk-evaluation",
        "name": "耕地质量稳定性与退化风险评价模型",
        "purpose": "基于3期历史数据，通过九模块综合评价耕地质量稳定性和退化风险，包括等级边界安全度、指标支撑均衡度、关键指标临界度、空间邻域一致性、历史变化趋势、掉级风险、关键因子退化风险、退化空间集聚风险和持续低质风险。",
        "minimum_inputs": ["parcel_id"],
        "recommended_layers": ["quality-overview", "degradation-risk"],
        "findings": [
            {"title": "稳定性评价", "content": "通过九模块综合评价耕地质量的稳定性状况。"},
            {"title": "退化风险", "content": "评估掉级风险、关键因子退化风险、退化空间集聚风险和持续低质风险。"},
            {"title": "历史趋势", "content": "基于2018/2021/2024三期数据评估历史变化趋势。"},
        ],
        "recommendations": [
            "先运行离线预计算处理shapefile数据，再进行在线查询。",
            "支持按module参数查询特定模块结果。",
        ],
        "fallback_fields": ["longitude", "latitude", "parcel_id"],
        "real_model": "farmland_stability",
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

# 这些能力没有对应的专业 Agent，保留为独立辅助/实验能力，不能混入正式专业模型目录。
NON_PROFESSIONAL_CATEGORIES = {
    "spatial-structure-analysis": "auxiliary",
    "soil-indicator-analysis": "auxiliary",
    "multi-factor-collaborative-improvement": "experimental",
}


def _lineage_for_model(model: ModelSpec) -> dict[str, Any]:
    return {
        "catalog": "data/lechang/catalog.json",
        "referenced_assets": [
            "external/AcidMap",
            "external/AcidificationModel/api",
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


def list_thematic_models(
    area_code: str = "lechang", *, include_non_professional: bool = False
) -> dict[str, Any]:
    """返回正式专业模型目录，可选附带辅助和实验性能力。"""

    overview = get_county_overview(area_code)
    if overview.get("status") != "ok":
        return overview

    models = [public_capability_descriptor(capability) for capability in PROFESSIONAL_CAPABILITIES]
    if include_non_professional:
        for model_id, category in NON_PROFESSIONAL_CATEGORIES.items():
            descriptor = _base_model_descriptor(MODEL_SPECS[model_id])
            descriptor.update({
                "category": category,
                "chat_routable": False,
                "runtime_requirement": "当前为独立辅助/实验能力，不调用专业 Agent。",
            })
            models.append(descriptor)

    return {
        "status": "ok",
        "area": overview["area"],
        "models": models,
        "lineage": {
            "catalog": "data/lechang/catalog.json",
            "runtime_dependency": "none",
        },
        "reliability": {
            "level": "mixed",
            "message": "正式能力按各 Agent 的真实/模拟状态返回；辅助和实验性能力明确标注为 Demo。",
        },
    }


def _run_professional_capability(payload: dict[str, Any], requested_model_id: str) -> dict[str, Any]:
    """延迟创建专业 Agent，避免专题模块与 Agent 实现产生导入环。"""
    capability = get_capability_by_model_id(requested_model_id)
    if capability is None:
        raise ValueError(f"未找到正式能力：{requested_model_id}")

    try:
        from framework.agents.manager import AgentManager

        agent = AgentManager().agents[capability.agent_id]
        result = agent.analyze(payload)
        result["model"] = public_capability_descriptor(capability)
        result["capability"] = public_capability_descriptor(capability)
        result.setdefault("recommended_layers", [])
        result.setdefault("area", {"code": payload.get("area_code", "lechang")})
        if requested_model_id in LEGACY_MODEL_ALIASES:
            result["deprecation"] = {
                "deprecated_model_id": requested_model_id,
                "canonical_model_id": capability.model_id,
                "message": "该模型标识已弃用，请迁移到 canonical_model_id。",
            }
        return result
    except Exception as exc:
        return {
            "status": "error",
            "model": public_capability_descriptor(capability),
            "capability": public_capability_descriptor(capability),
            "error": {
                "code": "PROFESSIONAL_AGENT_ERROR",
                "message": f"专业能力执行失败：{exc}",
            },
            "reliability": {"level": "unavailable", "message": "专业 Agent 未能完成分析。"},
            "fallback": {"used": True, "fields": [], "strategy": "不调用其他专业模型。"},
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


def _run_real_diagnosis_model(payload: dict[str, Any], model: ModelSpec) -> dict[str, Any]:
    """调用实际的障碍诊断模型"""
    parcel_id = payload.get("parcel_id")
    db_path = payload.get("db_path")

    if not parcel_id:
        return {
            "status": "error",
            "error": {
                "code": "MISSING_PARCEL_ID",
                "message": "调用障碍诊断模型时必须提供 parcel_id",
            },
        }

    result = query_parcel(parcel_id, db_path)

    if result["status"] == "not_ready":
        return {
            "status": "error",
            "error": {
                "code": "DIAGNOSIS_NOT_READY",
                "message": "诊断数据尚未就绪，请先运行批量评价和诊断流程",
            },
        }

    if result["status"] == "not_found":
        return {
            "status": "error",
            "error": {
                "code": "PARCEL_NOT_FOUND",
                "message": f"未找到地块 {parcel_id} 的诊断数据",
            },
        }

    diagnosis = result.get("diagnosis", {})
    evaluation = result.get("evaluation", {})

    return {
        "status": "ok",
        "model": _base_model_descriptor(model),
        "area": {"name": "地块诊断", "code": parcel_id},
        "summary": f"{model['name']} 已返回实际诊断结果。障碍类型：{diagnosis.get('ZALX', '未知')}",
        "findings": [
            {"title": "障碍类型", "content": diagnosis.get('ZALX', '无明显障碍')},
            {"title": "主要障碍因素", "content": diagnosis.get('ZYZAYS', '') or "无"},
            {"title": "次要障碍因素", "content": diagnosis.get('CYZAYS', '') or "无"},
            {"title": "质量等级", "content": f"综合等级：{evaluation.get('GDZLDJ', '未知')}"},
        ],
        "recommended_layers": model["recommended_layers"],
        "recommendations": [
            f"针对{diagnosis.get('ZALX', '')}问题，建议优先治理主要障碍因素",
            "结合酸化治理模型制定综合改良方案",
        ],
        "lineage": _lineage_for_model(model),
        "reliability": {
            "level": "real_model",
            "message": "当前结果来自实际耕地质量诊断模型计算。",
        },
        "fallback": {"used": False, "fields": [], "strategy": "已使用实际模型计算"},
        "diagnosis_detail": diagnosis,
        "evaluation_detail": evaluation,
    }


def _run_real_acidification_model(payload: dict[str, Any], model: ModelSpec) -> dict[str, Any]:
    """调用实际的酸化改良模型"""
    parcel_id = payload.get("parcel_id")
    db_path = payload.get("db_path")

    if not parcel_id:
        return {
            "status": "error",
            "error": {
                "code": "MISSING_PARCEL_ID",
                "message": "调用酸化改良模型时必须提供 parcel_id",
            },
        }

    result = query_acidification(parcel_id, db_path)

    if result["status"] == "not_ready":
        return {
            "status": "error",
            "error": {
                "code": "ACIDIFICATION_NOT_READY",
                "message": "酸化改良数据尚未就绪，请先运行批量评价和酸化评估流程",
            },
        }

    if result["status"] == "not_found":
        return {
            "status": "error",
            "error": {
                "code": "PARCEL_NOT_FOUND",
                "message": f"未找到地块 {parcel_id} 的酸化改良数据",
            },
        }

    acidification = result.get("acidification", {})

    return {
        "status": "ok",
        "model": _base_model_descriptor(model),
        "area": {"name": "地块酸化改良", "code": parcel_id},
        "summary": f"{model['name']} 已返回实际改良方案。酸化程度：{acidification.get('acidification_level', '未知')}",
        "findings": [
            {"title": "酸化程度", "content": acidification.get('acidification_level', '未知')},
            {"title": "改良需求", "content": "需要改良" if acidification.get('need_amendment', False) else "无需改良"},
            {"title": "石灰需求量", "content": f"{acidification.get('lime_demand', 0)} kg/亩"},
            {"title": "改良剂类型", "content": acidification.get('amendment_type', '有机肥')},
        ],
        "recommended_layers": model["recommended_layers"],
        "recommendations": [
            f"根据酸化程度，建议施用{acidification.get('amendment_type', '')}，施用量 {acidification.get('amendment_rate', 0)} kg/亩",
            acidification.get('reason', ''),
        ],
        "lineage": _lineage_for_model(model),
        "reliability": {
            "level": "real_model",
            "message": "当前结果来自实际耕地酸化改良模型计算。",
        },
        "fallback": {"used": False, "fields": [], "strategy": "已使用实际模型计算"},
        "acidification_detail": acidification,
    }


def _run_real_stability_model(payload: dict[str, Any], model: ModelSpec) -> dict[str, Any]:
    """调用实际的稳定性风险评价模型"""
    parcel_id = payload.get("parcel_id")
    module = payload.get("module")
    db_path = payload.get("db_path")

    if not parcel_id:
        return {
            "status": "error",
            "error": {
                "code": "MISSING_PARCEL_ID",
                "message": "调用稳定性风险模型时必须提供 parcel_id",
            },
        }

    storage = StabilityStorage(db_path)

    if not storage.is_ready():
        return {
            "status": "error",
            "error": {
                "code": "STABILITY_NOT_READY",
                "message": "稳定性风险数据尚未就绪，请先运行离线预计算流程",
            },
        }

    result = storage.get_result(parcel_id, module)

    if result is None:
        return {
            "status": "error",
            "error": {
                "code": "PARCEL_NOT_FOUND",
                "message": f"未找到地块 {parcel_id} 的稳定性风险数据",
            },
        }

    return {
        "status": "ok",
        "model": _base_model_descriptor(model),
        "area": {"name": "地块稳定性评价", "code": parcel_id},
        "summary": f"{model['name']} 已返回实际评价结果。地块ID：{parcel_id}",
        "findings": [
            {"title": "质量等级", "content": f"等级：{result.get('grade', '未知')}"},
            {"title": "综合得分", "content": f"综合指数：{result.get('score', '未知')}"},
            {"title": "九模块评价", "content": "已完成等级边界安全度、指标支撑均衡度、关键指标临界度、空间邻域一致性、历史变化趋势、掉级风险、关键因子退化风险、退化空间集聚风险和持续低质风险评价"},
        ],
        "recommended_layers": model["recommended_layers"],
        "recommendations": [
            "结合障碍诊断模型制定综合治理方案",
            "关注持续低质风险较高的区域",
        ],
        "lineage": _lineage_for_model(model),
        "reliability": {
            "level": "real_model",
            "message": "当前结果来自实际耕地质量稳定性与退化风险评价模型计算。",
        },
        "fallback": {"used": False, "fields": [], "strategy": "已使用实际模型计算"},
        "stability_detail": result,
    }


def run_thematic_model(payload: dict[str, Any]) -> dict[str, Any]:
    """执行正式专业模型或独立辅助/实验性能力。"""

    model_id = payload.get("model_id")
    if not model_id:
        return {
            "status": "error",
            "error": {
                "code": "MISSING_MODEL_ID",
                "message": "调用专题模型时必须提供 model_id",
            },
        }

    # 正式专业能力优先由对应 Agent 的统一结构化分析入口执行。
    if get_capability_by_model_id(model_id) is not None:
        return _run_professional_capability(payload, model_id)

    model = MODEL_SPECS.get(model_id)
    if model is None:
        return {
            "status": "error",
            "error": {
                "code": "INVALID_MODEL_ID",
                "message": "model_id 不在当前已注册的正式、辅助或实验性能力目录中",
            },
            "supported_model_ids": [
                capability.model_id for capability in PROFESSIONAL_CAPABILITIES
            ] + list(NON_PROFESSIONAL_CATEGORIES),
        }

    # 检查是否有实际模型实现
    real_model = model.get("real_model")
    if real_model:
        if real_model == "farmland_diagnosis" and payload.get("parcel_id") and DIAGNOSIS_MODEL_AVAILABLE:
            return _run_real_diagnosis_model(payload, model)
        elif real_model == "farmland_acidification" and payload.get("parcel_id") and DIAGNOSIS_MODEL_AVAILABLE:
            return _run_real_acidification_model(payload, model)
        elif real_model == "farmland_stability" and payload.get("parcel_id") and STABILITY_MODEL_AVAILABLE:
            return _run_real_stability_model(payload, model)

    area_code = payload.get("area_code", "lechang")
    overview = get_county_overview(area_code)
    if overview.get("status") != "ok":
        return overview

    if model_id == "multi-factor-collaborative-improvement":
        result = _collaborative_result(payload, model, overview["area"])
    else:
        result = _single_model_result(payload, model, overview["area"])

    result["capability"] = {
        **_base_model_descriptor(model),
        "category": NON_PROFESSIONAL_CATEGORIES[model_id],
        "chat_routable": False,
    }
    return result
