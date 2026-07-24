---
change: add-stability-risk-and-grade-evaluation
design-doc: docs/superpowers/specs/2026-07-24-farmland-model3-integration-design.md
base-ref: 277481d045527f56190120d5a355905ea2a63342
---

# 模型3（耕地质量主要问题精准识别与酸化改良）集成实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将模型3（calculator.py + calculator2.py）整合为项目模块化包，替换占位 MODEL_SPECS，实现批量评价、在线查询和综合诊断能力。

**Architecture:** 采用模块化集成方案，将模型3代码重构为独立的 Python 包（farmland_diagnosis、farmland_acidification、diagnosis_config、diagnosis_storage），通过 CoreEngine Adapter 接入现有架构，使用 SQLite 持久化评价结果，新增 question_type=5 路由到障碍诊断 Agent。

**Tech Stack:** Python 3.12, SQLite, pandas, numpy

## Global Constraints

- 模型3障碍诊断替换 `obstacle-factor-identification` 占位模型
- 模型3酸化改良替换 `acidification-governance` 占位模型
- 新增 question_type=5 用于障碍诊断路由
- 批量评价结果持久化为 SQLite 数据库
- 改良方案生成采用混合方式（基于障碍等级 + 指标数值计算）
- Agent 层实现模型3与模型1的综合诊断

---

## 文件结构

```
src/ai_culti_demo/
├── farmland_diagnosis/
│   ├── __init__.py
│   ├── config.py        # 配置管理（区域映射、隶属度系数、权重）
│   ├── storage.py       # SQLite 数据持久化
│   ├── evaluation.py    # 批量评价逻辑（隶属度、综合权重、等级划分）
│   └── diagnosis.py     # 障碍诊断逻辑（障碍类型、主要/次要因素）
├── farmland_acidification/
│   ├── __init__.py
│   └── acidification.py # 酸化改良逻辑（酸化因子提取、程度判定、改良方案）
└── thematic_models.py   # 更新 MODEL_SPECS

framework/
├── agents/
│   ├── nodes.py                 # 新增 QUESTION_TYPE_5_KEYWORDS
│   ├── specialized/
│   │   └── obstacle_diagnosis_agent.py  # 新增 ObstacleDiagnosisAgent
│   └── manager.py               # 扩展综合诊断逻辑
└── core_engine/
    └── adapter.py               # 扩展 run_thematic_model() 调度

tests/
├── test_farmland_diagnosis.py
└── test_farmland_acidification.py

data/
└── farmland_diagnosis/
    ├── test.csv                 # 测试数据
    └── farmland_diagnosis.db    # SQLite 数据库（运行时生成）
```

---

### Task 1: 创建诊断配置模块

**Files:**
- Create: `src/ai_culti_demo/farmland_diagnosis/config.py`
- Create: `src/ai_culti_demo/farmland_diagnosis/__init__.py`

**Interfaces:**
- Consumes: 无
- Produces: `REGION_MAP`, `SECONDARY_REGION_MAP`, `COLUMN_RENAME`, `TEXT_VALUE_MAPS`, `COEFFICIENTS`, `WEIGHTS`, `INDICATOR_NAME_MAP`, `calc_obstacle_level()`

- [ ] **Step 1: 编写配置模块代码**

