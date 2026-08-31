import pytest

from framework.agents.base import ProfessionalInputRejected
from framework.agents.manager import AgentManager
from framework.agents.specialized.acidification_agent import AcidificationRemediationAgent
from framework.agents.specialized.organic_matter_agent import OrganicMatterAgent


def test_acidification_chat_never_uses_mock_when_parcel_missing():
    with pytest.raises(ProfessionalInputRejected) as exc:
        AcidificationRemediationAgent().execute({
            "execution_channel": "chat", "guard_passed": True,
            "calculation_mode": "spatial",
        })
    assert exc.value.code == "verified_parcel_required"


def test_organic_chat_requires_verified_parcel():
    with pytest.raises(ProfessionalInputRejected) as exc:
        OrganicMatterAgent().execute({
            "execution_channel": "chat", "guard_passed": True,
            "calculation_mode": "spatial",
        })
    assert exc.value.code == "verified_parcel_required"


def test_model4_scenario_uses_only_supplied_values(monkeypatch):
    agent = AcidificationRemediationAgent()
    monkeypatch.setattr(agent, "_persist_result", lambda *args, **kwargs: True)
    result = agent.execute({
        "execution_channel": "chat", "guard_passed": True,
        "calculation_mode": "scenario",
        "SJD": 5.1, "JHX": 1.2, "JLA": 3.4,
        "land_type": "upland", "fertilizer_type": "compound",
    })
    assert result["status"] != "rejected"
    assert result["result"]


def test_agent_manager_rejects_unguarded_or_wrong_scale_chat(monkeypatch):
    manager = AgentManager()
    monkeypatch.setattr(
        manager, "_execute_with_dependencies",
        lambda *args, **kwargs: pytest.fail("professional agent must not execute"),
    )
    with pytest.raises(ProfessionalInputRejected, match="中央守卫"):
        manager.process("稳定性", {"question_type": 1, "execution_channel": "chat"})
    with pytest.raises(ProfessionalInputRejected, match="已验证对象"):
        manager.process("稳定性", {
            "question_type": 1,
            "execution_channel": "chat",
            "guard_passed": True,
            "calculation_mode": "spatial",
            "execution_context": {
                "analysis_context": {"object": {"type": "county", "id": "440281"}}
            },
        })
