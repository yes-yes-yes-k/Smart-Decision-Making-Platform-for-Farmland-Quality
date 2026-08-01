# -*- coding: utf-8 -*-
"""酸化改良过程模型。

本模块用过程模型（移植自模型5 v2 源码
D:\\destkop\\模型5_酸化模型_v2_20260801\\模型5_酸化模型_v2_20260801\\02_酸化模型计算.py）
替换旧的酸化改良经验逻辑。原理文档 01_产酸过程计算公式.docx 有笔误，以源码为准。

主要入口：
    calculate_acidification_amendment(pHstart, Hex, Alex, land_type, fertilizer_type, **optional_params)

4 个子模型：_paddy_urea / _paddy_compound / _upland_urea / _upland_compound
统一入口负责：缺失/越界校验 → 非法 land_type/fertilizer_type 回退 → 默认参数组装 →
可配参数白名单覆盖 → 子模型选择 → 输出标准化结构。

旧函数 query_acidification / evaluate_acidification 委托新模型（按需计算模式）；
classify_acidification / generate_amendment / calculate_lime_demand /
calculate_amendment_rate 保留原签名与实现以兼容旧引用（docstring 标记 deprecated）。
"""
import math
import sqlite3
import warnings as _warnings
from typing import Any, Dict, Optional

import pandas as pd  # 保留：旧 evaluate_acidification 路径与回归兼容

from .config import AMENDMENT_CONFIG
from .storage import DiagnosisStorage


MODEL_VERSION = "process_v2_20260801"

# 可配参数白名单（API 可覆盖；元素含量等内置参数不允许覆盖）
CONFIGURABLE_PARAMS = {"RPH", "R", "Y", "S", "FertN", "Ndep", "pHtarget"}

# ---------------------------------------------------------------------------
# 默认参数（数值与模型5源码 02_酸化模型计算-地块.py 完全一致）
# 元素含量单位为 %（质量分数），与源码一致；切勿与 g/kg 混用。
# ---------------------------------------------------------------------------
_PADDY_DEFAULTS: Dict[str, float] = {
    "RPH": 5.5,    # 降水pH年均值
    "R": 1893.0,   # 年降水量 mm
    "Y": 5109.0,   # 籽粒产量 kg/ha/yr
    "S": 5109.0,   # 秸秆产量 kg/ha/yr
    "Yp": 0.35,    # 籽粒P含量 %
    "Yk": 0.19,    # 籽粒K含量 %
    "Yca": 0.03,   # 籽粒Ca含量 %
    "Ymg": 0.12,   # 籽粒Mg含量 %
    "Sp": 0.176,   # 秸秆P含量 %
    "Sk": 1.99,    # 秸秆K含量 %
    "Sca": 0.54,   # 秸秆Ca含量 %
    "Smg": 0.212,  # 秸秆Mg含量 %
    "FertN": 180.0,  # 施肥量（以N元素计） kg/ha
    "Ndep": 47.6,    # N沉降 kg/ha
    "pHtarget": 6.5,  # 目标pH（水田6.5）
}

_UPLAND_DEFAULTS: Dict[str, float] = {
    "RPH": 5.5,
    "R": 1893.0,
    "Y": 6700.0,
    "S": 6968.0,
    "Yp": 0.41,
    "Yk": 0.44,
    "Yca": 0.03,
    "Ymg": 0.141,
    "Sp": 0.21,
    "Sk": 1.27,
    "Sca": 0.71,
    "Smg": 0.357333,
    "FertN": 180.0,
    "Ndep": 47.6,
    "pHtarget": 6.0,  # 旱地目标pH 6.0
}

# 复合肥额外参数（籽粒/秸秆含氮量 %）
_PADDY_COMPOUND_EXTRA: Dict[str, float] = {"YN": 1.87, "SN": 1.15}
_UPLAND_COMPOUND_EXTRA: Dict[str, float] = {"YN": 1.91, "SN": 0.66}


