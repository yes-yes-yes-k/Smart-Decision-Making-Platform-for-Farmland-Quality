"""测试 AgentManager 中心化编排器"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from framework.agents.manager import AgentManager
from framework.agents.output_contract import validate_result


def _assert_model_result(payload, expected_model_id):
    assert payload["model_id"] == expected_model_id
    valid, errors = validate_result(payload)
    assert valid, errors


def test_manager_register_six_agents():
    """Manager 注册 6 个智能体（model-1..model-6，model-6 为占位）"""
    mgr = AgentManager()
    assert set(mgr.agents.keys()) == {
        "model-1", "model-2", "model-3",
        "model-4", "model-5", "model-6",
    }
    print("✓ AgentManager 注册 6 个智能体（含 model-6 占位）")


def test_manager_topological_sort_province():
    """province 角色 [model-1, model-3]，model-3 依赖 model-2 但 model-2 不在集合内，
    因此仅按现有依赖排序，输出顺序保留两个智能体。"""
    mgr = AgentManager()
    ordered = mgr._topological_sort(["model-1", "model-3"])
    assert set(ordered) == {"model-1", "model-3"}
    print("✓ 拓扑排序处理部分依赖（依赖不在集合内时安全跳过）")


def test_manager_topological_sort_farmer():
    """farmer 角色 [model-4, model-5]，model-4/model-5 均无互相依赖，
    拓扑排序包含全部两个智能体。"""
    mgr = AgentManager()
    ordered = mgr._topological_sort(["model-4", "model-5"])
    assert set(ordered) == {"model-4", "model-5"}
    print("✓ 拓扑排序包含 farmer 角色全部两个智能体")


def test_manager_process_type1_returns_structured_result():
    """process 返回 Schema 2.0 内部编排结构（type 1 稳定性 → model-1）。"""
    mgr = AgentManager()
    result = mgr.process("我的田质量等级稳定吗", {"question_type": 1, "area_code": "lechang"})
    assert result["status"] == "ok"
    assert result["question_type"] == 1
    assert list(result["models"]) == ["model-1"]
    assert isinstance(result["answer"], str)
    assert isinstance(result["recommendations"], list)
    _assert_model_result(result["models"]["model-1"], "stability-risk-evaluation")
    print("✓ AgentManager.process 返回符合规范的结构化结果")


def test_manager_process_no_question_type_returns_no_routing():
    """无 question_type 的问题返回 no_routing（不再默认 farmer）"""
    mgr = AgentManager()
    result = mgr.process("你好", {})
    assert result["status"] == "no_routing"
    assert result["models"] == {}
    assert result["answer"] == "未识别问题类型"
    print("✓ 无 question_type 返回 no_routing")


def test_type2_routes_to_model2():
    """type=2 质量等级应路由到 model-2（1:1 映射）"""
    from framework.agents.router import QuestionTypeRouter
    router = QuestionTypeRouter()
    agents = router.get_agents_for_type(2)
    assert agents == ["model-2"], f"type 2 应仅映射 model-2: {agents}"
    print("✓ type 2 路由到 model-2（1:1 映射）")


def test_model2_executed_for_type2_question():
    """type=2 质量等级问题返回 model-2 的规范结果。"""
    mgr = AgentManager()
    result = mgr.process("我的田耕地质量等级是多少？", {"question_type": 2, "parcel_code": "A0001"})
    m2 = result["models"]["model-2"]
    _assert_model_result(m2, "quality-grade-evaluation")
    assert m2["status"] != "unavailable"
    print("✓ type=2 质量等级问题 model-2 被执行")


def test_process_type1_routes_to_model1_only():
    """type=1 稳定性 → 仅调 model-1，不调 model-2/3/4/5"""
    mgr = AgentManager()
    result = mgr.process("查询区域内耕地质量等级整体稳定吗", {"question_type": 1})
    assert result["status"] == "ok"
    assert list(result["models"]) == ["model-1"]
    assert result["question_type"] == 1
    print("✓ type=1 路由到 model-1（稳定性）")


def test_process_type2_routes_to_model2_only():
    """type=2 质量等级 → 仅调 model-2"""
    mgr = AgentManager()
    result = mgr.process("我的田耕地质量等级是多少", {"question_type": 2, "parcel_code": "A0001"})
    assert list(result["models"]) == ["model-2"]
    assert result["question_type"] == 2
    print("✓ type=2 路由到 model-2（质量等级）")


def test_process_type3_routes_to_model3_only():
    """type=3 障碍诊断 → 仅调 model-3，不调 model-1/2"""
    mgr = AgentManager()
    result = mgr.process("我这块地到底有啥毛病", {"question_type": 3})
    assert list(result["models"]) == ["model-3"]
    print("✓ type=3 路由到 model-3（障碍诊断）")


def test_process_type4_routes_to_model4_only():
    """type=4 酸化改良 → 仅调 model-4，不调 model-2"""
    mgr = AgentManager()
    result = mgr.process("我的田酸化严重吗", {"question_type": 4})
    assert list(result["models"]) == ["model-4"]
    print("✓ type=4 路由到 model-4（酸化改良）")


def test_process_type5_routes_to_model5_only():
    """type=5 有机质培肥 → 仅调 model-5，不调 model-1/2/3/4"""
    mgr = AgentManager()
    result = mgr.process("为了提升耕地土壤有机质，有机肥或者秸秆每亩施用量多少", {"question_type": 5})
    assert list(result["models"]) == ["model-5"]
    print("✓ type=5 路由到 model-5（有机质培肥）")


def test_process_no_routing_when_question_type_none():
    """question_type=None（context 缺失）→ no_routing 空结果"""
    mgr = AgentManager()
    result = mgr.process("你好", {})
    assert result["status"] == "no_routing"
    assert result["models"] == {}
    assert result["answer"] == "未识别问题类型"
    print("✓ question_type=None 返回 no_routing")


def test_process_no_routing_when_question_type_zero():
    """question_type=0 → no_routing（route_models 保证不进入，此处为防御性）"""
    mgr = AgentManager()
    result = mgr.process("什么是土壤酸化", {"question_type": 0})
    assert result["status"] == "no_routing"
    assert result["models"] == {}
    print("✓ question_type=0 返回 no_routing")


def test_process_no_routing_when_question_type_unknown():
    """question_type=8（超出范围）→ no_routing"""
    mgr = AgentManager()
    result = mgr.process("未知问题", {"question_type": 8})
    assert result["status"] == "no_routing"
    assert result["question_type"] == 8
    print("✓ 未知 question_type 返回 no_routing")


def test_type1_contains_only_valid_model1_result():
    """type=1 路由到 model-1，models 中只包含规范结果。"""
    mgr = AgentManager()
    result = mgr.process("我的田质量等级稳定吗", {"question_type": 1})
    assert list(result["models"]) == ["model-1"]
    _assert_model_result(result["models"]["model-1"], "stability-risk-evaluation")
    print("✓ type=1 models 中仅包含规范 model-1 结果")


def test_type2_contains_only_valid_model2_result():
    """type=2 路由到 model-2，models 中只包含规范结果。"""
    mgr = AgentManager()
    result = mgr.process("我的田耕地质量等级是多少", {"question_type": 2, "parcel_code": "A0001"})
    assert list(result["models"]) == ["model-2"]
    _assert_model_result(result["models"]["model-2"], "quality-grade-evaluation")
    print("✓ type=2 models 中仅包含规范 model-2 结果")


if __name__ == "__main__":
    test_manager_register_six_agents()
    test_manager_topological_sort_province()
    test_manager_topological_sort_farmer()
    test_manager_process_type1_returns_structured_result()
    test_manager_process_no_question_type_returns_no_routing()
    test_type2_routes_to_model2()
    test_model2_executed_for_type2_question()
    test_process_type1_routes_to_model1_only()
    test_process_type2_routes_to_model2_only()
    test_process_type3_routes_to_model3_only()
    test_process_type4_routes_to_model4_only()
    test_process_type5_routes_to_model5_only()
    test_process_no_routing_when_question_type_none()
    test_process_no_routing_when_question_type_zero()
    test_process_no_routing_when_question_type_unknown()
    test_no_skipped_entries_in_details_for_type1()
    test_no_skipped_entries_in_details_for_type2()
    print("\n所有 AgentManager 测试通过！")
