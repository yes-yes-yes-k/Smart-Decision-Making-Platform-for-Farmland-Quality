from framework.agents.specialized.stability_agent import StabilityRiskAgent


def test_real_result_reads_grouped_module_metrics(monkeypatch):
    """模型1聊天回答应读取预计算库中实际保存的九模块指标。"""
    agent = StabilityRiskAgent()
    monkeypatch.setattr(
        agent,
        "_get_real_stability",
        lambda context: {
            "module_2": {"指标支撑均衡度_绝对": 0.63},
            "module_6": {"掉级风险_绝对": 0.41},
        },
    )

    result = agent.answer_question("该地块的退化风险如何", {"parcel_id": "P001"})

    assert result["simulated"] is False
    assert "0.41" in result["answer"]
    assert "中风险" in result["answer"]
