from __future__ import annotations

from hashlib import sha1
from typing import Any

from .overview import _normalize_area_code, get_county_overview


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
    """执行县域结构化诊断，首版使用可替换的规则结果。

    返回同时兼容两类消费方：
    - 旧契约：summary / evidence / recommendations / key_areas 等
    - 前端 DiagnosisView：problems / measures / regions
    """

    topic = payload.get("topic", "quality")
    raw_area_code = payload.get("area_code", "lechang")
    area_code = _normalize_area_code(raw_area_code)
    # 把归一化后的写回 payload，避免后续 SHA 计算仍含原始中文名
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
        # 保证顶层有 message，便于前端拦截器直接提示
        err = overview.get("error") or {}
        overview.setdefault("message", err.get("message", "区域暂不支持"))
        return overview

    rule = TOPIC_RULES[topic]
    missing_location = "longitude" not in payload or "latitude" not in payload
    fallback_fields = []
    if missing_location:
        fallback_fields.extend(["longitude", "latitude"])

    # 前端 DiagnosisView 需要的 problems / measures / regions
    # 先给一套与前端默认值结构一致的规则数据，便于接口联调
    problems = [
        {
            "name": "土壤有机质偏低",
            "percent": 38.6,
            "color": "#f5222d",
        },
        {
            "name": "耕层浅薄",
            "percent": 24.1,
            "color": "#fa8c16",
        },
        {
            "name": "酸化风险",
            "percent": 17.2,
            "color": "#fadb14",
        },
        {
            "name": "灌溉条件不足",
            "percent": 12.8,
            "color": "#52c41a",
        },
        {
            "name": "障碍因子叠加",
            "percent": 7.3,
            "color": "#40a9ff",
        },
    ]

    measures = [
        {
            "name": "增施有机肥与秸秆还田",
            "apply": "有机质偏低区域",
            "icon": "TrendCharts",
            "icon_bg": "#f6ffed",
            "icon_color": "#52c41a",
            "cost": 120,
            "improve": 0.25,
            "period": "1-2年",
        },
        {
            "name": "改良酸化土壤",
            "apply": "酸化风险区域",
            "icon": "DataLine",
            "icon_bg": "#e6f7ff",
            "icon_color": "#1890ff",
            "cost": 150,
            "improve": 0.20,
            "period": "1-2年",
        },
        {
            "name": "完善灌溉排水",
            "apply": "灌溉条件不足区域",
            "icon": "Location",
            "icon_bg": "#e6f7ff",
            "icon_color": "#13c2c2",
            "cost": 450,
            "improve": 0.30,
            "period": "2-3年",
        },
        {
            "name": "深松松旋与耕层改良",
            "apply": "耕层浅薄区域",
            "icon": "Warning",
            "icon_bg": "#fff7e6",
            "icon_color": "#fa8c16",
            "cost": 180,
            "improve": 0.25,
            "period": "1-2年",
        },
    ]

    regions = [
        {
            "region": "韶关市曲江区",
            "problem": "有机质偏低、耕层浅薄",
            "measure": "增施有机肥+深松改良",
            "weight": 850,
            "effect": 0.36,
        },
        {
            "region": "清远市英德市",
            "problem": "有机质偏低、灌溉不足",
            "measure": "增施有机肥+完善灌溉",
            "weight": 780,
            "effect": 0.33,
        },
        {
            "region": "梅州市梅县区",
            "problem": "酸化风险、有机质偏低",
            "measure": "改良酸化+有机肥还田",
            "weight": 720,
            "effect": 0.31,
        },
        {
            "region": "河源市连平县",
            "problem": "耕层浅薄、灌溉不足",
            "measure": "深松改良+完善灌溉",
            "weight": 680,
            "effect": 0.30,
        },
        {
            "region": "茂名市高州市",
            "problem": "有机质偏低",
            "measure": "增施有机肥",
            "weight": 620,
            "effect": 0.27,
        },
    ]

    # 根据主题轻微调整 problems，避免不同 topic 返回完全一致的数据
    if topic == "acidification":
        problems = [
            {
                "name": "酸化风险",
                "percent": 45.2,
                "color": "#f5222d",
            },
            {
                "name": "土壤有机质偏低",
                "percent": 26.8,
                "color": "#fa8c16",
            },
            {
                "name": "耕层浅薄",
                "percent": 12.4,
                "color": "#fadb14",
            },
            {
                "name": "铝毒风险",
                "percent": 9.3,
                "color": "#52c41a",
            },
            {
                "name": "盐基离子淋失",
                "percent": 6.3,
                "color": "#40a9ff",
            },
        ]
        measures = [m for m in measures if "酸化" in m["name"] or m["name"].startswith("增施")]
    elif topic == "improvement":
        problems = [
            {
                "name": "治理综合得分偏低",
                "percent": 34.0,
                "color": "#f5222d",
            },
            {
                "name": "措施协同不足",
                "percent": 25.0,
                "color": "#fa8c16",
            },
            {
                "name": "投资强度不均",
                "percent": 20.0,
                "color": "#fadb14",
            },
            {
                "name": "见效周期不匹配",
                "percent": 12.0,
                "color": "#52c41a",
            },
            {
                "name": "长效机制待建立",
                "percent": 9.0,
                "color": "#40a9ff",
            },
        ]

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
        # 前端 DiagnosisView 需要的结构化字段
        "problems": problems,
        "problem_distribution": problems,
        "measures": measures,
        "treatments": measures,
        "regions": regions,
        "base_data": regions,
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
