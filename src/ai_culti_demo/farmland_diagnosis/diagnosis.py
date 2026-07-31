import pandas as pd
import numpy as np
import sqlite3
from typing import Dict, Any, Optional
from .config import INDICATOR_DISPLAY_MAP
from .storage import DiagnosisStorage


def parse_obstacle_level(text: str) -> str:
    if pd.isna(text):
        return np.nan
    text = str(text)
    if '重度' in text:
        return '重度'
    elif '中度' in text:
        return '中度'
    elif '轻度' in text:
        return '轻度'
    elif '丰富' in text or '无障碍' in text:
        return '无障碍'
    else:
        return np.nan


def diagnosis_row(row: pd.Series) -> Dict[str, Any]:
    degree_cols = [col for col in row.index if col.endswith('_OD')]
    level_cols = [col for col in row.index if '障碍等级' in col]

    deg_names = [col.replace('_OD', '') for col in degree_cols]
    lev_names = [col.replace('障碍等级', '') for col in level_cols]

    common_names = sorted(list(set(deg_names) & set(lev_names)))
    aligned_deg_cols = [name + '_OD' for name in common_names]
    aligned_lev_cols = [name + '障碍等级' for name in common_names]

    candidates = []
    for name, lcol, dcol in zip(common_names, aligned_lev_cols, aligned_deg_cols):
        raw_level = row.get(lcol, np.nan)
        std_level = parse_obstacle_level(raw_level)
        degree = row.get(dcol, np.nan)
        if pd.isna(degree):
            degree = 0.0
        if std_level in ['重度', '中度']:
            candidates.append((name, raw_level, std_level, degree))

    if not candidates:
        return {'obstacle_type': '无明显障碍', 'main_factors': [], 'secondary_factors': []}

    candidates.sort(key=lambda x: x[3], reverse=True)

    threshold_main = 0.20
    threshold_cumulative = 0.60
    threshold_heavy_boost = 0.15
    threshold_minor = 0.10

    main_factors = []
    minor_factors = []

    for c in candidates:
        if c[3] >= threshold_main:
            main_factors.append(c)

    if not main_factors:
        cumulative = 0.0
        for c in candidates:
            cumulative += c[3]
            main_factors.append(c)
            if cumulative >= threshold_cumulative:
                break

    for c in candidates:
        if c not in main_factors and c[2] == '重度' and c[3] >= threshold_heavy_boost:
            main_factors.append(c)

    for c in candidates:
        if c not in main_factors and c[3] >= threshold_minor:
            minor_factors.append(c)

    if len(main_factors) == 1 and len(minor_factors) == 0:
        obstacle_type = '单一障碍'
    elif len(main_factors) == 0:
        obstacle_type = '无明显障碍'
    else:
        obstacle_type = '多障碍'

    def format_factor(c):
        name, raw_level, _, deg = c
        return f"{name}({raw_level}, {deg:.1%})"

    main_desc = [format_factor(c) for c in main_factors]
    minor_desc = [format_factor(c) for c in minor_factors]

    return {
        'obstacle_type': obstacle_type,
        'main_factors': main_desc,
        'secondary_factors': minor_desc
    }


def diagnose(db_path: str = None) -> Dict[str, Any]:
    storage = DiagnosisStorage(db_path)

    conn = sqlite3.connect(storage.db_path)
    df = pd.read_sql('SELECT * FROM evaluation_results', conn)
    conn.close()

    if df.empty:
        return {"status": "error", "message": "No evaluation data found"}

    records = []
    for idx, row in df.iterrows():
        diagnosis = diagnosis_row(row)
        record = {'parcel_id': row['parcel_id'], **diagnosis}

        weighted_indicators = ['PH', 'YJ', 'YXP', 'SXK', 'RZ', 'YXT', 'GZ', 'GG', 'PS', 'DX', 'ZD', 'GCH']
        for ind in weighted_indicators:
            record[ind + '_obstacle_level'] = row.get(INDICATOR_NAME_MAP[ind] + '障碍等级')
            record[ind + '_obstacle_degree'] = row.get(ind + '_OD', 0.0)

        records.append(record)

    storage.save_diagnosis(records)

    return {"status": "ok", "diagnosed": len(records)}


def query_parcel(parcel_id: str, db_path: str = None) -> Dict[str, Any]:
    storage = DiagnosisStorage(db_path)

    if not storage.is_ready():
        return {"status": "not_ready"}

    evaluation = storage.get_evaluation(parcel_id)
    if evaluation is None:
        return {"status": "not_found"}

    diagnosis = storage.get_diagnosis(parcel_id)

    return {
        "status": "ok",
        "parcel_id": parcel_id,
        "evaluation": evaluation,
        "diagnosis": diagnosis if diagnosis else {}
    }
