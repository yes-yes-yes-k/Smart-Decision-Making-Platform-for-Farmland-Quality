"""测试 delta spec 与 xlsx 总览表的一致性（D1/D2/D3）。"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PROFESSIONAL_SPEC = "openspec/changes/archive/2026-07-24-sync-model-specs-from-overview/specs/professional-model-agents/spec.md"
ROUTING_SPEC = "openspec/changes/archive/2026-07-24-sync-model-specs-from-overview/specs/role-based-routing/spec.md"


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def test_six_models_present():
    s = _read(PROFESSIONAL_SPEC)
    for name in [
        "StabilityRiskAgent", "PotentialAssessmentAgent", "ProblemIdentificationAgent",
        "AcidificationRemediationAgent", "OrganicMatterAgent", "FertilityMLAgent",
    ]:
        assert name in s, f"delta spec 缺少智能体: {name}"


def test_model1_io_keywords():
    s = _read(PROFESSIONAL_SPEC)
    # 模型1 输入关键词
    assert "11 个评价指标及权重" in s
    assert "灌溉能力" in s and "排水能力" in s and "地形部位" in s
    # 模型1 输出关键词
    assert "等级边界安全度" in s
    assert "退化空间集聚风险" in s
    assert "持续低质风险" in s


def test_model4_io_and_standards():
    s = _read(PROFESSIONAL_SPEC)
    # 模型4 输入
    assert "交换性铝离子" in s
    assert "木本泥炭施用量" in s or "碱性调理剂施用量" in s
    # 模型4 引用标准
    assert "GB/T 42817-2023" in s
    assert "NY/T 443-2019" in s


def test_model5_io_keywords():
    s = _read(PROFESSIONAL_SPEC)
    assert "目标土壤有机质" in s
    assert "秸秆施用量" in s or "有机肥施用量" in s


def test_model6_name_rollback_d1():
    """D1: model 6 名称回退为"耕地综合地力改良提升模型"，旧名不出现"""
    s = _read(PROFESSIONAL_SPEC)
    assert "耕地综合地力改良提升模型" in s
    assert "耕地肥力机器学习预测模型" not in s


def test_model6_internal_implementation_note():
    """model 6 标注内部使用 ML 预测"""
    s = _read(PROFESSIONAL_SPEC)
    assert "ExtraTreesRegressor" in s or "ML 预测" in s or "model_6_execution" in s


def test_model6_xlsx_blank_note():
    """model 6 标注 xlsx 未填写，保留现有实现"""
    s = _read(PROFESSIONAL_SPEC)
    assert "xlsx 未填写" in s or "保留现有实现" in s


def test_scenarios_count_refined_d3():
    """D3: 提炼版 scenario 约 30 个（每模型 4-7 个）"""
    s = _read(PROFESSIONAL_SPEC)
    scenario_count = s.count("#### Scenario:")
    assert 20 <= scenario_count <= 40, f"scenario 数量 {scenario_count} 不在提炼版预期范围 20-40"


def test_three_role_scenarios_covered():
    """3 角色经典问题在 scenario 中有体现"""
    s = _read(PROFESSIONAL_SPEC)
    # 县域端
    assert "县域" in s or "本县" in s or "县" in s
    # 农户端
    assert "农户" in s or "我的" in s


def test_routing_type_descriptions_align_d5():
    """D5: role-based-routing TYPE 描述对齐"""
    s = _read(ROUTING_SPEC)
    assert "TYPE_1（等级稳定性/退化风险）" in s
    assert "TYPE_2（酸化程度/调理剂/改良方案）" in s
    assert "TYPE_3（潜力/障碍因素/主要问题）" in s
    assert "TYPE_4（有机质/有机肥/肥力/有机碳）" in s


def test_routing_type_to_model_mapping():
    s = _read(ROUTING_SPEC)
    assert "StabilityRiskAgent (model-1)" in s
    assert "AcidificationRemediationAgent (model-4)" in s
    assert "FertilityMLAgent (model-6)" in s
    assert "OrganicMatterAgent (model-5)" in s


def test_routing_keyword_priority_scenario():
    """关键词优先于向量匹配 scenario 存在"""
    s = _read(ROUTING_SPEC)
    assert "关键词优先于向量匹配" in s


if __name__ == "__main__":
    test_six_models_present()
    test_model1_io_keywords()
    test_model4_io_and_standards()
    test_model5_io_keywords()
    test_model6_name_rollback_d1()
    test_model6_internal_implementation_note()
    test_model6_xlsx_blank_note()
    test_scenarios_count_refined_d3()
    test_three_role_scenarios_covered()
    test_routing_type_descriptions_align_d5()
    test_routing_type_to_model_mapping()
    test_routing_keyword_priority_scenario()
    print("\nspec 一致性测试通过！")
