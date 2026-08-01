"""专业能力的唯一注册表。

正式专业模型、Agent 注册和问题类型路由均从本模块读取元数据，避免三处分别维护。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional


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


PROFESSIONAL_CAPABILITIES: tuple[ProfessionalCapability, ...] = (
    ProfessionalCapability(
        "model-1", "stability-risk-evaluation", "耕地质量稳定性与退化风险评价",
        "基于预计算结果识别稳定性、历史变化和退化风险。", "stability", 1,
        ("parcel_id",), "需先完成稳定性离线预计算并提供 parcel_id。",
    ),
    ProfessionalCapability(
        "model-2", "improvement-potential-assessment", "耕地质量提升潜力评估",
        "评估耕地质量提升空间、目标指标和潜在障碍度。", "potential", 6,
        ("indicators",), "可使用结构化土壤指标；缺失字段将按 Agent 既有规则处理。",
    ),
    ProfessionalCapability(
        "model-3", "obstacle-diagnosis", "耕地质量主要问题与障碍诊断",
        "识别主要/次要障碍因素、障碍类型和组合。", "problem", 3,
        ("parcel_id",), "需完成障碍诊断批量计算并提供 parcel_id。",
    ),
    ProfessionalCapability(
        "model-4", "acidification-remediation", "耕地土壤酸化改良",
        "判定酸化程度并给出调理剂和改良措施建议。", "acidification", 2,
        ("parcel_id",), "需完成酸化评估并提供 parcel_id；结构化指标可用于规则降级。",
    ),
    ProfessionalCapability(
        "model-5", "organic-matter-improvement", "耕地土壤有机质培肥提升",
        "围绕有机肥、秸秆还田和培肥措施提供治理建议。", "organic_matter", 7,
        ("indicators",), "可使用结构化土壤指标；当前规则结果会明确模拟状态。",
    ),
    ProfessionalCapability(
        "model-6", "fertility-soc-dose-prediction", "耕地肥力 SOC/Dose 预测",
        "使用 ML 模型预测土壤有机碳和施肥量。", "fertility_ml", 4,
        ("indicators",), "需提供模型特征；模型文件不可用时返回训练集均值降级结果。",
    ),
    ProfessionalCapability(
        "model-7", "quality-grade-evaluation", "耕地质量等级评价",
        "通过质量等级评价程序输出综合指数、等级和障碍度。", "grade", 5,
        ("parcel_code",), "真实评价需部署 exe/dat 文件并提供 parcel_code。",
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
    }
