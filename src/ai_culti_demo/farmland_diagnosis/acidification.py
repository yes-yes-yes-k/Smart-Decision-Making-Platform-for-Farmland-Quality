import pandas as pd
import numpy as np
import sqlite3
from typing import Dict, Any, Optional
from .config import AMENDMENT_CONFIG, INDICATOR_NAME_MAP
from .storage import DiagnosisStorage


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
    """
    酸化程度分区
    """
    levels = ACIDIFICATION_LEVELS.get(region_code, ACIDIFICATION_LEVELS['default'])

    for level, bounds in levels.items():
        if bounds['min'] <= pH < bounds['max']:
            return {
                'level': level,
                'description': bounds['desc'],
                'pH': pH
            }

    return {
        'level': 'neutral',
        'description': '中性',
        'pH': pH
    }


def generate_amendment(pH: float, organic_matter: float, region_code: str) -> Dict[str, Any]:
    """
    生成酸化改良方案
    """
    acid_info = classify_acidification(pH, region_code)
    level = acid_info['level']

    if level in ['neutral', 'alkaline']:
        return {
            'acidification_level': acid_info['description'],
            'need_amendment': False,
            'reason': '土壤酸碱度适中，无需酸化改良',
            'amendment_plan': []
        }

    # AMENDMENT_CONFIG 结构为 {'lime_rate': {...}, 'measures': {'mild'/'moderate'/'severe': [...]}}
    # 注意 classify_acidification 返回的 level='slight' 对应 measures 中的 'mild' 键
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


def evaluate_acidification(db_path: str = None) -> Dict[str, Any]:
    """
    批量评估酸化改良方案
    """
    storage = DiagnosisStorage(db_path)

    conn = sqlite3.connect(storage.db_path)
    df = pd.read_sql('SELECT * FROM evaluation_results', conn)
    conn.close()

    if df.empty:
        return {"status": "error", "message": "No evaluation data found"}

    records = []
    for idx, row in df.iterrows():
        pH = row.get('PH', 6.5)
        organic_matter = row.get('YJ', 20)
        region_code = row.get('JY', 'HN')

        result = generate_amendment(pH, organic_matter, region_code)
        
        record = {
            'parcel_id': row['parcel_id'],
            'acidification_level': result['acidification_level'],
            'acidification_direction': '降低' if pH < 6.5 else '保持',
            'target_pH': 6.5 if pH < 6.5 else pH,
            'lime_demand': calculate_lime_demand(pH, organic_matter),
            'amendment_type': '石灰' if pH < 5.5 else '有机肥',
            'amendment_rate': calculate_amendment_rate(pH),
            'measures': result.get('amendment_plan', []),
            'expected_effect': f'预计pH可提升至{6.5 if pH < 6.5 else pH}'
        }

        records.append(record)

    storage.save_acidification(records)

    return {"status": "ok", "evaluated": len(records)}


def calculate_lime_demand(pH: float, organic_matter: float) -> float:
    """计算石灰需求量（kg/亩）"""
    if pH >= 6.5:
        return 0.0
    # 简单估算：每降低0.5个pH单位，需要约50-100kg/亩石灰
    deficit = 6.5 - pH
    base_demand = deficit * 100  # kg/亩
    # 有机质含量低时需要更多石灰
    if organic_matter < 15:
        base_demand *= 1.2
    return round(base_demand, 1)


def calculate_amendment_rate(pH: float) -> float:
    """计算改良剂施用率"""
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
    """
    查询单个地块的酸化改良方案
    """
    storage = DiagnosisStorage(db_path)

    if not storage.is_ready():
        return {"status": "not_ready"}

    result = storage.get_acidification(parcel_id)
    if result is None:
        return {"status": "not_found"}

    return {
        "status": "ok",
        "parcel_id": parcel_id,
        "acidification": result
    }
