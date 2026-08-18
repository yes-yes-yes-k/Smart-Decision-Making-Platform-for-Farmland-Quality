"""Model-4 酸化改良 — 移植自 模型5_酸化模型/02_酸化模型计算.py。

4 个产酸平衡函数:
- paddy_urea: 水田尿素 (YTK 系数 0.6, pHtarget=6.5)
- paddy_compound: 水田复合肥 (YTK 0.6, pHtarget=6.5, 含 Ano3_crop)
- upland_urea: 旱地尿素 (YTK 0.77, pHtarget=6.0)
- upland_compound: 旱地复合肥 (YTK 0.7, pHtarget=6.0, 含 Ano3_crop)

输入: SJD(pH), Hex(交换性氢), Alex(交换性铝)
输出: Adep, Acrop, ANcy, Aagri, Aback, YTK(石灰施用量), MBNT(有机肥施用量)
"""
from __future__ import annotations
import math
from typing import Dict


def paddy_urea(SJD: float, Hex: float, Alex: float,
               RPH: float = 5.5, R: float = 1893, Y: float = 5109, S: float = 5109,
               Yp: float = 0.35, Yk: float = 0.19, Yca: float = 0.03, Ymg: float = 0.12,
               Sp: float = 0.176, Sk: float = 1.99, Sca: float = 0.54, Smg: float = 0.212,
               FertN: float = 180, Ndep: float = 47.6, pHtarget: float = 6.5) -> Dict[str, float]:
    """水田尿素产酸平衡计算（移植自原始 paddy_urea）。"""
    Adep = 10**(-RPH) * 667 * (R/1000) * 1000 * 15
    Hgrain = (-Y*Yp*1000/100/30.97 + Y*Yk*1000/100/39.1
              + Y*Yca*1000/100*2/40.08 + Y*Ymg*1000/100*2/24.305)
    Hstraw = (-S*Sp*1000/100/30.97 + S*Sk*1000/100/39.1
              + S*Sca*1000/100*2/40.08 + S*Smg*1000/100*2/24.305)
    Acrop = Hgrain + Hstraw
    Anit = 2.221 * math.exp(0.0048*(FertN+Ndep)) * 1000/14
    Ano3_runoff = (Ndep - (0.16*Ndep + 2.97)) * 1000/14 * 2
    Ano3_crop = 0
    Avol = (Ndep - (0.16*Ndep + 2.97)) * 1000/14 * 2
    ANcy = Anit + Ano3_runoff + Ano3_crop + Avol
    Aagri = Adep + Acrop + ANcy
    Aback = (6.25*10**(9-SJD) - 6.25*10**(9-pHtarget)
             + 2.5*Hex*10**7 + 2.5*Alex*10**7) / 1000
    YTK = (Aback + 0.8*Aagri) / 17.042 * 0.6
    MBNT = 0.1*Aagri/1.89 + Alex*590*15
    return {"Adep": Adep, "Acrop": Acrop, "ANcy": ANcy, "Aagri": Aagri,
            "Aback": Aback, "YTK": YTK, "MBNT": MBNT}


def paddy_compound(SJD: float, Hex: float, Alex: float,
                   RPH: float = 5.5, R: float = 1893, Y: float = 5109, S: float = 5109,
                   Yp: float = 0.35, Yk: float = 0.19, Yca: float = 0.03, Ymg: float = 0.12,
                   Sp: float = 0.176, Sk: float = 1.99, Sca: float = 0.54, Smg: float = 0.212,
                   YN: float = 1.87, SN: float = 1.15,
                   FertN: float = 180, Ndep: float = 47.6, pHtarget: float = 6.5) -> Dict[str, float]:
    """水田复合肥产酸平衡计算（移植自原始 paddy_compound）。"""
    Adep = 10**(-RPH) * 667 * (R/1000) * 1000 * 15
    Hgrain = (-Y*Yp*1000/100/30.97 + Y*Yk*1000/100/39.1
              + Y*Yca*1000/100*2/40.08 + Y*Ymg*1000/100*2/24.305)
    Hstraw = (-S*Sp*1000/100/30.97 + S*Sk*1000/100/39.1
              + S*Sca*1000/100*2/40.08 + S*Smg*1000/100*2/24.305)
    Acrop = Hgrain + Hstraw
    Anit = 2.221 * math.exp(0.0048*(FertN+Ndep)) * 1000/14
    Ano3_crop = -(Y*YN + S*SN) * 1000/100/14 * 0.3
    Ano3_runoff = ((FertN - (0.16*FertN + 2.97)) * 1000/14 * 2 * 0.3
                   + (Ndep - (0.16*Ndep + 2.97)) * 1000/14 * 2)
    Avol = ((0.16*FertN + 2.97) * 1000/14 * 0.3
            + (0.16*Ndep + 2.97) * 1000/14)
    ANcy = Anit + Ano3_runoff + Ano3_crop + Avol
    Aagri = Adep + Acrop + ANcy
    Aback = (6.25*10**(9-SJD) - 6.25*10**(9-pHtarget)
             + 2.5*Hex*10**7 + 2.5*Alex*10**7) / 1000
    YTK = (Aback + 0.8*Aagri) / 17.042 * 0.6
    MBNT = 0.15*Aagri/1.89 + Alex*590*15
    return {"Adep": Adep, "Acrop": Acrop, "ANcy": ANcy, "Aagri": Aagri,
            "Aback": Aback, "YTK": YTK, "MBNT": MBNT}