# ---------------------------------------------------------------------------
# 通用计算基元（设计文档 §1.2，逐行对照模型5源码）
# ---------------------------------------------------------------------------
def _adep(RPH: float, R: float) -> float:
    """酸沉降产酸量 Adep = 10^(-RPH) * 667 * (R/1000) * 1000 * 15  (mol/ha/yr)。"""
    return (10 ** (-RPH)) * 667 * (R / 1000.0) * 1000 * 15


def _hcrop(Y: float, S: float, ec: Dict[str, float]) -> float:
    """植株吸收利用产 H+ 量 = Hgrain + Hstraw（mol/ha/yr）。

    元素含量 ec 中 Yp/Yk/Yca/Ymg/Sp/Sk/Sca/Smg 单位为 %（与源码一致）。
    化学计量：P、K 为 1 价消耗/释放；Ca、Mg 为 2 价（*2 当量）。
    符号：P 产酸（负贡献），K/Ca/Mg 产碱（正贡献，消耗 H+）。
    公式与源码逐行一致：
        Hgrain = -Y*Yp*1000/100/30.97 + Y*Yk*1000/100/39.1
                 + Y*Yca*1000/100*2/40.08 + Y*Ymg*1000/100*2/24.305
        Hstraw = -S*Sp*1000/100/30.97 + S*Sk*1000/100/39.1
                 + S*Sca*1000/100*2/40.08 + S*Smg*1000/100*2/24.305
    """
    Hgrain = (-Y * ec["Yp"] * 1000 / 100 / 30.97
              + Y * ec["Yk"] * 1000 / 100 / 39.1
              + Y * ec["Yca"] * 1000 / 100 * 2 / 40.08
              + Y * ec["Ymg"] * 1000 / 100 * 2 / 24.305)
    Hstraw = (-S * ec["Sp"] * 1000 / 100 / 30.97
              + S * ec["Sk"] * 1000 / 100 / 39.1
              + S * ec["Sca"] * 1000 / 100 * 2 / 40.08
              + S * ec["Smg"] * 1000 / 100 * 2 / 24.305)
    return Hgrain + Hstraw


def _finalize(pHstart: float, Hex: float, Alex: float, pHtarget: float,
              Adep: float, Acrop: float, ANcy: float, Aagri: float,
              ytk_coef: float, mbnt_a: float, mbnt_b: float) -> Dict[str, float]:
    """计算 Aback 与 YTK/MBNT，返回完整 7 字段 dict。

    返回字段：Adep, Acrop, ANcy, Aagri, Aback, ytk, mbnt。
    中间变量由调用方（4 个子模型）计算后传入，本函数只负责 Aback/YTK/MBNT 收尾。
    """
    Aback = (6.25 * (10 ** (9 - pHstart))
             - 6.25 * (10 ** (9 - pHtarget))
             + 2.5 * Hex * 1e7
             + 2.5 * Alex * 1e7) / 1000.0
    ytk = (Aback + 0.8 * Aagri) / 17.042 * ytk_coef
    mbnt = mbnt_a * Aagri / 1.89 + Alex * 590 * 15 * mbnt_b
    return {"Adep": Adep, "Acrop": Acrop, "ANcy": ANcy, "Aagri": Aagri,
            "Aback": Aback, "ytk": ytk, "mbnt": mbnt}


# ---------------------------------------------------------------------------
# 4 个子模型（tasks 2.1，差异矩阵见设计文档 §1.3；公式以模型5源码为准）
# ---------------------------------------------------------------------------
def _paddy_urea(pHstart, Hex, Alex, p):
    Adep = _adep(p["RPH"], p["R"])
    Acrop = _hcrop(p["Y"], p["S"], p)
    Anit = 2.221 * math.exp(0.0048 * (p["FertN"] + p["Ndep"])) * 1000 / 14
    Ano3_runoff = (p["Ndep"] - (0.16 * p["Ndep"] + 2.97)) * 1000 / 14 * 2
    Ano3_crop = 0.0
    Avol = (p["Ndep"] - (0.16 * p["Ndep"] + 2.97)) * 1000 / 14 * 2
    ANcy = Anit + Ano3_runoff + Ano3_crop + Avol
    Aagri = Adep + Acrop + ANcy
    return _finalize(pHstart, Hex, Alex, p["pHtarget"],
                     Adep, Acrop, ANcy, Aagri,
                     ytk_coef=0.6, mbnt_a=0.1, mbnt_b=1.0)


