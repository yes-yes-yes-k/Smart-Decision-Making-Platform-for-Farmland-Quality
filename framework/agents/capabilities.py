"""专业能力的唯一注册表。

正式专业模型、Agent 注册和问题类型路由均从本模块读取元数据，避免三处分别维护。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Literal, Optional


@dataclass(frozen=True)
class ProfessionalCapability:
    """一个可由专业 Agent 执行的正式能力。"""

    agent_id: str
    model_id: str
    name: str
    description: str
    domain: str
    question_type: int
    minimum_inputs: tuple[str, ...] = ()
    runtime_requirement: str = "无需额外运行时前置条件"
    analysis_scale: str = "地块"        # 分析尺度：省/县/片区/地块
    data_type: str = "指标数据"          # 数据类型：指标数据/评价结果/处方用量
    supported_object_types: tuple[str, ...] = ("parcel",)
    requires_spatial_object: bool = True
    supports_scenario: bool = False
    required_scenario_inputs: tuple[str, ...] = ()
    tool_name: str | None = None
    result_schema: str | None = None
    cost_class: Literal["standard", "high"] = "standard"
    timeout_seconds: int = 90
    retry_limit: int = 2
    comprehensive_role: Literal["core", "optional", "disabled"] = "disabled"
    allowed_triggers: tuple[str, ...] = ()


COMPREHENSIVE_METADATA = {
    "model-1": {
        "tool_name": "model_1_stability_evaluation",
        "result_schema": "stability-v1",
        "comprehensive_role": "optional",
        "allowed_triggers": ("history_available",),
    },
    "model-2": {
        "tool_name": "model_2_quality_grade_evaluation",
        "result_schema": "quality-grade-v1",
        "comprehensive_role": "core",
        "allowed_triggers": ("always",),
    },
    "model-3": {
        "tool_name": "model_3_obstacle_diagnosis",
        "result_schema": "obstacle-v1",
        "comprehensive_role": "core",
        "allowed_triggers": ("always",),
    },
    "model-4": {
        "tool_name": "model_4_acidification_remediation",
        "result_schema": "acidification-v1",
        "comprehensive_role": "optional",
        "allowed_triggers": (
            "user_requested_acidification",
            "acidification_evidence",
        ),
    },
    "model-5": {
        "tool_name": "model_5_organic_matter_improvement",
        "result_schema": "organic-matter-v1",
        "comprehensive_role": "optional",
        "allowed_triggers": (
            "user_requested_organic_matter",
            "organic_matter_evidence",
        ),
    },
}


PROFESSIONAL_CAPABILITIES: tuple[ProfessionalCapability, ...] = (
    # question_type 编号与 routing.py 的 QUESTION_TYPE_N_KEYWORDS 语义对齐：
    #   type=1 稳定性 / type=2 质量等级 / type=3 障碍诊断
    #   type=4 酸化改良 / type=5 有机质培肥
    # agent_id 与 model_id 一一对应，与 spec professional-model-agents 保持一致。
    ProfessionalCapability(
        "model-1", "stability-risk-evaluation", "耕地质量稳定性与退化风险评价",
        "基于预计算结果识别稳定性、历史变化和退化风险。", "stability", 1,
        ("parcel_id",), "需先完成稳定性离线预计算并提供 parcel_id。",
        "地块", "评价结果",   # model-1 稳定性风险：地块级评价结果
        **COMPREHENSIVE_METADATA["model-1"],
    ),
    ProfessionalCapability(
        "model-2", "quality-grade-evaluation", "耕地质量等级评价",
        "通过质量等级评价程序输出综合指数、等级和障碍度。", "grade", 2,
        ("parcel_code",), "真实评价需部署 exe/dat 文件并提供 parcel_code。",
        "地块", "评价结果",   # model-2 质量等级评价：地块级评价结果
        **COMPREHENSIVE_METADATA["model-2"],
    ),
    ProfessionalCapability(
        "model-3", "obstacle-diagnosis", "耕地质量主要问题与障碍诊断",
        "识别主要/次要障碍因素、障碍类型和组合。", "problem", 3,
        ("parcel_id",), "需完成障碍诊断批量计算并提供 parcel_id。",
        "地块", "指标数据",   # model-3 障碍诊断：地块级指标数据
        **COMPREHENSIVE_METADATA["model-3"],
    ),
    ProfessionalCapability(
        "model-4", "acidification-remediation", "耕地土壤酸化改良",
        "判定酸化程度并给出调理剂和改良措施建议。", "acidification", 4,
        ("parcel_id",), "需完成酸化评估并提供 parcel_id；结构化指标可用于规则降级。",
        "地块", "处方用量",   # model-4 酸化改良：地块级处方用量
        ("parcel",), True, True,
        ("SJD", "JHX", "JLA", "land_type", "fertilizer_type"),
        **COMPREHENSIVE_METADATA["model-4"],
    ),
    ProfessionalCapability(
        "model-5", "organic-matter-improvement", "耕地土壤有机质培肥提升",
        "基于韶关旱地/水田 RF 与全局肥力模型预测有机质培肥施用量。", "organic_matter", 5,
        ("area_code", "land_type", "indicators"),
        "韶关需要 area_code 与 land_type；缺少特征时明确降级并提示补充输入。",
        "地块", "处方用量",
        **COMPREHENSIVE_METADATA["model-5"],
    ),
    ProfessionalCapability(
        "model-6", "comprehensive-fertility-improvement", "耕地综合地力改良提升模型",
        "综合耕地地力评价与改良提升（整合酸化改良与有机质培肥建议）。", "fertility", 6,
        ("parcel_id",), "占位状态：综合地力改良提升业务逻辑尚未实现，本能力暂不可执行；数据库结构（comprehensive_fertility_result 表）已就绪。",
        "地块", "评价结果",   # model-6 综合地力：地块级评价结果（占位）
        comprehensive_role="disabled",
    ),
)

CAPABILITY_BY_AGENT_ID: Dict[str, ProfessionalCapability] = {
    item.agent_id: item for item in PROFESSIONAL_CAPABILITIES
}
CAPABILITY_BY_MODEL_ID: Dict[str, ProfessionalCapability] = {
    item.model_id: item for item in PROFESSIONAL_CAPABILITIES
}
CAPABILITY_BY_QUESTION_TYPE: Dict[int, ProfessionalCapability] = {
    item.question_type: item for item in PROFESSIONAL_CAPABILITIES
}

# 保留无歧义的历史公开模型标识，响应会返回规范 model_id 和弃用信息。
LEGACY_MODEL_ALIASES: Dict[str, str] = {
    "obstacle-factor-identification": "obstacle-diagnosis",
    "acidification-governance": "acidification-remediation",
}


def get_capability_by_model_id(model_id: Optional[str]) -> Optional[ProfessionalCapability]:
    """按规范或兼容模型标识获取正式能力。"""
    if not model_id:
        return None
    canonical_id = LEGACY_MODEL_ALIASES.get(model_id, model_id)
    return CAPABILITY_BY_MODEL_ID.get(canonical_id)


def get_capability_by_question_type(question_type: Optional[int]) -> Optional[ProfessionalCapability]:
    """按问题类型获取正式能力。"""
    return CAPABILITY_BY_QUESTION_TYPE.get(question_type)


def public_capability_descriptor(capability: ProfessionalCapability) -> dict:
    """返回可用于 API 和文档的稳定能力描述。"""
    return {
        "agent_id": capability.agent_id,
        "model_id": capability.model_id,
        "name": capability.name,
        "purpose": capability.description,
        "minimum_inputs": list(capability.minimum_inputs),
        "question_type": capability.question_type,
        "category": "professional",
        "chat_routable": True,
        "runtime_requirement": capability.runtime_requirement,
        "supported_object_types": list(capability.supported_object_types),
        "requires_spatial_object": capability.requires_spatial_object,
        "supports_scenario": capability.supports_scenario,
        "required_scenario_inputs": list(capability.required_scenario_inputs),
        "tool_name": capability.tool_name,
        "result_schema": capability.result_schema,
        "cost_class": capability.cost_class,
        "timeout_seconds": capability.timeout_seconds,
        "retry_limit": capability.retry_limit,
        "comprehensive_role": capability.comprehensive_role,
        "allowed_triggers": list(capability.allowed_triggers),
    }


def public_comprehensive_capabilities() -> list[dict]:
    """Return public descriptors for workflow-enabled professional capabilities."""
    return [
        public_capability_descriptor(capability)
        for capability in PROFESSIONAL_CAPABILITIES
        if capability.comprehensive_role != "disabled"
    ]
