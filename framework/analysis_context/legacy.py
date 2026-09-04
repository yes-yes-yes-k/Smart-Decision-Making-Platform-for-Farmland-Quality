"""Compatibility adapter for deprecated chat spatial identifiers."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from sqlalchemy.exc import SQLAlchemyError

from framework.models import ParcelInfo, SpatialRegionCatalog

from .contracts import AnalysisObject, ContextAction, ObjectType
from .errors import (
    AnalysisObjectInvalid,
    AnalysisObjectValidationUnavailable,
    LegacyIdentifierAmbiguity,
)
from .resolvers import SpatialObjectResolverRegistry


@dataclass(frozen=True)
class LegacyResolution:
    object: AnalysisObject | None
    validated_identifiers: dict[str, str]
    deprecations: Sequence[str]


class LegacyAnalysisContextAdapter:
    LEGACY_FIELDS = ("parcel_id", "parcel_code", "area_code")

    def __init__(self, resolver: SpatialObjectResolverRegistry | None = None):
        self._resolver = resolver or SpatialObjectResolverRegistry()

    def resolve(self, body: Mapping[str, Any], *, user_id: int) -> LegacyResolution:
        if not isinstance(body, Mapping):
            raise AnalysisObjectInvalid("请求体必须为对象")
        new_object = self._resolve_new_ref(body, user_id=user_id)
        legacy_object, identifiers, deprecations = self._resolve_legacy_refs(body, user_id=user_id)
        if new_object and legacy_object and (
            new_object.type is not legacy_object.type or new_object.id != legacy_object.id
        ):
            raise AnalysisObjectInvalid("新旧分析对象标识冲突")
        return LegacyResolution(
            object=new_object or legacy_object,
            validated_identifiers=identifiers,
            deprecations=tuple(deprecations),
        )

    def _resolve_new_ref(self, body: Mapping[str, Any], *, user_id: int) -> AnalysisObject | None:
        context = body.get("analysis_context")
        if context is None:
            return None
        if not isinstance(context, Mapping):
            raise AnalysisObjectInvalid("analysis_context 必须为对象")
        action = context.get("action")
        if action is not None:
            try:
                canonical_action = ContextAction(action)
            except ValueError as exc:
                raise AnalysisObjectInvalid("analysis_context.action 非法") from exc
            if canonical_action is not ContextAction.SET:
                return None
        ref = context.get("object")
        if ref is None:
            return None
        if not isinstance(ref, Mapping):
            raise AnalysisObjectInvalid("analysis_context.object 必须为对象")
        # Only type/id are consumed. Client display_name, area_code, source and
        # parent_path are deliberately ignored.
        return self._resolver.resolve(ref.get("type"), ref.get("id"), user_id=user_id)

    def _resolve_legacy_refs(
        self, body: Mapping[str, Any], *, user_id: int
    ) -> tuple[AnalysisObject | None, dict[str, str], list[str]]:
        refs = {name: body.get(name) for name in self.LEGACY_FIELDS if body.get(name) is not None}
        if not refs:
            return None, {}, []
        for name, value in refs.items():
            if not isinstance(value, str) or not value.strip():
                raise AnalysisObjectInvalid(f"{name} 不能为空")
        try:
            parcel_by_id = self._parcel_by("parcel_id", refs.get("parcel_id"))
            parcel_by_code = self._parcel_by("legacy_parcel_code", refs.get("parcel_code"))
            if parcel_by_id and parcel_by_code and parcel_by_id.id != parcel_by_code.id:
                raise LegacyIdentifierAmbiguity("parcel_id 与 parcel_code 未映射到同一地块")
            parcel = parcel_by_id or parcel_by_code
            region = self._region_by_area_code(refs.get("area_code"), user_id=user_id)
            parcel_object = (
                self._resolver.resolve(ObjectType.PARCEL, parcel.parcel_id, user_id=user_id)
                if parcel else None
            )
            if parcel_object and region:
                if parcel_object.area_code != region.area_code:
                    raise AnalysisObjectInvalid("地块与区域编码冲突")
                resolved = parcel_object
            else:
                resolved = parcel_object or region
        except SQLAlchemyError as exc:
            raise AnalysisObjectValidationUnavailable("空间对象验证服务暂时不可用") from exc
        identifiers = dict(refs)
        if parcel:
            identifiers["parcel_id"] = parcel.parcel_id
            if parcel.legacy_parcel_code:
                identifiers["parcel_code"] = parcel.legacy_parcel_code
        return resolved, identifiers, list(refs)

    @staticmethod
    def _parcel_by(column: str, value: str | None):
        if value is None:
            return None
        row = ParcelInfo.query.filter_by(**{column: value}).one_or_none()
        if row is None:
            if column == "legacy_parcel_code":
                raise LegacyIdentifierAmbiguity("旧地块编码无法映射到权威地块")
            raise AnalysisObjectInvalid("地块不存在")
        return row

    def _region_by_area_code(self, value: str | None, *, user_id: int) -> AnalysisObject | None:
        if value is None:
            return None
        rows = SpatialRegionCatalog.query.filter_by(area_code=value, enabled=True).all()
        canonical = {(row.object_type, row.object_id) for row in rows}
        if not canonical:
            raise AnalysisObjectInvalid("区域编码不存在")
        if len(canonical) != 1:
            raise LegacyIdentifierAmbiguity("区域编码匹配多个空间对象")
        object_type, object_id = next(iter(canonical))
        return self._resolver.resolve(ObjectType(object_type), object_id, user_id=user_id)
