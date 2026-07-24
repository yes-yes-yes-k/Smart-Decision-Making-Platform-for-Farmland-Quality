import pandas as pd
import numpy as np
import os
from typing import Dict, Any, Optional
from .config import (
    REGION_MAP, SECONDARY_REGION_MAP, COLUMN_RENAME, TEXT_VALUE_MAPS,
    COEFFICIENTS, WEIGHTS, INDICATOR_NAME_MAP, calc_obstacle_level
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


def evaluate_single(row: pd.Series, region_code: str, secondary_region_code: str) -> Dict[str, Any]:
    result = {'region_code': region_code, 'secondary_region_code': secondary_region_code}

    continuous_cols = ['PH', 'YJ', 'YXP', 'SXK', 'RZ', 'YXT', 'GCH']
    discrete_cols = ['GZ', 'GG', 'PS', 'DX', 'ZD']

    coeff = COEFFICIENTS.get(region_code)
    if not coeff:
        raise ValueError(f"No coefficients for region '{region_code}'.")

    for col in continuous_cols:
        result[col] = row.get(col)
        try:
            val = float(row.get(col))
            result[col + '_LD'] = calc_continuous(val, coeff[col])
        except Exception:
            result[col + '_LD'] = np.nan

    for col in discrete_cols:
        result[col] = row.get(col)
        try:
            raw = row.get(col)
            try:
                result[col + '_LD'] = calc_discrete(raw, coeff[col])
            except (ValueError, KeyError):
                result[col + '_LD'] = calc_discrete(str(raw), coeff[col])
        except Exception:
            result[col + '_LD'] = np.nan

    weights = WEIGHTS.get(secondary_region_code)
    if not weights:
        raise ValueError(f"No weights for secondary region '{secondary_region_code}'.")

    weighted_indicators = ['PH', 'YJ', 'YXP', 'SXK', 'RZ', 'YXT', 'GZ', 'GG', 'PS', 'DX', 'ZD', 'GCH']
    composite_weight = 0.0
    for ind in weighted_indicators:
        ld_val = result.get(ind + '_LD', np.nan)
        w = weights.get(ind, 0.0)
        if pd.notna(ld_val):
            composite_weight += ld_val * w
    result['composite_weight'] = composite_weight

    grade_config = {
        'HN': ([0, 0.6650, 0.6900, 0.7150, 0.7400, 0.7650, 0.7900, 0.8150, 0.8400, 0.8650, float('inf')],
               ['10', '9', '8', '7', '6', '5', '4', '3', '2', '1']),
        'CJ': ([0, 0.6960, 0.7224, 0.7488, 0.7751, 0.8015, 0.8279, 0.8543, 0.8806, 0.9070, float('inf')],
               ['10', '9', '8', '7', '6', '5', '4', '3', '2', '1']),
    }

    bins, labels = grade_config[region_code]
    grade = pd.cut([composite_weight], bins=bins, labels=labels, right=False)[0]
    result['grade'] = str(grade) if grade is not None else 'Unknown'

    std_levels = calc_obstacle_level(result, weighted_indicators)
    for ind in weighted_indicators:
        level = std_levels.get(ind)
        if pd.notna(level) and level != '无障碍':
            if ind == 'PH':
                if pd.notna(result['PH']):
                    if result['PH'] < 6.5:
                        direction = '酸化'
                    elif result['PH'] > 7.5:
                        direction = '碱化'
                    else:
                        direction = ''
                    if direction:
                        level = level.replace('障碍', direction)
            elif ind == 'RZ':
                if pd.notna(result['RZ']):
                    if result['RZ'] > 1.2:
                        direction = '板结'
                    else:
                        direction = '松散'
                    if direction:
                        level = level.replace('障碍', direction)
            elif ind == 'YJ':
                mapping = {'重度障碍': '重度贫瘠', '中度障碍': '中度贫瘠', '轻度障碍': '轻度贫瘠', '无障碍': '丰富'}
                level = mapping.get(level, level)
            elif ind in ['YXP', 'SXK']:
                mapping = {'重度障碍': '重度缺乏', '中度障碍': '中度缺乏', '轻度障碍': '轻度缺乏', '无障碍': '丰富'}
                level = mapping.get(level, level)
        result[INDICATOR_NAME_MAP[ind] + '障碍等级'] = level

    sum_terms = 0.0
    terms = {}
    for ind in weighted_indicators:
        u = result.get(ind + '_LD', np.nan)
        w = weights.get(ind, 0.0)
        term = (1.0 - u) * w if pd.notna(u) else 0.0
        terms[ind] = term
        sum_terms += term

    for ind in weighted_indicators:
        if sum_terms > 0:
            result[ind + '_OD'] = terms[ind] / sum_terms
        else:
            result[ind + '_OD'] = 0.0

    return result


def bulk_evaluate(input_csv: str, output_db_path: str = None) -> Dict[str, Any]:
    try:
        df = pd.read_csv(input_csv, encoding='utf-8')
    except UnicodeDecodeError:
        df = pd.read_csv(input_csv, encoding='gbk')

    df.rename(columns=COLUMN_RENAME, inplace=True)

    required = ['JY', 'EJ', 'PH', 'YJ', 'YXP', 'SXK', 'RZ', 'GZ', 'GG', 'PS', 'DX', 'ZD', 'YXT', 'GCH']
    missing = [c for c in required if c not in df.columns]
    if missing:
        return {"status": "error", "message": f"Missing columns: {missing}"}

    df['JY'] = df['JY'].astype(str).str.strip().map(REGION_MAP)
    if df['JY'].isna().any():
        bad = df[df['JY'].isna()].index.tolist()
        return {"status": "error", "message": f"Unknown primary region names at rows {bad}"}

    for col, mapping in TEXT_VALUE_MAPS.items():
        if col in df.columns:
            df[col] = df[col].map(mapping)

    df['EJ_code'] = df['EJ'].astype(str).str.strip().map(SECONDARY_REGION_MAP)
    if df['EJ_code'].isna().any():
        bad = df[df['EJ_code'].isna()].index.tolist()
        return {"status": "error", "message": f"Unknown secondary region names at rows {bad}"}

    storage = DiagnosisStorage(output_db_path)
    storage.create_tables()

    records = []
    errors = []
    for idx, row in df.iterrows():
        try:
            result = evaluate_single(row, row['JY'], row['EJ_code'])
            result['parcel_id'] = str(idx)
            records.append(result)
        except Exception as e:
            errors.append(f"Row {idx}: {str(e)}")

    if records:
        storage.save_evaluation(records)

    return {
        "status": "ok",
        "processed": len(records),
        "errors": errors
    }