```python
# src/ai_culti_demo/farmland_diagnosis/config.py
import numpy as np
import pandas as pd

REGION_MAP = {
    '华南区': 'HN',
    '长江中下游区': 'CJ',
}

SECONDARY_REGION_MAP = {
    '闽南粤中农林水产区': 'MNY',
    '粤西桂南农林区': 'YXG',
    '琼雷及南海诸岛农林区': 'QN',
    '南岭丘陵山地林农区': 'NL',
}

COLUMN_RENAME = {
    '一级农业区': 'JY',
    '二级农业区': 'EJ',
    'pH': 'PH',
    '有机质': 'YJ',
    '有效磷': 'YXP',
    '速效钾': 'SXK',
    '容重': 'RZ',
    '耕层质地': 'GZ',
    '灌溉能力': 'GG',
    '排水能力': 'PS',
    '地形部位': 'DX',
    '质地构型': 'ZD',
    '有效土层': 'YXT',
    '耕层厚度': 'GCH'
}

TEXT_VALUE_MAPS = {
    'DX': {
        '山间盆地': 'MB', '宽谷盆地': 'WVB', '平原低阶': 'PLT', '平原中阶': 'PMG',
        '平原高阶': 'PUG', '丘陵上部': 'UHR', '丘陵中部': 'MPH', '丘陵下部': 'LHR',
        '山地坡上': 'MSU', '山地坡中': 'MSM', '山地坡下': 'MSL',
    },
    'GZ': {
        '壤土':'RT', '粉(砂)质壤土':'FRT', '粉(砂)质黏壤土':'FNRT', '砂质黏壤土':'SNRT', 
        '黏壤土':'NRT', '砂质壤土':'SRT', '壤质黏土':'RNT', '粉(砂)质黏土':'FNT', 
        '砂质黏土':'SNT', '黏土':'NT', '重黏土':'ZNT', '砂土及壤质砂土':'SRST' 
    },
    'ZD': {
        '薄层型': 'TL', '松散型': 'Lt', '紧实型': 'Ct', '夹层型': 'IL',
        '上紧下松型': 'TCBL', '上松下紧型': 'TLBC', '海绵型': 'St',
    },
    'GG': {
        '充分满足': 'FS', '满足': 'S', '基本满足': 'BS', '不满足': 'US',
    },
    'PS': {
        '充分满足': 'CM', '满足': 'M', '基本满足': 'JM', '不满足': 'BM',
    },
}

COEFFICIENTS = {
    'HN': {
        'PH':  {'a': 0.256941, 'c': 6.7, 'L':4.0, 'U':9.5},
        'YJ':  {'a': 0.002163, 'c': 38, 'L':6.0, 'U':38.0},
        'YXP': {'a': 0.0038, 'c': 40, 'L':5.0, 'U':40.0},
        'SXK': {'a': 0.000068, 'c': 205, 'L':30, 'U':205},
        'RZ':  {'a': 2.786523, 'c': 1.35, 'L':0.9, 'U':2.1},
        'YXT': {'a': 0.00023, 'c': 100, 'L': 10, 'U': 100},
        'GCH': {'a': 0.019247, 'c': 20.2, 'L': 5, 'U': 20.2},
        'GZ':  {'RT': 1, 'FRT': 0.95, 'FNRT': 0.9, 'SNRT': 0.85, 'NRT': 0.8, 'SRT': 0.75, 'RNT': 0.7, 'FNT': 0.65,  'SNT': 0.6, 'NT': 0.55, 'ZNT': 0.5, 'SRST': 0.4},
        'GG':  {'FS': 1,'S': 0.8,'BS': 0.6,'US':0.3},
        'PS':  {'CM': 1,'M': 0.8,'JM': 0.6,'BM':0.3},
        'DX':  {'MB':0.7, 'WVB':0.9, 'PLT':1, 'PMG':0.9,'PUG':0.8, 'UHR':0.4, 'MPH':0.5, 'LHR':0.6, 'MSU':0.2, 'MSM':0.3, 'MSL':0.5},
        'ZD':  {'TL':0.3, 'Lt':0.2, 'Ct':0.5, 'IL':0.7,'TCBL':0.4, 'TLBC':1, 'St':0.8},
    },
    'CJ': {
        'PH':  {'a': 0.221129, 'c': 6.811204, 'L':3.0, 'U':10},
        'YJ':  {'a': 0.0018842, 'c': 33.656446, 'L':0, 'U':33.7},
        'YXP': {'a': 0.002025, 'c': 33.346824, 'L':4.0, 'U':33.3},
        'SXK': {'a': 0.000081, 'c': 181.622535, 'L':0, 'U':182},
        'RZ':  {'a': 2.236726, 'c': 1.211674, 'L':0.5, 'U':2.21},
        'YXT': {'a': 0.000205, 'c': 99.092342, 'L':10, 'U':99},
        'GCH': {'a': 0.008008, 'c': 23.333126, 'L': 0, 'U': 23},
        'GZ':  {'RT': 1, 'FRT': 0.95, 'FNRT': 0.85, 'SNRT': 0.75, 'NRT': 0.9, 'SRT': 0.65, 'RNT': 0.65, 'FNT': 0.8,  'SNT': 0.6, 'NT': 0.62, 'ZNT': 0.55, 'SRST': 0.5},
        'GG':  {'FS': 1,'S': 0.8,'BS': 0.6,'US':0.3},
        'PS':  {'CM': 1,'M': 0.8,'JM': 0.6,'BM':0.3},
        'DX':  {'MB':0.8, 'WVB':0.95, 'PLT':1, 'PMG':0.95,'PUG':0.9, 'UHR':0.6, 'MPH':0.7, 'LHR':0.8, 'MSU':0.3, 'MSM':0.45, 'MSL':0.68},
        'ZD':  {'TL':0.55, 'Lt':0.3, 'Ct':0.75, 'IL':0.85,'TCBL':0.4, 'TLBC':1, 'St':0.95},
    },
}

WEIGHTS = {
    'MNY': {
        'GG': 0.1253, 'DX': 0.124, 'PS': 0.1057, 'YJ': 0.0958,
        'GZ': 0.0827, 'ZD': 0.079, 'SXK': 0.0736, 'YXT': 0.0716,
        'PH': 0.0668, 'RZ': 0.0596, 'YXP': 0.0574, 'GCH':0.0585
    },
    'YXG': {
        'GG': 0.1249, 'DX': 0.1233, 'PS': 0.1003, 'YJ': 0.1,
        'GZ': 0.0815, 'ZD': 0.0737, 'SXK': 0.0791, 'YXT': 0.0726,
        'PH': 0.0678, 'RZ': 0.0576, 'YXP': 0.0602, 'GCH':0.059
    },
    'NL': {
        'GG': 0.1369, 'DX': 0.127, 'PS': 0.107, 'YJ': 0.1046,
        'GZ': 0.0905, 'ZD': 0.0731, 'SXK': 0.0681, 'YXT': 0.05779,
        'PH': 0.0704, 'RZ': 0.0494, 'YXP': 0.0577, 'GCH':0.0594
    },
    'QN': {
        'GG': 0.1266, 'DX': 0.1025, 'PS': 0.1154, 'YJ': 0.1039,
        'GZ': 0.08, 'ZD': 0.0814, 'SXK': 0.0775, 'YXT': 0.0604,
        'PH': 0.0726, 'RZ': 0.0631, 'YXP': 0.0607, 'GCH':0.0499
    }
}

INDICATOR_NAME_MAP = {
    'PH': 'pH',
    'YJ': '有机质',
    'YXP': '有效磷',
    'SXK': '速效钾',
    'RZ': '容重',
    'YXT': '有效土层',
    'GZ': '耕层质地',
    'GG': '灌溉能力',
    'PS': '排水能力',
    'DX': '地形部位',
    'ZD': '质地构型',
    'GCH': '耕层厚度',
}

AMENDMENT_CONFIG = {
    'lime_rate': {'mild': 50, 'moderate': 100, 'severe': 150},
    'measures': {
        'mild': ['常规监测', '合理施肥'],
        'moderate': ['施用石灰', '有机肥培肥', '轮作调整'],
        'severe': ['大量施用石灰', '深翻改土', '长期培肥']
    }
}

def calc_obstacle_level(row, indicators):
    levels = {}
    for ind in indicators:
        if ind == 'PH':
            val = row.get('PH', np.nan)
            if pd.isna(val): levels['PH'] = np.nan
            elif val <= 3 or val > 10: levels['PH'] = '重度障碍'
            elif (val > 3 and val <= 4.5) or (val > 9.5 and val <= 10): levels['PH'] = '重度障碍'
            elif (val > 4.5 and val <= 5.5) or (val > 8.5 and val <= 9.5): levels['PH'] = '中度障碍'
            elif (val > 5.5 and val < 6.5) or (val > 7.5 and val <= 8.5): levels['PH'] = '轻度障碍'
            elif 6.5 <= val <= 7.5: levels['PH'] = '无障碍'
            else: levels['PH'] = np.nan
        elif ind == 'YJ':
            val = row.get('YJ', np.nan)
            if pd.isna(val): levels['YJ'] = np.nan
            elif val <= 10: levels['YJ'] = '重度障碍'
            elif val <= 20: levels['YJ'] = '中度障碍'
            elif val <= 25: levels['YJ'] = '轻度障碍'
            else: levels['YJ'] = '无障碍'
        elif ind == 'YXP':
            val = row.get('YXP', np.nan)
            if pd.isna(val): levels['YXP'] = np.nan
            elif val <= 10: levels['YXP'] = '重度障碍'
            elif val <= 20: levels['YXP'] = '中度障碍'
            elif val <= 35: levels['YXP'] = '轻度障碍'
            else: levels['YXP'] = '无障碍'
        elif ind == 'SXK':
            val = row.get('SXK', np.nan)
            if pd.isna(val): levels['SXK'] = np.nan
            elif val <= 50: levels['SXK'] = '重度障碍'
            elif val <= 100: levels['SXK'] = '中度障碍'
            elif val <= 150: levels['SXK'] = '轻度障碍'
            else: levels['SXK'] = '无障碍'
        elif ind == 'RZ':
            val = row.get('RZ', np.nan)
            if pd.isna(val): levels['RZ'] = np.nan
            elif val <= 0.9: levels['RZ'] = '重度障碍'
            elif 0.9 <= val < 0.95: levels['RZ'] = '中度障碍'
            elif 0.95 <= val < 1: levels['RZ'] = '轻度障碍'
            elif 1 <= val <= 1.2: levels['RZ'] = '无障碍'
            elif 1.2 < val <= 1.3: levels['RZ'] = '轻度障碍'
            elif 1.3 < val <= 1.4: levels['RZ'] = '中度障碍'
            elif val > 1.4: levels['RZ'] = '重度障碍'
        elif ind == 'GCH':
            val = row.get('GCH', np.nan)
            if pd.isna(val): levels['GCH'] = np.nan
            elif val <= 10: levels['GCH'] = '重度障碍'
            elif val <= 15: levels['GCH'] = '中度障碍'
            elif val < 20: levels['GCH'] = '轻度障碍'
            else: levels['GCH'] = '无障碍'
        elif ind == 'YXT':
            val = row.get('YXT', np.nan)
            if pd.isna(val): levels['YXT'] = np.nan
            elif val < 60: levels['YXT'] = '重度障碍'
            elif 60 <= val < 80: levels['YXT'] = '中度障碍'
            elif 80 <= val < 100: levels['YXT'] = '轻度障碍'
            else: levels['YXT'] = '无障碍'
        elif ind in ['GG', 'PS']:
            code = row.get(ind, np.nan)
            if pd.isna(code): levels[ind] = np.nan
            else:
                if ind == 'GG':
                    m = {'US': '重度障碍', 'BS': '中度障碍', 'S': '轻度障碍', 'FS': '无障碍'}
                else:
                    m = {'BM': '重度障碍', 'JM': '中度障碍', 'M': '轻度障碍', 'CM': '无障碍'}
                levels[ind] = m.get(code, np.nan)
        elif ind == 'ZD':
            code = row.get('ZD', np.nan)
            if pd.isna(code): levels['ZD'] = np.nan
            elif code in ['TCBL', 'TL', 'Lt']: levels['ZD'] = '重度障碍'
            elif code == 'Ct': levels['ZD'] = '中度障碍'
            elif code == 'IL': levels['ZD'] = '轻度障碍'
            elif code in ['TLBC', 'St']: levels['ZD'] = '无障碍'
            else: levels['ZD'] = np.nan
        elif ind == 'GZ':
            ld_val = row.get('GZ_LD', np.nan)
            if pd.isna(ld_val): levels['GZ'] = np.nan
            elif 0.4 <= ld_val < 0.6: levels['GZ'] = '重度障碍'
            elif 0.6 <= ld_val <= 0.7: levels['GZ'] = '中度障碍'
            elif 0.75 <= ld_val <= 0.85: levels['GZ'] = '轻度障碍'
            elif 0.9 <= ld_val <= 1: levels['GZ'] = '无障碍'
            else: levels['GZ'] = np.nan
        elif ind == 'DX':
            ld_val = row.get('DX_LD', np.nan)
            if pd.isna(ld_val): levels['DX'] = np.nan
            elif 0.2 <= ld_val < 0.5: levels['DX'] = '重度障碍'
            elif 0.5 <= ld_val <= 0.68: levels['DX'] = '中度障碍'
            elif 0.7 <= ld_val <= 0.8: levels['DX'] = '轻度障碍'
            elif 0.9 <= ld_val <= 1: levels['DX'] = '无障碍'
            else: levels['DX'] = np.nan
        else:
            levels[ind] = np.nan
    return levels
```

