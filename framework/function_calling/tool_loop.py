"""多轮工具调用循环：绑定 tools → LLM 推理 → 执行 tool → 反馈结果 → 直到终止。

把"绑定工具→循环→执行→再生成"的多轮对话循环抽出，避免 LLMService 膨胀。
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, List, Optional

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from .executor import tool_executor
from .registry import tool_registry
from .specialized_tools import TOOL_NAME_TO_AGENT_ID
from framework.agents.output_contract import llm_context
from framework.analysis_context.errors import AnalysisContextConflict

logger = logging.getLogger(__name__)

# system prompt 模板：注入能力清单 + 上下文
_SYSTEM_PROMPT_TEMPLATE = """你是耕地质量与土壤改良领域的助手。你可以调用以下专业工具来回答用户问题：

可用工具：
1. model_1_stability_evaluation - 评价耕地质量等级稳定性与退化风险（稳定性/退化风险/掉级）
2. model_2_quality_grade_evaluation - 耕地质量等级评价（质量等级/综合指数/等级评定）
3. model_3_obstacle_diagnosis - 识别耕地主要/次要障碍因素（障碍诊断/主要毛病/障碍因素）
4. model_4_acidification_remediation - 计算酸化改良剂需求（酸化治理/调理剂用量/pH提升）
5. model_5_organic_matter_improvement - 预测有机质培肥施用量（有机质/有机肥用量/秸秆还田/培肥）

调用规则：
- 根据用户问题选择合适的工具，可以组合调用多个工具。
- 空间对象参数由后端提供，不得自行选择、猜测或覆盖。
- 调用完工具后，基于工具返回的计算结果，给出准确、简洁、可执行的中文答复。
- 不要编造未提供的数据，保留明确的数值、单位和建议。
- 【只答所问】严格围绕用户问题作答，只回答用户实际询问的内容；用户未问到的结论、建议、用量方案、补充参数请求、后续测算提议、其它模型的推荐、衍生风险或扩展解释，一律不得输出。
- 用户未询问治理/改良/用量/措施时，不得输出调理剂/木本泥炭用量、补充参数或重算提议，也不得输出模型内部提示码（如 MODEL4_QUANTITATIVE_UNAVAILABLE 等）。

