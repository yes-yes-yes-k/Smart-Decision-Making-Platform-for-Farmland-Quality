"""验证正式 OpenSpec 规格反映统一专业能力目录。"""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROFESSIONAL_SPEC = ROOT / "openspec/specs/professional-model-agents/spec.md"
ROUTING_SPEC = ROOT / "openspec/specs/role-based-routing/spec.md"
THEMATIC_SPEC = ROOT / "openspec/specs/callable-thematic-model-stubs/spec.md"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_formal_spec_defines_five_professional_capabilities():
    content = _read(PROFESSIONAL_SPEC)
    for agent_id, model_id in [
        ("model-1", "stability-risk-evaluation"),
        ("model-2", "quality-grade-evaluation"),
        ("model-3", "obstacle-diagnosis"),
        ("model-4", "acidification-remediation"),
        ("model-5", "organic-matter-improvement"),
    ]:
        assert agent_id in content
        assert model_id in content


def test_formal_spec_requires_structured_agent_analysis():
    content = _read(PROFESSIONAL_SPEC)
    assert "analyze(payload)" in content
    assert "reliability" in content
    assert "fallback" in content


def test_routing_spec_defines_all_five_professional_types():
    content = _read(ROUTING_SPEC)
    for question_type, agent_id in [
        (1, "model-1"), (2, "model-2"), (3, "model-3"),
        (4, "model-4"), (5, "model-5"),
    ]:
        assert f"{question_type}→`{agent_id}`" in content


def test_thematic_spec_separates_non_professional_capabilities():
    content = _read(THEMATIC_SPEC)
    assert "spatial-structure-analysis" in content
    assert "soil-indicator-analysis" in content
    assert "multi-factor-collaborative-improvement" in content
    assert "辅助" in content
    assert "实验性" in content
