"""验证统一专业能力目录、路由和专题接口共用同一份定义。"""
from framework.agents.capabilities import (
    CAPABILITY_BY_QUESTION_TYPE,
    PROFESSIONAL_CAPABILITIES,
)
from framework.agents.manager import AgentManager
from framework.agents.router import TYPE_AGENTS


def test_professional_capability_catalog_has_six_unique_entries():
    assert len(PROFESSIONAL_CAPABILITIES) == 6
    assert len({item.agent_id for item in PROFESSIONAL_CAPABILITIES}) == 6
    assert len({item.model_id for item in PROFESSIONAL_CAPABILITIES}) == 6
    assert set(CAPABILITY_BY_QUESTION_TYPE) == {1, 2, 3, 4, 5, 6}


def test_agent_manager_and_router_read_the_capability_catalog():
    manager = AgentManager()
    assert set(manager.agents) == {item.agent_id for item in PROFESSIONAL_CAPABILITIES}
    assert TYPE_AGENTS == {
        item.question_type: [item.agent_id] for item in PROFESSIONAL_CAPABILITIES
    }


def test_formal_model_api_returns_agent_capability_descriptor():
    from ai_culti_demo import run_thematic_model

    result = run_thematic_model({"model_id": "quality-grade-evaluation"})
    assert result["status"] == "ok"
    assert result["capability"]["agent_id"] == "model-2"
    assert result["capability"]["model_id"] == "quality-grade-evaluation"
    assert "reliability" in result
    assert "fallback" in result


def test_legacy_model_id_reports_canonical_model_id():
    from ai_culti_demo import run_thematic_model

    result = run_thematic_model({"model_id": "obstacle-factor-identification"})
    assert result["model"]["model_id"] == "obstacle-diagnosis"
    assert result["deprecation"]["canonical_model_id"] == "obstacle-diagnosis"
