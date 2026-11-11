"""地块指标数据访问器：从 parcel_info 表查询 soil_indicators JSON 字段的统一入口。"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

from ..provenance import (
    MODEL4_INPUT_SOURCES,
    MODEL5_FEATURE_SOURCES,
    PROVENANCE_KEY,
    map_feature_sources,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ParcelDataSnapshot:
    parcel_id: str
    area_code: str | None
    parcel_code: str | None
    land_type: str | None
    fertilizer_type: str | None
    target_ph: float | None
    indicators: dict[str, Any]
    source_version: str


class ParcelDataAccessor:
    """从 parcel_info 表查询地块指标的统一入口。"""

    def __init__(self, app=None):
        self._app = app

    def _get_app(self):
        """获取 Flask app 实例（延迟初始化）。"""
        if self._app is None:
            try:
                from framework.api.app import create_app
                self._app = create_app("default")
            except Exception:
                pass
        return self._app

    def get_parcel_indicators(self, parcel_id: str) -> Optional[dict]:
        """按 parcel_id 查询 soil_indicators JSON 字段。

        Args:
            parcel_id: 地块唯一编号。

        Returns:
            dict: soil_indicators 内容（如 {"soil_ph": 5.5, "organic_matter": 2.1}）。
            None: parcel_id 不存在或 DB 异常。
        """
        try:
            from framework.models.thematic_model import ParcelInfo

            app = self._get_app()
            ctx = app.app_context() if app else None
            if ctx:
                ctx.push()
            try:
                parcel = ParcelInfo.query.filter_by(parcel_id=parcel_id).first()
                if parcel is None:
                    return None
                return parcel.soil_indicators
            finally:
                if ctx:
                    ctx.pop()
        except Exception as e:
            logger.warning("查询 parcel_info 失败 (parcel_id=%s): %s", parcel_id, e)
            return None

    def get_parcel_snapshot(self, parcel_id: str) -> Optional[ParcelDataSnapshot]:
        """Read one authoritative row and detach it from the ORM session."""
        try:
            from framework.models.thematic_model import ParcelInfo
            app = self._get_app()
            ctx = app.app_context() if app else None
            if ctx: ctx.push()
            try:
                row = ParcelInfo.query.filter_by(parcel_id=parcel_id).first()
                if row is None: return None
                updated = getattr(row, "updated_at", None)
                version = updated.isoformat() if isinstance(updated, datetime) else str(updated or "unknown")
                return ParcelDataSnapshot(row.parcel_id, row.area_code, row.legacy_parcel_code, row.land_type, row.fertilizer_type, row.target_ph, dict(row.soil_indicators or {}), f"parcel:{version}")
            finally:
                if ctx: ctx.pop()
        except Exception as exc:
            logger.warning("查询 parcel snapshot 失败 (parcel_id=%s): %s", parcel_id, exc)
            return None

    def resolve_region_path(self, area_code: str) -> str:
        """按 area_code 解析省/市/县行政区划名称链（如“广东省韶关市乐昌市”）。

        无法解析或缺失上级行政区时返回空字符串，调用方据此决定是否省略区域前缀。
        """
        if not area_code:
            return ""
        try:
            from framework.models.thematic_model import SpatialRegionCatalog
            app = self._get_app()
            ctx = app.app_context() if app else None
            if ctx: ctx.push()
            try:
                current = SpatialRegionCatalog.query.filter_by(
                    object_type="county", object_id=area_code, enabled=True
                ).one_or_none()
                if current is None:
                    return ""
                names = [current.display_name]
                seen = {(current.object_type, current.object_id)}
                while current.parent_object_type and current.parent_object_id:
                    parent = SpatialRegionCatalog.query.filter_by(
                        object_type=current.parent_object_type,
                        object_id=current.parent_object_id,
                        enabled=True,
                    ).one_or_none()
                    if parent is None:
                        break
                    key = (parent.object_type, parent.object_id)
                    if key in seen:
                        break
                    seen.add(key)
                    names.append(parent.display_name)
                    current = parent
                return "".join(reversed(names))
            finally:
                if ctx: ctx.pop()
        except Exception as exc:
            logger.warning("解析区域路径失败 (area_code=%s): %s", area_code, exc)
            return ""

    def get_parcel_record(self, parcel_id: str) -> Optional[dict]:
        """按 parcel_id 返回地块记录 dict（含 soil_indicators/land_type/fertilizer_type/target_ph）。

        供报告上下文聚合 model-4/5 计算所需的地块元信息。
        """
        try:
            from framework.models.thematic_model import ParcelInfo

            app = self._get_app()
            ctx = app.app_context() if app else None
            if ctx:
                ctx.push()
            try:
                parcel = ParcelInfo.query.filter_by(parcel_id=parcel_id).first()
                if parcel is None:
                    return None
                return {
                    "parcel_id": parcel.parcel_id,
                    "soil_indicators": parcel.soil_indicators or {},
                    "land_type": parcel.land_type or "upland",
                    "fertilizer_type": parcel.fertilizer_type or "urea",
                    "target_ph": parcel.target_ph,
                    "area_code": parcel.area_code,
                }
            finally:
                if ctx:
                    ctx.pop()
        except Exception as e:
            logger.warning("查询 parcel 记录失败 (parcel_id=%s): %s", parcel_id, e)
            return None

    def get_parcel_ids_by_area_code(self, area_code: str) -> list[str]:
        """按 area_code 返回区域内全部地块编号列表（报告区域范围解析用）。"""
        try:
            from framework.models.thematic_model import ParcelInfo

            app = self._get_app()
            ctx = app.app_context() if app else None
            if ctx:
                ctx.push()
            try:
                rows = ParcelInfo.query.filter_by(area_code=area_code).all()
                return [r.parcel_id for r in rows]
            finally:
                if ctx:
                    ctx.pop()
        except Exception as e:
            logger.warning("查询区域地块列表失败 (area_code=%s): %s", area_code, e)
            return []

    def get_parcel_ids_by_area_prefix(self, prefix: str) -> list[str]:
        """按 area_code 前缀 LIKE 查询（市级覆盖其下所有区县）。"""
        try:
            from framework.models.thematic_model import ParcelInfo

            app = self._get_app()
            ctx = app.app_context() if app else None
            if ctx:
                ctx.push()
            try:
                rows = ParcelInfo.query.filter(
                    ParcelInfo.area_code.like(f"{prefix}%")
                ).all()
                return [r.parcel_id for r in rows]
            finally:
                if ctx:
                    ctx.pop()
        except Exception as e:
            logger.warning("查询区域地块列表失败 (prefix=%s): %s", prefix, e)
            return []

    def _to_code(self, indicator: str, value) -> Optional[str]:
        """英文/中文值 → 代码（先英文后中文回退）。

        Args:
            indicator: 指标缩写（GCZD/GGNL/PSNL/DXBW/ZDGX）。
            value: DB 中的离散值（英文或中文）。

        Returns:
            代码字符串（如 RT/FS/CM），未知值返回 None。
        """
        if value is None:
            return None
        from framework.domain.calculations.coefficients import DISCRETE_EN_MAP, DISCRETE_CN_MAP
        en_code = DISCRETE_EN_MAP.get(indicator, {}).get(value)
        if en_code is not None:
            return en_code
        cn_code = DISCRETE_CN_MAP.get(indicator, {}).get(value)
        if cn_code is not None:
            return cn_code
        logger.warning("未知离散值 indicator=%s value=%s", indicator, value)
        return None

    def _map_indicators_to_inputs(self, indicators: dict, agent_id: str) -> dict:
        """V3.0 英文 snake_case → 模型输入字段的统一映射。

        Args:
            indicators: soil_indicators JSON（V3.0 snake_case 键名）。
            agent_id: 模型标识（model-1 ~ model-5）。

        Returns:
            映射后的字段 dict，键名为各模型计算所需的缩写。
        """
        if agent_id in ("model-2", "model-3"):
            return {
                "SJD": indicators.get("soil_ph"),
                "YJZ": indicators.get("organic_matter"),
                "YXL": indicators.get("available_phosphorus"),
                "SXJ": indicators.get("available_potassium"),
                "TRRZ": indicators.get("bulk_density"),
                "YXTCHD": indicators.get("effective_soil_depth", indicators.get("topsoil_thickness")),
                "GCHD": indicators.get("plow_layer_thickness"),
                "GCZD": self._to_code("GCZD", indicators.get("soil_texture")),
                "GGNL": self._to_code("GGNL", indicators.get("irrigation_condition")),
                "PSNL": self._to_code("PSNL", indicators.get("drainage_capacity")),
                "DXBW": self._to_code("DXBW", indicators.get("terrain_position")),
                "ZDGX": self._to_code("ZDGX", indicators.get("soil_structure")),
            }
        elif agent_id == "model-4":
            return map_feature_sources(indicators, MODEL4_INPUT_SOURCES)
        elif agent_id == "model-5":
            return map_feature_sources(indicators, MODEL5_FEATURE_SOURCES)
        elif agent_id == "model-1":
            # Model-1 需要原始指标 + 映射后的字段；来源标记属于元数据，不进模型输入
            base = {key: value for key, value in indicators.items() if key != PROVENANCE_KEY}
            return {**base,
                    "GCZD": self._to_code("GCZD", indicators.get("soil_texture")),
                    "GGNL": self._to_code("GGNL", indicators.get("irrigation_condition")),
                    "PSNL": self._to_code("PSNL", indicators.get("drainage_capacity")),
                    "DXBW": self._to_code("DXBW", indicators.get("terrain_position")),
                    "ZDGX": self._to_code("ZDGX", indicators.get("soil_structure"))}
        else:
            return indicators
