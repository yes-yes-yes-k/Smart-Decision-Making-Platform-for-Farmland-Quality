"""把 5 个专题 Agent 包装成 LangChain Tool，供 LLM function calling 调用。

每个 Tool 用 pydantic BaseModel 定义 args_schema，wrapper 函数体内延迟导入
agent_manager 避免循环导入，统一组装 payload dict 后调用 agent.execute()。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Literal, Optional

from langchain_core.tools import Tool
from pydantic import BaseModel, Field

from .registry import tool_registry

logger = logging.getLogger(__name__)


def _normalize_tool_result(agent: Any, payload: Dict[str, Any], execution: Dict[str, Any]) -> Dict[str, Any]:
    """保留工具的 execute 调用契约，同时统一工具返回值。"""
    from framework.agents.output_contract import normalize_execution

    return normalize_execution(agent, payload, execution)


# ── pydantic args_schema ──────────────────────────────────────────────


class Model1StabilityArgs(BaseModel):
    """Model-1 稳定性风险评价参数。"""

    parcel_id: str = Field(..., description="地块 ID（如图斑编号）")
    area_code: str = Field(default="lechang", description="区域代码")
    db_path: Optional[str] = Field(default=None, description="legacy 数据库路径（可选）")
    quality_index: Optional[float] = Field(default=None, description="综合质量指数（可选）")
    quality_grade: Optional[str] = Field(default=None, description="质量等级（可选）")


class Model2QualityGradeArgs(BaseModel):
    """Model-2 质量等级评价参数。"""

    parcel_id: str = Field(..., description="地块 ID（DB 路径优先）")
    area_code: str = Field(default="440281", description="区域代码")
    exe_path: Optional[str] = Field(default=None, description="评价程序路径（legacy）")
    dat_path: Optional[str] = Field(default=None, description="数据文件路径（legacy）")


class Model3ObstacleArgs(BaseModel):
    """Model-3 障碍诊断参数。"""

    parcel_id: str = Field(..., description="地块 ID")
    area_code: str = Field(default="440281", description="区域代码")
    db_path: Optional[str] = Field(default=None, description="legacy 数据库路径（可选）")


class Model4AcidificationArgs(BaseModel):
    """Model-4 酸化改良参数。"""

    parcel_id: str = Field(..., description="地块 ID")
    land_type: Literal["upland", "paddy"] = Field(default="upland", description="土地利用类型：upland(旱地)/paddy(水田)")
    fertilizer_type: Literal["compound", "single"] = Field(
        default="compound", description="肥料类型：compound(复合肥)/single(单质肥)"
    )
    target_ph: Optional[float] = Field(default=None, description="目标 pH 值（默认 6.5）")
    SJD: Optional[float] = Field(default=None, description="土壤 pH 值（legacy 兜底）")


class Model5OrganicMatterArgs(BaseModel):
    """Model-5 有机质培肥参数。"""

    parcel_id: Optional[str] = Field(default=None, description="地块 ID（可选）")
    area_code: str = Field(default="lechang", description="区域代码")
    land_type: Literal["upland", "paddy"] = Field(default="upland", description="土地利用类型：upland(旱地)/paddy(水田)")
    indicators: Optional[Dict[str, Any]] = Field(
        default=None, description="土壤指标字典（pH/SOMbe/AK/AP/TN 等 ML 特征）"
    )


# ── wrapper 函数 ──────────────────────────────────────────────────────


def _model_1_wrapper(
    parcel_id: str,
    area_code: str = "lechang",
    db_path: Optional[str] = None,
    quality_index: Optional[float] = None,
    quality_grade: Optional[str] = None,
) -> Dict[str, Any]:
    """包装 Model-1 稳定性风险评价 Agent。"""
    from framework.agents.manager import agent_manager

    agent = agent_manager.agents.get("model-1")
    if agent is None:
        return {"status": "error", "agent_id": "model-1", "message": "Agent 未注册"}
    payload = {"parcel_id": parcel_id, "area_code": area_code}
    if db_path:
        payload["db_path"] = db_path
    if quality_index is not None:
        payload["quality_index"] = quality_index
    if quality_grade is not None:
        payload["quality_grade"] = quality_grade
    return _normalize_tool_result(agent, payload, agent.execute(data=payload))


def _model_2_wrapper(
    parcel_id: str,
    area_code: str = "440281",
    exe_path: Optional[str] = None,
    dat_path: Optional[str] = None,
) -> Dict[str, Any]:
    """包装 Model-2 质量等级评价 Agent。"""
    from framework.agents.manager import agent_manager

    agent = agent_manager.agents.get("model-2")
    if agent is None:
        return {"status": "error", "agent_id": "model-2", "message": "Agent 未注册"}
    payload = {"parcel_id": parcel_id, "parcel_code": parcel_id, "area_code": area_code}
    if exe_path:
        payload["exe_path"] = exe_path
    if dat_path:
        payload["dat_path"] = dat_path
    return _normalize_tool_result(agent, payload, agent.execute(data=payload))


def _model_3_wrapper(
    parcel_id: str,
    area_code: str = "440281",
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """包装 Model-3 障碍诊断 Agent。"""
    from framework.agents.manager import agent_manager

    agent = agent_manager.agents.get("model-3")
    if agent is None:
        return {"status": "error", "agent_id": "model-3", "message": "Agent 未注册"}
    payload = {"parcel_id": parcel_id, "area_code": area_code}
    if db_path:
        payload["db_path"] = db_path
    return _normalize_tool_result(agent, payload, agent.execute(task=payload))


def _model_4_wrapper(
    parcel_id: str,
    land_type: str = "upland",
    fertilizer_type: str = "compound",
    target_ph: Optional[float] = None,
    SJD: Optional[float] = None,
) -> Dict[str, Any]:
    """包装 Model-4 酸化改良 Agent。"""
    from framework.agents.manager import agent_manager

    agent = agent_manager.agents.get("model-4")
    if agent is None:
        return {"status": "error", "agent_id": "model-4", "message": "Agent 未注册"}
    payload = {"parcel_id": parcel_id, "land_type": land_type, "fertilizer_type": fertilizer_type}
    if target_ph is not None:
        payload["target_ph"] = target_ph
    if SJD is not None:
        payload["SJD"] = SJD
    return _normalize_tool_result(agent, payload, agent.execute(task=payload))


def _model_5_wrapper(
    parcel_id: Optional[str] = None,
    area_code: str = "lechang",
    land_type: str = "upland",
    indicators: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """包装 Model-5 有机质培肥 Agent。"""
    from framework.agents.manager import agent_manager

    agent = agent_manager.agents.get("model-5")
    if agent is None:
        return {"status": "error", "agent_id": "model-5", "message": "Agent 未注册"}
    payload = {"area_code": area_code, "land_type": land_type}
    if parcel_id:
        payload["parcel_id"] = parcel_id
    if indicators:
        payload["indicators"] = indicators
    return _normalize_tool_result(agent, payload, agent.execute(task=payload))


# ── Tool 构造与注册 ───────────────────────────────────────────────────

_MODEL_1_TOOL = Tool(
    name="model_1_stability_evaluation",
    func=_model_1_wrapper,
    description=(
        "评价耕地质量等级稳定性与退化风险。需要地块 ID。"
        "输出稳定性九模块得分、掉级风险等级、稳定性等级。"
        "当用户询问'稳定性'/'退化风险'/'掉级'/'等级稳定吗'时调用。"
    ),
    args_schema=Model1StabilityArgs,
)

_MODEL_2_TOOL = Tool(
    name="model_2_quality_grade_evaluation",
    func=_model_2_wrapper,
    description=(
        "耕地质量等级评价。输出综合指数、质量等级、障碍度排序。"
        "当用户询问'质量等级'/'综合指数'/'等级评定'时调用。"
    ),
    args_schema=Model2QualityGradeArgs,
)

_MODEL_3_TOOL = Tool(
    name="model_3_obstacle_diagnosis",
    func=_model_3_wrapper,
    description=(
        "识别耕地主要/次要障碍因素、障碍类型与组合。"
        "当用户询问'有哪些问题'/'障碍诊断'/'主要毛病'/'障碍因素'时调用。"
    ),
    args_schema=Model3ObstacleArgs,
)

_MODEL_4_TOOL = Tool(
    name="model_4_acidification_remediation",
    func=_model_4_wrapper,
    description=(
        "基于过程模型计算酸化改良剂需求（亿土康 YTK / 木本泥炭 MBNT）。"
        "当用户询问'酸化治理'/'调理剂用量'/'石灰用量'/'pH 提升'时调用。"
    ),
    args_schema=Model4AcidificationArgs,
)

_MODEL_5_TOOL = Tool(
    name="model_5_organic_matter_improvement",
    func=_model_5_wrapper,
    description=(
        "基于 RF 模型预测有机质培肥施用量。"
        "当用户询问'有机质'/'有机肥用量'/'秸秆还田'/'培肥'时调用。"
    ),
    args_schema=Model5OrganicMatterArgs,
)

# 注册到 tool_registry
tool_registry.register("model_1_stability_evaluation", _MODEL_1_TOOL)
tool_registry.register("model_2_quality_grade_evaluation", _MODEL_2_TOOL)
tool_registry.register("model_3_obstacle_diagnosis", _MODEL_3_TOOL)
tool_registry.register("model_4_acidification_remediation", _MODEL_4_TOOL)
tool_registry.register("model_5_organic_matter_improvement", _MODEL_5_TOOL)

# 已注册的 5 个专题工具名
SPECIALIZED_TOOL_NAMES: frozenset[str] = frozenset(
    {
        "model_1_stability_evaluation",
        "model_2_quality_grade_evaluation",
        "model_3_obstacle_diagnosis",
        "model_4_acidification_remediation",
        "model_5_organic_matter_improvement",
    }
)

# Tool → agent_id 映射（用于标注 agents_invoked）
TOOL_NAME_TO_AGENT_ID: Dict[str, str] = {
    "model_1_stability_evaluation": "model-1",
    "model_2_quality_grade_evaluation": "model-2",
    "model_3_obstacle_diagnosis": "model-3",
    "model_4_acidification_remediation": "model-4",
    "model_5_organic_matter_improvement": "model-5",
}


def get_specialized_tools() -> List[Tool]:
    """返回 5 个专题 Tool 列表，供 LLMService.bind_tools 使用。"""
    return [
        tool_registry.get(name)
        for name in SPECIALIZED_TOOL_NAMES
        if tool_registry.get(name) is not None
    ]