def _paddy_compound(pHstart, Hex, Alex, p):
    Adep = _adep(p["RPH"], p["R"])
    Acrop = _hcrop(p["Y"], p["S"], p)
    Anit = 2.221 * math.exp(0.0048 * (p["FertN"] + p["Ndep"])) * 1000 / 14
    Ano3_crop = -(p["Y"] * p["YN"] + p["S"] * p["SN"]) * 1000 / 100 / 14 * 0.3
    Ano3_runoff = ((p["FertN"] - (0.16 * p["FertN"] + 2.97)) * 1000 / 14 * 2 * 0.3
                   + (p["Ndep"] - (0.16 * p["Ndep"] + 2.97)) * 1000 / 14 * 2)
    Avol = ((0.16 * p["FertN"] + 2.97) * 1000 / 14 * 0.3
            + (0.16 * p["Ndep"] + 2.97) * 1000 / 14)
    ANcy = Anit + Ano3_runoff + Ano3_crop + Avol
    Aagri = Adep + Acrop + ANcy
    return _finalize(pHstart, Hex, Alex, p["pHtarget"],
                     Adep, Acrop, ANcy, Aagri,
                     ytk_coef=0.6, mbnt_a=0.15, mbnt_b=1.0)


def _upland_urea(pHstart, Hex, Alex, p):
    Adep = _adep(p["RPH"], p["R"])
    Acrop = _hcrop(p["Y"], p["S"], p)
    Anit = 2.7 * math.exp(0.0088 * (p["FertN"] + p["Ndep"])) * 1000 / 14
    Ano3_runoff = (p["Ndep"] - (0.17 * p["Ndep"] - 4.95)) * 1000 / 14 * 2
    Ano3_crop = 0.0
    Avol = (0.17 * p["Ndep"] - 4.95) * 1000 / 14
    ANcy = Anit + Ano3_runoff + Ano3_crop + Avol
    Aagri = Adep + Acrop + ANcy
    return _finalize(pHstart, Hex, Alex, p["pHtarget"],
                     Adep, Acrop, ANcy, Aagri,
                     ytk_coef=0.77, mbnt_a=0.1, mbnt_b=0.2)


def _upland_compound(pHstart, Hex, Alex, p):
    Adep = _adep(p["RPH"], p["R"])
    Acrop = _hcrop(p["Y"], p["S"], p)
    Anit = 2.7 * math.exp(0.0088 * (p["FertN"] + p["Ndep"])) * 1000 / 14
    Ano3_crop = -(p["Y"] * p["YN"] + p["S"] * p["SN"]) * 1000 / 100 / 14 * 0.3
    Ano3_runoff = ((p["FertN"] - (0.17 * p["FertN"] - 4.95)) * 1000 / 14 * 2 * 0.3
                   + (p["Ndep"] - (0.17 * p["Ndep"] - 4.95)) * 1000 / 14 * 2)
    Avol = ((0.17 * p["FertN"] - 4.95) * 1000 / 14 * 0.3
            + (0.17 * p["Ndep"] - 4.95) * 1000 / 14)
    ANcy = Anit + Ano3_runoff + Ano3_crop + Avol
    Aagri = Adep + Acrop + ANcy
    return _finalize(pHstart, Hex, Alex, p["pHtarget"],
                     Adep, Acrop, ANcy, Aagri,
                     ytk_coef=0.7, mbnt_a=0.1, mbnt_b=0.3)


