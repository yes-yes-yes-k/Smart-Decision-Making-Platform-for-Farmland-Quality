import re
import pandas as pd
import numpy as np
import sqlite3
from typing import Dict, Any, Optional, Tuple, List
from .config import INDICATOR_DISPLAY_MAP, WEIGHTED_INDICATORS
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


def replace_abbr_in_text(text, abbr_map):
    """将障碍因素描述中的缩写替换为中文名，例如 SJD(中度酸化, 25.0%) -> pH(中度酸化, 25.0%)。

    多个因素以 '；' 连接。逻辑同 V2.0。
    """
    if pd.isna(text) or text == '':
        return text
    parts = str(text).split('；')
    new_parts = []
    for part in parts:
        match = re.match(r'^([A-Za-z0-9]+)\(', part)
        if match:
            abbr = match.group(1)
            display = abbr_map.get(abbr, abbr)
            new_part = display + part[len(abbr):]
        else:
            new_part = part
        new_parts.append(new_part)
    return '；'.join(new_parts)


def diagnosis_row(row, indicator_names, level_cols, degree_cols) -> Tuple[str, str, str]:
    """对单行执行障碍诊断，返回 (ZALX, ZYZAYS, CYZAYS) 字符串三元组。

    - level_cols / degree_cols 与 indicator_names 一一对应，统一用指标码前缀（ind+'ZADJ' / ind+'ZAD'），
     根治旧实现中文列名与 _OD 后缀大小写不匹配导致 set 交集恒空的生产 bug。
    - ZYZAYS/CYZAYS 内部已应用 replace_abbr_in_text（缩写→中文显示名）。
    - 空 CYZAYS 归一为 '无'（V2.0 行为）。
    """
    candidates = []
    for name, lcol, dcol in zip(indicator_names, level_cols, degree_cols):
        raw_level = row.get(lcol, np.nan)
        std_level = parse_obstacle_level(raw_level)
        degree = row.get(dcol, np.nan)
        if pd.isna(degree):
            degree = 0.0
        if std_level in ['重度', '中度']:
            candidates.append((name, raw_level, std_level, degree))

    if not candidates:
        # ZYZAYS 空，CYZAYS 归一为 '无'
        return '无明显障碍', '', '无'

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

    main_desc = '；'.join([format_factor(c) for c in main_factors])
    minor_desc = '；'.join([format_factor(c) for c in minor_factors])

    # 缩写 → 中文显示名
    zyzays = replace_abbr_in_text(main_desc, INDICATOR_DISPLAY_MAP)
    cyzays = replace_abbr_in_text(minor_desc, INDICATOR_DISPLAY_MAP)
    # 空 CYZAYS 归一为 '无'
    if pd.isna(cyzays) or str(cyzays).strip() == '':
        cyzays = '无'

    return obstacle_type, zyzays, cyzays


def diagnose(db_path: str = None) -> Dict[str, Any]:
    storage = DiagnosisStorage(db_path)

    conn = sqlite3.connect(storage.db_path)
    df = pd.read_sql('SELECT * FROM evaluation_results', conn)
    conn.close()

    if df.empty:
        return {"status": "error", "message": "No evaluation data found"}

    level_cols = [ind + 'ZADJ' for ind in WEIGHTED_INDICATORS]
    degree_cols = [ind + 'ZAD' for ind in WEIGHTED_INDICATORS]

    records: List[Dict[str, Any]] = []
    for idx, row in df.iterrows():
        zalx, zyzays, cyzays = diagnosis_row(row, WEIGHTED_INDICATORS, level_cols, degree_cols)
        record: Dict[str, Any] = {
            'parcel_id': row['parcel_id'],
            'ZALX': zalx,
            'ZYZAYS': zyzays,
            'CYZAYS': cyzays,
        }
        for ind in WEIGHTED_INDICATORS:
            record[ind + 'ZADJ'] = row.get(ind + 'ZADJ')
            record[ind + 'ZAD'] = row.get(ind + 'ZAD', 0.0)
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
        "diagnosis": diagnosis if diagnosis else {},
    }
