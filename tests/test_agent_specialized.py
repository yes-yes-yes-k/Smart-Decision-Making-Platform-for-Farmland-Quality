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


def test_problem_agent_consumes_standard_field_names_has_question(monkeypatch):
    """真实诊断分支应读取标准码字段 GDZLDJ/ZALX/ZYZAYS（"有没有问题"分支）"""
    from framework.agents.specialized.problem_agent import ProblemIdentificationAgent
    agent = ProblemIdentificationAgent()
    fake_real_result = {
        "status": "ok",
        "diagnosis": {
            "ZALX": "酸化障碍",
            "ZYZAYS": "pH偏低；有机质贫瘠；耕层浅薄",
            "CYZAYS": "有效磷不足；速效钾偏低",
        },
        "evaluation": {"GDZLDJ": 7},
    }
    monkeypatch.setattr(agent, "_get_real_diagnosis", lambda context: fake_real_result)

    out = agent.answer_question("我这块地有没有问题？", {})
    assert out["simulated"] is False
    assert "酸化障碍" in out["answer"]
    assert "pH偏低" in out["answer"]
    assert "7级" in out["answer"]
    assert "无明显障碍" not in out["answer"]
    assert "未知" not in out["answer"]
    print("✓ ProblemIdentificationAgent 真实诊断分支消费 GDZLDJ/ZALX/ZYZAYS（有没有问题分支）")


def test_problem_agent_consumes_standard_field_names_county_question(monkeypatch):
    """真实诊断分支应读取标准码字段含 CYZAYS（"县/乡镇/方面"分支）"""
    from framework.agents.specialized.problem_agent import ProblemIdentificationAgent
    agent = ProblemIdentificationAgent()
    fake_real_result = {
        "status": "ok",
        "diagnosis": {
            "ZALX": "酸化障碍",
            "ZYZAYS": "pH偏低；有机质贫瘠",
            "CYZAYS": "有效磷不足；速效钾偏低",
        },
        "evaluation": {"GDZLDJ": 7},
    }
    monkeypatch.setattr(agent, "_get_real_diagnosis", lambda context: fake_real_result)

    out = agent.answer_question("县域耕地在哪些方面有问题？", {})
    assert out["simulated"] is False
    assert "酸化障碍" in out["answer"]
    assert "pH偏低" in out["answer"]
    assert "有效磷不足" in out["answer"]
    assert "7级" in out["answer"]
    print("✓ ProblemIdentificationAgent 真实诊断分支消费 CYZAYS（县域方面分支）")


def test_problem_agent_consumes_standard_field_names_else_branch(monkeypatch):
    """真实诊断分支应读取标准码字段（else 兜底分支）"""
    from framework.agents.specialized.problem_agent import ProblemIdentificationAgent
    agent = ProblemIdentificationAgent()
    fake_real_result = {
        "status": "ok",
        "diagnosis": {
            "ZALX": "板结障碍",
            "ZYZAYS": "容重偏高；孔隙度偏低",
            "CYZAYS": "耕层浅薄",
        },
        "evaluation": {"GDZLDJ": 8},
    }
    monkeypatch.setattr(agent, "_get_real_diagnosis", lambda context: fake_real_result)

    out = agent.answer_question("主要障碍因素是什么？", {})
    assert out["simulated"] is False
    assert "板结障碍" in out["answer"]
    assert "容重偏高" in out["answer"]
    assert "耕层浅薄" in out["answer"]
    assert "8级" in out["answer"]
    print("✓ ProblemIdentificationAgent 真实诊断分支消费标准字段（else 分支）")


def test_acidification_agent_execute(monkeypatch):
    from framework.agents.specialized.acidification_agent import AcidificationRemediationAgent
    monkeypatch.setattr(
        "framework.agents.specialized.acidification_agent.model_4_execution",
        lambda data, land_type=None, fertilizer_type=None: {
            "status": "success", "ytk": 1234.5, "mbnt": 567.8,
            "sub_model": "upland_compound", "land_type": "upland",
            "fertilizer_type": "compound", "model_version": "process_v2_20260801",
            "customized_params": {"FertN": 200.0},
        }
    )
    agent = AcidificationRemediationAgent()
    assert agent.model_id == "model-4"
    result = agent.execute({"SJD":4.31,"JHX":1.56,"JLA":4.08})
    assert result["status"] == "success"
    assert result["result"]["ytk"] == 1234.5
    assert result["result"]["mbnt"] == 567.8
    assert result["metadata"]["model_version"] == "process_v2_20260801"
    print("✓ AcidificationRemediationAgent.execute 返回三层结构含 ytk/mbnt")