def _build_params(land_type: str, fertilizer_type: str) -> Dict[str, float]:
    """组装默认参数（不含可配覆盖）。

    land_type: "paddy" 或 "upland"
    fertilizer_type: "urea" 或 "compound"
    返回：含基础默认参数 + 复合肥额外参数（若 compound）的 dict 副本。
    被 calculate_acidification_amendment 与 run_csv 共用，消除重复装配逻辑。
    """
    base: Dict[str, float] = dict(_UPLAND_DEFAULTS) if land_type == "upland" else dict(_PADDY_DEFAULTS)
    if fertilizer_type == "compound":
        base.update(_UPLAND_COMPOUND_EXTRA if land_type == "upland" else _PADDY_COMPOUND_EXTRA)
    return base


_SUB_MODEL_MAP = {
    ("paddy", "urea"): _paddy_urea,
    ("paddy", "compound"): _paddy_compound,
    ("upland", "urea"): _upland_urea,
    ("upland", "compound"): _upland_compound,
}


# ---------------------------------------------------------------------------
# 统一入口（tasks 2.2/2.4/2.5/2.6）
# ---------------------------------------------------------------------------
def calculate_acidification_amendment(
    pHstart: float,
    Hex: float,
    Alex: float,
    land_type: str = "upland",
    fertilizer_type: str = "compound",
    **optional_params: float,
) -> Dict[str, Any]:
    """过程模型统一入口：校验 → 回退 → 默认参数 → 可配覆盖 → 子模型 → 标准化输出。

    返回结构：
        {status, ytk, mbnt, sub_model, land_type, fertilizer_type,
         customized_params, model_version, warning(可选), reason(可选),
         out_of_range_features(可选)}
    """
    warnings_list = []
    # 1. 缺失输入校验
    if pHstart is None or Hex is None or Alex is None:
        return {"status": "rejected", "reason": "missing_input",
                "ytk": None, "mbnt": None, "model_version": MODEL_VERSION}
    # 2. 越界校验
    oor = []
    if not (3.0 <= float(pHstart) <= 10.0):
        oor.append({"feature": "pHstart", "value": pHstart, "valid_range": [3.0, 10.0]})
    if float(Hex) < 0:
        oor.append({"feature": "Hex", "value": Hex, "valid_range": [0.0, None]})
    if float(Alex) < 0:
        oor.append({"feature": "Alex", "value": Alex, "valid_range": [0.0, None]})
    if oor:
        return {"status": "rejected", "reason": "input_out_of_range",
                "out_of_range_features": oor, "ytk": None, "mbnt": None,
                "model_version": MODEL_VERSION}
    # 3. 子模型选择 + 非法回退
    lt = land_type if land_type in ("paddy", "upland") else "upland"
    ft = fertilizer_type if fertilizer_type in ("urea", "compound") else "compound"
    if lt != land_type:
        warnings_list.append(f"land_type='{land_type}' 非法，回退 'upland'")
    if ft != fertilizer_type:
        warnings_list.append(f"fertilizer_type='{fertilizer_type}' 非法，回退 'compound'")
    # 4. 组装默认参数（复用 _build_params，与 run_csv 共享装配逻辑）
    base = _build_params(lt, ft)
    # 5. 可配参数覆盖（仅白名单）
    customized: Dict[str, float] = {}
    for k, v in optional_params.items():
        if k in CONFIGURABLE_PARAMS and v is not None:
            base[k] = v
            customized[k] = v
    # 6. 子模型计算
    sub_fn = _SUB_MODEL_MAP[(lt, ft)]
    out = sub_fn(float(pHstart), float(Hex), float(Alex), base)
    result: Dict[str, Any] = {
        "status": "success",
        "ytk": out["ytk"],
        "mbnt": out["mbnt"],
        "sub_model": sub_fn.__name__.lstrip("_"),
        "land_type": lt,
        "fertilizer_type": ft,
        "customized_params": customized,
        "model_version": MODEL_VERSION,
    }
    if warnings_list:
        result["warning"] = "; ".join(warnings_list)
    return result


