"""土壤调理剂用量计算（库函数，不接 API）。

注意：本函数为库函数，不通过 HTTP API 暴露。
API 调理剂需求走 model-4 酸化模型，避免能力重叠。
"""
import math
from typing import Dict
from .config import EvaluationConfig


def calculate_soil_conditioner(
    config: EvaluationConfig,
    tybh: str,
    mj: float,
    xqmc: int,
    ph_start: float,
    alex: float,
    hex_: float,
    r: float = 1893.0,
    rph: float = 5.5,
    fert_n: float = 180.0,
    ndep: float = 47.6,
    y: float = 5109.0,
    s: float = 5109.0,
    ph_target: float = 6.811,
) -> Dict[str, float]:
    """计算土壤调理剂施用量。

    Args:
        config: 评价配置（含县区名称字典）。
        tybh: 地块统一代码。
        mj: 地块面积（亩）。
        xqmc: 县区编码。
        ph_start: 原始酸碱度。
        alex: 交换性铝离子。
        hex_: 交换性氢离子。
        r: 年均降水量(mm)，默认 1893.0。
        rph: 降水pH年均值，默认 5.5。
        fert_n: 氮元素施用量(kg/ha)，默认 180.0。
        ndep: 氮沉降量(kg/ha)，默认 47.6。
        y: 籽粒年产量(kg/ha·yr)，默认 5109.0。
        s: 秸秆年产量(kg/ha·yr)，默认 5109.0。
        ph_target: 目标酸碱度，默认 6.811。

    Returns:
        含 ytk_per_ha / mbnt_per_ha / ytk_tons / mbnt_tons 的字典。
    """
    a_values = [-1.0, 1.0, 1.0, 1.0]
    b_vals = [1.0, 1.0, 2.0, 2.0]
    c_vals = [30.97, 39.1, 40.08, 24.305]
    y_k = [0.0035, 0.0019, 0.0003, 0.0012]
    s_k = [0.0018, 0.0199, 0.0054, 0.0021]

    a_dep = (10.0 ** (-rph)) * r * (667.0 / 1000.0 * 1000.0 * 15.0)
    h_grain = [a_values[k] * y * y_k[k] * 1000.0 / 100.0 * b_vals[k] / c_vals[k] for k in range(4)]
    h_straw = [a_values[k] * s * s_k[k] * 1000.0 / 100.0 * b_vals[k] / c_vals[k] for k in range(4)]
    a_crop = sum(h_grain) + sum(h_straw)
    a_no3_runoff = 2.221 * math.exp(0.0049) * (fert_n + ndep) * 1000 / 14
    anit = (ndep - (0.16 * ndep + 2.97)) * 1000 / 14 * 2
    a_vol = anit
    ano3_crop = 0.0
    ancy = a_no3_runoff + anit + a_vol
    a_agri = a_dep + a_crop + ancy + ano3_crop
    a_back = (6.25 * 10.0 ** (9 - ph_start)) / 1000.0 \
             - (6.25 * 10.0 ** (9 - ph_target)) / 1000.0 \
             + (2.5 * hex_ * 10.0 ** 7) / 1000.0 \
             + (2.5 * alex * 10.0 ** 7) / 1000.0

    ytk = (a_back + a_agri * 0.8) / 17.042 * 0.6 * mj
    mbnt = a_agri / 18.9 + alex * 590.0 * 15.0 * mj

    ytk_per_ha = ytk / mj if mj > 0 else 0.0
    mbnt_per_ha = mbnt / mj if mj > 0 else 0.0
    ytk_tons = ytk / 1000.0
    mbnt_tons = mbnt / 1000.0

    return {
        "ytk_per_ha": ytk_per_ha,
        "mbnt_per_ha": mbnt_per_ha,
        "ytk_tons": ytk_tons,
        "mbnt_tons": mbnt_tons,
    }