def upland_urea(SJD: float, Hex: float, Alex: float,
                RPH: float = 5.5, R: float = 1893, Y: float = 6700, S: float = 6968,
                Yp: float = 0.41, Yk: float = 0.44, Yca: float = 0.03, Ymg: float = 0.141,
                Sp: float = 0.21, Sk: float = 1.27, Sca: float = 0.71, Smg: float = 0.357333,
                FertN: float = 180, Ndep: float = 47.6, pHtarget: float = 6.0) -> Dict[str, float]:
    """旱地尿素产酸平衡计算（移植自原始 upland_urea）。"""
    Adep = 10**(-RPH) * 667 * (R/1000) * 1000 * 15
    Hgrain = (-Y*Yp*1000/100/30.97 + Y*Yk*1000/100/39.1
              + Y*Yca*1000/100*2/40.08 + Y*Ymg*1000/100*2/24.305)
    Hstraw = (-S*Sp*1000/100/30.97 + S*Sk*1000/100/39.1
              + S*Sca*1000/100*2/40.08 + S*Smg*1000/100*2/24.305)
    Acrop = Hgrain + Hstraw
    Anit = 2.7 * math.exp(0.0088*(FertN+Ndep)) * 1000/14
    Ano3_runoff = (Ndep - (0.17*Ndep - 4.95)) * 1000/14 * 2
    Ano3_crop = 0
    Avol = (0.17*Ndep - 4.95) * 1000/14
    ANcy = Anit + Ano3_runoff + Ano3_crop + Avol
    Aagri = Adep + Acrop + ANcy
    Aback = (6.25*10**(9-SJD) - 6.25*10**(9-pHtarget)
             + 2.5*Hex*10**7 + 2.5*Alex*10**7) / 1000
    YTK = (Aback + 0.8*Aagri) / 17.042 * 0.77
    MBNT = 0.1*Aagri/1.89 + Alex*590*15 * 0.2
    return {"Adep": Adep, "Acrop": Acrop, "ANcy": ANcy, "Aagri": Aagri,
            "Aback": Aback, "YTK": YTK, "MBNT": MBNT}


def upland_compound(SJD: float, Hex: float, Alex: float,
                    RPH: float = 5.5, R: float = 1893, Y: float = 6700, S: float = 6968,
                    Yp: float = 0.41, Yk: float = 0.44, Yca: float = 0.03, Ymg: float = 0.141,
                    Sp: float = 0.21, Sk: float = 1.27, Sca: float = 0.71, Smg: float = 0.357333,
                    YN: float = 1.91, SN: float = 0.66,
                    FertN: float = 180, Ndep: float = 47.6, pHtarget: float = 6.0) -> Dict[str, float]:
    """旱地复合肥产酸平衡计算（移植自原始 upland_compound）。"""
    Adep = 10**(-RPH) * 667 * (R/1000) * 1000 * 15
    Hgrain = (-Y*Yp*1000/100/30.97 + Y*Yk*1000/100/39.1
              + Y*Yca*1000/100*2/40.08 + Y*Ymg*1000/100*2/24.305)
    Hstraw = (-S*Sp*1000/100/30.97 + S*Sk*1000/100/39.1
              + S*Sca*1000/100*2/40.08 + S*Smg*1000/100*2/24.305)
    Acrop = Hgrain + Hstraw
    Anit = 2.7 * math.exp(0.0088*(FertN+Ndep)) * 1000/14
    Ano3_crop = -(Y*YN + S*SN) * 1000/100/14 * 0.3
    Ano3_runoff = ((FertN - (0.17*FertN - 4.95)) * 1000/14 * 2 * 0.3
                   + (Ndep - (0.17*Ndep - 4.95)) * 1000/14 * 2)
    Avol = ((0.17*FertN - 4.95) * 1000/14 * 0.3
            + (0.17*Ndep - 4.95) * 1000/14)
    ANcy = Anit + Ano3_runoff + Ano3_crop + Avol
    Aagri = Adep + Acrop + ANcy
    Aback = (6.25*10**(9-SJD) - 6.25*10**(9-pHtarget)
             + 2.5*Hex*10**7 + 2.5*Alex*10**7) / 1000
    YTK = (Aback + 0.8*Aagri) / 17.042 * 0.7
    MBNT = 0.1*Aagri/1.89 + Alex*590*15 * 0.3
    return {"Adep": Adep, "Acrop": Acrop, "ANcy": ANcy, "Aagri": Aagri,
            "Aback": Aback, "YTK": YTK, "MBNT": MBNT}


# 函数选择器
FUNCTION_SELECTOR = {
    ("paddy", "urea"): paddy_urea,
    ("paddy", "compound"): paddy_compound,
    ("upland", "urea"): upland_urea,
    ("upland", "compound"): upland_compound,
}


def calculate_acidification(SJD: float, Hex: float, Alex: float,
                           land_type: str, fertilizer_type: str,
                           pHtarget: float = None) -> Dict[str, float]:
    """根据 land_type 和 fertilizer_type 选择对应函数计算。

    Args:
        SJD: 土壤 pH。
        Hex: 交换性氢。
        Alex: 交换性铝。
        land_type: "paddy" 或 "upland"。
        fertilizer_type: "urea" 或 "compound"。
        pHtarget: 目标 pH（覆盖函数默认值，通常从 ParcelInfo.target_ph 读取）。

    Returns:
        dict: Adep, Acrop, ANcy, Aagri, Aback, YTK, MBNT。

    Raises:
        ValueError: land_type/fertilizer_type 组合无效。
    """
    key = (land_type, fertilizer_type)
    func = FUNCTION_SELECTOR.get(key)
    if func is None:
        raise ValueError(f"无效的 land_type×fertilizer_type: {key}")

    kwargs = {}
    if pHtarget is not None:
        kwargs["pHtarget"] = pHtarget

    return func(SJD=SJD, Hex=Hex, Alex=Alex, **kwargs)
