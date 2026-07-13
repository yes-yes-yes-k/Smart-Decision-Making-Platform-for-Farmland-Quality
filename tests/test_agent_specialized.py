"""测试 6 个专业智能体"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_stability_risk_agent_execute():
    from framework.agents.specialized.stability_risk_agent import StabilityRiskAgent
    agent = StabilityRiskAgent()
    assert agent.model_id == "model-1"
    assert agent.dependencies == []
    result = agent.execute({"area_code": "lechang"})
    assert result["status"] == "ok"
    assert result["metadata"]["simulated"] is True
    counties = result["result"]["counties"]
    assert isinstance(counties, list) and len(counties) >= 1
    first = counties[0]
    assert "name" in first and "quality_grade" in first and "stability" in first
    print("✓ StabilityRiskAgent.execute 返回县区稳定性数据")


def test_stability_risk_agent_answer_question_overall():
    from framework.agents.specialized.stability_risk_agent import StabilityRiskAgent
    agent = StabilityRiskAgent()
    out = agent.answer_question("全省耕地质量整体稳定吗？", {})
    assert out["simulated"] is True
    assert "稳定" in out["answer"] or "稳定" in str(out["evidence"])
    assert 0.0 <= out["confidence"] <= 1.0
    assert any("占比" in str(e) or "面积" in str(e) for e in out["evidence"])
    print("✓ StabilityRiskAgent.answer_question 返回稳定性总体评价")


def test_stability_risk_agent_answer_question_risk():
    from framework.agents.specialized.stability_risk_agent import StabilityRiskAgent
    agent = StabilityRiskAgent()
    out = agent.answer_question("哪些县区高等级耕地存在退化风险？", {})
    assert out["simulated"] is True
    assert "县" in out["answer"] or len(out["evidence"]) >= 1
    print("✓ StabilityRiskAgent.answer_question 识别退化风险区域")


def test_potential_agent_execute():
    from framework.agents.specialized.potential_agent import PotentialAssessmentAgent
    agent = PotentialAssessmentAgent()
    assert agent.model_id == "model-2"
    assert agent.dependencies == []
    result = agent.execute({"area_code": "lechang"})
    assert result["status"] == "ok"
    assert result["metadata"]["simulated"] is True
    indicators = result["result"]["indicators"]
    assert isinstance(indicators, list) and len(indicators) == 11
    first = indicators[0]
    assert "name" in first and "current" in first and "potential" in first and "obstacle_degree" in first
    print("✓ PotentialAssessmentAgent.execute 返回 11 评价指标")


def test_potential_agent_answer_question():
    from framework.agents.specialized.potential_agent import PotentialAssessmentAgent
    agent = PotentialAssessmentAgent()
    out = agent.answer_question("耕地质量提升潜力如何？", {})
    assert out["simulated"] is True
    assert "潜力" in out["answer"] or "障碍" in out["answer"]
    assert 0.0 <= out["confidence"] <= 1.0
    print("✓ PotentialAssessmentAgent.answer_question 返回潜力评估")


def test_potential_agent_target_ph_in_context():
    """answer_question 应将 target_ph 写入 evidence 供下游使用"""
    from framework.agents.specialized.potential_agent import PotentialAssessmentAgent
    agent = PotentialAssessmentAgent()
    out = agent.answer_question("如何提升耕地质量？", {"current_ph": 5.0})
    assert any("target_ph" in str(e) for e in out["evidence"])
    print("✓ PotentialAssessmentAgent 在 evidence 中暴露 target_ph")


def test_problem_agent_execute():
    from framework.agents.specialized.problem_agent import ProblemIdentificationAgent
    agent = ProblemIdentificationAgent()
    assert agent.model_id == "model-3"
    assert agent.dependencies == ["model-2"]
    result = agent.execute({"area_code": "lechang"})
    assert result["status"] == "ok"
    assert result["metadata"]["simulated"] is True
    assert "primary_factors" in result["result"]
    assert "secondary_factors" in result["result"]
    assert "combinations" in result["result"]
    print("✓ ProblemIdentificationAgent.execute 返回障碍因素结构")


def test_problem_agent_answer_question():
    from framework.agents.specialized.problem_agent import ProblemIdentificationAgent
    agent = ProblemIdentificationAgent()
    out = agent.answer_question("耕地在哪些方面有问题？", {})
    assert out["simulated"] is True
    assert "障碍" in out["answer"] or "问题" in out["answer"]
    assert len(out["evidence"]) >= 1
    print("✓ ProblemIdentificationAgent.answer_question 返回障碍识别")


def test_problem_agent_uses_model2_target_ph():
    """当 context 包含 model-2 结果时，应使用其 target_ph"""
    from framework.agents.specialized.problem_agent import ProblemIdentificationAgent
    agent = ProblemIdentificationAgent()
    ctx = {"model-2": {"target_ph": 6.8, "answer": "...", "evidence": [], "confidence": 0.8, "simulated": True}}
    out = agent.answer_question("主要障碍因素是什么？", ctx)
    assert any("6.8" in str(e) for e in out["evidence"])
    print("✓ ProblemIdentificationAgent 消费 model-2 的 target_ph")


if __name__ == "__main__":
    test_stability_risk_agent_execute()
    test_stability_risk_agent_answer_question_overall()
    test_stability_risk_agent_answer_question_risk()
    test_potential_agent_execute()
    test_potential_agent_answer_question()
    test_potential_agent_target_ph_in_context()
    test_problem_agent_execute()
    test_problem_agent_answer_question()
    test_problem_agent_uses_model2_target_ph()
    print("\n所有专业智能体测试通过！")