def run_csv(input_file: str, output_file: str,
            land_type: str, fertilizer_type: str) -> "pd.DataFrame":
    """批量 CSV 计算：读 CSV → 4 子模型批量计算 → 输出 CSV。

    与 v2 源码 02_酸化模型计算.py 语义一致：
    - 输入 CSV 需包含 SJD（或 pH）、Hex、Alex 列
    - 输出 CSV 含输入列 + 中间变量列（Adep/Acrop/ANcy/Aagri/Aback）+ 结果列（YTK/MBNT）
    - NaN 行输出 7 个 None，不抛异常
    - 不做越界校验（仅单次入口 calculate_acidification_amendment 做）

    Args:
        input_file: 输入 CSV 路径（utf-8-sig 编码）
        output_file: 输出 CSV 路径
        land_type: "paddy" 或 "upland"
        fertilizer_type: "urea" 或 "compound"

    Returns:
        填充计算列后的 DataFrame
    """
    if land_type not in ("paddy", "upland") or fertilizer_type not in ("urea", "compound"):
        raise ValueError("土地类型只能为水田或旱地，肥料类型只能为尿素或复合肥")

    df = pd.read_csv(input_file, encoding="utf-8-sig")
    p_col = "SJD" if "SJD" in df else "pH"
    if not {p_col, "Hex", "Alex"} <= set(df):
        raise ValueError("CSV必须包含pH或SJD、Hex、Alex列")

    sub_fn = _SUB_MODEL_MAP[(land_type, fertilizer_type)]
    params = _build_params(land_type, fertilizer_type)
    cols = ["Adep", "Acrop", "ANcy", "Aagri", "Aback", "YTK", "MBNT"]

    def _compute_row(v):
        if pd.isna(v).any():
            return [None] * 7
        out = sub_fn(*map(float, v), params)
        return [round(out["Adep"], 2), round(out["Acrop"], 2), round(out["ANcy"], 2),
                round(out["Aagri"], 2), round(out["Aback"], 2),
                round(out["ytk"], 2), round(out["mbnt"], 2)]

    df[cols] = [_compute_row(v) for v in df[[p_col, "Hex", "Alex"]].to_numpy()]
    df.to_csv(output_file, index=False, encoding="utf-8-sig")
    return df


# ===========================================================================
# 旧函数（兼容层）
# ===========================================================================
# classify/generate/calculate_* 保留原实现（docstring 标记 deprecated），
# 以避免破坏既有引用与测试；query/evaluate 委托新模型并发出 DeprecationWarning。

ACIDIFICATION_LEVELS = {
    'HN': {
        'severe': {'min': 0, 'max': 4.5, 'desc': '强酸性'},
        'moderate': {'min': 4.5, 'max': 5.5, 'desc': '酸性'},
        'slight': {'min': 5.5, 'max': 6.5, 'desc': '微酸性'},
        'neutral': {'min': 6.5, 'max': 7.5, 'desc': '中性'},
        'alkaline': {'min': 7.5, 'max': 14, 'desc': '碱性'}
    },
    'CJ': {
        'severe': {'min': 0, 'max': 4.5, 'desc': '强酸性'},
        'moderate': {'min': 4.5, 'max': 5.5, 'desc': '酸性'},
        'slight': {'min': 5.5, 'max': 6.5, 'desc': '微酸性'},
        'neutral': {'min': 6.5, 'max': 7.5, 'desc': '中性'},
        'alkaline': {'min': 7.5, 'max': 14, 'desc': '碱性'}
    },
    'default': {
        'severe': {'min': 0, 'max': 4.5, 'desc': '强酸性'},
        'moderate': {'min': 4.5, 'max': 5.5, 'desc': '酸性'},
        'slight': {'min': 5.5, 'max': 6.5, 'desc': '微酸性'},
        'neutral': {'min': 6.5, 'max': 7.5, 'desc': '中性'},
        'alkaline': {'min': 7.5, 'max': 14, 'desc': '碱性'}
    }
}


def classify_acidification(pH: float, region_code: str) -> Dict[str, Any]:
    """[DEPRECATED] 酸化程度分区。保留原实现以兼容旧引用；新代码请用过程模型。"""
    levels = ACIDIFICATION_LEVELS.get(region_code, ACIDIFICATION_LEVELS['default'])
    for level, bounds in levels.items():
        if bounds['min'] <= pH < bounds['max']:
            return {'level': level, 'description': bounds['desc'], 'pH': pH}
    return {'level': 'neutral', 'description': '中性', 'pH': pH}


