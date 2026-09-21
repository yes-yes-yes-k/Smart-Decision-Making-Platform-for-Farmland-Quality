"""报告生成后数字审计（change: add-input-provenance-and-report-number-audit）行为测试。"""
from __future__ import annotations

from src.ai_culti_demo.report_audit import (
    FALLBACK_TEXT,
    UNGROUNDED_QUANTITATIVE_CLAIM,
    audit_report_sections,
    audit_section,
    collect_allowed_numbers,
    collect_imputed_inputs,
    is_grounded,
    strip_tags,
)

CONTEXT = {
    "scope": {"type": "parcel", "id": "1"},
    "soil_ph": 5.31,
    "organic_matter": 29.24,
    "dose_prediction": 607.9,
    "source_meta": {"total_parcels": 12, "model_versions": ["SG_RF_v2_20260804"]},
}


# ---------------------------------------------------------------- 白名单

def test_collect_allowed_numbers_walks_nested_structures():
    allowed = collect_allowed_numbers(CONTEXT, "<p>面积 3692.1987 亩</p>")
    assert is_grounded(5.31, allowed)
    assert is_grounded(12, allowed)
    assert is_grounded(3692.1987, allowed)
    assert not is_grounded(25, allowed)


def test_is_grounded_allows_rounding_tolerance():
    allowed = [29.2379]
    assert is_grounded(29.24, allowed)
    assert is_grounded(29.2, allowed)
    assert not is_grounded(38.6, allowed)


# ---------------------------------------------------------------- 章节审计

def test_grounded_numbers_are_kept_and_no_issue_raised():
    html = "<p>当前有机质 29.24 g/kg，pH 5.31。</p>"
    content, result = audit_section("现状", html, collect_allowed_numbers(CONTEXT))
    assert content == html
    assert result["issues"] == []
    assert result["checked_claims"] == 2
    assert result["grounded_claims"] == 2


def test_ungrounded_numbers_are_replaced_and_reported():
    html = "<p>预计 pH 提升 25%，增产 13%，投资 300 元/亩。</p>"
    content, result = audit_section("结论与建议", html, collect_allowed_numbers(CONTEXT))
    assert FALLBACK_TEXT in content
    assert "25%" not in content
    assert "13%" not in content
    assert "300 元/亩" not in content
    assert strip_tags(content).count(FALLBACK_TEXT) == 3
    assert result["checked_claims"] == 3
    assert result["grounded_claims"] == 0
    assert {issue["code"] for issue in result["issues"]} == {UNGROUNDED_QUANTITATIVE_CLAIM}
    assert {issue["claim"] for issue in result["issues"]} == {"25%", "13%", "300 元/亩"}
    assert all(issue["section"] == "结论与建议" for issue in result["issues"])


def test_predictive_time_claim_is_audited_but_plain_schedule_is_not():
    allowed = collect_allowed_numbers(CONTEXT)
    _, result = audit_section("计划", "<p>分三个阶段实施，预计 1-2 年见效。</p>", allowed)
    audited = [issue["claim"] for issue in result["issues"]]
    # “三个阶段”不属于定量承诺，不应被审计
    assert "3" not in audited
    # 预测性句子里的时长会被审计
    assert any("年" in claim for claim in audited)


def test_numbers_inside_tags_are_not_audited():
    html = '<table border="1"><tr><td colspan="3">内容</td></tr></table>'
    content, result = audit_section("表格", html, collect_allowed_numbers(CONTEXT))
    assert content == html
    assert result["checked_claims"] == 0


def test_audit_report_sections_summary():
    sections = [
        {"idx": 0, "heading": "结论", "content": "<p>提升 25%。</p>"},
        {"idx": 1, "heading": "数据", "content": "<p>有机质 29.24 g/kg。</p>"},
    ]
    sanitized, summary = audit_report_sections(sections, collect_allowed_numbers(CONTEXT))
    assert summary["checked_claims"] == 2
    assert summary["grounded_claims"] == 1
    assert summary["ungrounded_claims"] == 1
    assert sanitized[0]["content"] != sections[0]["content"]
    assert sanitized[1]["content"] == sections[1]["content"]


# ---------------------------------------------------------------- 回填输入披露

def test_collect_imputed_inputs_groups_three_key_shapes():
    ctx = {
        "models": {"model-5": {"result": {"imputed_features": ["TN"]}}},
        "report": {"imputed_inputs": ["target_ph"]},
        "parcel": {
            "soil_indicators": {
                "provenance": {
                    "exchangeable_aluminum": "region_mean_backfill",
                    "soil_ph": "measured",
                }
            }
        },
    }
    collected = collect_imputed_inputs(ctx)
    assert collected["imputed_features"] == ["TN"]
    assert collected["imputed_inputs"] == ["target_ph"]
    assert collected["provenance"] == ["exchangeable_aluminum（region_mean_backfill）"]


def test_collect_imputed_inputs_ignores_measured_only():
    assert collect_imputed_inputs({"provenance": {"soil_ph": "measured"}}) == {}


# ---------------------------------------------------------------- 报告集成

def test_generate_report_degrades_and_replaces_ungrounded_numbers(monkeypatch):
    import src.ai_culti_demo.report as report_module

    fake_ctx = {
        "soil_ph": 5.31,
        "organic_matter": 29.24,
        "source_meta": {"total_parcels": 12},
    }
    monkeypatch.setattr(report_module, "build_report_context", lambda *a, **k: fake_ctx)
    monkeypatch.setattr(
        report_module,
        "REPORT_TEMPLATES",
        {
            "acidification-treatment": {
                "title": "酸化治理报告",
                "sections": [{"kind": "summary", "heading": "结论与建议", "prompt_hint": "总结"}],
            }
        },
    )
    monkeypatch.setattr(
        report_module.llm_service,
        "generate",
        lambda *a, **k: {
            "success": True,
            "content": "<p>有机质 29.24 g/kg；预计 pH 提升 25%，增产 13%。</p>",
        },
    )

    result = report_module.generate_report(
        "acidification-treatment", {"type": "parcel", "id": "1"}
    )
    assert result["status"] == "degraded"
    assert result["audit"]["ungrounded_claims"] == 2
    assert FALLBACK_TEXT in result["content"]
    assert "25%" not in result["content"]
    assert {issue["code"] for issue in result["issues"]} == {UNGROUNDED_QUANTITATIVE_CLAIM}
    assert all(issue["field"] == "结论与建议" for issue in result["issues"])


def test_generate_report_stays_ok_when_all_numbers_are_grounded(monkeypatch):
    import src.ai_culti_demo.report as report_module

    fake_ctx = {"soil_ph": 5.31, "organic_matter": 29.24, "source_meta": {"total_parcels": 12}}
    monkeypatch.setattr(report_module, "build_report_context", lambda *a, **k: fake_ctx)
    monkeypatch.setattr(
        report_module,
        "REPORT_TEMPLATES",
        {
            "acidification-treatment": {
                "title": "酸化治理报告",
                "sections": [{"kind": "summary", "heading": "结论与建议", "prompt_hint": "总结"}],
            }
        },
    )
    monkeypatch.setattr(
        report_module.llm_service,
        "generate",
        lambda *a, **k: {"success": True, "content": "<p>有机质 29.24 g/kg，pH 5.31。</p>"},
    )

    result = report_module.generate_report(
        "acidification-treatment", {"type": "parcel", "id": "1"}
    )
    assert result["status"] == "ok"
    assert result["audit"] == {
        "checked_claims": 2,
        "grounded_claims": 2,
        "ungrounded_claims": 0,
        "issues": [],
    }
    assert result["issues"] == []
