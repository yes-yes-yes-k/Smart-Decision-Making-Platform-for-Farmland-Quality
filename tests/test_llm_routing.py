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