- [ ] **Step 2: 编写 __init__.py**

```python
# src/ai_culti_demo/farmland_diagnosis/__init__.py
from .config import (
    REGION_MAP, SECONDARY_REGION_MAP, COLUMN_RENAME, TEXT_VALUE_MAPS,
    COEFFICIENTS, WEIGHTS, INDICATOR_NAME_MAP, AMENDMENT_CONFIG,
    calc_obstacle_level
)
from .storage import DiagnosisStorage
from .evaluation import bulk_evaluate, evaluate_single
from .diagnosis import diagnose, query_parcel

__all__ = [
    'REGION_MAP', 'SECONDARY_REGION_MAP', 'COLUMN_RENAME', 'TEXT_VALUE_MAPS',
    'COEFFICIENTS', 'WEIGHTS', 'INDICATOR_NAME_MAP', 'AMENDMENT_CONFIG',
    'calc_obstacle_level', 'DiagnosisStorage',
    'bulk_evaluate', 'evaluate_single', 'diagnose', 'query_parcel'
]
```

- [ ] **Step 3: 编写单元测试**

```python
# tests/test_farmland_diagnosis.py
import pytest
from src.ai_culti_demo.farmland_diagnosis.config import (
    REGION_MAP, COEFFICIENTS, WEIGHTS, calc_obstacle_level
)

def test_region_map():
    assert REGION_MAP['华南区'] == 'HN'
    assert REGION_MAP['长江中下游区'] == 'CJ'

def test_coefficients_exists():
    assert 'HN' in COEFFICIENTS
    assert 'CJ' in COEFFICIENTS
    assert 'PH' in COEFFICIENTS['HN']

def test_weights_exists():
    assert 'MNY' in WEIGHTS
    assert 'PH' in WEIGHTS['MNY']

def test_calc_obstacle_level_ph():
    row = {'PH': 5.0}
    result = calc_obstacle_level(row, ['PH'])
    assert result['PH'] == '中度障碍'

def test_calc_obstacle_level_organic():
    row = {'YJ': 15}
    result = calc_obstacle_level(row, ['YJ'])
    assert result['YJ'] == '中度障碍'
```

