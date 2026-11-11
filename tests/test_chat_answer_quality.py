# -*- coding: utf-8 -*-
"""聊天回答质量回归断言（fix-chat-answer-quality）。

覆盖：
- 稳定性复合意图路由保底（LLM 初判为 type-2 时回落到 type-1）
- 障碍度排序 Mapping 逐项渲染（禁止 str(dict) 字面量）
- Model-4 酸化状态确定性前缀（有实测报 pH + 分级；无实测给补测引导）
- LLM 幻觉字段名拦截（「耕作制度」）
- 会话上下文已知前提提取（同会话同地块）
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest


@pytest.fixture
def stability_routing_llm_override(monkeypatch):
    """模拟 ROUTING_MODE=llm 且 LLM 把稳定性问题误判为 type-2。"""
    from framework.config import Config
    import framework.agents.routing as routing

    monkeypatch.setattr(Config, "ROUTING_MODE", "llm")

    class _FakeLLM:
        def is_available(self):
            return True

        def generate(self, prompt, temperature=0.0):
            return {
                "success": True,
                "content": '{"question_type": 2, "relevance": 0.7, "reason": "测试误判为等级"}',
            }

    monkeypatch.setattr(routing, "llm_service", _FakeLLM())


def test_question_router_returns_type_2_for_grade_question():
    from framework.config import Config
    from framework.agents.routing import identify_question_type

    if Config.ROUTING_MODE == "llm":
        pytest.skip("纯关键词用例仅在 keyword 模式运行")
    question_type, relevance = identify_question_type(
        "这块地的质量等级怎么样", None,
    )
    assert question_type == 2


def test_stability_priority_overrides_llm_initial_judgment(stability_routing_llm_override):
    """「质量等级稳不稳，退化风险高吗」即使 LLM 判 type-2，也必须回落 type-1。"""
    from framework.agents.routing import identify_question_type
    import framework.agents.routing as routing

    question_type, relevance = identify_question_type(
        "我的田质量等级稳不稳，退化风险高吗",
        {"scale": "地块", "parcel_id": "3597", "data_type": "评价结果"},
    )
    assert question_type == 1
    assert routing._last_router_method == "keyword_override_llm"


def test_stability_priority_preserved_in_keyword_mode():
    """keyword 模式下稳定性问题仍为 type-1。"""
    from framework.agents.routing import identify_question_type

    question_type, relevance = identify_question_type(
        "我的田质量等级稳不稳，退化风险高吗",
        {"scale": "地块", "parcel_id": "3597"},
    )
    assert question_type == 1


def test_obstacle_degree_mapping_rendered_table():
    """障碍度数值型 dict 渲染为 GFM Markdown 表格（按数值降序），禁止 str(dict) 字面量。"""
    from framework.agents.parcel_field_query import _format_value

    rendered = _format_value(
        {"土壤酸碱度": 0.14, "有机质": 0.23, "质地构型": 0.23}, 3,
    )
    rows = rendered.split("\n")
    assert rows[0] == "| 指标 | 数值 |"
    assert rows[1] == "| --- | --- |"
    assert "| 有机质 | 0.23 |" in rows
    assert "| 土壤酸碱度 | 0.14 |" in rows
    # 降序：两条 0.23 在前，0.14 在后
    assert rows.index("| 有机质 | 0.23 |") == 2
    assert rows.index("| 土壤酸碱度 | 0.14 |") == 4
    assert "{" not in rendered
    assert "'" not in rendered


def test_acidification_prefix_with_measured_ph():
    """Model-4 结果携带实测 soil_ph 时输出 pH 与强酸性分级。"""
    from framework.agents.nodes import build_acidification_state_prefix

    prefix = build_acidification_state_prefix(
        {"model-4": {"result": {"soil_ph": 5.17}}}, parcel_id=None,
    )
    assert "土壤酸碱度（pH）为 5.17" in prefix
    assert "强酸性" in prefix


def test_acidification_prefix_without_measured_ph():
    """无实测 soil_ph 时给出确定性补测引导，而非笼统无法判断。"""
    from framework.agents.nodes import build_acidification_state_prefix

    prefix = build_acidification_state_prefix({}, parcel_id=None)
    assert "缺少实测土壤酸碱度" in prefix
    assert "补测" in prefix


def test_prohibited_field_name_detection():
    from framework.agents.nodes import has_prohibited_field_name

    assert has_prohibited_field_name("质地构型与耕作制度是主要障碍")
    assert not has_prohibited_field_name("质地构型与有机质是主要障碍")


def test_extract_prior_knowledge_same_parcel():
    from framework.agents.nodes import extract_prior_knowledge

    history = [
        {"role": "user", "content": "查询这块地的综合指数和障碍度排序"},
        {
            "role": "assistant",
            "content": (
                "分析对象：地块 3597\n\n"
                "广东省韶关市始兴县 地块 3597：耕地质量综合指数为 0.84。\n"
                "土壤酸碱度：0.14\n有机质：0.23"
            ),
        },
    ]
    prior = extract_prior_knowledge(history, "3597")
    assert "0.84" in prior
    assert "土壤酸碱度：0.14" in prior


def test_extract_prior_knowledge_cross_parcel_blocked():
    from framework.agents.nodes import extract_prior_knowledge

    history = [
        {
            "role": "assistant",
            "content": "分析对象：地块 1024\n\n综合指数为 0.80。",
        },
    ]
    assert extract_prior_knowledge(history, "3597") == ""


def test_tool_loop_injects_model4_soil_ph_from_snapshot(monkeypatch):
    """Model-4 工具结果缺 soil_ph 时，从权威快照兜底注入实测值，防 LLM 误报。"""
    from framework.function_calling.tool_loop import _inject_model4_soil_ph

    # 模拟权威快照：2621 实测 pH 5.43（强酸性 [4.5,5.5)）
    fake_snapshot = SimpleNamespace(
        indicators={
            "soil_ph": 5.434989,
            "organic_matter": 29.0,
        }
    )
    import framework.domain.data.parcel_data_accessor as pda_module

    monkeypatch.setattr(
        pda_module.ParcelDataAccessor,
        "get_parcel_snapshot",
        lambda self, pid: fake_snapshot,
    )

    payload = {
        "status": "ok",
        "result": {"parcel_id": "2621", "Aback": 108048.48},
    }
    _inject_model4_soil_ph(payload, {"parcel_id": "2621"})
    assert payload["result"]["soil_ph"] == 5.434989
    assert payload["result"]["acidification_level"] == "强酸性"
