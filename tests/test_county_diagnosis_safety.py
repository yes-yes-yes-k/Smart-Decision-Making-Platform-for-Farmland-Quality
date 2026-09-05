from __future__ import annotations

import json
from copy import deepcopy

import pytest
from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from ai_culti_demo import build_report_summary, diagnose_county
from ai_culti_demo.diagnosis import (
    DiagnosisContractError,
    validate_diagnosis_response,
)
from framework.api.routes.county import county_bp
from framework.api.routes.report import report_bp
from framework.core_engine import core_engine


METRICS_BY_COLLECTION = {
    "problems": ("percent",),
    "problem_distribution": ("percent",),
    "measures": ("cost", "improve", "period"),
    "treatments": ("cost", "improve", "period"),
    "regions": ("weight", "effect"),
    "base_data": ("weight", "effect"),
}
REQUIRED_META_KEYS = {
    "status",
    "reason",
    "unit",
    "source",
    "method",
    "model_version",
    "calculated_at",
    "scope",
}
OLD_PLACEHOLDERS = (
    "1-2年",
    "2-3年",
    "见效周期不匹配",
    "38.6",
    "45.2",
    "0.36",
)


@pytest.mark.parametrize("topic", ["acidification", "quality", "improvement"])
def test_template_diagnosis_has_no_placeholder_metrics(topic):
    result = diagnose_county({"topic": topic, "area_code": "lechang"})

    assert result["status"] == "degraded"
    assert result["result_kind"] == "advisory_only"
    assert result["reliability"]["predictive"] is False
    assert result["reliability"]["quantitative_available"] is False
    assert result["regions"] == []
    assert result["base_data"] == []

    serialized = json.dumps(result, ensure_ascii=False)
    assert not any(value in serialized for value in OLD_PLACEHOLDERS)

    for collection, fields in METRICS_BY_COLLECTION.items():
        for item in result[collection]:
            for field in fields:
                assert item[field] is None
                meta = item["metric_meta"][field]
                assert set(meta) == REQUIRED_META_KEYS
                assert meta["status"] == "unavailable"
                assert meta["reason"]


def test_unavailable_metric_cannot_have_a_value():
    result = diagnose_county({"topic": "quality", "area_code": "lechang"})
    result["problems"][0]["percent"] = 38.6

    with pytest.raises(DiagnosisContractError, match="不可用时值必须为 null"):
        validate_diagnosis_response(result)


def test_available_metric_requires_complete_provenance():
    result = diagnose_county({"topic": "quality", "area_code": "lechang"})
    metric = result["problems"][0]
    metric["percent"] = 12.5
    metric["metric_meta"]["percent"].update(
        {
            "status": "available",
            "reason": None,
            "source": None,
            "method": "county_statistics",
            "calculated_at": "2026-09-05T00:00:00+08:00",
        }
    )
    result["result_kind"] = "validated_result"

    with pytest.raises(DiagnosisContractError, match="缺少 source"):
        validate_diagnosis_response(result)


def test_compatible_aliases_do_not_restore_values():
    result = diagnose_county({"topic": "improvement", "area_code": "lechang"})

    for primary, alias in (
        ("problems", "problem_distribution"),
        ("measures", "treatments"),
        ("regions", "base_data"),
    ):
        assert result[primary] == result[alias]
        assert result[primary] is not result[alias]

    for collection in ("measures", "treatments"):
        for item in result[collection]:
            assert item["cost"] is None
            assert item["improve"] is None
            assert item["period"] is None


def test_summary_preserves_degraded_safety_contract():
    diagnosis = diagnose_county({"topic": "quality", "area_code": "lechang"})
    summary = build_report_summary(diagnosis)

    assert summary["status"] == "degraded"
    assert summary["result_kind"] == "advisory_only"
    assert summary["reliability"] == diagnosis["reliability"]
    assert summary["quantitative_estimates"] == diagnosis["quantitative_estimates"]
    assert summary["source"]["diagnosis_status"] == "degraded"
    assert summary["source"]["result_kind"] == "advisory_only"
    serialized = json.dumps(summary, ensure_ascii=False)
    assert not any(value in serialized for value in OLD_PLACEHOLDERS)


def test_core_engine_preserves_degraded_status():
    diagnosis = core_engine.diagnose_county(
        {"topic": "quality", "area_code": "lechang"}
    )
    summary = core_engine.build_report_summary(diagnosis)

    assert diagnosis["status"] == "degraded"
    assert diagnosis["result_kind"] == "advisory_only"
    assert summary["status"] == "degraded"
    assert summary["result_kind"] == "advisory_only"


def _authenticated_client():
    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        JWT_SECRET_KEY="county-diagnosis-test-secret-key-32-bytes",
    )
    JWTManager(app)
    app.register_blueprint(county_bp, url_prefix="/county")
    app.register_blueprint(report_bp, url_prefix="/report")
    with app.app_context():
        token = create_access_token(identity="test-user")
    return app.test_client(), {"Authorization": f"Bearer {token}"}


def test_api_routes_preserve_degraded_status(monkeypatch):
    diagnosis = diagnose_county({"topic": "quality", "area_code": "lechang"})
    client, headers = _authenticated_client()

    monkeypatch.setattr(
        "framework.api.routes.county.core_engine.diagnose_county",
        lambda payload: deepcopy(diagnosis),
    )
    county_response = client.post(
        "/county/diagnose",
        json={"topic": "quality", "area_code": "lechang"},
        headers=headers,
    )
    assert county_response.status_code == 200
    assert county_response.get_json()["status"] == "degraded"
    assert county_response.get_json()["data"]["result_kind"] == "advisory_only"

    monkeypatch.setattr(
        "framework.api.routes.report.core_engine.build_report_summary",
        build_report_summary,
    )
    report_response = client.post(
        "/report/summary",
        json=diagnosis,
        headers=headers,
    )
    assert report_response.status_code == 200
    assert report_response.get_json()["status"] == "degraded"
    assert report_response.get_json()["data"]["result_kind"] == "advisory_only"


def test_invalid_topic_and_area_normalization_behavior_is_unchanged():
    invalid_topic = diagnose_county({"topic": "bad-topic"})
    normalized_area = diagnose_county(
        {"topic": "quality", "area_code": "bad-area"}
    )

    assert invalid_topic["status"] == "error"
    assert invalid_topic["error"]["code"] == "INVALID_TOPIC"
    assert normalized_area["status"] == "degraded"
    assert normalized_area["area"]["code"] == "lechang"