- [ ] **Step 4: 运行测试**

Run: `cd d:\17417\Documents\agent_culti_demo; python -m pytest tests/test_farmland_diagnosis.py::test_region_map -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/ai_culti_demo/farmland_diagnosis/ tests/test_farmland_diagnosis.py
git commit -m "feat: add farmland_diagnosis config module"
```

---

### Task 2: 创建 SQLite 数据持久化模块

**Files:**
- Create: `src/ai_culti_demo/farmland_diagnosis/storage.py`

**Interfaces:**
- Consumes: 无
- Produces: `DiagnosisStorage` 类

- [ ] **Step 1: 编写存储模块代码**

```python
# src/ai_culti_demo/farmland_diagnosis/storage.py
import sqlite3
import json
import os
from datetime import datetime
from typing import Optional, List, Dict, Any

class DiagnosisStorage:
    def __init__(self, db_path: str = None):
        if db_path is None:
            db_dir = os.path.join(os.path.dirname(__file__), '../../data/farmland_diagnosis')
            os.makedirs(db_dir, exist_ok=True)
            db_path = os.path.join(db_dir, 'farmland_diagnosis.db')
        self.db_path = db_path
        self._ensure_connection()
    
    def _ensure_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute('PRAGMA foreign_keys = ON')
        conn.close()
    
    def create_tables(self) -> None:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS evaluation_results (
                parcel_id TEXT PRIMARY KEY,
                region_code TEXT,
                secondary_region_code TEXT,
                PH REAL, YJ REAL, YXP REAL, SXK REAL, RZ REAL,
                GZ TEXT, GG TEXT, PS TEXT, DX TEXT, ZD TEXT,
                YXT REAL, GCH REAL,
                PH_LD REAL, YJ_LD REAL, YXP_LD REAL, SXK_LD REAL, RZ_LD REAL,
                GZ_LD REAL, GG_LD REAL, PS_LD REAL, DX_LD REAL, ZD_LD REAL,
                YXT_LD REAL, GCH_LD REAL,
                composite_weight REAL,
                grade TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS diagnosis_results (
                parcel_id TEXT PRIMARY KEY REFERENCES evaluation_results(parcel_id),
                obstacle_type TEXT,
                main_factors TEXT,
                secondary_factors TEXT,
                PH_obstacle_level TEXT, YJ_obstacle_level TEXT,
                YXP_obstacle_level TEXT, SXK_obstacle_level TEXT,
                RZ_obstacle_level TEXT, GZ_obstacle_level TEXT,
                GG_obstacle_level TEXT, PS_obstacle_level TEXT,
                DX_obstacle_level TEXT, ZD_obstacle_level TEXT,
                YXT_obstacle_level TEXT, GCH_obstacle_level TEXT,
                PH_obstacle_degree REAL, YJ_obstacle_degree REAL,
                YXP_obstacle_degree REAL, SXK_obstacle_degree REAL,
                RZ_obstacle_degree REAL, GZ_obstacle_degree REAL,
                GG_obstacle_degree REAL, PS_obstacle_degree REAL,
                DX_obstacle_degree REAL, ZD_obstacle_degree REAL,
                YXT_obstacle_degree REAL, GCH_obstacle_degree REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS acidification_results (
                parcel_id TEXT PRIMARY KEY REFERENCES evaluation_results(parcel_id),
                acidification_level TEXT,
                acidification_direction TEXT,
                target_pH REAL,
                lime_demand REAL,
                amendment_type TEXT,
                amendment_rate REAL,
                measures TEXT,
                expected_effect TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def save_evaluation(self, records: List[Dict[str, Any]]) -> int:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        for record in records:
            cursor.execute('''
                INSERT OR REPLACE INTO evaluation_results
                (parcel_id, region_code, secondary_region_code,
                 PH, YJ, YXP, SXK, RZ, GZ, GG, PS, DX, ZD, YXT, GCH,
                 PH_LD, YJ_LD, YXP_LD, SXK_LD, RZ_LD,
                 GZ_LD, GG_LD, PS_LD, DX_LD, ZD_LD, YXT_LD, GCH_LD,
                 composite_weight, grade, updated_at)
                VALUES (?, ?, ?,
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?, ?, ?,
                        ?, ?, ?)
            ''', (
                record['parcel_id'], record.get('region_code'), record.get('secondary_region_code'),
                record.get('PH'), record.get('YJ'), record.get('YXP'), record.get('SXK'), record.get('RZ'),
                record.get('GZ'), record.get('GG'), record.get('PS'), record.get('DX'), record.get('ZD'),
                record.get('YXT'), record.get('GCH'),
                record.get('PH_LD'), record.get('YJ_LD'), record.get('YXP_LD'), record.get('SXK_LD'), record.get('RZ_LD'),
                record.get('GZ_LD'), record.get('GG_LD'), record.get('PS_LD'), record.get('DX_LD'), record.get('ZD_LD'),
                record.get('YXT_LD'), record.get('GCH_LD'),
                record.get('composite_weight'), record.get('grade'), datetime.now()
            ))
        
        conn.commit()
        count = cursor.rowcount
        conn.close()
        return count
    
    def save_diagnosis(self, records: List[Dict[str, Any]]) -> int:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        for record in records:
            cursor.execute('''
                INSERT OR REPLACE INTO diagnosis_results
                (parcel_id, obstacle_type, main_factors, secondary_factors,
                 PH_obstacle_level, YJ_obstacle_level, YXP_obstacle_level, SXK_obstacle_level,
                 RZ_obstacle_level, GZ_obstacle_level, GG_obstacle_level, PS_obstacle_level,
                 DX_obstacle_level, ZD_obstacle_level, YXT_obstacle_level, GCH_obstacle_level,
                 PH_obstacle_degree, YJ_obstacle_degree, YXP_obstacle_degree, SXK_obstacle_degree,
                 RZ_obstacle_degree, GZ_obstacle_degree, GG_obstacle_degree, PS_obstacle_degree,
                 DX_obstacle_degree, ZD_obstacle_degree, YXT_obstacle_degree, GCH_obstacle_degree)
                VALUES (?, ?, ?, ?,
                        ?, ?, ?, ?,
                        ?, ?, ?, ?,
                        ?, ?, ?, ?,
                        ?, ?, ?, ?,
                        ?, ?, ?, ?,
                        ?, ?, ?, ?)
            ''', (
                record['parcel_id'], record.get('obstacle_type'),
                json.dumps(record.get('main_factors', [])),
                json.dumps(record.get('secondary_factors', [])),
                record.get('PH_obstacle_level'), record.get('YJ_obstacle_level'),
                record.get('YXP_obstacle_level'), record.get('SXK_obstacle_level'),
                record.get('RZ_obstacle_level'), record.get('GZ_obstacle_level'),
                record.get('GG_obstacle_level'), record.get('PS_obstacle_level'),
                record.get('DX_obstacle_level'), record.get('ZD_obstacle_level'),
                record.get('YXT_obstacle_level'), record.get('GCH_obstacle_level'),
                record.get('PH_obstacle_degree'), record.get('YJ_obstacle_degree'),
                record.get('YXP_obstacle_degree'), record.get('SXK_obstacle_degree'),
                record.get('RZ_obstacle_degree'), record.get('GZ_obstacle_degree'),
                record.get('GG_obstacle_degree'), record.get('PS_obstacle_degree'),
                record.get('DX_obstacle_degree'), record.get('ZD_obstacle_degree'),
                record.get('YXT_obstacle_degree'), record.get('GCH_obstacle_degree')
            ))
        
        conn.commit()
        count = cursor.rowcount
        conn.close()
        return count
    
    def save_acidification(self, records: List[Dict[str, Any]]) -> int:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        for record in records:
            cursor.execute('''
                INSERT OR REPLACE INTO acidification_results
                (parcel_id, acidification_level, acidification_direction,
                 target_pH, lime_demand, amendment_type, amendment_rate, measures, expected_effect)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                record['parcel_id'], record.get('acidification_level'), record.get('acidification_direction'),
                record.get('target_pH'), record.get('lime_demand'), record.get('amendment_type'),
                record.get('amendment_rate'), json.dumps(record.get('measures', [])), record.get('expected_effect')
            ))
        
        conn.commit()
        count = cursor.rowcount
        conn.close()
        return count
    
    def get_evaluation(self, parcel_id: str) -> Optional[Dict[str, Any]]:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM evaluation_results WHERE parcel_id = ?', (parcel_id,))
        row = cursor.fetchone()
        conn.close()
        
        if row is None:
            return None
        
        columns = [desc[0] for desc in cursor.description]
        return dict(zip(columns, row))
    
    def get_diagnosis(self, parcel_id: str) -> Optional[Dict[str, Any]]:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM diagnosis_results WHERE parcel_id = ?', (parcel_id,))
        row = cursor.fetchone()
        conn.close()
        
        if row is None:
            return None
        
        columns = [desc[0] for desc in cursor.description]
        result = dict(zip(columns, row))
        result['main_factors'] = json.loads(result.get('main_factors', '[]'))
        result['secondary_factors'] = json.loads(result.get('secondary_factors', '[]'))
        return result
    
    def get_acidification(self, parcel_id: str) -> Optional[Dict[str, Any]]:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM acidification_results WHERE parcel_id = ?', (parcel_id,))
        row = cursor.fetchone()
        conn.close()
        
        if row is None:
            return None
        
        columns = [desc[0] for desc in cursor.description]
        result = dict(zip(columns, row))
        result['measures'] = json.loads(result.get('measures', '[]'))
        return result
    
    def is_ready(self) -> bool:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='evaluation_results'")
        eval_exists = cursor.fetchone() is not None
        
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='diagnosis_results'")
        diag_exists = cursor.fetchone() is not None
        
        if eval_exists:
            cursor.execute('SELECT COUNT(*) FROM evaluation_results')
            eval_count = cursor.fetchone()[0]
        else:
            eval_count = 0
        
        if diag_exists:
            cursor.execute('SELECT COUNT(*) FROM diagnosis_results')
            diag_count = cursor.fetchone()[0]
        else:
            diag_count = 0
        
        conn.close()
        return eval_exists and diag_exists and eval_count > 0 and diag_count > 0
```