def test_acidification_agent_passes_through_params(monkeypatch):
    from framework.agents.specialized.acidification_agent import AcidificationRemediationAgent
    captured = {}
    def fake(data, land_type=None, fertilizer_type=None):
        captured["land_type"] = land_type
        captured["fertilizer_type"] = fertilizer_type
        return {"status":"success","ytk":1.0,"mbnt":2.0,"sub_model":"paddy_urea",
                "land_type":land_type,"fertilizer_type":fertilizer_type,
                "model_version":"process_v2_20260801","customized_params":{}}
    monkeypatch.setattr("framework.agents.specialized.acidification_agent.model_4_execution", fake)
    agent = AcidificationRemediationAgent()
    agent.answer_question("如何治理酸化？", {"data":{"SJD":4.31,"JHX":1.56,"JLA":4.08},
                                          "land_type":"paddy","fertilizer_type":"urea"})
    assert captured["land_type"] == "paddy"
    assert captured["fertilizer_type"] == "urea"
    print("✓ AcidificationRemediationAgent 透传 land_type/fertilizer_type 给 model_4_execution")


def test_acidification_agent_answer_no_gb_standard(monkeypatch):
    from framework.agents.specialized.acidification_agent import AcidificationRemediationAgent
    monkeypatch.setattr(
        "framework.agents.specialized.acidification_agent.model_4_execution",
        lambda data, land_type=None, fertilizer_type=None: {
            "status":"success","ytk":1234.5,"mbnt":567.8,"sub_model":"upland_compound",
            "land_type":"upland","fertilizer_type":"compound",
            "model_version":"process_v2_20260801","customized_params":{}})
    agent = AcidificationRemediationAgent()
    out = agent.answer_question("如何治理强酸性耕地？施加多少调理剂？", {"data":{"SJD":4.31,"JHX":1.56,"JLA":4.08}})
    assert "GB/T 42817-2023" not in out["answer"]
    assert "亿土康" in out["answer"] or "ytk" in str(out["evidence"]).lower() or "木本泥炭" in out["answer"]
    print("✓ AcidificationRemediationAgent answer 不含 GB/T 42817-2023，含 YTK/MBNT")


def test_organic_matter_agent_execute():
    from framework.agents.specialized.organic_matter_agent import OrganicMatterAgent
    agent = OrganicMatterAgent()
    assert agent.model_id == "model-5"
    assert agent.dependencies == []
    result = agent.execute({"area_code": "lechang"})
    assert result["status"] == "ok"
    assert result["metadata"]["simulated"] is True
    assert "level" in result["result"]
    assert "manure_dosage" in result["result"]
    assert "potential_increase" in result["result"]
    print("✓ OrganicMatterAgent.execute 返回有机质分级与施用量")


def test_organic_matter_agent_answer_question_content():
    from framework.agents.specialized.organic_matter_agent import OrganicMatterAgent
    agent = OrganicMatterAgent()
    out = agent.answer_question("全省耕地土壤有机质含量如何？", {})
    assert out["simulated"] is True
    assert "有机质" in out["answer"]
    print("✓ OrganicMatterAgent 返回有机质含量评估")


def test_organic_matter_agent_answer_question_dosage():
    from framework.agents.specialized.organic_matter_agent import OrganicMatterAgent
    agent = OrganicMatterAgent()
    out = agent.answer_question("有机肥每亩施用量多少？", {})
    assert out["simulated"] is True
    assert "kg" in out["answer"] or "有机肥" in out["answer"]
    assert any("manure_dosage" in str(e) or "有机肥" in str(e) for e in out["evidence"])
    print("✓ OrganicMatterAgent 返回有机肥施用量建议")


def test_fertility_ml_agent_execute_structure(monkeypatch):
    """execute 返回结构包含 status/result/metadata 三层"""
    from framework.agents.specialized.fertility_ml_agent import FertilityMLAgent
    from framework.domain.other_models import model_6
    # mock model_6_execution 返回 success
    monkeypatch.setattr(
        "framework.agents.specialized.fertility_ml_agent.model_6_execution",
        lambda data, land_type="upland": {
            "status": "success",
            "soc_prediction": 12.5,
            "soc_confidence": 0.91,
            "dose_prediction": 150.0,
            "dose_confidence": 0.47,
            "dose_warning": "Dose 模型 R²=0.47，预测结果仅供参考",
            "imputed_features": [],
            "imputation_applied": False,
            "model_version": "ETR_v1_20260713",
        }
    )
    agent = FertilityMLAgent()
    assert agent.model_id == "model-6"
    assert agent.dependencies == []
    result = agent.execute({"pH": 6.5})
    assert "status" in result
    assert "result" in result
    assert "metadata" in result
    assert result["result"]["soc_prediction"] == 12.5
    print("✓ FertilityMLAgent.execute 返回三层结构")


def test_fertility_ml_agent_answer_dose_keywords(monkeypatch):
    """问'施用量' → 仅返回 Dose 预测"""
    from framework.agents.specialized.fertility_ml_agent import FertilityMLAgent
    monkeypatch.setattr(
        "framework.agents.specialized.fertility_ml_agent.model_6_execution",
        lambda data, land_type="upland": {
            "status": "success",
            "soc_prediction": 12.5,
            "soc_confidence": 0.91,
            "dose_prediction": 150.0,
            "dose_confidence": 0.47,
            "dose_warning": "Dose 模型 R²=0.47",
            "imputed_features": [],
            "imputation_applied": False,
            "model_version": "ETR_v1_20260713",
        }
    )
    agent = FertilityMLAgent()
    out = agent.answer_question("我这块地需要施多少肥？", {"data": {"pH": 6.5}})
    assert "施肥" in out["answer"] or "t/ha" in out["answer"]
    # evidence 应包含 dose_prediction 但不应包含 soc_prediction
    metrics = [e.get("metric") for e in out["evidence"]]
    assert "dose_prediction" in metrics
    assert "soc_prediction" not in metrics
    print("✓ FertilityMLAgent 施用量问题返回 Dose 预测")


