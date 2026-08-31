import pytest

from framework.agents.base import ProfessionalInputRejected
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
