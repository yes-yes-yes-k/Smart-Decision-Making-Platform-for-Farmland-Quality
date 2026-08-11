"""LLM 路由判定测试：覆盖开关、可用性、解析失败回退、越界回退、排他规则叠加。"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest


def test_routing_mode_default_is_llm(monkeypatch):
    """默认 ROUTING_MODE 为 llm。"""
    monkeypatch.delenv("ROUTING_MODE", raising=False)
    # 强制重新读取 Config（类属性在模块加载时已绑定，故用直接断言默认值）
    from framework.config import Config
    assert Config.ROUTING_MODE == "llm"


def test_routing_mode_reads_env(monkeypatch):
    """ROUTING_MODE 环境变量覆盖默认值。

    Config.ROUTING_MODE 在类定义时绑定，故通过重新加载 config 模块验证。
    """
    import importlib
    monkeypatch.setenv("ROUTING_MODE", "keyword")
    import framework.config as _cfg
    importlib.reload(_cfg)
    assert _cfg.Config.ROUTING_MODE == "keyword"
    # 还原
    monkeypatch.delenv("ROUTING_MODE", raising=False)
    importlib.reload(_cfg)


class TestSafeParseLLMResult:
    """_safe_parse_llm_result 解析与边界保护。"""

    def test_parse_valid_json(self):
        from framework.agents.routing import _safe_parse_llm_result
        result = _safe_parse_llm_result(
            '{"question_type": 3, "relevance": 0.9, "reason": "障碍诊断"}'
        )
        assert result == (3, 0.9, "障碍诊断")

    def test_parse_valid_json_with_extra_fields(self):
        from framework.agents.routing import _safe_parse_llm_result
        result = _safe_parse_llm_result(
            '{"question_type": 1, "relevance": 0.8, "reason": "稳定性", "extra": "ignored"}'
        )
        assert result == (1, 0.8, "稳定性")

    def test_parse_invalid_json_returns_none(self):
        from framework.agents.routing import _safe_parse_llm_result
        assert _safe_parse_llm_result("not a json") is None
        assert _safe_parse_llm_result("") is None
        assert _safe_parse_llm_result("{broken") is None

    def test_parse_missing_question_type_returns_none(self):
        from framework.agents.routing import _safe_parse_llm_result
        assert _safe_parse_llm_result('{"relevance": 0.5, "reason": "x"}') is None

    def test_parse_non_int_question_type_returns_none(self):
        from framework.agents.routing import _safe_parse_llm_result
        assert _safe_parse_llm_result('{"question_type": "3", "relevance": 0.5}') is None

    def test_parse_out_of_range_returns_none(self):
        from framework.agents.routing import _safe_parse_llm_result
        # 越界：7 超过 0..6
        assert _safe_parse_llm_result('{"question_type": 7, "relevance": 0.5}') is None
        # 越界：-1
        assert _safe_parse_llm_result('{"question_type": -1, "relevance": 0.5}') is None

    def test_parse_boundary_values_accepted(self):
        from framework.agents.routing import _safe_parse_llm_result
        # 0..6 均合法
        assert _safe_parse_llm_result('{"question_type": 0, "relevance": 0.0}') is not None
        assert _safe_parse_llm_result('{"question_type": 6, "relevance": 1.0}') is not None

    def test_parse_missing_reason_defaults_to_empty(self):
        from framework.agents.routing import _safe_parse_llm_result
        # reason 缺失：允许，默认空串
        result = _safe_parse_llm_result('{"question_type": 2, "relevance": 0.5}')
        assert result == (2, 0.5, "")

    def test_parse_missing_relevance_defaults_zero(self):
        from framework.agents.routing import _safe_parse_llm_result
        result = _safe_parse_llm_result('{"question_type": 2, "reason": "x"}')
        assert result == (2, 0.0, "x")


class TestIdentifyQuestionTypeLLM:
    """_identify_question_type_llm 行为：mock llm_service，覆盖可用/不可用/解析失败。"""

    def test_llm_unavailable_returns_none(self, monkeypatch):
        from framework.agents import routing
        from framework.llm.service import llm_service
        monkeypatch.setattr(llm_service, "is_available", lambda: False)
        result = routing._identify_question_type_llm("我的田酸化严重吗？", None)
        assert result is None

    def test_llm_returns_valid_json(self, monkeypatch):
        from framework.agents import routing
        from framework.llm.service import llm_service

        def _fake_generate(prompt, **kwargs):
            return {
                "success": True,
                "content": '{"question_type": 4, "relevance": 0.95, "reason": "酸化改良"}',
                "model": "mock",
                "type": "llm",
            }

        monkeypatch.setattr(llm_service, "is_available", lambda: True)
        monkeypatch.setattr(llm_service, "generate", _fake_generate)
        result = routing._identify_question_type_llm("我的田酸化严重吗？", None)
        assert result == (4, 0.95, "酸化改良")

    def test_llm_returns_invalid_json_returns_none(self, monkeypatch):
        from framework.agents import routing
        from framework.llm.service import llm_service

        def _fake_generate(prompt, **kwargs):
            return {"success": True, "content": "not json", "model": "mock", "type": "llm"}

        monkeypatch.setattr(llm_service, "is_available", lambda: True)
        monkeypatch.setattr(llm_service, "generate", _fake_generate)
        result = routing._identify_question_type_llm("我的田酸化严重吗？", None)
        assert result is None

    def test_llm_returns_out_of_range_returns_none(self, monkeypatch):
        from framework.agents import routing
        from framework.llm.service import llm_service

        def _fake_generate(prompt, **kwargs):
            return {
                "success": True,
                "content": '{"question_type": 99, "relevance": 0.9}',
                "model": "mock",
                "type": "llm",
            }

        monkeypatch.setattr(llm_service, "is_available", lambda: True)
        monkeypatch.setattr(llm_service, "generate", _fake_generate)
        result = routing._identify_question_type_llm("我的田酸化严重吗？", None)
        assert result is None

    def test_llm_generate_raises_returns_none(self, monkeypatch):
        from framework.agents import routing
        from framework.llm.service import llm_service

        def _boom(prompt, **kwargs):
            raise RuntimeError("network down")

        monkeypatch.setattr(llm_service, "is_available", lambda: True)
        monkeypatch.setattr(llm_service, "generate", _boom)
        result = routing._identify_question_type_llm("我的田酸化严重吗？", None)
        assert result is None

    def test_llm_call_uses_temperature_zero(self, monkeypatch):
        """LLM 调用必须传 temperature=0.0 以保证确定性。"""
        from framework.agents import routing
        from framework.llm.service import llm_service

        captured = {}

        def _fake_generate(prompt, **kwargs):
            captured["kwargs"] = kwargs
            return {
                "success": True,
                "content": '{"question_type": 4, "relevance": 0.9, "reason": "x"}',
                "model": "mock",
                "type": "llm",
            }

        monkeypatch.setattr(llm_service, "is_available", lambda: True)
        monkeypatch.setattr(llm_service, "generate", _fake_generate)
        routing._identify_question_type_llm("我的田酸化严重吗？", None)
        assert captured["kwargs"].get("temperature") == 0.0

    def test_llm_prompt_contains_all_capabilities(self, monkeypatch):
        """prompt 必须包含全部 6 个能力的名称与描述。"""
        from framework.agents import routing
        from framework.agents.capabilities import PROFESSIONAL_CAPABILITIES
        from framework.llm.service import llm_service

        captured = {}

        def _fake_generate(prompt, **kwargs):
            captured["prompt"] = prompt
            return {
                "success": True,
                "content": '{"question_type": 1, "relevance": 0.9, "reason": "x"}',
                "model": "mock",
                "type": "llm",
            }

        monkeypatch.setattr(llm_service, "is_available", lambda: True)
        monkeypatch.setattr(llm_service, "generate", _fake_generate)
        routing._identify_question_type_llm("我的田酸化严重吗？", None)
        prompt_text = captured["prompt"]
        for cap in PROFESSIONAL_CAPABILITIES:
            assert cap.name in prompt_text, f"prompt 缺少能力名称：{cap.name}"
            assert cap.description in prompt_text, f"prompt 缺少能力描述：{cap.description}"

    def test_llm_duration_recorded(self, monkeypatch):
        """成功调用后 _last_llm_duration_ms 应为非负 float。"""
        from framework.agents import routing
        from framework.llm.service import llm_service

        def _fake_generate(prompt, **kwargs):
            return {
                "success": True,
                "content": '{"question_type": 4, "relevance": 0.9, "reason": "x"}',
                "model": "mock",
                "type": "llm",
            }

        monkeypatch.setattr(llm_service, "is_available", lambda: True)
        monkeypatch.setattr(llm_service, "generate", _fake_generate)
        routing._identify_question_type_llm("我的田酸化严重吗？", None)
        assert routing._last_llm_duration_ms is not None
        assert routing._last_llm_duration_ms >= 0.0
        assert routing._last_llm_reason == "x"


class TestIdentifyQuestionTypeRouting:
    """identify_question_type 在 ROUTING_MODE 切换下的端到端行为。"""

    def test_knowledge_question_skips_llm(self, monkeypatch):
        """知识性问题（type 0）不调 LLM。"""
        from framework.agents import routing
        from framework.llm.service import llm_service

        called = {"count": 0}

        def _fake_generate(prompt, **kwargs):
            called["count"] += 1
            return {"success": True, "content": "{}", "model": "mock", "type": "llm"}

        monkeypatch.setattr(routing, "LLM_AVAILABLE", True)
        monkeypatch.setattr(llm_service, "is_available", lambda: True)
        monkeypatch.setattr(llm_service, "generate", _fake_generate)
        monkeypatch.setattr(routing, "EMBEDDING_AVAILABLE", False)

        qt, rel = routing.identify_question_type("什么是耕地质量等级？")
        assert qt == 0
        assert called["count"] == 0  # LLM 未被调用
        assert routing._last_router_method == "knowledge"

    def test_keyword_mode_skips_llm(self, monkeypatch):
        """ROUTING_MODE=keyword 时纯关键词路径，不调 LLM。"""
        from framework.agents import routing
        from framework.llm.service import llm_service
        from framework.config import Config

        called = {"count": 0}

        def _fake_generate(prompt, **kwargs):
            called["count"] += 1
            return {"success": True, "content": "{}", "model": "mock", "type": "llm"}

        monkeypatch.setattr(routing, "LLM_AVAILABLE", True)
        monkeypatch.setattr(llm_service, "is_available", lambda: True)
        monkeypatch.setattr(llm_service, "generate", _fake_generate)
        monkeypatch.setattr(routing, "EMBEDDING_AVAILABLE", False)
        monkeypatch.setattr(Config, "ROUTING_MODE", "keyword")

        qt, _ = routing.identify_question_type("我的田耕地质量等级是多少")
        assert qt == 2
        assert called["count"] == 0
        assert routing._last_router_method == "keyword"

    def test_llm_mode_uses_llm_result_when_available(self, monkeypatch):
        """ROUTING_MODE=llm 且 LLM 可用：使用 LLM 结果。"""
        from framework.agents import routing
        from framework.llm.service import llm_service
        from framework.config import Config

        def _fake_generate(prompt, **kwargs):
            return {
                "success": True,
                "content": '{"question_type": 2, "relevance": 0.9, "reason": "等级评价"}',
                "model": "mock",
                "type": "llm",
            }

        monkeypatch.setattr(routing, "LLM_AVAILABLE", True)
        monkeypatch.setattr(llm_service, "is_available", lambda: True)
        monkeypatch.setattr(llm_service, "generate", _fake_generate)
        monkeypatch.setattr(routing, "EMBEDDING_AVAILABLE", False)
        monkeypatch.setattr(Config, "ROUTING_MODE", "llm")

        qt, rel = routing.identify_question_type("我的田耕地质量等级是多少")
        assert qt == 2
        assert rel == 0.9
        assert routing._last_router_method == "llm"
        assert routing._last_llm_reason == "等级评价"

    def test_llm_mode_falls_back_when_llm_unavailable(self, monkeypatch):
        """ROUTING_MODE=llm 但 LLM 不可用：回退关键词。"""
        from framework.agents import routing
        from framework.llm.service import llm_service
        from framework.config import Config

        monkeypatch.setattr(routing, "LLM_AVAILABLE", True)
        monkeypatch.setattr(llm_service, "is_available", lambda: False)
        monkeypatch.setattr(routing, "EMBEDDING_AVAILABLE", False)
        monkeypatch.setattr(Config, "ROUTING_MODE", "llm")

        qt, _ = routing.identify_question_type("我的田耕地质量等级是多少")
        assert qt == 2
        assert routing._last_router_method == "keyword"

    def test_llm_mode_falls_back_on_parse_failure(self, monkeypatch):
        """ROUTING_MODE=llm，LLM 返回非 JSON：回退关键词。"""
        from framework.agents import routing
        from framework.llm.service import llm_service
        from framework.config import Config

        def _fake_generate(prompt, **kwargs):
            return {"success": True, "content": "not json", "model": "mock", "type": "llm"}

        monkeypatch.setattr(routing, "LLM_AVAILABLE", True)
        monkeypatch.setattr(llm_service, "is_available", lambda: True)
        monkeypatch.setattr(llm_service, "generate", _fake_generate)
        monkeypatch.setattr(routing, "EMBEDDING_AVAILABLE", False)
        monkeypatch.setattr(Config, "ROUTING_MODE", "llm")

        qt, _ = routing.identify_question_type("我的田耕地质量等级是多少")
        assert qt == 2
        assert routing._last_router_method == "keyword"

    def test_llm_mode_falls_back_on_out_of_range(self, monkeypatch):
        """ROUTING_MODE=llm，LLM 返回越界类型：回退关键词。"""
        from framework.agents import routing
        from framework.llm.service import llm_service
        from framework.config import Config

        def _fake_generate(prompt, **kwargs):
            return {
                "success": True,
                "content": '{"question_type": 99, "relevance": 0.9}',
                "model": "mock",
                "type": "llm",
            }

        monkeypatch.setattr(routing, "LLM_AVAILABLE", True)
        monkeypatch.setattr(llm_service, "is_available", lambda: True)
        monkeypatch.setattr(llm_service, "generate", _fake_generate)
        monkeypatch.setattr(routing, "EMBEDDING_AVAILABLE", False)
        monkeypatch.setattr(Config, "ROUTING_MODE", "llm")

        qt, _ = routing.identify_question_type("我的田耕地质量等级是多少")
        assert qt == 2
        assert routing._last_router_method == "keyword"

    def test_exclusive_rules_applied_after_llm(self, monkeypatch):
        """LLM 判定后仍叠加排他规则：scale-only context 不触发维度规则，保持 LLM 结果。"""
        from framework.agents import routing
        from framework.llm.service import llm_service
        from framework.config import Config

        def _fake_generate(prompt, **kwargs):
            return {
                "success": True,
                "content": '{"question_type": 3, "relevance": 0.9, "reason": "障碍"}',
                "model": "mock",
                "type": "llm",
            }

        monkeypatch.setattr(routing, "LLM_AVAILABLE", True)
        monkeypatch.setattr(llm_service, "is_available", lambda: True)
        monkeypatch.setattr(llm_service, "generate", _fake_generate)
        monkeypatch.setattr(routing, "EMBEDDING_AVAILABLE", False)
        monkeypatch.setattr(Config, "ROUTING_MODE", "llm")

        qt, _ = routing.identify_question_type(
            "我这块地到底有啥毛病", {"scale": "地块"}
        )
        assert qt == 3  # 排他规则不改变结果
        assert routing._last_router_method == "llm"

    def test_exclusive_rules_override_llm_when_triggered(self, monkeypatch):
        """排他规则命中时覆盖 LLM 判定（保留现有规则语义）。"""
        from framework.agents import routing
        from framework.llm.service import llm_service
        from framework.config import Config

        # LLM 判定为 model-5（有机质），但问题含"酸化调理剂"，排他规则应修正为 model-4
        def _fake_generate(prompt, **kwargs):
            return {
                "success": True,
                "content": '{"question_type": 5, "relevance": 0.9, "reason": "有机质"}',
                "model": "mock",
                "type": "llm",
            }

        monkeypatch.setattr(routing, "LLM_AVAILABLE", True)
        monkeypatch.setattr(llm_service, "is_available", lambda: True)
        monkeypatch.setattr(llm_service, "generate", _fake_generate)
        monkeypatch.setattr(routing, "EMBEDDING_AVAILABLE", False)
        monkeypatch.setattr(Config, "ROUTING_MODE", "llm")

        # 五维 context 触发排他规则：酸化调理剂 → model-4
        context = {
            "scale": "地块",
            "data_type": "处方用量",
            "business_task": "酸化改良",
            "expected_output": "处方用量",
        }
        qt, _ = routing.identify_question_type("酸化调理剂每亩施用量", context)
        assert qt == 4  # 排他规则修正
        # router_method 仍记录 LLM（实际初判来源），排他规则是后续叠加
        assert routing._last_router_method == "llm"

    def test_state_reset_between_calls(self, monkeypatch):
        """多次调用之间，模块级状态被正确重置。"""
        from framework.agents import routing
        from framework.llm.service import llm_service
        from framework.config import Config

        def _fake_generate(prompt, **kwargs):
            return {
                "success": True,
                "content": '{"question_type": 2, "relevance": 0.9, "reason": "等级"}',
                "model": "mock",
                "type": "llm",
            }

        monkeypatch.setattr(routing, "LLM_AVAILABLE", True)
        monkeypatch.setattr(llm_service, "is_available", lambda: True)
        monkeypatch.setattr(llm_service, "generate", _fake_generate)
        monkeypatch.setattr(routing, "EMBEDDING_AVAILABLE", False)
        monkeypatch.setattr(Config, "ROUTING_MODE", "llm")

        # 第一次：LLM 调用
        routing.identify_question_type("我的田耕地质量等级是多少")
        assert routing._last_router_method == "llm"
        assert routing._last_llm_duration_ms is not None

        # 第二次：keyword 模式，状态应被重置
        monkeypatch.setattr(Config, "ROUTING_MODE", "keyword")
        routing.identify_question_type("我的田耕地质量等级是多少")
        assert routing._last_router_method == "keyword"
        # keyword 模式下 LLM 未调用，duration 应为 None
        assert routing._last_llm_duration_ms is None
        assert routing._last_llm_reason is None

    def test_context_none_preserves_v1_behavior(self, monkeypatch):
        """context=None 时行为与 v1 完全一致（不应用排他规则，不调 LLM 若 keyword 模式）。"""
        from framework.agents import routing
        from framework.config import Config

        monkeypatch.setattr(routing, "EMBEDDING_AVAILABLE", False)
        monkeypatch.setattr(Config, "ROUTING_MODE", "keyword")

        cases = [
            ("我这块地到底有啥毛病？", 3),
            ("酸化调理剂每亩施用量", 4),
            ("有机肥每亩施用量多少", 5),
            ("这块地稳定性退化风险", 1),
            ("耕地质量等级评价结果", 2),
        ]
        for q, expected in cases:
            qt, _ = routing.identify_question_type(q)
            assert qt == expected, f"「{q}」期望 TYPE_{expected}，实际 TYPE_{qt}"
