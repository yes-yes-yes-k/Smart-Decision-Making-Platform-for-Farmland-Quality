"""Backend-persisted analysis context value objects.

These contracts intentionally have no Flask or SQLAlchemy dependency.  They
represent canonical objects returned by a server-side resolver; display fields
from a client request must never be used to construct an ``AnalysisObject``.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Mapping, Sequence


class ObjectType(str, Enum):
    PROVINCE = "province"
    CITY = "city"
    COUNTY = "county"
    TOWNSHIP = "township"
    VILLAGE = "village"
    ZONE = "zone"
    PARCEL = "parcel"


REGION_OBJECT_TYPES = frozenset({
    ObjectType.PROVINCE,
    ObjectType.CITY,
    ObjectType.COUNTY,
})


class CalculationMode(str, Enum):
    SPATIAL = "spatial"
    SCENARIO = "scenario"


class ContextAction(str, Enum):
    SET = "set"
    INHERIT = "inherit"
    CLEAR = "clear"


def _non_empty_id(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


def _mapping(value: object, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field_name} must be an object")
    return value


def _timezone_datetime(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("validated_at must be an ISO-8601 string")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("validated_at must be a valid ISO-8601 datetime") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("validated_at must include timezone information")
    return parsed


@dataclass(frozen=True)
class ParentPathItem:
    type: ObjectType
    id: str
    display_name: str
    area_code: str | None

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ParentPathItem":
        item = _mapping(data, "parent_path item")
        return cls(
            type=ObjectType(item["type"]),
            id=_non_empty_id(item["id"], "parent_path item id"),
            display_name=item["display_name"],
            area_code=item["area_code"],
        )


def region_path_label(parent_path: Sequence[ParentPathItem]) -> str:
    """Concatenate administrative parent names in their original chain order."""
    return "".join(
        item.display_name
        for item in parent_path
        if item.type in REGION_OBJECT_TYPES and item.display_name
    )


def public_object_name(display_name: str, parent_path: Sequence[ParentPathItem]) -> str:
    """Prefix an object name with its administrative path unless already present."""
    region = region_path_label(parent_path)
    if not region or region in display_name:
        return display_name
    return f"{region} {display_name}"


@dataclass(frozen=True)
class AnalysisObject:
    type: ObjectType
    id: str
    display_name: str
    area_code: str | None
    parent_path: Sequence[ParentPathItem]
    source: str
    validated_at: datetime

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type.value,
            "id": self.id,
            "display_name": self.display_name,
            "area_code": self.area_code,
            "parent_path": [
                {
                    "type": item.type.value,
                    "id": item.id,
                    "display_name": item.display_name,
                    "area_code": item.area_code,
                }
                for item in self.parent_path
            ],
            "source": self.source,
            "validated_at": self.validated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "AnalysisObject":
        """Restore a canonical object from already-persisted backend JSON."""
        obj = _mapping(data, "object")
        parent_path = obj["parent_path"]
        if not isinstance(parent_path, Sequence) or isinstance(parent_path, (str, bytes)):
            raise ValueError("parent_path must be an array")
        return cls(
            type=ObjectType(obj["type"]),
            id=_non_empty_id(obj["id"], "object id"),
            display_name=obj["display_name"],
            area_code=obj["area_code"],
            parent_path=tuple(ParentPathItem.from_dict(item) for item in parent_path),
            source=obj["source"],
            validated_at=_timezone_datetime(obj["validated_at"]),
        )


@dataclass(frozen=True)
class AnalysisContext:
    mode: CalculationMode
    version: int | None
    object: AnalysisObject | None

    def to_dict(self) -> dict[str, Any]:
        if self.mode is CalculationMode.SCENARIO:
            return {"mode": self.mode.value, "version": None, "object": None}
        return {
            "mode": self.mode.value,
            "version": self.version,
            "object": self.object.to_dict() if self.object else None,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "AnalysisContext":
        """Restore an analysis context from already-persisted backend JSON."""
        context = _mapping(data, "analysis context")
        mode = CalculationMode(context["mode"])
        object_data = context["object"]
        if mode is CalculationMode.SCENARIO:
            if context["version"] is not None or object_data is not None:
                raise ValueError("scenario context cannot contain version or object")
            return cls(mode=mode, version=None, object=None)
        return cls(
            mode=mode,
            version=context["version"],
            object=AnalysisObject.from_dict(object_data) if object_data is not None else None,
        )


@dataclass(frozen=True)
class GuardDecision:
    allowed: bool
    interaction_state: str
    required_object_types: Sequence[str] = ()
    missing_inputs: Sequence[str] = ()
    message: str = ""