- [ ] **Step 2: 编写单元测试**

```python
# tests/test_farmland_diagnosis.py (继续追加)
from src.ai_culti_demo.farmland_diagnosis.storage import DiagnosisStorage
import tempfile
import os

def test_storage_create_tables():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, 'test.db')
        storage = DiagnosisStorage(db_path)
        storage.create_tables()
        
        conn = storage._ensure_connection()
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        
        assert 'evaluation_results' in tables
        assert 'diagnosis_results' in tables
        assert 'acidification_results' in tables
        conn.close()

def test_storage_save_and_get_evaluation():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, 'test.db')
        storage = DiagnosisStorage(db_path)
        storage.create_tables()
        
        record = {
            'parcel_id': 'test-001',
            'region_code': 'HN',
            'secondary_region_code': 'MNY',
            'PH': 6.5, 'YJ': 25, 'YXP': 30, 'SXK': 150, 'RZ': 1.2,
            'GZ': 'RT', 'GG': 'FS', 'PS': 'CM', 'DX': 'PLT', 'ZD': 'TLBC',
            'YXT': 100, 'GCH': 20,
            'PH_LD': 1.0, 'YJ_LD': 1.0, 'YXP_LD': 0.8, 'SXK_LD': 0.8, 'RZ_LD': 1.0,
            'GZ_LD': 1.0, 'GG_LD': 1.0, 'PS_LD': 1.0, 'DX_LD': 1.0, 'ZD_LD': 1.0,
            'YXT_LD': 1.0, 'GCH_LD': 1.0,
            'composite_weight': 0.85,
            'grade': '3'
        }
        
        count = storage.save_evaluation([record])
        assert count == 1
        
        result = storage.get_evaluation('test-001')
        assert result is not None
        assert result['parcel_id'] == 'test-001'
        assert result['PH'] == 6.5

def test_storage_is_ready():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, 'test.db')
        storage = DiagnosisStorage(db_path)
        assert not storage.is_ready()
        
        storage.create_tables()
        assert not storage.is_ready()
        
        record = {
            'parcel_id': 'test-001', 'region_code': 'HN', 'secondary_region_code': 'MNY',
            'PH': 6.5, 'YJ': 25, 'YXP': 30, 'SXK': 150, 'RZ': 1.2,
            'GZ': 'RT', 'GG': 'FS', 'PS': 'CM', 'DX': 'PLT', 'ZD': 'TLBC',
            'YXT': 100, 'GCH': 20,
            'PH_LD': 1.0, 'YJ_LD': 1.0, 'YXP_LD': 0.8, 'SXK_LD': 0.8, 'RZ_LD': 1.0,
            'GZ_LD': 1.0, 'GG_LD': 1.0, 'PS_LD': 1.0, 'DX_LD': 1.0, 'ZD_LD': 1.0,
            'YXT_LD': 1.0, 'GCH_LD': 1.0,
            'composite_weight': 0.85, 'grade': '3'
        }
        storage.save_evaluation([record])
        
        diag_record = {
            'parcel_id': 'test-001', 'obstacle_type': '无明显障碍',
            'main_factors': [], 'secondary_factors': []
        }
        storage.save_diagnosis([diag_record])
        
        assert storage.is_ready()
```

