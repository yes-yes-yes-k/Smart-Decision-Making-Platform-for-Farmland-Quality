import pandas as pd
import numpy as np
import os
from typing import Dict, Any, Optional
from .config import (
    REGION_MAP, SECONDARY_REGION_MAP,
    COEFFICIENTS, WEIGHTS, DISCRETE_CN_MAP, GRADE_CONFIG,
    ALL_INDICATORS, CONTINUOUS_INDICATORS, DISCRETE_INDICATORS, WEIGHTED_INDICATORS,
    INDICATOR_DISPLAY_MAP, ACIDIFICATION_INDICATORS, calc_obstacle_level,
)
from .storage import DiagnosisStorage


def calc_continuous(value: float, params: Dict[str, Any]) -> float:
    a = params.get('a')
    c = params.get('c')
    if a is None or c is None:
        raise ValueError("Missing 'a' or 'c' for continuous indicator.")
    L = params.get('L')
    U = params.get('U')
    if (L is not None) and (value < L):
        return 0.0
    if (U is not None) and (value > U):
        return 0.0
    return 1.0 / (1.0 + a * (value - c) ** 2)


def calc_discrete(value, mapping: Dict) -> float:
    if not mapping:
        raise ValueError("Discrete indicator mapping is empty.")
    if '__ANY__' in mapping:
        return mapping['__ANY__']
    if value not in mapping:
        raise ValueError(f"Value '{value}' not in discrete mapping.")
    return mapping[value]


def translate_obstacle_level(ind, level, orig_val):
    """将标准障碍等级（重度/中度/轻度障碍）按指标方向转译为可读描述。

    逻辑同 V2.0：SJD→酸化/碱化、TRRZ→板结/松散、YJZ→贫瘠/丰富、YXL/SXJ→缺乏/丰富。
    """
    if pd.isna(level) or level == '无障碍':
        return '无障碍'
    if ind == 'SJD':
        if pd.notna(orig_val):
            direction = '酸化' if orig_val < 6.5 else '碱化' if orig_val > 7.5 else ''
            return level.replace('障碍', direction) if direction else level
        return level
    elif ind == 'TRRZ':
        if pd.notna(orig_val):
            direction = '板结' if orig_val > 1.2 else '松散'
            return level.replace('障碍', direction) if direction else level
        return level
    elif ind == 'YJZ':
        mapping = {'重度障碍': '重度贫瘠', '中度障碍': '中度贫瘠', '轻度障碍': '轻度贫瘠', '无障碍': '丰富'}
        return mapping.get(level, level)
    elif ind in ['YXL', 'SXJ']:
        mapping = {'重度障碍': '重度缺乏', '中度障碍': '中度缺乏', '轻度障碍': '轻度缺乏', '无障碍': '丰富'}
        return mapping.get(level, level)
    else:
        return level


