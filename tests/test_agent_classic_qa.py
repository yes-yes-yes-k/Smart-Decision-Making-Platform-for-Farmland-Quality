"""测试 5 个专题模型 agent 对经典问题的回复。

真实计算优先：当 ai_culti_demo 可导入且提供 parcel_id 时走真实路径；
缺失输入时返回统一降级响应（degraded=True），不再返回 mock 数据。
"""
import sys
import os
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJECT_ROOT)
# 让 ai_culti_demo（位于 src/）可导入，使 model-1/2/3/4 走真实计算路径
sys.path.insert(0, os.path.join(_PROJECT_ROOT, "src"))


def test_stability_overall_province():
    """model-1 真实 agent：空 context 缺 parcel_id 时返回统一降级响应（非 mock）"""
    from framework.agents.specialized.stability_agent import StabilityRiskAgent
    out = StabilityRiskAgent().answer_question("查询区域内耕地质量等级整体稳定吗？", {})
    assert out["degraded"] is True
    assert out["simulated"] is False
    assert out["reason"] == "missing_input"
    assert out["need_input"] == "parcel_id"


def test_stability_weak_county_list():
    """县域端：稳定性较弱乡镇/地块清单——缺输入时降级而非返回 mock 清单"""
    from framework.agents.specialized.stability_agent import StabilityRiskAgent
    out = StabilityRiskAgent().answer_question(
        "本县哪些乡镇或地块等级稳定性较弱，需要现场复核？", {})
    assert out["degraded"] is True
    assert "parcel_id" in out["answer"]


def test_stability_farmer_plain_language():
    """农户端：稳不稳——缺输入时降级而非编造「比较稳/一般稳/不太稳」"""
    from framework.agents.specialized.stability_agent import StabilityRiskAgent
    out = StabilityRiskAgent().answer_question("我的这块田质量等级稳不稳？", {})
    assert out["degraded"] is True
    assert out["simulated"] is False


def test_stability_attention_list():
    """重点关注清单——缺输入时降级而非返回 mock 关注清单"""
    from framework.agents.specialized.stability_agent import StabilityRiskAgent
    out = StabilityRiskAgent().answer_question("查询区域内哪些对象需要纳入重点关注清单？", {})
    assert out["degraded"] is True
    assert out["reason"] == "missing_input"


def test_problem_overall_factors():
    """model-3 真实 agent：缺 parcel_id 时返回统一降级响应（非 mock 障碍因素）"""
    from framework.agents.specialized.problem_agent import ProblemIdentificationAgent
    out = ProblemIdentificationAgent().answer_question("全省耕地质量存在哪些问题？", {})
    assert out["degraded"] is True
    assert out["simulated"] is False
    assert out["reason"] == "missing_input"
    assert out["need_input"] == "parcel_id"


def test_problem_county_diagnosis():
    """县域端：县/乡镇耕地障碍诊断——缺输入时降级而非编造诊断"""
    from framework.agents.specialized.problem_agent import ProblemIdentificationAgent
    out = ProblemIdentificationAgent().answer_question("县/乡镇里的耕地在哪些方面有问题", {})
    assert out["degraded"] is True
    assert "parcel_id" in out["answer"]


def test_problem_farmer_simple_language():
    """农户端：我这块地有没有问题——缺输入时降级而非编造诊断"""
    from framework.agents.specialized.problem_agent import ProblemIdentificationAgent
    out = ProblemIdentificationAgent().answer_question("我这块地有没有问题？", {})
    assert out["degraded"] is True
    assert out["simulated"] is False


def test_acidification_degree_with_standard():
    """酸化程度判定：过程模型输出 YTK/MBNT"""
    from framework.agents.specialized.acidification_agent import AcidificationRemediationAgent
    out = AcidificationRemediationAgent().answer_question(
        "查询区域内农用地土壤酸化程度如何，不同酸化等级比例分别多少？", {})
    # 过程模型（YTK/MBNT）取代旧的 GB/T 42817-2023 分级
    assert "GB/T 42817-2023" not in out["answer"]
    assert ("亿土康" in out["answer"] or "木本泥炭" in out["answer"])


def test_acidification_remediation_dosage_with_standard():
    """调理剂施用量：过程模型 YTK/MBNT 取代旧的 GB/T 42817-2023 与 NY/T 443-2019"""
    from framework.agents.specialized.acidification_agent import AcidificationRemediationAgent
    out = AcidificationRemediationAgent().answer_question(
        "我的田酸化了，pH是5.0，我要施加多少碱性调理剂可以治理好？", {})
    # 过程模型（YTK/MBNT）取代旧的 GB/T 42817-2023 与 NY/T 443-2019 石灰剂量
    assert "GB/T 42817-2023" not in out["answer"]
    assert "NY/T 443-2019" not in out["answer"]
    assert ("亿土康" in out["answer"] or "YTK" in out["answer"])