- [ ] **Step 3: 运行测试**

Run: `cd d:\17417\Documents\agent_culti_demo; python -m pytest tests/test_farmland_diagnosis.py::test_storage_create_tables -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add src/ai_culti_demo/farmland_diagnosis/storage.py
git commit -m "feat: add DiagnosisStorage SQLite persistence"
```

---

### Task 3: 创建批量评价模块

**Files:**
- Create: `src/ai_culti_demo/farmland_diagnosis/evaluation.py`

**Interfaces:**
- Consumes: `DiagnosisStorage`, `REGION_MAP`, `COLUMN_RENAME`, `TEXT_VALUE_MAPS`, `COEFFICIENTS`, `WEIGHTS`, `INDICATOR_NAME_MAP`, `calc_obstacle_level`
- Produces: `bulk_evaluate()`, `evaluate_single()`

- [ ] **Step 1: 编写评价模块代码**

```python
# src/ai_culti_demo/farmland_diagnosis/evaluation.py
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
```

- [ ] **Step 2: 编写测试数据**

```python
# 在 tests/ 目录创建测试 CSV
# tests/test_data.csv
一级农业区,二级农业区,pH,有机质,有效磷,速效钾,容重,耕层质地,灌溉能力,排水能力,地形部位,质地构型,有效土层,耕层厚度
华南区,闽南粤中农林水产区,6.5,25,30,150,1.2,壤土,充分满足,充分满足,平原低阶,上松下紧型,100,20
华南区,粤西桂南农林区,5.0,18,15,80,1.5,黏土,基本满足,基本满足,丘陵中部,紧实型,70,15
```

