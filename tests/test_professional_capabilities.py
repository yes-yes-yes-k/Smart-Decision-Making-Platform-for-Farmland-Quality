"""验证统一专业能力目录、路由和专题接口共用同一份定义。"""
from framework.agents.capabilities import (
    CAPABILITY_BY_QUESTION_TYPE,
    PROFESSIONAL_CAPABILITIES,
    public_capability_descriptor,
)
from framework.agents.manager import AgentManager
from framework.agents.router import TYPE_AGENTS


def test_professional_capability_catalog_has_six_unique_entries():
    assert len(PROFESSIONAL_CAPABILITIES) == 6
    assert len({item.agent_id for item in PROFESSIONAL_CAPABILITIES}) == 6
    assert len({item.model_id for item in PROFESSIONAL_CAPABILITIES}) == 6
    assert set(CAPABILITY_BY_QUESTION_TYPE) == {1, 2, 3, 4, 5, 6}
    for capability in PROFESSIONAL_CAPABILITIES:
        assert capability.supported_object_types == ("parcel",)
        assert capability.requires_spatial_object is True
        assert isinstance(capability.supports_scenario, bool)
        assert isinstance(capability.required_scenario_inputs, tuple)


def test_public_descriptor_exposes_guard_metadata():
    descriptor = public_capability_descriptor(PROFESSIONAL_CAPABILITIES[3])
    assert descriptor["supported_object_types"] == ["parcel"]
    assert descriptor["requires_spatial_object"] is True
    assert descriptor["supports_scenario"] is True
    assert descriptor["required_scenario_inputs"] == [
        "SJD", "JHX", "JLA", "land_type", "fertilizer_type"
    ]


def test_agent_manager_and_router_read_the_capability_catalog():
    manager = AgentManager()
    assert set(manager.agents) == {item.agent_id for item in PROFESSIONAL_CAPABILITIES}
    assert TYPE_AGENTS == {
        item.question_type: [item.agent_id] for item in PROFESSIONAL_CAPABILITIES
    }


def test_formal_model_api_returns_agent_capability_descriptor():
    from ai_culti_demo import run_thematic_model

    result = run_thematic_model({"model_id": "quality-grade-evaluation"})
    # 缺少 parcel_code 时 model-2 使用规范 rejected 状态，不再返回能力描述副本。
    assert result["model_id"] == "quality-grade-evaluation"
    assert result["status"] == "rejected"
    assert result["result"] is None
    assert result["issues"][0]["code"] == "MISSING_INPUT"
    assert "capability" not in result
    assert "model" not in result


def test_legacy_model_id_reports_canonical_model_id():
    from ai_culti_demo import run_thematic_model

    result = run_thematic_model({"model_id": "obstacle-factor-identification"})
    assert result["model_id"] == "obstacle-diagnosis"
    deprecated = next(issue for issue in result["issues"] if issue["code"] == "DEPRECATED_MODEL_ID")
    assert deprecated["details"]["canonical_model_id"] == "obstacle-diagnosis"
