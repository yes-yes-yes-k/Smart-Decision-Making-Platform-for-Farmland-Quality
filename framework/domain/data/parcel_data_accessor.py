"""地块指标数据访问器：从 parcel_info 表查询 soil_indicators JSON 字段的统一入口。"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)


class ParcelDataAccessor:
    """从 parcel_info 表查询地块指标的统一入口。"""

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

            parcel = ParcelInfo.query.filter_by(parcel_id=parcel_id).first()
            if parcel is None:
                return None
            return parcel.soil_indicators
        except Exception as e:
            logger.warning("查询 parcel_info 失败 (parcel_id=%s): %s", parcel_id, e)
            return None

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
                "YXTCHD": indicators.get("topsoil_thickness"),
                "GCHD": indicators.get("plow_layer_thickness"),
                "GCZD": self._to_code("GCZD", indicators.get("soil_texture")),
                "GGNL": self._to_code("GGNL", indicators.get("irrigation_condition")),
                "PSNL": self._to_code("PSNL", indicators.get("drainage_capacity")),
                "DXBW": self._to_code("DXBW", indicators.get("terrain_position")),
                "ZDGX": self._to_code("ZDGX", indicators.get("soil_structure")),
            }
        elif agent_id == "model-4":
            return {
                "SJD": indicators.get("soil_ph"),
                "Hex": indicators.get("exchangeable_hydrogen"),
                "Alex": indicators.get("exchangeable_aluminum"),
            }
        elif agent_id == "model-5":
            return {
                "pH": indicators.get("soil_ph"),
                "SOMbe": indicators.get("organic_matter"),
                "AK": indicators.get("available_potassium"),
                "AP": indicators.get("available_phosphorus"),
                "TN": indicators.get("total_nitrogen"),
            }
        elif agent_id == "model-1":
            # Model-1 需要原始指标 + 映射后的字段
            return {**indicators,
                    "GCZD": self._to_code("GCZD", indicators.get("soil_texture")),
                    "GGNL": self._to_code("GGNL", indicators.get("irrigation_condition")),
                    "PSNL": self._to_code("PSNL", indicators.get("drainage_capacity")),
                    "DXBW": self._to_code("DXBW", indicators.get("terrain_position")),
                    "ZDGX": self._to_code("ZDGX", indicators.get("soil_structure"))}
        else:
            return indicators