- [ ] **Step 3: 编写单元测试**

```python
# tests/test_farmland_diagnosis.py (继续追加)
from src.ai_culti_demo.farmland_diagnosis.evaluation import bulk_evaluate, evaluate_single
import pandas as pd

def test_bulk_evaluate():
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_path = os.path.join(tmpdir, 'test.csv')
        with open(csv_path, 'w', encoding='utf-8') as f:
            f.write('''一级农业区,二级农业区,pH,有机质,有效磷,速效钾,容重,耕层质地,灌溉能力,排水能力,地形部位,质地构型,有效土层,耕层厚度
华南区,闽南粤中农林水产区,6.5,25,30,150,1.2,壤土,充分满足,充分满足,平原低阶,上松下紧型,100,20
''')
        
        db_path = os.path.join(tmpdir, 'test.db')
        result = bulk_evaluate(csv_path, db_path)
        
        assert result['status'] == 'ok'
        assert result['processed'] == 1
        
        storage = DiagnosisStorage(db_path)
        eval_result = storage.get_evaluation('0')
        assert eval_result is not None
        assert eval_result['PH'] == 6.5
        assert eval_result['grade'] == '3'

def test_bulk_evaluate_missing_columns():
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_path = os.path.join(tmpdir, 'test.csv')
        with open(csv_path, 'w', encoding='utf-8') as f:
            f.write('pH,有机质\n6.5,25\n')
        
        result = bulk_evaluate(csv_path)
        assert result['status'] == 'error'
        assert 'Missing columns' in result['message']

def test_evaluate_single():
    row = pd.Series({
        'JY': 'HN', 'EJ': 'MNY',
        'PH': 6.5, 'YJ': 25, 'YXP': 30, 'SXK': 150, 'RZ': 1.2,
        'GZ': 'RT', 'GG': 'FS', 'PS': 'CM', 'DX': 'PLT', 'ZD': 'TLBC',
        'YXT': 100, 'GCH': 20
    })
    
    result = evaluate_single(row, 'HN', 'MNY')
    
    assert 'PH_LD' in result
    assert 'composite_weight' in result
    assert 'grade' in result
    assert result['grade'] == '3'
```

- [ ] **Step 4: 运行测试**

Run: `cd d:\17417\Documents\agent_culti_demo; python -m pytest tests/test_farmland_diagnosis.py::test_bulk_evaluate -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/ai_culti_demo/farmland_diagnosis/evaluation.py tests/test_data.csv
git commit -m "feat: add bulk evaluation module"
```

---

### Task 4: 创建障碍诊断模块

**Files:**
- Create: `src/ai_culti_demo/farmland_diagnosis/diagnosis.py`

**Interfaces:**
- Consumes: `DiagnosisStorage`, `INDICATOR_NAME_MAP`
- Produces: `diagnose()`, `query_parcel()`

- [ ] **Step 1: 编写诊断模块代码**