def evaluate_single(row: pd.Series, region_code: str, secondary_region_code: str) -> Dict[str, Any]:
    result = {'region_code': region_code, 'secondary_region_code': secondary_region_code}

    coeff = COEFFICIENTS.get(region_code)
    if not coeff:
        raise ValueError(f"No coefficients for region '{region_code}'.")

    # 连续指标：原始值 + 隶属度
    for col in CONTINUOUS_INDICATORS:
        result[col] = row.get(col)
        try:
            val = float(row.get(col))
            result[col + 'LSD'] = calc_continuous(val, coeff[col])
        except Exception:
            result[col + 'LSD'] = np.nan

    # 离散指标：原始值（已转为代码） + 隶属度
    for col in DISCRETE_INDICATORS:
        result[col] = row.get(col)
        try:
            raw = row.get(col)
            try:
                result[col + 'LSD'] = calc_discrete(raw, coeff[col])
            except (ValueError, KeyError):
                result[col + 'LSD'] = calc_discrete(str(raw), coeff[col])
        except Exception:
            result[col + 'LSD'] = np.nan

    # 综合权重 ZHQZ
    weights = WEIGHTS.get(secondary_region_code)
    if not weights:
        raise ValueError(f"No weights for secondary region '{secondary_region_code}'.")

    composite_weight = 0.0
    for ind in WEIGHTED_INDICATORS:
        ld_val = result.get(ind + 'LSD', np.nan)
        w = weights.get(ind, 0.0)
        if pd.notna(ld_val):
            composite_weight += ld_val * w
    result['ZHQZ'] = composite_weight

    # 质量等级 GDZLDJ
    bins, labels = GRADE_CONFIG[region_code]
    grade = pd.cut([composite_weight], bins=bins, labels=labels, right=False)[0]
    result['GDZLDJ'] = str(grade) if grade is not None else 'Unknown'

    # 障碍等级 xxxZADJ（需在隶属度计算后调用 calc_obstacle_level，因 GCZD/DXBW 依赖隶属度）
    std_levels = calc_obstacle_level(result, WEIGHTED_INDICATORS)
    for ind in WEIGHTED_INDICATORS:
        level = std_levels.get(ind)
        level = translate_obstacle_level(ind, level, result.get(ind))
        result[ind + 'ZADJ'] = level

    # 障碍度 xxxZAD（独立列，不覆盖原始值）
    sum_terms = 0.0
    terms = {}
    for ind in WEIGHTED_INDICATORS:
        u = result.get(ind + 'LSD', np.nan)
        w = weights.get(ind, 0.0)
        term = (1.0 - u) * w if pd.notna(u) else 0.0
        terms[ind] = term
        sum_terms += term

    for ind in WEIGHTED_INDICATORS:
        if sum_terms > 0:
            result[ind + 'ZAD'] = terms[ind] / sum_terms
        else:
            result[ind + 'ZAD'] = 0.0

    return result


def bulk_evaluate(input_csv: str, output_db_path: str = None) -> Dict[str, Any]:
    try:
        df = pd.read_csv(input_csv, encoding='utf-8')
    except UnicodeDecodeError:
        df = pd.read_csv(input_csv, encoding='gbk')

    # CSV 直接使用标准码表头，不再 COLUMN_RENAME
    # 必填列：评价所需指标（排除酸化专用可选字段 JHX/JLA）
    required = ['YJNYQ', 'EJNYQ'] + [i for i in ALL_INDICATORS if i not in ACIDIFICATION_INDICATORS]
    missing = [c for c in required if c not in df.columns]
    if missing:
        return {"status": "error", "message": f"Missing columns: {missing}"}

    # 一级区映射
    df['YJNYQ_code'] = df['YJNYQ'].astype(str).str.strip().map(REGION_MAP)
    if df['YJNYQ_code'].isna().any():
        bad = df[df['YJNYQ_code'].isna()].index.tolist()
        return {"status": "error", "message": f"Unknown primary region names at rows {bad}"}

    # 二级区映射
    df['EJNYQ_code'] = df['EJNYQ'].astype(str).str.strip().map(SECONDARY_REGION_MAP)
    if df['EJNYQ_code'].isna().any():
        bad = df[df['EJNYQ_code'].isna()].index.tolist()
        return {"status": "error", "message": f"Unknown secondary region names at rows {bad}"}

    # 离散指标中文值 → 代码
    for ind in DISCRETE_INDICATORS:
        cn_map = DISCRETE_CN_MAP.get(ind, {})
        if cn_map and ind in df.columns:
            df[ind] = df[ind].astype(str).str.strip().map(cn_map)
            if df[ind].isna().any():
                bad_vals = df.loc[df[ind].isna(), ind].unique()
                print(f"警告：{ind}列存在未映射的值：{bad_vals}")

    storage = DiagnosisStorage(output_db_path)
    storage.create_tables()

    records = []
    errors = []
    for idx, row in df.iterrows():
        try:
            result = evaluate_single(row, row['YJNYQ_code'], row['EJNYQ_code'])
            result['parcel_id'] = str(idx)
            records.append(result)
        except Exception as e:
            errors.append(f"Row {idx}: {str(e)}")

    if records:
        storage.save_evaluation(records)

    return {
        "status": "ok",
        "processed": len(records),
        "errors": errors,
    }
