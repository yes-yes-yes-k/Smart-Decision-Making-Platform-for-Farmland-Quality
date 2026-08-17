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
            return parcel.soil_indicators or None
        except Exception as e:
            logger.warning("查询 parcel_info 失败 (parcel_id=%s): %s", parcel_id, e)
            return None