```python
# src/ai_culti_demo/farmland_diagnosis/diagnosis.py
import pandas as pd
import numpy as np
import re
from typing import Dict, Any, Optional
from .config import INDICATOR_NAME_MAP
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
    
    conn = storage._ensure_connection()
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
```

- [ ] **Step 2: 编写单元测试**

```python
# tests/test_farmland_diagnosis.py (继续追加)
from src.ai_culti_demo.farmland_diagnosis.diagnosis import diagnose, query_parcel, diagnosis_row
import pandas as pd

def test_diagnosis_row_no_obstacle():
    row = pd.Series({
        'pH障碍等级': '无障碍', '有机质障碍等级': '丰富',
        'pH_OD': 0.05, '有机质_OD': 0.05
    })
    
    result = diagnosis_row(row)
    assert result['obstacle_type'] == '无明显障碍'
    assert result['main_factors'] == []
    assert result['secondary_factors'] == []

def test_diagnosis_row_single_obstacle():
    row = pd.Series({
        'pH障碍等级': '中度障碍', '有机质障碍等级': '无障碍',
        'pH_OD': 0.25, '有机质_OD': 0.05
    })
    
    result = diagnosis_row(row)
    assert result['obstacle_type'] == '单一障碍'
    assert len(result['main_factors']) == 1

def test_diagnose():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, 'test.db')
        storage = DiagnosisStorage(db_path)
        storage.create_tables()
        
        record = {
            'parcel_id': 'test-001', 'region_code': 'HN', 'secondary_region_code': 'MNY',
            'PH': 5.0, 'YJ': 25, 'YXP': 30, 'SXK': 150, 'RZ': 1.2,
            'GZ': 'RT', 'GG': 'FS', 'PS': 'CM', 'DX': 'PLT', 'ZD': 'TLBC',
            'YXT': 100, 'GCH': 20,
            'PH_LD': 0.5, 'YJ_LD': 1.0, 'YXP_LD': 0.8, 'SXK_LD': 0.8, 'RZ_LD': 1.0,
            'GZ_LD': 1.0, 'GG_LD': 1.0, 'PS_LD': 1.0, 'DX_LD': 1.0, 'ZD_LD': 1.0,
            'YXT_LD': 1.0, 'GCH_LD': 1.0,
            'composite_weight': 0.85, 'grade': '3',
            'pH障碍等级': '中度障碍', '有机质障碍等级': '丰富',
            'pH_OD': 0.25, '有机质_OD': 0.05
        }
        storage.save_evaluation([record])
        
        result = diagnose(db_path)
        assert result['status'] == 'ok'
        assert result['diagnosed'] == 1
        
        diag_result = storage.get_diagnosis('test-001')
        assert diag_result is not None
        assert diag_result['obstacle_type'] == '单一障碍'

def test_query_parcel():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, 'test.db')
        storage = DiagnosisStorage(db_path)
        
        result = query_parcel('test-001', db_path)
        assert result['status'] == 'not_ready'
        
        storage.create_tables()
        eval_record = {
            'parcel_id': 'test-001', 'region_code': 'HN', 'secondary_region_code': 'MNY',
            'PH': 6.5, 'YJ': 25, 'YXP': 30, 'SXK': 150, 'RZ': 1.2,
            'GZ': 'RT', 'GG': 'FS', 'PS': 'CM', 'DX': 'PLT', 'ZD': 'TLBC',
            'YXT': 100, 'GCH': 20,
            'PH_LD': 1.0, 'YJ_LD': 1.0, 'YXP_LD': 0.8, 'SXK_LD': 0.8, 'RZ_LD': 1.0,
            'GZ_LD': 1.0, 'GG_LD': 1.0, 'PS_LD': 1.0, 'DX_LD': 1.0, 'ZD_LD': 1.0,
            'YXT_LD': 1.0, 'GCH_LD': 1.0,
            'composite_weight': 0.85, 'grade': '3',
            'pH障碍等级': '无障碍', '有机质障碍等级': '丰富',
            'pH_OD': 0.0, '有机质_OD': 0.0
        }
        storage.save_evaluation([eval_record])
        
        diag_record = {
            'parcel_id': 'test-001', 'obstacle_type': '无明显障碍',
            'main_factors': [], 'secondary_factors': []
        }
        storage.save_diagnosis([diag_record])
        
        result = query_parcel('test-001', db_path)
        assert result['status'] == 'ok'
        assert result['parcel_id'] == 'test-001'
```

- [ ] **Step 3: 运行测试**

Run: `cd d:\17417\Documents\agent_culti_demo; python -m pytest tests/test_farmland_diagnosis.py::test_diagnosis_row_no_obstacle -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add src/ai_culti_demo/farmland_diagnosis/diagnosis.py
git commit -m "feat: add obstacle diagnosis module"
```

---

### Task 5: 创建酸化改良模块

**Files:**
- Create: `src/ai_culti_demo/farmland_acidification/__init__.py`
- Create: `src/ai_culti_demo/farmland_acidification/acidification.py`

**Interfaces:**
- Consumes: `DiagnosisStorage`, `AMENDMENT_CONFIG`, `INDICATOR_NAME_MAP`
- Produces: `extract_acidification()`, `classify_level()`, `generate_plan()`, `query_parcel()`

- [ ] **Step 1: 编写酸化改良模块代码**

```python
# src/ai_culti_demo/farmland_acidification/acid