当前上下文：
{context}
"""


class ToolCallingLoop:
    """多轮工具调用循环。

    持有绑定了 tools 的 LLM Runnable，循环调用直到 LLM 不再发出 tool_calls。
    """

    def __init__(
        self,
        llm,  # 已 bind_tools 的 Runnable
        max_iterations: int = 3,
        default_args: Optional[Dict[str, Any]] = None,
        trace_id: Optional[str] = None,
    ):
        self._llm = llm
        self._max_iterations = max_iterations
        self._default_args = default_args or {}
        self._trace_id = trace_id
        self._trace: List[Dict[str, Any]] = []
        self._tool_results: Dict[str, Any] = {}  # agent_id → result

    def run(self, prompt: str, messages: Optional[list] = None) -> Dict[str, Any]:
        """执行多轮工具调用循环。

        Returns:
            success=True 时包含 content/tool_calls_trace/iterations/tool_results
            success=False 时包含 reason/partial_results
        """
        # 构造 system prompt
        context_str = self._format_context()
        system_msg = SystemMessage(content=_SYSTEM_PROMPT_TEMPLATE.format(context=context_str))

        # 组装对话历史
        history: List[Any] = [system_msg]
        if messages:
            for msg in messages:
                role = msg.get("role", "user") if isinstance(msg, dict) else None
                content = msg.get("content", "") if isinstance(msg, dict) else str(msg)
                if role == "system":
                    history.append(SystemMessage(content=content))
                elif role == "assistant":
                    history.append(AIMessage(content=content))
                else:
                    history.append(HumanMessage(content=content))
        history.append(HumanMessage(content=prompt))

        # 多轮循环
        for iteration in range(1, self._max_iterations + 1):
            started = time.perf_counter()
            try:
                ai_msg = self._llm.invoke(history)
            except Exception as e:
                logger.warning(
                    "[ToolLoop] trace=%s iter=%d LLM 调用失败: %s",
                    self._trace_id,
                    iteration,
                    e,
                )
                return {
                    "success": False,
                    "reason": "llm_invoke_failed",
                    "error": str(e),
                    "tool_calls_trace": self._trace,
                    "partial_results": self._tool_results,
                    "iterations": iteration,
                }

            elapsed = time.perf_counter() - started
            logger.info(
                "[ToolLoop] trace=%s iter=%d LLM 耗时=%.2fs",
                self._trace_id,
                iteration,
                elapsed,
            )

            # 检查是否有 tool_calls
            tool_calls = getattr(ai_msg, "tool_calls", None) or []
            if not tool_calls:
                # LLM 不再调用工具，返回最终内容
                content = ai_msg.content if hasattr(ai_msg, "content") else str(ai_msg)
                return {
                    "success": True,
                    "content": content,
                    "tool_calls_trace": self._trace,
                    "tool_results": self._tool_results,
                    "iterations": iteration,
                    "model": "tool_calling",
                    "type": "tool_calling",
                }

            # 处理 tool_calls
            history.append(ai_msg)
            for tc in tool_calls:
                tc_name = tc.get("name", "") if isinstance(tc, dict) else getattr(tc, "name", "")
                tc_args = tc.get("args", {}) if isinstance(tc, dict) else getattr(tc, "args", {})
                tc_id = tc.get("id", "") if isinstance(tc, dict) else getattr(tc, "id", "")

                # 合并 default_args（LLM 参数优先）
                try:
                    merged_args = self._merge_default_args(tc_name, tc_args)
                except AnalysisContextConflict as exc:
                    return {
                        "success": False,
                        "reason": "analysis_object_conflict",
                        "error": exc.message,
                        "tool_calls_trace": self._trace,
                        "partial_results": self._tool_results,
                        "iterations": iteration,
                    }

                tool_started = time.perf_counter()
                result = tool_executor.execute(tc_name, merged_args)
                tool_elapsed = time.perf_counter() - tool_started

                # 记录 trace
                agent_id = TOOL_NAME_TO_AGENT_ID.get(tc_name, tc_name)
                trace_entry = {
                    "tool_name": tc_name,
                    "agent_id": agent_id,
                    "arguments": merged_args,
                    "success": result.get("success", False),
                    "elapsed": round(tool_elapsed, 3),
                    "iteration": iteration,
                }
                self._trace.append(trace_entry)

                # 收集结果
                if result.get("success"):
                    tool_result = result.get("result", {})
                    self._tool_results[agent_id] = tool_result
                    logger.info(
                        "[ToolLoop] trace=%s iter=%d tool=%s agent=%s 成功 耗时=%.2fs",
                        self._trace_id,
                        iteration,
                        tc_name,
                        agent_id,
                        tool_elapsed,
                    )
                else:
                    logger.warning(
                        "[ToolLoop] trace=%s iter=%d tool=%s 失败: %s",
                        self._trace_id,
                        iteration,
                        tc_name,
                        result.get("error", "unknown"),
                    )

                # 把工具结果作为 ToolMessage 反馈给 LLM。使用 llm_context 紧凑投影，
                # 只保留有展示名的业务字段与标准中文名/单位，避免把
                # background_acid/acid_deposition_input 等中间产酸量分解暴露给 LLM
                # （酸化 spec 要求不暴露中间变量）；该副本只用于提示词，不回写
                # 工具结果、API 响应或数据库。
                raw_payload = result.get("result", result.get("error", ""))
                tool_payload = raw_payload
                if result.get("success") and isinstance(raw_payload, dict):
                    try:
                        tool_payload = llm_context(raw_payload)
                    except Exception:
                        tool_payload = raw_payload
                if isinstance(tool_payload, dict) and isinstance(tool_payload.get("issues"), list):
                    # 内部问题码仅用于系统日志，不回灌 LLM；只保留可读说明与级别，
                    # 避免 MODEL4_QUANTITATIVE_UNAVAILABLE 等内部标识泄露并诱发冗余补充说明。
                    tool_payload["issues"] = [
                        {"severity": item.get("severity", "warning"), "message": item.get("message", "")}
                        for item in tool_payload["issues"]
                        if item.get("message")
                    ]
                tool_msg_content = json.dumps(
                    result.get("result", result.get("error", "")),
                    ensure_ascii=False,
                    default=str,
                )
                history.append(ToolMessage(content=tool_msg_content, tool_call_id=tc_id))

        # 超过最大迭代数
        logger.warning(
            "[ToolLoop] trace=%s 达到最大迭代数 %d，未获得终止答复",
            self._trace_id,
            self._max_iterations,
        )
        return {
            "success": False,
            "reason": "tool_loop_exhausted",
            "tool_calls_trace": self._trace,
            "partial_results": self._tool_results,
            "iterations": self._max_iterations,
        }

    def _merge_default_args(self, tool_name: str, llm_args: Dict[str, Any]) -> Dict[str, Any]:
        """锁定空间字段使用后端值，其他字段仍允许 LLM 提供。

        只合并工具实际接受的参数名，避免 TypeError。
        """
        tool = tool_registry.get(tool_name)
        if tool is None:
            return dict(llm_args)

        # 获取工具接受的参数名
        accepted_keys = self._get_accepted_keys(tool)
        if not accepted_keys:
            return dict(llm_args)

        locked_keys = frozenset({"parcel_id", "parcel_code", "area_code"})
        for key in locked_keys:
            if key in llm_args and key in self._default_args and llm_args[key] != self._default_args[key]:
                raise AnalysisContextConflict(f"工具参数 {key} 与当前分析对象不一致")
        merged: Dict[str, Any] = {}
        for key in accepted_keys:
            if key in locked_keys and key in self._default_args:
                merged[key] = self._default_args[key]
            elif key in llm_args:
                merged[key] = llm_args[key]
            elif key in self._default_args:
                merged[key] = self._default_args[key]
        return merged

    @staticmethod
    def _get_accepted_keys(tool) -> set:
        """从 tool 的 args_schema 或函数签名获取接受的参数名。"""
        if hasattr(tool, "args_schema") and tool.args_schema:
            # pydantic v2
            if hasattr(tool.args_schema, "model_fields"):
                return set(tool.args_schema.model_fields.keys())
            # pydantic v1
            if hasattr(tool.args_schema, "__fields__"):
                return set(tool.args_schema.__fields__.keys())
        # 从函数签名推断
        try:
            from inspect import signature

            sig = signature(tool.func)
            return set(sig.parameters.keys())
        except (TypeError, ValueError):
            return set()

    def _format_context(self) -> str:
        """把 default_args 格式化为可读的上下文字符串。"""
        if not self._default_args:
            return "（无额外上下文）"
        lines = []
        for key, val in self._default_args.items():
            if key in ("data", "question_type"):
                continue
            if val is not None:
                lines.append(f"- {key}: {val}")
        return "\n".join(lines) if lines else "（无额外上下文）"