def test_acidification_landuse_types():
    """不同土地利用类型：过程模型酸化改良输出"""
    from framework.agents.specialized.acidification_agent import AcidificationRemediationAgent
    out = AcidificationRemediationAgent().answer_question(
        "查询区域内不同土地利用类型的酸化程度", {})
    # 过程模型（YTK/MBNT）取代旧的"不同土地利用类型酸化程度"判定
    assert "GB/T 42817-2023" not in out["answer"]
    assert ("亿土康" in out["answer"] or "木本泥炭" in out["answer"])


def test_acidification_farmer_severity():
    """农户端：我的这块田酸化严重吗——过程模型输出 YTK/MBNT"""
    from framework.agents.specialized.acidification_agent import AcidificationRemediationAgent
    out = AcidificationRemediationAgent().answer_question("我的这块田酸化严重吗？", {})
    # 过程模型（YTK/MBNT）取代旧的 GB/T 42817-2023 酸化等级判定
    assert "GB/T 42817-2023" not in out["answer"]
    assert ("亿土康" in out["answer"] or "木本泥炭" in out["answer"])


def test_organic_content_overall():
    """省市端：有机质含量评估"""
    from framework.agents.specialized.organic_matter_agent import OrganicMatterAgent
    out = OrganicMatterAgent().answer_question(
        "全省耕地土壤有机质含量如何，空间分布情况？", {})
    assert out["simulated"] is True
    # 收紧：实现产出 "全省耕地有机质含量平均..."
    assert "全省耕地有机质含量平均" in out["answer"]


def test_organic_manure_straw_dosage():
    """有机肥/秸秆施用量"""
    from framework.agents.specialized.organic_matter_agent import OrganicMatterAgent
    out = OrganicMatterAgent().answer_question(
        "为了提升耕地土壤有机质，有机肥或者秸秆每亩施用量多少？", {})
    assert out["simulated"] is True
    # 收紧：实现产出 "建议有机肥施用量 {manure_dosage} kg/亩..."
    assert "建议有机肥施用量" in out["answer"]


def test_organic_county_average():
    """县域端：本县有机质平均含量"""
    from framework.agents.specialized.organic_matter_agent import OrganicMatterAgent
    out = OrganicMatterAgent().answer_question("本县耕地土壤有机质平均含量是多少？", {})
    assert out["simulated"] is True
    # 收紧：实现产出 "本县耕地土壤有机质平均含量..."
    assert "本县耕地土壤有机质平均含量" in out["answer"]


def test_organic_low_value_reason():
    """有机质低值原因"""
    from framework.agents.specialized.organic_matter_agent import OrganicMatterAgent
    out = OrganicMatterAgent().answer_question("耕地有机质含量低的原因是什么？", {})
    assert out["simulated"] is True
    # 收紧：实现产出 "耕地有机质含量低的原因：..."
    assert "耕地有机质含量低的原因" in out["answer"]


def test_all_agents_degraded_or_real_flag():
    """缺输入时各 agent 的标记一致性：

    - model-1/3（真实 agent，需 parcel_id + DB）：返回 degraded=True、simulated=False
    - model-5（有机质，缺模型特征）：走规则降级，标记 simulated=True
    - model-4（酸化，有默认输入）：真实计算，simulated=False（独立测试覆盖）
    """
    from framework.agents.specialized.stability_agent import StabilityRiskAgent
    from framework.agents.specialized.problem_agent import ProblemIdentificationAgent
    from framework.agents.specialized.organic_matter_agent import OrganicMatterAgent

    degraded_cases = [
        (StabilityRiskAgent(), "查询区域内耕地质量等级整体稳定吗？"),
        (ProblemIdentificationAgent(), "全省耕地质量存在哪些问题？"),
    ]
    for agent, q in degraded_cases:
        out = agent.answer_question(q, {})
        assert out.get("degraded") is True, f"{agent.name} 未标记 degraded"
        assert out.get("simulated") is False, f"{agent.name} 仍标记 simulated"
        assert out.get("answer"), f"{agent.name} answer 为空"

    # model-5 缺模型特征时走规则降级，仍标记 simulated=True
    out = OrganicMatterAgent().answer_question("全省耕地土壤有机质含量如何？", {})
    assert out.get("simulated") is True
    assert out.get("fallback") is True


if __name__ == "__main__":
    test_stability_overall_province()
    test_stability_weak_county_list()
    test_stability_farmer_plain_language()
    test_stability_attention_list()
    test_problem_overall_factors()
    test_problem_county_diagnosis()
    test_problem_farmer_simple_language()
    test_acidification_degree_with_standard()
    test_acidification_remediation_dosage_with_standard()
    test_acidification_landuse_types()
    test_acidification_farmer_severity()
    test_organic_content_overall()
    test_organic_manure_straw_dosage()
    test_organic_county_average()
    test_organic_low_value_reason()
    test_all_agents_degraded_or_real_flag()
    print("\nmodel-1/2/3/4/5 经典 Q&A 测试通过！")