def generate_amendment(pH: float, organic_matter: float, region_code: str) -> Dict[str, Any]:
    """[DEPRECATED] 生成酸化改良方案。保留原实现以兼容旧引用。"""
    acid_info = classify_acidification(pH, region_code)
    level = acid_info['level']
    if level in ['neutral', 'alkaline']:
        return {
            'acidification_level': acid_info['description'],
            'need_amendment': False,
            'reason': '土壤酸碱度适中，无需酸化改良',
            'amendment_plan': []
        }
    measures_config = AMENDMENT_CONFIG.get('measures', {})
    amendments = []
    if level == 'severe':
        amendments.extend(measures_config.get('severe', []))
    elif level == 'moderate':
        amendments.extend(measures_config.get('moderate', []))
    elif level == 'slight':
        amendments.extend(measures_config.get('mild', []))
    if organic_matter < 15:
        amendments.append({
            'measure': '增施有机肥',
            'description': f'当前有机质含量 {organic_matter} g/kg，建议增施有机肥提升土壤缓冲能力',
            'application_rate': '15-30 t/ha',
            'frequency': '每年'
        })
    return {
        'acidification_level': acid_info['description'],
        'need_amendment': True,
        'reason': f'土壤pH={pH}，属于{acid_info["description"]}，需要改良',
        'amendment_plan': amendments
    }


def calculate_lime_demand(pH: float, organic_matter: float) -> float:
    """[DEPRECATED] 计算石灰需求量（kg/亩）。保留原实现以兼容旧引用。"""
    if pH >= 6.5:
        return 0.0
    deficit = 6.5 - pH
    base_demand = deficit * 100
    if organic_matter < 15:
        base_demand *= 1.2
    return round(base_demand, 1)


def calculate_amendment_rate(pH: float) -> float:
    """[DEPRECATED] 计算改良剂施用率。保留原实现以兼容旧引用。"""
    if pH < 4.5:
        return 200.0
    elif pH < 5.5:
        return 150.0
    elif pH < 6.0:
        return 100.0
    elif pH < 6.5:
        return 50.0
    return 0.0


def query_acidification(parcel_id: str, db_path: str = None) -> Dict[str, Any]:
    """[DEPRECATED] 查询单个地块的酸化改良方案。

    保留签名以兼容导入；按需计算模式下仅 parcel_id 不足以触发计算
    （DB 中需含 SJD/JHX/JLA），否则返回 not_ready/missing_input。
    新代码请直接调用 calculate_acidification_amendment。
    """
    _warnings.warn("query_acidification 已废弃，请用 calculate_acidification_amendment",
                   DeprecationWarning, stacklevel=2)
    storage = DiagnosisStorage(db_path)
    if not storage.is_ready():
        return {"status": "not_ready"}
    ev = storage.get_evaluation(parcel_id)
    if ev is None:
        return {"status": "not_found"}
    sjd = ev.get("SJD")
    if sjd is None or ev.get("JHX") is None or ev.get("JLA") is None:
        return {"status": "not_ready", "reason": "missing_input",
                "message": "需要 SJD/JHX/JLA 才能计算，DB 中缺失"}
    res = calculate_acidification_amendment(float(sjd), float(ev["JHX"]), float(ev["JLA"]))
    return {"status": "ok" if res["status"] == "success" else res["status"],
            "parcel_id": parcel_id, "acidification": res}


def evaluate_acidification(db_path: str = None) -> Dict[str, Any]:
    """[DEPRECATED] 批量评估酸化改良方案。

    按需计算模式下不再需要批量评估；保留签名以兼容导入。
    新代码请用 calculate_acidification_amendment 按需计算。
    """
    _warnings.warn("evaluate_acidification 已废弃，请用 calculate_acidification_amendment 按需计算",
                   DeprecationWarning, stacklevel=2)
    return {"status": "deprecated", "message": "使用 calculate_acidification_amendment 按需计算"}
