"""用户可见数值的统一格式化规则。

该模块只服务于对外投影和文本展示，不参与数据库写入、审计或模型计算，
因此不得在此处修改原始精度。
"""
from __future__ import annotations

import math
import re
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

#: 匹配长小数，同时避免改写 2.1.0、2026.10.24 这类版本号或编号。
#: 仅对 4 位及以上小数四舍五入到 decimals 位；3 位小数按原值保留，
#: 与酸化卡片展示位数（ACID_RESULT_DIGITS=3）及各模型 3 位精度输出一致，
#: 避免「0.093 t/mu」被压成「0.09」造成卡片与回答数值不一致。
LONG_DECIMAL = re.compile(r"(?<![\w.])(\d+\.\d{4,})(?![\w.])")


def _quantizer(decimals: int) -> Decimal:
    return Decimal(1).scaleb(-decimals)


def format_public_number(value: Any, decimals: int = 2) -> str:
    """格式化用户可见数值，float 固定保留 ``decimals`` 位小数。"""
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int):
        return str(int(value))
    if isinstance(value, float):
        if not math.isfinite(value):
            return str(value)
        rounded = Decimal(str(value)).quantize(
            _quantizer(decimals), rounding=ROUND_HALF_UP,
        )
        return f"{rounded:.{decimals}f}"
    return str(value)


def round_public_floats(payload: Any, decimals: int = 2) -> Any:
    """递归对 JSON 风格数据中的 float 做四舍五入，其余类型保持原样。"""
    if isinstance(payload, bool) or payload is None:
        return payload
    if isinstance(payload, float):
        if not math.isfinite(payload):
            return payload
        return float(
            Decimal(str(payload)).quantize(
                _quantizer(decimals), rounding=ROUND_HALF_UP,
            )
        )
    if isinstance(payload, dict):
        return {
            key: round_public_floats(value, decimals)
            for key, value in payload.items()
        }
    if isinstance(payload, list):
        return [round_public_floats(item, decimals) for item in payload]
    if isinstance(payload, tuple):
        return tuple(round_public_floats(item, decimals) for item in payload)
    return payload


def round_long_decimals(text: Any, decimals: int = 2) -> Any:
    """把文本中的长小数（三位及以上）四舍五入到 ``decimals`` 位。"""
    if not isinstance(text, str):
        return text

    def _replace(match: re.Match[str]) -> str:
        rounded = Decimal(match.group(1)).quantize(
            _quantizer(decimals), rounding=ROUND_HALF_UP,
        )
        return f"{rounded:.{decimals}f}"

    return LONG_DECIMAL.sub(_replace, text)


__all__ = ["format_public_number", "round_public_floats", "round_long_decimals"]
