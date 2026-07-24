"""测试 6 个 agent 对 xlsx 3 角色经典问题的回复（D4 最小化改动）。"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_stability_overall_province():
    from framework.agents.specialized.stability_risk_agent import StabilityRiskAgent
    out = StabilityRiskAgent().answer_question("查询区域内耕地质量等级整体稳定吗？", {})
    assert out["simulated"] is True
    assert "稳定" in out["answer"]
    assert 0.0 <= out["confidence"] <= 1.0


def test_stability_weak_county_list():
    """县域端：稳定性较弱乡镇/地块清单"""
    from framework.agents.specialized.stability_risk_agent import StabilityRiskAgent
    out = StabilityRiskAgent().answer_question(
        "本县哪些乡镇或地块等级稳定性较弱，需要现场复核？", {})
    assert out["simulated"] is True
    # 收紧：必须命中「县域薄弱片区分支」专属产出，旧 else 分支不含此字符串
    assert "本县稳定性较弱" in out["answer"]
    assert len(out["evidence"]) >= 1


def test_stability_farmer_plain_language():
    """农户端：通俗语言说明稳不稳"""
    from framework.agents.specialized.stability_risk_agent import StabilityRiskAgent
    out = StabilityRiskAgent().answer_question("我的这块田质量等级稳不稳？", {})
    assert out["simulated"] is True
    assert "稳" in out["answer"]
    # 收紧：必须命中「农户稳不稳分支」三档之一，排除"稳定/一般/较弱"宽泛词
    assert any(w in out["answer"] for w in ["比较稳", "一般稳", "不太稳"])


def test_stability_attention_list():
    """重点关注清单"""
    from framework.agents.specialized.stability_risk_agent import StabilityRiskAgent
    out = StabilityRiskAgent().answer_question("查询区域内哪些对象需要纳入重点关注清单？", {})
    assert out["simulated"] is True
    # 收紧：必须命中「关注清单分支」专属产出
    assert "建议纳入重点关注清单" in out["answer"]


def test_potential_overall_uplift():
    from framework.agents.specialized.potential_agent import PotentialAssessmentAgent
    out = PotentialAssessmentAgent().answer_question(
        "辖区耕地质量提升的总体潜力有多大？可增产多少粮食？", {})
    assert out["simulated"] is True
    assert "潜力" in out["answer"] or "障碍" in out["answer"]


def test_potential_county_distribution():
    """县域端：优先改良片区潜力分布"""
    from framework.agents.specialized.potential_agent import PotentialAssessmentAgent
    out = PotentialAssessmentAgent().answer_question(
        "我们县划定的优先改良片区具体在哪几个村？每块潜力多大？", {})
    assert out["simulated"] is True
    # 收紧：必须命中「县域潜力分布分支」专属产出，旧 else 分支不含此字符串
    assert "县域优先改良片区" in out["answer"]


def test_potential_farmer_plot_diagnosis():
    """农户端：地块诊断"毛病\""""
    from framework.agents.specialized.potential_agent import PotentialAssessmentAgent
    out = PotentialAssessmentAgent().answer_question("我这块地到底有啥毛病？", {})
    assert out["simulated"] is True
    # 收紧：必须命中「农户地块诊断分支」专属产出
    assert "地块诊断结论" in out["answer"]


def test_problem_overall_factors():
    """省市端：主要障碍因素"""
    from framework.agents.specialized.problem_agent import ProblemIdentificationAgent
    out = ProblemIdentificationAgent().answer_question("全省耕地质量存在哪些问题？", {})
    assert out["simulated"] is True
    # 收紧：实现产出 "主要障碍因素：..."
    assert "主要障碍因素" in out["answer"]


def test_problem_county_diagnosis():
    """县域端：县/乡镇耕地障碍诊断"""
    from framework.agents.specialized.problem_agent import ProblemIdentificationAgent
    out = ProblemIdentificationAgent().answer_question("县/乡镇里的耕地在哪些方面有问题", {})
    assert out["simulated"] is True
    # 收紧：实现产出 "县域障碍诊断：..."
    assert "县域障碍诊断" in out["answer"]


def test_problem_farmer_simple_language():
    """农户端：我这块地有没有问题（简单语言）"""
    from framework.agents.specialized.problem_agent import ProblemIdentificationAgent
    out = ProblemIdentificationAgent().answer_question("我这块地有没有问题？", {})
    assert out["simulated"] is True
    # 收紧：实现产出 "您的地块耕地质量等级诊断：..."
    assert "地块耕地质量等级诊断" in out["answer"]


def test_acidification_degree_with_standard():
    """酸化程度判定引用 GB/T 42817-2023"""
    from framework.agents.specialized.acidification_agent import AcidificationRemediationAgent
    out = AcidificationRemediationAgent().answer_question(
        "查询区域内农用地土壤酸化程度如何，不同酸化等级比例分别多少？", {})
    assert out["simulated"] is True
    # 收紧：实现产出 "酸化程度为{degree}（依据 GB/T 42817-2023 分级）"
    assert "酸化程度为" in out["answer"]
    assert "GB/T 42817-2023" in out["answer"]


def test_acidification_remediation_dosage_with_standard():
    """调理剂施用量引用 GB/T 42817-2023 与 NY/T 443-2019"""
    from framework.agents.specialized.acidification_agent import AcidificationRemediationAgent
    out = AcidificationRemediationAgent().answer_question(
        "我的田酸化了，pH是5.0，我要施加多少碱性调理剂可以治理好？", {})
    assert out["simulated"] is True
    # 收紧：实现产出 "建议施石灰 {lime_dosage} kg/亩..." + "依据 GB/T 42817-2023...NY/T 443-2019..."
    assert "建议施石灰" in out["answer"]
    assert "GB/T 42817-2023" in out["answer"]
    assert "NY/T 443-2019" in out["answer"]


def test_acidification_landuse_types():
    """不同土地利用类型酸化程度"""
    from framework.agents.specialized.acidification_agent import AcidificationRemediationAgent
    out = AcidificationRemediationAgent().answer_question(
        "查询区域内不同土地利用类型的酸化程度", {})
    assert out["simulated"] is True
    # 收紧：实现产出 "不同土地利用类型酸化程度：..."
    assert "不同土地利用类型酸化程度" in out["answer"]


def test_acidification_farmer_severity():
    """农户端：我的这块田酸化严重吗"""
    from framework.agents.specialized.acidification_agent import AcidificationRemediationAgent
    out = AcidificationRemediationAgent().answer_question("我的这块田酸化严重吗？", {})
    assert out["simulated"] is True
    # 收紧：实现产出 "您的地块土壤 pH=...酸化等级为...（依据 GB/T 42817-2023...）"
    assert "酸化等级为" in out["answer"]
    assert "GB/T 42817-2023" in out["answer"]


if __name__ == "__main__":
    test_stability_overall_province()
    test_stability_weak_county_list()
    test_stability_farmer_plain_language()
    test_stability_attention_list()
    test_potential_overall_uplift()
    test_potential_county_distribution()
    test_potential_farmer_plot_diagnosis()
    test_problem_overall_factors()
    test_problem_county_diagnosis()
    test_problem_farmer_simple_language()
    test_acidification_degree_with_standard()
    test_acidification_remediation_dosage_with_standard()
    test_acidification_landuse_types()
    test_acidification_farmer_severity()
    print("\nmodel-1/model-2/model-3/model-4 经典 Q&A 测试通过！")
