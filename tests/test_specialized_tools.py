"""专题模型 function calling 工具测试。

测试内容：
1. pydantic args_schema 序列化为合法 JSON Schema
2. wrapper 函数正确组装 payload（mock agent.execute）
3. tool_executor 集成调用
4. FUNCTION_CALLING_ENABLED=false 时直接 fallback
5. bind_tools 不支持时 fallback
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest


# ── 1. pydantic args_schema 序列化 ──────────────────────────────


class TestSchemaSerialization:
    """测试每个 pydantic args_schema 能序列化为合法 JSON Schema。"""

    def test_model1_schema(self):
        from framework.function_calling.specialized_tools import Model1StabilityArgs

        schema = Model1StabilityArgs.model_json_schema()
        assert "properties" in schema
        assert "parcel_id" in schema["properties"]
        assert "parcel_id" in schema.get("required", [])

    def test_model2_schema(self):
        from framework.function_calling.specialized_tools import Model2QualityGradeArgs

        schema = Model2QualityGradeArgs.model_json_schema()
        assert "parcel_id" in schema["properties"]
        assert "parcel_id" in schema.get("required", [])

    def test_model3_schema(self):
        from framework.function_calling.specialized_tools import Model3ObstacleArgs

        schema = Model3ObstacleArgs.model_json_schema()
        assert "parcel_id" in schema["properties"]

    def test_model4_schema(self):
        from framework.function_calling.specialized_tools import Model4AcidificationArgs

        schema = Model4AcidificationArgs.model_json_schema()
        assert "parcel_id" in schema["properties"]
        # land_type 应有 enum
        land_type = schema["properties"].get("land_type", {})
        assert "enum" in land_type

    def test_model5_schema(self):
        from framework.function_calling.specialized_tools import Model5OrganicMatterArgs

        schema = Model5OrganicMatterArgs.model_json_schema()
        assert "area_code" in schema["properties"]

    def test_all_schemas_are_valid_json(self):
        """所有 schema 序列化后是合法 JSON。"""
        from framework.function_calling.specialized_tools import (
            Model1StabilityArgs,
            Model2QualityGradeArgs,
            Model3ObstacleArgs,
            Model4AcidificationArgs,
            Model5OrganicMatterArgs,
        )

        for model_cls in [
            Model1StabilityArgs,
            Model2QualityGradeArgs,
            Model3ObstacleArgs,
            Model4AcidificationArgs,
            Model5OrganicMatterArgs,
        ]:
            schema = model_cls.model_json_schema()
            # 确保能序列化为 JSON 字符串
            json_str = json.dumps(schema)
            assert len(json_str) > 0


# ── 2. wrapper 函数 payload 组装 ─────────────────────────────────


class TestWrapperPayload:
    """测试 wrapper 函数正确组装 payload 并调用 agent.execute()。"""

    @pytest.fixture(autouse=True)
    def _mock_agent_manager(self):
        """mock agent_manager 避免真实 Agent 初始化。"""
        mock_agent = MagicMock()
        mock_agent.execute = MagicMock(return_value={"status": "ok", "result": {}})

        with patch("framework.agents.manager.agent_manager") as mock_mgr:
            mock_mgr.agents = {
                "model-1": mock_agent,
                "model-2": mock_agent,
                "model-3": mock_agent,
                "model-4": mock_agent,
                "model-5": mock_agent,
            }
            yield mock_mgr, mock_agent

    def test_model1_wrapper_assembles_payload(self, _mock_agent_manager):
        from framework.function_calling.specialized_tools import _model_1_wrapper

        result = _model_1_wrapper(parcel_id="1", area_code="lechang")
        _mock_agent_manager[1].execute.assert_called_once()
        call_args = _mock_agent_manager[1].execute.call_args
        # model-1 实际稳定性 Agent 使用 data 参数
        assert "data" in call_args.kwargs
        payload = call_args.kwargs["data"]
        assert payload["parcel_id"] == "1"

    def test_model2_wrapper_does_not_invent_parcel_code(self, _mock_agent_manager):
        from framework.function_calling.specialized_tools import _model_2_wrapper

        result = _model_2_wrapper(parcel_id="P001", area_code="440281")
        call_args = _mock_agent_manager[1].execute.call_args
        payload = call_args.kwargs["data"]
        assert payload["parcel_id"] == "P001"
        assert "parcel_code" not in payload

    def test_model3_wrapper_uses_task_param(self, _mock_agent_manager):
        from framework.function_calling.specialized_tools import _model_3_wrapper

        result = _model_3_wrapper(parcel_id="1", area_code="440281")
        call_args = _mock_agent_manager[1].execute.call_args
        # model-3 用 task 参数
        assert "task" in call_args.kwargs
        payload = call_args.kwargs["task"]
        assert payload["parcel_id"] == "1"

    def test_model4_wrapper_includes_land_type(self, _mock_agent_manager):
        from framework.function_calling.specialized_tools import _model_4_wrapper

        result = _model_4_wrapper(parcel_id="1", land_type="paddy", fertilizer_type="single")
        call_args = _mock_agent_manager[1].execute.call_args
        payload = call_args.kwargs["task"]
        assert payload["land_type"] == "paddy"
        assert payload["fertilizer_type"] == "urea"

    def test_model5_wrapper_requires_verified_parcel_id(self, _mock_agent_manager):
        from framework.function_calling.specialized_tools import _model_5_wrapper

        with pytest.raises(TypeError):
            _model_5_wrapper(area_code="440281", land_type="upland")

    def test_wrapper_returns_error_when_agent_missing(self):
        """Agent 未注册时返回 error dict。"""
        from framework.function_calling.specialized_tools import _model_1_wrapper

        with patch("framework.agents.manager.agent_manager") as mock_mgr:
            mock_mgr.agents = {}
            result = _model_1_wrapper(parcel_id="1")
            assert result["status"] == "error"
            assert result["agent_id"] == "model-1"


# ── 3. tool_registry 和 tool_executor 集成 ──────────────────────


class TestRegistryIntegration:
    """测试工具注册到 registry 并能被 executor 调用。"""

    def test_specialized_tools_registered(self):
        """5 个专题工具已注册到 tool_registry。"""
        from framework.function_calling.specialized_tools import SPECIALIZED_TOOL_NAMES
        from framework.function_calling.registry import tool_registry

        for name in SPECIALIZED_TOOL_NAMES:
            tool = tool_registry.get(name)
            assert tool is not None, f"工具 {name} 未注册"

    def test_get_specialized_tools_returns_5(self):
        from framework.function_calling.specialized_tools import get_specialized_tools

        tools = get_specialized_tools()
        assert len(tools) == 5

    def test_tool_executor_can_call_model3(self):
        """tool_executor 能调用 model_3 wrapper。"""
        mock_agent = MagicMock(
            return_value={"status": "ok", "result": {"obstacle_type": "multi"}}
        )
        with patch("framework.agents.manager.agent_manager") as mock_mgr:
            mock_mgr.agents = {"model-3": mock_agent}
            from framework.function_calling.executor import tool_executor

            result = tool_executor.execute("model_3_obstacle_diagnosis", {"parcel_id": "1"})
            assert result["success"] is True
            assert result["tool_name"] == "model_3_obstacle_diagnosis"


# ── 4. FUNCTION_CALLING_ENABLED=false 时 fallback ──────────────


class TestFallbackBehavior:
    """测试 function calling 失败时的 fallback 行为。"""

    def test_fc_disabled_returns_none(self):
        """FUNCTION_CALLING_ENABLED=false 时 _execute_via_function_calling 返回 None。"""
        with patch("framework.config.Config") as mock_config:
            mock_config.FUNCTION_CALLING_ENABLED = False
            from framework.agents.nodes import _execute_via_function_calling

            result = _execute_via_function_calling("测试问题", {}, None)
            assert result is None

    def test_fc_llm_unavailable_returns_none(self):
        """LLM 不可用时返回 None。"""
        with patch("framework.config.Config") as mock_config:
            mock_config.FUNCTION_CALLING_ENABLED = True
            with patch("framework.llm.service.llm_service") as mock_llm:
                mock_llm.is_available.return_value = False
                from framework.agents.nodes import _execute_via_function_calling

                result = _execute_via_function_calling("测试问题", {}, None)
                assert result is None

    def test_fc_bind_tools_unsupported_returns_none(self):
        """bind_tools 不支持时返回 None。"""
        with patch("framework.llm.service.Config") as mock_config:
            mock_config.FUNCTION_CALLING_ENABLED = True
            mock_config.SILICONFLOW_SUPPORTS_TOOL_CALLING = False
            mock_config.FUNCTION_CALLING_MAX_ITERATIONS = 3
            mock_config.SILICONFLOW_CHAT_MODEL = "test-model"
            from framework.agents.nodes import _execute_via_function_calling

            result = _execute_via_function_calling("测试问题", {}, None)
            assert result is None

    def test_fc_no_tool_calls_returns_none(self, monkeypatch):
        """LLM 返回 success=True 但未调用任何工具时，应返回 None 触发 fallback。

        对齐方案设计："无 tool_calls → 降级走旧 agent_manager.process 路径"。
        否则空 tool_results 会绕过 fallback，用户拿不到真实模型计算。
        """
        from framework.config import Config

        # 覆盖 conftest 的 FC=False，开启 FC 路径
        monkeypatch.setattr(Config, "FUNCTION_CALLING_ENABLED", True)

        mock_llm = MagicMock()
        mock_llm.is_available.return_value = True
        mock_llm.generate_with_tools.return_value = {
            "success": True,
            "content": "我直接答复，未调用工具",
            "tool_results": {},
            "tool_calls_trace": [],
            "iterations": 1,
        }
        monkeypatch.setattr("framework.llm.service.llm_service", mock_llm)

        from framework.agents.nodes import _execute_via_function_calling

        result = _execute_via_function_calling("任意问题", {"question_type": 1}, trace_id="t-no-tools")
        assert result is None


# ── 5. ToolCallingLoop mock 测试 ─────────────────────────────────


class TestToolCallingLoop:
    """测试 ToolCallingLoop 多轮调用逻辑。"""

    def test_loop_terminates_when_no_tool_calls(self):
        """LLM 第 1 轮就返回纯文本，循环立即终止。"""
        from framework.function_calling.tool_loop import ToolCallingLoop

        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "这是最终答复"
        mock_response.tool_calls = None
        mock_llm.invoke.return_value = mock_response

        loop = ToolCallingLoop(llm=mock_llm, max_iterations=3)
        result = loop.run("测试问题")

        assert result["success"] is True
        assert result["content"] == "这是最终答复"
        assert result["iterations"] == 1

    def test_loop_executes_tool_then_terminates(self):
        """LLM 第 1 轮返回 tool_calls，第 2 轮返回纯文本。"""
        from framework.function_calling.tool_loop import ToolCallingLoop

        mock_llm = MagicMock()
        # 第 1 轮：返回 tool_call
        resp1 = MagicMock()
        resp1.content = ""
        resp1.tool_calls = [
            {"name": "model_1_stability_evaluation", "args": {"parcel_id": "1"}, "id": "tc1"}
        ]
        # 第 2 轮：返回纯文本
        resp2 = MagicMock()
        resp2.content = "稳定性分析完成"
        resp2.tool_calls = None

        mock_llm.invoke.side_effect = [resp1, resp2]

        # mock tool_executor
        with patch("framework.function_calling.tool_loop.tool_executor") as mock_exec:
            mock_exec.execute.return_value = {
                "success": True,
                "result": {"status": "ok", "result": {"module_1": {"SAFE_ABS": 0.0}}},
            }
            loop = ToolCallingLoop(llm=mock_llm, max_iterations=3)
            result = loop.run("请分析地块 1 的稳定性")

        assert result["success"] is True
        assert result["content"] == "稳定性分析完成"
        assert result["iterations"] == 2
        assert len(result["tool_calls_trace"]) == 1
        assert result["tool_calls_trace"][0]["tool_name"] == "model_1_stability_evaluation"

    def test_loop_exhausted_returns_partial(self):
        """LLM 永远返回 tool_calls，超限后返回 partial。"""
        from framework.function_calling.tool_loop import ToolCallingLoop

        mock_llm = MagicMock()
        resp = MagicMock()
        resp.content = ""
        resp.tool_calls = [{"name": "model_1_stability_evaluation", "args": {"parcel_id": "1"}, "id": "tc1"}]
        mock_llm.invoke.return_value = resp  # 永远返回 tool_calls

        with patch("framework.function_calling.tool_loop.tool_executor") as mock_exec:
            mock_exec.execute.return_value = {"success": True, "result": {"status": "ok"}}
            loop = ToolCallingLoop(llm=mock_llm, max_iterations=2)
            result = loop.run("测试")

        assert result["success"] is False
        assert result["reason"] == "tool_loop_exhausted"
        assert result["iterations"] == 2

    def test_llm_cannot_override_locked_parcel_id(self):
        from framework.function_calling.tool_loop import ToolCallingLoop

        mock_llm = MagicMock()
        response = MagicMock(content="")
        response.tool_calls = [{
            "name": "model_1_stability_evaluation",
            "args": {"parcel_id": "P999"}, "id": "tc-conflict",
        }]
        mock_llm.invoke.return_value = response
        with patch("framework.function_calling.tool_loop.tool_executor") as mock_exec:
            result = ToolCallingLoop(
                llm=mock_llm, default_args={"parcel_id": "P001"}
            ).run("分析当前地块")
        assert result["success"] is False
        assert result["reason"] == "analysis_object_conflict"
        mock_exec.execute.assert_not_called()
