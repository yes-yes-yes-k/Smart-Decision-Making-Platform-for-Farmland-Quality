from datetime import datetime, timezone

import pytest

from framework.analysis_context.contracts import (
    AnalysisContext,
    AnalysisObject,
    CalculationMode,
    ContextAction,
    ObjectType,
    ParentPathItem,
)
from framework.analysis_context.errors import (
    AnalysisContextConflict,
    AnalysisContextError,
    AnalysisObjectInvalid,
    AnalysisObjectValidationUnavailable,
    LegacyIdentifierAmbiguity,
)


def test_analysis_object_serializes_only_canonical_fields():
    obj = AnalysisObject(
        type=ObjectType.PARCEL,
        id="P001",
        display_name="地块 P001",
        area_code="440281",
        parent_path=(
            ParentPathItem(ObjectType.COUNTY, "440281", "乐昌市", "440281"),
        ),
        source="parcel_info",
        validated_at=datetime(2026, 8, 30, tzinfo=timezone.utc),
    )
    assert obj.to_dict()["type"] == "parcel"
    assert obj.to_dict()["parent_path"][0]["display_name"] == "乐昌市"


def test_unknown_object_type_is_rejected():
    with pytest.raises(ValueError):
        ObjectType("village")


def test_scenario_snapshot_never_exposes_conversation_object():
    snapshot = AnalysisContext(
        mode=CalculationMode.SCENARIO,
        version=None,
        object=None,
    )
    assert snapshot.to_dict() == {
        "mode": "scenario",
        "version": None,
        "object": None,
    }


@pytest.mark.parametrize(
    ("error_type", "code", "http_status"),
    [
        (AnalysisContextError, "analysis_context_error", 422),
        (AnalysisContextConflict, "analysis_context_conflict", 409),
        (AnalysisObjectInvalid, "analysis_object_invalid", 422),
        (LegacyIdentifierAmbiguity, "legacy_identifier_ambiguity", 422),
        (
            AnalysisObjectValidationUnavailable,
            "analysis_object_validation_unavailable",
            503,
        ),
    ],
)
def test_domain_errors_expose_stable_code_status_and_details(
    error_type, code, http_status
):
    error = error_type("Invalid context", details={"object_id": "P001"})

    assert str(error) == "Invalid context"
    assert error.message == "Invalid context"
    assert error.code == code
    assert error.http_status == http_status
    assert error.details == {"object_id": "P001"}


def test_from_dict_restores_valid_backend_snapshot():
    restored = AnalysisContext.from_dict(
        {
            "mode": "spatial",
            "version": 4,
            "object": {
                "type": "parcel",
                "id": "P001",
                "display_name": "地块 P001",
                "area_code": "440281",
                "parent_path": [],
                "source": "parcel_info",
                "validated_at": "2026-08-30T00:00:00+00:00",
            },
        }
    )

    assert restored.mode is CalculationMode.SPATIAL
    assert restored.object is not None
    assert restored.object.id == "P001"


@pytest.mark.parametrize(
    "snapshot",
    [
        {
            "mode": "spatial",
            "version": 1,
            "object": {
                "type": "parcel",
                "id": "",
                "display_name": "地块 P001",
                "area_code": "440281",
                "parent_path": [],
                "source": "parcel_info",
                "validated_at": "2026-08-30T00:00:00+00:00",
            },
        },
        {
            "mode": "spatial",
            "version": 1,
            "object": {
                "type": "parcel",
                "id": "P001",
                "display_name": "地块 P001",
                "area_code": "440281",
                "parent_path": [],
                "source": "parcel_info",
                "validated_at": "2026-08-30T00:00:00",
            },
        },
    ],
)
def test_from_dict_rejects_invalid_backend_snapshot(snapshot):
    with pytest.raises(ValueError):
        AnalysisContext.from_dict(snapshot)


def test_context_action_has_only_supported_values():
    assert {action.value for action in ContextAction} == {"set", "inherit", "clear"}
