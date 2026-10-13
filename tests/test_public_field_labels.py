import pytest
from types import SimpleNamespace

from framework.agents.output_contract import deterministic_answer
from framework.agents.workflows.comprehensive.reporting import user_facing_text
from framework.api.services.chat_service import ChatRequestService
from framework.domain.public_field_labels import (
    PublicTextStreamTranslator,
    translate_public_text,
)


@pytest.mark.parametrize(
    ("code", "label"),
    [
        ("GGNL", "灌溉能力"),
        ("DXBW", "地形部位"),
        ("SXJ", "速效钾"),
        ("SJD", "土壤酸碱度"),
        ("JHX", "交换性氢"),
        ("JLA", "交换性铝"),
        ("SOCbe", "初始土壤有机碳"),
        ("TN", "全氮"),
        ("Dose", "建议施用量"),
    ],
)
def test_translate_public_text_uses_standard_chinese_fields(code, label):
    text = translate_public_text(f"主要障碍：{code}（需要改善）")
    assert code not in text
    assert label in text


def test_translate_public_text_does_not_rewrite_embedded_machine_identifier():
    assert translate_public_text("GGNLcode 与 XGGNL 保持原样") == "GGNLcode 与 XGGNL 保持原样"


def test_stream_translator_handles_field_split_across_chunks():
    translator = PublicTextStreamTranslator()
    chunks = ["重度障碍：G", "GN", "L、DX", "BW；中度：S", "XJ。"]
    rendered = "".join(translator.feed(chunk) for chunk in chunks) + translator.flush()
    assert rendered == "重度障碍：灌溉能力、地形部位；中度：速效钾。"


def test_deterministic_answer_never_exposes_internal_factor_codes():
    answer = deterministic_answer({
        "status": "ok",
        "result": {"primary_factors": ["GGNL", "DXBW", "SXJ"]},
    })
    assert "GGNL" not in answer
    assert "DXBW" not in answer
    assert "SXJ" not in answer
    assert all(label in answer for label in ("灌溉能力", "地形部位", "速效钾"))


def test_comprehensive_report_uses_the_same_public_field_dictionary():
    text = user_facing_text("GGNL、DXBW、SXJ、JHX、Dose")
    assert text == "灌溉能力、地形部位、速效钾、交换性氢、建议施用量"


def test_chat_persistence_boundary_normalizes_answer_and_report_draft():
    service = ChatRequestService.__new__(ChatRequestService)
    prepared = SimpleNamespace(context_snapshot={"mode": "spatial", "version": 1})
    normalized = service._normalize_result(prepared, {
        "answer": "GGNL 与 DXBW",
        "report_draft": "SXJ 与 JHX",
        "recommendations": ["改善 PSNL"],
        "provenance": {},
    })
    assert normalized["answer"] == "灌溉能力 与 地形部位"
    assert normalized["report_draft"] == "速效钾 与 交换性氢"
    assert normalized["recommendations"] == ["改善 排水能力"]