def test_fertility_ml_agent_answer_soc_keywords(monkeypatch):
    """问'有机碳' → 仅返回 SOC 预测"""
    from framework.agents.specialized.fertility_ml_agent import FertilityMLAgent
    monkeypatch.setattr(
        "framework.agents.specialized.fertility_ml_agent.model_6_execution",
        lambda data, land_type="upland": {
            "status": "success",
            "soc_prediction": 12.5,
            "soc_confidence": 0.91,
            "dose_prediction": 150.0,
            "dose_confidence": 0.47,
            "dose_warning": "Dose 模型 R²=0.47",
            "imputed_features": [],
            "imputation_applied": False,
            "model_version": "ETR_v1_20260713",
        }
    )
    agent = FertilityMLAgent()
    out = agent.answer_question("我的田有机碳含量多少？", {"data": {"pH": 6.5}})
    assert "SOC" in out["answer"] or "有机碳" in out["answer"]
    metrics = [e.get("metric") for e in out["evidence"]]
    assert "soc_prediction" in metrics
    assert "dose_prediction" not in metrics
    print("✓ FertilityMLAgent 有机碳问题返回 SOC 预测")


def test_fertility_ml_agent_answer_fertility_keywords(monkeypatch):
    """问'肥力' → 返回 SOC + Dose 综合诊断"""
    from framework.agents.specialized.fertility_ml_agent import FertilityMLAgent
    monkeypatch.setattr(
        "framework.agents.specialized.fertility_ml_agent.model_6_execution",
        lambda data, land_type="upland": {
            "status": "success",
            "soc_prediction": 12.5,
            "soc_confidence": 0.91,
            "dose_prediction": 150.0,
            "dose_confidence": 0.47,
            "dose_warning": "Dose 模型 R²=0.47",
            "imputed_features": [],
            "imputation_applied": False,
            "model_version": "ETR_v1_20260713",
        }
    )
    agent = FertilityMLAgent()
    out = agent.answer_question("我的田肥力怎么样？", {"data": {"pH": 6.5}})
    metrics = [e.get("metric") for e in out["evidence"]]
    assert "soc_prediction" in metrics
    assert "dose_prediction" in metrics
    print("✓ FertilityMLAgent 肥力问题返回综合诊断")


def test_fertility_ml_agent_answer_fallback_status(monkeypatch):
    """status=fallback → answer 标注'模型不可用'"""
    from framework.agents.specialized.fertility_ml_agent import FertilityMLAgent
    monkeypatch.setattr(
        "framework.agents.specialized.fertility_ml_agent.model_6_execution",
        lambda data, land_type="upland": {
            "status": "fallback",
            "soc_prediction": 12.0,
            "soc_confidence": 0.3,
            "dose_prediction": 100.0,
            "dose_confidence": 0.3,
            "dose_warning": "模型不可用，返回训练集均值估算",
            "imputed_features": [],
            "imputation_applied": False,
            "model_version": "ETR_v1_20260713",
            "fallback_reason": "model_file_missing",
        }
    )
    agent = FertilityMLAgent()
    out = agent.answer_question("我的田肥力怎么样？", {"data": {}})
    assert "模型不可用" in out["answer"] or "训练集均值" in out["answer"]
    print("✓ FertilityMLAgent fallback 时标注模型不可用")


def test_fertility_ml_agent_answer_rejected_status(monkeypatch):
    """status=rejected → answer 标注越界特征"""
    from framework.agents.specialized.fertility_ml_agent import FertilityMLAgent
    monkeypatch.setattr(
        "framework.agents.specialized.fertility_ml_agent.model_6_execution",
        lambda data, land_type="upland": {
            "status": "rejected",
            "reason": "input_out_of_range",
            "out_of_range_features": [
                {"feature": "pH", "value": 99.0, "valid_range": [3.0, 11.0]}
            ],
            "soc_prediction": None,
            "soc_confidence": 0.0,
            "dose_prediction": None,
            "dose_confidence": 0.0,
            "dose_warning": "输入值越界，未执行预测",
            "imputed_features": [],
            "imputation_applied": False,
            "model_version": "ETR_v1_20260713",
        }
    )
    agent = FertilityMLAgent()
    out = agent.answer_question("我的田肥力怎么样？", {"data": {"pH": 99.0}})
    assert "越界" in out["answer"] or "异常" in out["answer"]
    assert "pH" in out["answer"]
    assert out["evidence"] == []
    print("✓ FertilityMLAgent rejected 时标注越界特征")


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
    test_organic_matter_agent_execute()
    test_organic_matter_agent_answer_question_content()
    test_organic_matter_agent_answer_question_dosage()
    print("\n所有专业智能体测试通过！")
