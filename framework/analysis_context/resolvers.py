"""Authoritative spatial-object resolvers and access policy."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol

from sqlalchemy.exc import SQLAlchemyError

from framework.models import ParcelInfo, SpatialRegionCatalog

from .contracts import AnalysisObject, ObjectType, ParentPathItem
from .errors import AnalysisObjectInvalid, AnalysisObjectValidationUnavailable


class AnalysisObjectAccessPolicy(Protocol):
    def can_access(self, *, user_id: int, object_type: ObjectType, object_id: str) -> bool: ...


class RegisteredDataAccessPolicy:
    """Registered enabled data is visible to an authenticated user."""

    def can_access(self, *, user_id: int, object_type: ObjectType, object_id: str) -> bool:
        return user_id is not None


class RegionObjectResolver:
    MAX_PARENT_DEPTH = 8

    def resolve(self, object_type: ObjectType, object_id: str) -> AnalysisObject:
        row = SpatialRegionCatalog.query.filter_by(
            object_type=object_type.value, object_id=object_id, enabled=True
        ).one_or_none()
        if row is None:
            raise AnalysisObjectInvalid("分析区域不存在或已停用")
        parents = self._parent_path(row)
        return AnalysisObject(
            type=object_type,
            id=row.object_id,
            display_name=row.display_name,
            area_code=row.area_code,
            parent_path=parents,
            source=row.source,
            validated_at=datetime.now(timezone.utc),
        )

    def _parent_path(self, row: SpatialRegionCatalog) -> tuple[ParentPathItem, ...]:
        reversed_path: list[ParentPathItem] = []
        seen = {(row.object_type, row.object_id)}
        current = row
        depth = 0
        while current.parent_object_type or current.parent_object_id:
            if not current.parent_object_type or not current.parent_object_id:
                break
            depth += 1
            if depth > self.MAX_PARENT_DEPTH:
                raise AnalysisObjectInvalid("区域父级路径超过最大深度")
            try:
                parent_type = ObjectType(current.parent_object_type)
            except ValueError as exc:
                raise AnalysisObjectInvalid("区域父级类型非法") from exc
            if parent_type is ObjectType.PARCEL:
                raise AnalysisObjectInvalid("区域父级类型非法")
            key = (parent_type.value, current.parent_object_id)
            if key in seen:
                raise AnalysisObjectInvalid("区域父级路径存在循环")
            seen.add(key)
            parent = SpatialRegionCatalog.query.filter_by(
                object_type=parent_type.value,
                object_id=current.parent_object_id,
                enabled=True,
            ).one_or_none()
            if parent is None:
                break
            reversed_path.append(ParentPathItem(
                type=parent_type,
                id=parent.object_id,
                display_name=parent.display_name,
                area_code=parent.area_code,
            ))
            current = parent
        return tuple(reversed(reversed_path))


class ParcelObjectResolver:
    def __init__(self, region_resolver: RegionObjectResolver):
        self._region_resolver = region_resolver

    def resolve(self, object_id: str) -> AnalysisObject:
        parcel = ParcelInfo.query.filter_by(parcel_id=object_id).one_or_none()
        if parcel is None:
            raise AnalysisObjectInvalid("地块不存在")
        parent_path: tuple[ParentPathItem, ...] = ()
        if parcel.area_code:
            county = SpatialRegionCatalog.query.filter_by(
                object_type=ObjectType.COUNTY.value,
                object_id=parcel.area_code,
                enabled=True,
            ).one_or_none()
            if county is not None:
                region = self._region_resolver.resolve(ObjectType.COUNTY, county.object_id)
                parent_path = region.parent_path + (ParentPathItem(
                    type=region.type,
                    id=region.id,
                    display_name=region.display_name,
                    area_code=region.area_code,
                ),)
        return AnalysisObject(
            type=ObjectType.PARCEL,
            id=parcel.parcel_id,
            display_name=f"地块 {parcel.parcel_id}",
            area_code=parcel.area_code,
            parent_path=parent_path,
            source="parcel_info",
            validated_at=datetime.now(timezone.utc),
        )


class SpatialObjectResolverRegistry:
    def __init__(self, access_policy: AnalysisObjectAccessPolicy | None = None):
        self._access_policy = access_policy or RegisteredDataAccessPolicy()
        self._region_resolver = RegionObjectResolver()
        self._parcel_resolver = ParcelObjectResolver(self._region_resolver)

    def resolve(self, object_type: ObjectType | str, object_id: str, *, user_id: int) -> AnalysisObject:
        try:
            canonical_type = ObjectType(object_type)
        except (TypeError, ValueError) as exc:
            raise AnalysisObjectInvalid("分析对象类型非法") from exc
        if not isinstance(object_id, str) or not object_id.strip():
            raise AnalysisObjectInvalid("分析对象标识不能为空")
        try:
            if canonical_type is ObjectType.PARCEL:
                obj = self._parcel_resolver.resolve(object_id)
            else:
                obj = self._region_resolver.resolve(canonical_type, object_id)
        except SQLAlchemyError as exc:
            raise AnalysisObjectValidationUnavailable("空间对象验证服务暂时不可用") from exc
        if not self._access_policy.can_access(
            user_id=user_id, object_type=canonical_type, object_id=obj.id
        ):
            raise AnalysisObjectInvalid("无权访问该分析对象")
        return obj
