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
    # 回复应包含薄弱片区清单语义
    assert "较弱" in out["answer"] or "薄弱" in out["answer"] or "稳定" in out["answer"]
    assert len(out["evidence"]) >= 1


def test_stability_farmer_plain_language():
    """农户端：通俗语言说明稳不稳"""
    from framework.agents.specialized.stability_risk_agent import StabilityRiskAgent
    out = StabilityRiskAgent().answer_question("我的这块田质量等级稳不稳？", {})
    assert out["simulated"] is True
    assert "稳" in out["answer"]
    # 通俗语言：包含"比较稳""一般稳""不太稳"之一或稳定性类型说明
    assert any(w in out["answer"] for w in ["比较稳", "一般稳", "不太稳", "稳定", "一般", "较弱"])


def test_stability_attention_list():
    """重点关注清单"""
    from framework.agents.specialized.stability_risk_agent import StabilityRiskAgent
    out = StabilityRiskAgent().answer_question("查询区域内哪些对象需要纳入重点关注清单？", {})
    assert out["simulated"] is True
    assert "关注" in out["answer"] or "清单" in out["answer"] or "风险" in out["answer"]


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
    assert "潜力" in out["answer"] or "障碍" in out["answer"] or "片区" in out["answer"]


def test_potential_farmer_plot_diagnosis():
    """农户端：地块诊断"毛病\""""
    from framework.agents.specialized.potential_agent import PotentialAssessmentAgent
    out = PotentialAssessmentAgent().answer_question("我这块地到底有啥毛病？", {})
    assert out["simulated"] is True
    # 回复应给出诊断/障碍因子
    assert "障碍" in out["answer"] or "毛病" in out["answer"] or "潜力" in out["answer"] or "诊断" in out["answer"]


if __name__ == "__main__":
    test_stability_overall_province()
    test_stability_weak_county_list()
    test_stability_farmer_plain_language()
    test_stability_attention_list()
    test_potential_overall_uplift()
    test_potential_county_distribution()
    test_potential_farmer_plot_diagnosis()
    print("\nmodel-1/model-2 经典 Q&A 测试通过！")
