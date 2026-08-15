"""验证 context 增强路由：用户已选地块时，模糊提问应路由到专业模型。

测试场景：
1. 无 parcel_id 时「帮我出个施肥方案」→ type=0（知识性，落入 RAG）
2. 带 parcel_id 时「帮我出个施肥方案」→ type=5（有机质培肥，路由到专业模型）
3. 带 parcel_id 时「这块地怎么样」→ type=2（质量等级评价）
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from framework.config import Config
# 确保使用 LLM 模式
setattr(Config, "ROUTING_MODE", "llm")

from framework.agents.routing import identify_question_type


def test_no_parcel_施肥方案_routes_to_rag():
    """无 parcel_id 时「帮我出个施肥方案」→ type=0（知识性，保守落入 RAG）"""
    qt, _ = identify_question_type("帮我出个施肥方案", context=None)
    assert qt == 0, f"无地块上下文时施肥方案应落入 RAG (type=0)，实际 type={qt}"
    print(f"✓ 无 parcel_id: 「帮我出个施肥方案」→ type={qt}（RAG，合理）")


def test_with_parcel_施肥方案_routes_to_type5():
    """带 parcel_id 时「帮我出个施肥方案」→ type=5（有机质培肥）"""
    context = {
        "scale": "地块",
        "data_type": "指标数据",
        "parcel_id": "001",
    }
    qt, _ = identify_question_type("帮我出个施肥方案", context=context)
    assert qt == 5, f"带 parcel_id 时施肥方案应路由到 type=5（有机质培肥），实际 type={qt}"
    print(f"✓ 带 parcel_id: 「帮我出个施肥方案」→ type={qt}（有机质培肥，命中）")


def test_with_parcel_这块地怎么样_routes_to_type2():
    """带 parcel_id 时「这块地怎么样」→ type=2（质量等级评价）"""
    context = {
        "scale": "地块",
        "data_type": "评价结果",
        "parcel_id": "001",
    }
    qt, _ = identify_question_type("这块地怎么样", context=context)
    assert qt == 2, f"带 parcel_id 时「这块地怎么样」应路由到 type=2（质量等级），实际 type={qt}"
    print(f"✓ 带 parcel_id: 「这块地怎么样」→ type={qt}（质量等级，命中）")


def test_with_parcel_code_also_triggers_context_rule():
    """带 parcel_code（无 parcel_id）也应触发 context 路由规则"""
    context = {
        "scale": "地块",
        "data_type": "评价结果",
        "parcel_code": "A0001",
    }
    qt, _ = identify_question_type("帮我出个施肥方案", context=context)
    assert qt == 5, f"带 parcel_code 时施肥方案应路由到 type=5，实际 type={qt}"
    print(f"✓ 带 parcel_code: 「帮我出个施肥方案」→ type={qt}（有机质培肥，命中）")


def test_no_parcel_无关问题仍_routes_to_rag():
    """无 parcel_id 时无关问题仍落入 RAG（context 增强不影响无关问题）"""
    qt, _ = identify_question_type("今天天气怎么样", context=None)
    assert qt == 0, f"无关问题应落入 RAG (type=0)，实际 type={qt}"
    print(f"✓ 无 parcel_id: 「今天天气怎么样」→ type={qt}（RAG，正确）")


if __name__ == "__main__":
    test_no_parcel_施肥方案_routes_to_rag()
    test_with_parcel_施肥方案_routes_to_type5()
    test_with_parcel_这块地怎么样_routes_to_type2()
    test_with_parcel_code_also_triggers_context_rule()
    test_no_parcel_无关问题仍_routes_to_rag()
    print("\n所有 context 增强路由测试通过！")
