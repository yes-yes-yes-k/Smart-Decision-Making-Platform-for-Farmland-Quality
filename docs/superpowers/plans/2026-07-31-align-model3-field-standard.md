---
change: align-model3-to-field-standard
design-doc: docs/superpowers/specs/2026-07-31-align-model3-field-standard-design.md
base-ref: f7801671d5e0ceffb169910d6d17c9ef201f75d1
---

# align-model3-to-field-standard 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 model-3（farmland_diagnosis）字段命名全量对齐到《数据字段标准化》规范与模型3 V2.0 实现，移植 V2.0 关键函数（translate_obstacle_level / replace_abbr_in_text / diagnosis_row 三元组），顺带根治 diagnosis_row 大小写 bug 和 acidification 读错列 bug，保留 DB 持久化 + 在线查询架构。

**Architecture:** 保留现有 DB 持久化 + 在线查询架构（bulk_evaluate → evaluation_results → diagnose → diagnosis_results → query_parcel），仅对齐字段名与诊断语义。CSV 直接使用标准码表头（YJNYQ/EJNYQ/SJD/YJZ/...），不再做中文列名重命名。障碍度存独立 `xxxZAD` 列，不覆盖原始值。障碍等级用 `xxxZADJ`，综合权重 `ZHQZ`，质量等级 `GDZLDJ`，障碍诊断输出 `ZALX/ZYZAYS/CYZAYS` 字符串三元组。

**Tech Stack:** Python 3、pandas、numpy、sqlite3、pytest。无新增依赖。

## Global Constraints

- 字段映射权威表（旧→新）：PH→SJD, YJ→YJZ, YXP→YXL, SXK→SXJ, RZ→TRRZ, GZ→GCZD, GG→GGNL, PS→PSNL, DX→DXBW, ZD→ZDGX, YXT→YXTCHD, GCH→GCHD
- 后缀映射：`_LD`→`LSD`（隶属度）、`_OD`→`ZAD`（障碍度）、`障碍等级`（列名）→`ZADJ`（后缀，与指标码拼接，如 `SJDZADJ`）
- 字段映射：`composite_weight`→`ZHQZ`、`grade`→`GDZLDJ`、`JY/EJ`（区域列）→`YJNYQ/EJNYQ`（CSV 列）/`region_code/secondary_region_code`（DB 列，保留）、`obstacle_type`→`ZALX`、`main_factors`(list)→`ZYZAYS`(string)、`secondary_factors`(list)→`CYZAYS`(string)
- 配置映射：`INDICATOR_NAME_MAP`→`INDICATOR_DISPLAY_MAP`、`TEXT_VALUE_MAPS`→`DISCRETE_CN_MAP`（键改为 GCZD/GGNL/PSNL/DXBW/ZDGX，值映射不变）、移除 `COLUMN_RENAME`、新增 `GRADE_CONFIG`（从 evaluation.py 抽出）
- 标准指标码常量：`ALL_INDICATORS = ['SJD','YJZ','YXL','SXJ','TRRZ','GCZD','GGNL','PSNL','DXBW','ZDGX','YXTCHD','GCHD']`、`CONTINUOUS_INDICATORS = ['SJD','YJZ','YXL','SXJ','TRRZ','YXTCHD','GCHD']`、`DISCRETE_INDICATORS = ['GCZD','GGNL','PSNL','DXBW','ZDGX']`、`WEIGHTED_INDICATORS = ALL_INDICATORS`
- 系数/权重数值不变，仅改键名
- 非目标：不改 model-1/model-7；不改 API 对外路由结构；不改 RAG/LLM 基础设施；不迁移旧 DB 数据；不改 openapi.json 对外结构
- 提交规范：每个任务结束提交一次，commit message 前缀 `refactor(model-3):` 或 `fix(model-3):` 或 `test(model-3):`
- CSV 编码兼容：保留 utf-8/gbk 回退
- V2.0 参考实现路径：`D:\destkop\模型3_V2.0 (2)\模型3_V2.0\模型3_V2.0\calculatorall.py` 与 `mappings_config.py`

---

## File Structure

| 文件 | 职责 | 本变更改动 |
|------|------|-----------|
| `src/ai_culti_demo/farmland_diagnosis/config.py` | 区域映射、系数、权重、显示名映射、障碍等级计算 | 常量重命名+新增 GRADE_CONFIG/指标常量、calc_obstacle_level 改标准码 |
| `src/ai_culti_demo/farmland_diagnosis/storage.py` | SQLite 表结构、CRUD | evaluation_results/diagnosis_results 列名全量重建 |
| `src/ai_culti_demo/farmland_diagnosis/evaluation.py` | 隶属度/综合权重/等级/障碍度计算 | 新增 translate_obstacle_level、evaluate_single/bulk_evaluate 改标准码 |
| `src/ai_culti_demo/farmland_diagnosis/diagnosis.py` | 障碍诊断三元组、查询 | diagnosis_row 改签名返回三元组、新增 replace_abbr_in_text、diagnose/query_parcel 适配 |
| `src/ai_culti_demo/farmland_diagnosis/acidification.py` | 酸化改良 | 字段引用修正 SJD/YJZ/region_code（顺带修读错列 bug） |
| `src/ai_culti_demo/farmland_diagnosis/__init__.py` | 模块导出 | 导出新增常量/函数，移除已删除导出 |
| `framework/agents/specialized/problem_agent.py` | 模型3 消费端 | evaluation/diagnosis 字段引用改标准码 |
| `tests/test_farmland_diagnosis.py` | 单元/集成测试 | 全量更新字段名 + 新增 4 个测试 |
| `docs/model-integration-analysis.md` | 模型集成分析 | 纳入版本控制确认 |
| `docs/model-provider-spec.md` | 模型提供方规范 | 纳入版本控制确认 |

---

### Task 1: config.py 配置层字段标准化

**Files:**
- Modify: `src/ai_culti_demo/farmland_diagnosis/config.py`
- Test: `tests/test_farmland_diagnosis.py`（仅 config 相关测试段：`test_region_map` / `test_coefficients_exists` / `test_weights_exists` / `test_indicator_name_map` / `test_calc_obstacle_level_*`）

**Interfaces:**
- Consumes: 无（基础层）
- Produces: `REGION_MAP`、`SECONDARY_REGION_MAP`（不变）、`DISCRETE_CN_MAP`、`COEFFICIENTS`（标准码键）、`WEIGHTS`（标准码键）、`INDICATOR_DISPLAY_MAP`、`GRADE_CONFIG`、`ALL_INDICATORS`、`CONTINUOUS_INDICATORS`、`DISCRETE_INDICATORS`、`WEIGHTED_INDICATORS`、`AMENDMENT_CONFIG`（不变）、`calc_obstacle_level(row, indicators)`（标准码键，读 `GCZDLSD`/`DXBWLSD`）。移除 `COLUMN_RENAME`、`TEXT_VALUE_MAPS`、`INDICATOR_NAME_MAP`。

- [x] **Step 1: 更新 config 相关测试为标准码（红）**

把 `tests/test_farmland_diagnosis.py` 顶部 config 测试段改为：

```python
import pytest
import numpy as np
from src.ai_culti_demo.farmland_diagnosis.config import (
    REGION_MAP, COEFFICIENTS, WEIGHTS, INDICATOR_DISPLAY_MAP,
    GRADE_CONFIG, ALL_INDICATORS, CONTINUOUS_INDICATORS, DISCRETE_INDICATORS,
    calc_obstacle_level
)

def test_region_map():
    assert REGION_MAP['华南区'] == 'HN'
    assert REGION_MAP['长江中下游区'] == 'CJ'

def test_coefficients_exists():
    assert 'HN' in COEFFICIENTS
    assert 'CJ' in COEFFICIENTS
    assert 'SJD' in COEFFICIENTS['HN']
    assert 'YJZ' in COEFFICIENTS['HN']

def test_weights_exists():
    assert 'MNY' in WEIGHTS
    assert 'SJD' in WEIGHTS['MNY']
    assert 'GGNL' in WEIGHTS['MNY']

def test_indicator_display_map():
    assert INDICATOR_DISPLAY_MAP['SJD'] == 'pH'
    assert INDICATOR_DISPLAY_MAP['YJZ'] == '有机质'

def test_grade_config_exists():
    assert 'HN' in GRADE_CONFIG
    assert 'CJ' in GRADE_CONFIG
    assert len(GRADE_CONFIG['HN'][0]) == 11  # 10 个边界 + inf

def test_indicator_constants():
    assert len(ALL_INDICATORS) == 12
    assert set(CONTINUOUS_INDICATORS) | set(DISCRETE_INDICATORS) == set(ALL_INDICATORS)
    assert set(CONTINUOUS_INDICATORS) & set(DISCRETE_INDICATORS) == set()

def test_calc_obstacle_level_sjd_moderate():
    row = {'SJD': 5.0}
    result = calc_obstacle_level(row, ['SJD'])
    assert result['SJD'] == '中度障碍'

def test_calc_obstacle_level_sjd_no_obstacle():
    row = {'SJD': 7.0}
    result = calc_obstacle_level(row, ['SJD'])
    assert result['SJD'] == '无障碍'

def test_calc_obstacle_level_sjd_severe():
    row = {'SJD': 4.0}
    result = calc_obstacle_level(row, ['SJD'])
    assert result['SJD'] == '重度障碍'

def test_calc_obstacle_level_organic_moderate():
    row = {'YJZ': 15}
    result = calc_obstacle_level(row, ['YJZ'])
    assert result['YJZ'] == '中度障碍'

def test_calc_obstacle_level_organic_no_obstacle():
    row = {'YJZ': 30}
    result = calc_obstacle_level(row, ['YJZ'])
    assert result['YJZ'] == '无障碍'

def test_calc_obstacle_level_multiple_indicators():
    row = {'SJD': 6.5, 'YJZ': 25, 'SXJ': 80}
    result = calc_obstacle_level(row, ['SJD', 'YJZ', 'SXJ'])
    assert result['SJD'] == '无障碍'
    assert result['YJZ'] == '轻度障碍'
    assert result['SXJ'] == '中度障碍'

def test_calc_obstacle_level_gczd_uses_lsd():
    # GCZD 障碍等级依赖隶属度列 GCZDLSD
    row = {'GCZDLSD': 0.5}
    result = calc_obstacle_level(row, ['GCZD'])
    assert result['GCZD'] == '重度障碍'

def test_calc_obstacle_level_dxbw_uses_lsd():
    row = {'DXBWLSD': 0.3}
    result = calc_obstacle_level(row, ['DXBW'])
    assert result['DXBW'] == '重度障碍'
```

- [x] **Step 2: 运行 config 测试确认失败**

Run: `pytest tests/test_farmland_diagnosis.py -k "region_map or coefficients_exists or weights_exists or indicator_display_map or grade_config or indicator_constants or calc_obstacle_level" -v`
Expected: FAIL（ImportError: cannot import name 'INDICATOR_DISPLAY_MAP'/'GRADE_CONFIG'/'ALL_INDICATORS' 等，且现有测试仍引用 PH/YJ）

- [x] **Step 3: 重写 config.py 为标准码（绿）**

用以下内容完整替换 `src/ai_culti_demo/farmland_diagnosis/config.py`：

```python
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

# 标准指标码（按输出顺序）
ALL_INDICATORS = ['SJD', 'YJZ', 'YXL', 'SXJ', 'TRRZ', 'GCZD', 'GGNL', 'PSNL', 'DXBW', 'ZDGX', 'YXTCHD', 'GCHD']
CONTINUOUS_INDICATORS = ['SJD', 'YJZ', 'YXL', 'SXJ', 'TRRZ', 'YXTCHD', 'GCHD']
DISCRETE_INDICATORS = ['GCZD', 'GGNL', 'PSNL', 'DXBW', 'ZDGX']
WEIGHTED_INDICATORS = ALL_INDICATORS  # 参与加权和障碍诊断

# 离散指标中文值 → 代码（用于将 CSV 中的中文转为系数查找所需的代码）
DISCRETE_CN_MAP = {
    'DXBW': {
        '山间盆地': 'MB', '宽谷盆地': 'WVB', '平原低阶': 'PLT', '平原中阶': 'PMG',
        '平原高阶': 'PUG', '丘陵上部': 'UHR', '丘陵中部': 'MPH', '丘陵下部': 'LHR',
        '山地坡上': 'MSU', '山地坡中': 'MSM', '山地坡下': 'MSL',
    },
    'GCZD': {
        '壤土': 'RT', '粉(砂)质壤土': 'FRT', '粉(砂)质黏壤土': 'FNRT', '砂质黏壤土': 'SNRT',
        '黏壤土': 'NRT', '砂质壤土': 'SRT', '壤质黏土': 'RNT', '粉(砂)质黏土': 'FNT',
        '砂质黏土': 'SNT', '黏土': 'NT', '重黏土': 'ZNT', '砂土及壤质砂土': 'SRST',
    },
    'ZDGX': {
        '薄层型': 'TL', '松散型': 'Lt', '紧实型': 'Ct', '夹层型': 'IL',
        '上紧下松型': 'TCBL', '上松下紧型': 'TLBC', '海绵型': 'St',
    },
    'GGNL': {
        '充分满足': 'FS', '满足': 'S', '基本满足': 'BS', '不满足': 'US',
    },
    'PSNL': {
        '充分满足': 'CM', '满足': 'M', '基本满足': 'JM', '不满足': 'BM',
    },
}

COEFFICIENTS = {
    'HN': {
        'SJD':   {'a': 0.256941, 'c': 6.7, 'L': 4.0, 'U': 9.5},
        'YJZ':   {'a': 0.002163, 'c': 38, 'L': 6.0, 'U': 38.0},
        'YXL':   {'a': 0.0038, 'c': 40, 'L': 5.0, 'U': 40.0},
        'SXJ':   {'a': 0.000068, 'c': 205, 'L': 30, 'U': 205},
        'TRRZ':  {'a': 2.786523, 'c': 1.35, 'L': 0.9, 'U': 2.1},
        'YXTCHD':{'a': 0.00023, 'c': 100, 'L': 10, 'U': 100},
        'GCHD':  {'a': 0.019247, 'c': 20.2, 'L': 5, 'U': 20.2},
        'GCZD':  {'RT': 1, 'FRT': 0.95, 'FNRT': 0.9, 'SNRT': 0.85, 'NRT': 0.8, 'SRT': 0.75, 'RNT': 0.7, 'FNT': 0.65, 'SNT': 0.6, 'NT': 0.55, 'ZNT': 0.5, 'SRST': 0.4},
        'GGNL':  {'FS': 1, 'S': 0.8, 'BS': 0.6, 'US': 0.3},
        'PSNL':  {'CM': 1, 'M': 0.8, 'JM': 0.6, 'BM': 0.3},
        'DXBW':  {'MB': 0.7, 'WVB': 0.9, 'PLT': 1, 'PMG': 0.9, 'PUG': 0.8, 'UHR': 0.4, 'MPH': 0.5, 'LHR': 0.6, 'MSU': 0.2, 'MSM': 0.3, 'MSL': 0.5},
        'ZDGX':  {'TL': 0.3, 'Lt': 0.2, 'Ct': 0.5, 'IL': 0.7, 'TCBL': 0.4, 'TLBC': 1, 'St': 0.8},
    },
    'CJ': {
        'SJD':   {'a': 0.221129, 'c': 6.811204, 'L': 3.0, 'U': 10},
        'YJZ':   {'a': 0.0018842, 'c': 33.656446, 'L': 0, 'U': 33.7},
        'YXL':   {'a': 0.002025, 'c': 33.346824, 'L': 4.0, 'U': 33.3},
        'SXJ':   {'a': 0.000081, 'c': 181.622535, 'L': 0, 'U': 182},
        'TRRZ':  {'a': 2.236726, 'c': 1.211674, 'L': 0.5, 'U': 2.21},
        'YXTCHD':{'a': 0.000205, 'c': 99.092342, 'L': 10, 'U': 99},
        'GCHD':  {'a': 0.008008, 'c': 23.333126, 'L': 0, 'U': 23},
        'GCZD':  {'RT': 1, 'FRT': 0.95, 'FNRT': 0.85, 'SNRT': 0.75, 'NRT': 0.9, 'SRT': 0.65, 'RNT': 0.65, 'FNT': 0.8, 'SNT': 0.6, 'NT': 0.62, 'ZNT': 0.55, 'SRST': 0.5},
        'GGNL':  {'FS': 1, 'S': 0.8, 'BS': 0.6, 'US': 0.3},
        'PSNL':  {'CM': 1, 'M': 0.8, 'JM': 0.6, 'BM': 0.3},
        'DXBW':  {'MB': 0.8, 'WVB': 0.95, 'PLT': 1, 'PMG': 0.95, 'PUG': 0.9, 'UHR': 0.6, 'MPH': 0.7, 'LHR': 0.8, 'MSU': 0.3, 'MSM': 0.45, 'MSL': 0.68},
        'ZDGX':  {'TL': 0.55, 'Lt': 0.3, 'Ct': 0.75, 'IL': 0.85, 'TCBL': 0.4, 'TLBC': 1, 'St': 0.95},
    },
}

WEIGHTS = {
    'MNY': {
        'GGNL': 0.1253, 'DXBW': 0.124, 'PSNL': 0.1057, 'YJZ': 0.0958,
        'GCZD': 0.0827, 'ZDGX': 0.079, 'SXJ': 0.0736, 'YXTCHD': 0.0716,
        'SJD': 0.0668, 'TRRZ': 0.0596, 'YXL': 0.0574, 'GCHD': 0.0585,
    },
    'YXG': {
        'GGNL': 0.1249, 'DXBW': 0.1233, 'PSNL': 0.1003, 'YJZ': 0.1,
        'GCZD': 0.0815, 'ZDGX': 0.0737, 'SXJ': 0.0791, 'YXTCHD': 0.0726,
        'SJD': 0.0678, 'TRRZ': 0.0576, 'YXL': 0.0602, 'GCHD': 0.059,
    },
    'NL': {
        'GGNL': 0.1369, 'DXBW': 0.127, 'PSNL': 0.107, 'YJZ': 0.1046,
        'GCZD': 0.0905, 'ZDGX': 0.0731, 'SXJ': 0.0681, 'YXTCHD': 0.05779,
        'SJD': 0.0704, 'TRRZ': 0.0494, 'YXL': 0.0577, 'GCHD': 0.0594,
    },
    'QN': {
        'GGNL': 0.1266, 'DXBW': 0.1025, 'PSNL': 0.1154, 'YJZ': 0.1039,
        'GCZD': 0.08, 'ZDGX': 0.0814, 'SXJ': 0.0775, 'YXTCHD': 0.0604,
        'SJD': 0.0726, 'TRRZ': 0.0631, 'YXL': 0.0607, 'GCHD': 0.0499,
    },
}

# 缩写 → 中文显示名（用于障碍因素描述中缩写替换）
INDICATOR_DISPLAY_MAP = {
    'SJD': 'pH',
    'YJZ': '有机质',
    'YXL': '有效磷',
    'SXJ': '速效钾',
    'TRRZ': '容重',
    'YXTCHD': '有效土层',
    'GCZD': '耕层质地',
    'GGNL': '灌溉能力',
    'PSNL': '排水能力',
    'DXBW': '地形部位',
    'ZDGX': '质地构型',
    'GCHD': '耕层厚度',
}

# 综合等级划分（一级区 -> (边界, 等级标签)）
GRADE_CONFIG = {
    'HN': ([0, 0.6650, 0.6900, 0.7150, 0.7400, 0.7650, 0.7900, 0.8150, 0.8400, 0.8650, float('inf')],
           ['10', '9', '8', '7', '6', '5', '4', '3', '2', '1']),
    'CJ': ([0, 0.6960, 0.7224, 0.7488, 0.7751, 0.8015, 0.8279, 0.8543, 0.8806, 0.9070, float('inf')],
           ['10', '9', '8', '7', '6', '5', '4', '3', '2', '1']),
}

AMENDMENT_CONFIG = {
    'lime_rate': {'mild': 50, 'moderate': 100, 'severe': 150},
    'measures': {
        'mild': ['常规监测', '合理施肥'],
        'moderate': ['施用石灰', '有机肥培肥', '轮作调整'],
        'severe': ['大量施用石灰', '深翻改土', '长期培肥'],
    },
}


def calc_obstacle_level(row, indicators):
    """计算一行所有指标的标准障碍等级（重度/中度/轻度/无障碍）。

    row: 一行数据字典，键为指标简写（连续/离散原始值）；对 GCZD/DXBW 需含隶属度键 GCZDLSD/DXBWLSD。
    indicators: 指标简写列表。
    """
    levels = {}
    for ind in indicators:
        if ind == 'SJD':
            val = row.get('SJD', np.nan)
            if pd.isna(val):
                levels['SJD'] = np.nan
            elif val <= 3 or val > 10:
                levels['SJD'] = '重度障碍'
            elif (val > 3 and val <= 4.5) or (val > 9.5 and val <= 10):
                levels['SJD'] = '重度障碍'
            elif (val > 4.5 and val <= 5.5) or (val > 8.5 and val <= 9.5):
                levels['SJD'] = '中度障碍'
            elif (val > 5.5 and val < 6.5) or (val > 7.5 and val <= 8.5):
                levels['SJD'] = '轻度障碍'
            elif 6.5 <= val <= 7.5:
                levels['SJD'] = '无障碍'
            else:
                levels['SJD'] = np.nan
        elif ind == 'YJZ':
            val = row.get('YJZ', np.nan)
            if pd.isna(val):
                levels['YJZ'] = np.nan
            elif val <= 10:
                levels['YJZ'] = '重度障碍'
            elif val <= 20:
                levels['YJZ'] = '中度障碍'
            elif val <= 25:
                levels['YJZ'] = '轻度障碍'
            else:
                levels['YJZ'] = '无障碍'
        elif ind == 'YXL':
            val = row.get('YXL', np.nan)
            if pd.isna(val):
                levels['YXL'] = np.nan
            elif val <= 10:
                levels['YXL'] = '重度障碍'
            elif val <= 20:
                levels['YXL'] = '中度障碍'
            elif val <= 35:
                levels['YXL'] = '轻度障碍'
            else:
                levels['YXL'] = '无障碍'
        elif ind == 'SXJ':
            val = row.get('SXJ', np.nan)
            if pd.isna(val):
                levels['SXJ'] = np.nan
            elif val <= 50:
                levels['SXJ'] = '重度障碍'
            elif val <= 100:
                levels['SXJ'] = '中度障碍'
            elif val <= 150:
                levels['SXJ'] = '轻度障碍'
            else:
                levels['SXJ'] = '无障碍'
        elif ind == 'TRRZ':
            val = row.get('TRRZ', np.nan)
            if pd.isna(val):
                levels['TRRZ'] = np.nan
            elif val <= 0.9:
                levels['TRRZ'] = '重度障碍'
            elif 0.9 <= val < 0.95:
                levels['TRRZ'] = '中度障碍'
            elif 0.95 <= val < 1:
                levels['TRRZ'] = '轻度障碍'
            elif 1 <= val <= 1.2:
                levels['TRRZ'] = '无障碍'
            elif 1.2 < val <= 1.3:
                levels['TRRZ'] = '轻度障碍'
            elif 1.3 < val <= 1.4:
                levels['TRRZ'] = '中度障碍'
            elif val > 1.4:
                levels['TRRZ'] = '重度障碍'
        elif ind == 'GCHD':
            val = row.get('GCHD', np.nan)
            if pd.isna(val):
                levels['GCHD'] = np.nan
            elif val <= 10:
                levels['GCHD'] = '重度障碍'
            elif val <= 15:
                levels['GCHD'] = '中度障碍'
            elif val < 20:
                levels['GCHD'] = '轻度障碍'
            else:
                levels['GCHD'] = '无障碍'
        elif ind == 'YXTCHD':
            val = row.get('YXTCHD', np.nan)
            if pd.isna(val):
                levels['YXTCHD'] = np.nan
            elif val < 60:
                levels['YXTCHD'] = '重度障碍'
            elif 60 <= val < 80:
                levels['YXTCHD'] = '中度障碍'
            elif 80 <= val < 100:
                levels['YXTCHD'] = '轻度障碍'
            else:
                levels['YXTCHD'] = '无障碍'
        elif ind in ['GGNL', 'PSNL']:
            code = row.get(ind, np.nan)
            if pd.isna(code):
                levels[ind] = np.nan
            else:
                if ind == 'GGNL':
                    m = {'US': '重度障碍', 'BS': '中度障碍', 'S': '轻度障碍', 'FS': '无障碍'}
                else:
                    m = {'BM': '重度障碍', 'JM': '中度障碍', 'M': '轻度障碍', 'CM': '无障碍'}
                levels[ind] = m.get(str(code).strip(), np.nan)
        elif ind == 'ZDGX':
            code = str(row.get('ZDGX', '')).strip()
            if pd.isna(code) or code == '' or code.lower() == 'nan':
                levels['ZDGX'] = np.nan
            elif code in ['TCBL', 'TL', 'Lt']:
                levels['ZDGX'] = '重度障碍'
            elif code == 'Ct':
                levels['ZDGX'] = '中度障碍'
            elif code == 'IL':
                levels['ZDGX'] = '轻度障碍'
            elif code in ['TLBC', 'St']:
                levels['ZDGX'] = '无障碍'
            else:
                levels['ZDGX'] = np.nan
        elif ind == 'GCZD':
            ld_val = row.get('GCZDLSD', np.nan)
            if pd.isna(ld_val):
                levels['GCZD'] = np.nan
            elif 0.4 <= ld_val < 0.6:
                levels['GCZD'] = '重度障碍'
            elif 0.6 <= ld_val <= 0.7:
                levels['GCZD'] = '中度障碍'
            elif 0.75 <= ld_val <= 0.85:
                levels['GCZD'] = '轻度障碍'
            elif 0.9 <= ld_val <= 1:
                levels['GCZD'] = '无障碍'
            else:
                levels['GCZD'] = np.nan
        elif ind == 'DXBW':
            ld_val = row.get('DXBWLSD', np.nan)
            if pd.isna(ld_val):
                levels['DXBW'] = np.nan
            elif 0.2 <= ld_val < 0.5:
                levels['DXBW'] = '重度障碍'
            elif 0.5 <= ld_val <= 0.68:
                levels['DXBW'] = '中度障碍'
            elif 0.7 <= ld_val <= 0.8:
                levels['DXBW'] = '轻度障碍'
            elif 0.9 <= ld_val <= 1:
                levels['DXBW'] = '无障碍'
            else:
                levels['DXBW'] = np.nan
        else:
            levels[ind] = np.nan
    return levels
```

- [x] **Step 4: 运行 config 测试确认通过**

Run: `pytest tests/test_farmland_diagnosis.py -k "region_map or coefficients_exists or weights_exists or indicator_display_map or grade_config or indicator_constants or calc_obstacle_level" -v`
Expected: PASS（全部 config 测试通过；其他模块测试此时仍失败，属预期，不在本任务范围）

- [x] **Step 5: 提交**

```bash
git add src/ai_culti_demo/farmland_diagnosis/config.py tests/test_farmland_diagnosis.py
git commit -m "refactor(model-3): config.py 字段命名对齐标准码，新增 GRADE_CONFIG 与指标常量"
```

---

### Task 2: storage.py 表结构重建

**Files:**
- Modify: `src/ai_culti_demo/farmland_diagnosis/storage.py`
- Test: `tests/test_farmland_diagnosis.py`（storage 测试段：`test_storage_create_tables` / `test_storage_save_and_get_evaluation` / `test_storage_save_and_get_diagnosis` / `test_storage_is_ready`）

**Interfaces:**
- Consumes: 无（Task 1 的常量此处不直接使用）
- Produces: `DiagnosisStorage`，其 `evaluation_results` 表列名为标准码（`SJD`/`YJZ`/.../`SJDLSD`/.../`ZHQZ`/`GDZLDJ`/`region_code`/`secondary_region_code`/`parcel_id`/时间戳）；`diagnosis_results` 表含 `ZALX`/`ZYZAYS`/`CYZAYS` 及各 `xxxZADJ`(TEXT)/`xxxZAD`(REAL)；`acidification_results` 表不变。`save_evaluation`/`save_diagnosis` 适配新列；`get_diagnosis` 不再对 `ZYZAYS`/`CYZAYS` 做 JSON loads（直接 TEXT）；`get_acidification` 的 `measures` 仍 JSON loads。

- [x] **Step 1: 更新 storage 测试为标准码字段（红）**

把 `tests/test_farmland_diagnosis.py` 中 storage 测试段改为：

```python
# Storage tests
from src.ai_culti_demo.farmland_diagnosis.storage import DiagnosisStorage
import tempfile
import os
import sqlite3

def test_storage_create_tables():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, 'test.db')
        storage = DiagnosisStorage(db_path)
        storage.create_tables()

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
            'SJD': 6.5, 'YJZ': 25, 'YXL': 30, 'SXJ': 150, 'TRRZ': 1.2,
            'GCZD': 'RT', 'GGNL': 'FS', 'PSNL': 'CM', 'DXBW': 'PLT', 'ZDGX': 'TLBC',
            'YXTCHD': 100, 'GCHD': 20,
            'SJDLSD': 1.0, 'YJZLSD': 1.0, 'YXLLSD': 0.8, 'SXJLSD': 0.8, 'TRRZLSD': 1.0,
            'GCZDLSD': 1.0, 'GGNLLSD': 1.0, 'PSNLLSD': 1.0, 'DXBWLSD': 1.0, 'ZDGXLSD': 1.0,
            'YXTCHDLSD': 1.0, 'GCHDLSD': 1.0,
            'ZHQZ': 0.85,
            'GDZLDJ': '3',
        }

        count = storage.save_evaluation([record])
        assert count == 1

        result = storage.get_evaluation('test-001')
        assert result is not None
        assert result['parcel_id'] == 'test-001'
        assert result['SJD'] == 6.5
        assert result['ZHQZ'] == 0.85
        assert result['GDZLDJ'] == '3'

def test_storage_save_and_get_diagnosis():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, 'test.db')
        storage = DiagnosisStorage(db_path)
        storage.create_tables()

        eval_record = {
            'parcel_id': 'test-001',
            'region_code': 'HN', 'secondary_region_code': 'MNY',
            'SJD': 5.0, 'YJZ': 25, 'YXL': 30, 'SXJ': 150, 'TRRZ': 1.2,
            'GCZD': 'RT', 'GGNL': 'FS', 'PSNL': 'CM', 'DXBW': 'PLT', 'ZDGX': 'TLBC',
            'YXTCHD': 100, 'GCHD': 20,
            'SJDLSD': 0.5, 'YJZLSD': 1.0, 'YXLLSD': 0.8, 'SXJLSD': 0.8, 'TRRZLSD': 1.0,
            'GCZDLSD': 1.0, 'GGNLLSD': 1.0, 'PSNLLSD': 1.0, 'DXBWLSD': 1.0, 'ZDGXLSD': 1.0,
            'YXTCHDLSD': 1.0, 'GCHDLSD': 1.0,
            'ZHQZ': 0.85, 'GDZLDJ': '3',
        }
        storage.save_evaluation([eval_record])

        diag_record = {
            'parcel_id': 'test-001',
            'ZALX': '单一障碍',
            'ZYZAYS': 'pH(中度酸化, 25.0%)',
            'CYZAYS': '无',
            'SJDZADJ': '中度酸化',
            'SJDZAD': 0.25,
        }
        storage.save_diagnosis([diag_record])

        result = storage.get_diagnosis('test-001')
        assert result is not None
        assert result['ZALX'] == '单一障碍'
        # ZYZAYS/CYZAYS 是 TEXT 字符串，不再是 JSON list
        assert result['ZYZAYS'] == 'pH(中度酸化, 25.0%)'
        assert result['CYZAYS'] == '无'
        assert result['SJDZADJ'] == '中度酸化'
        assert result['SJDZAD'] == 0.25

def test_storage_is_ready():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, 'test.db')
        storage = DiagnosisStorage(db_path)
        assert not storage.is_ready()

        storage.create_tables()
        assert not storage.is_ready()

        eval_record = {
            'parcel_id': 'test-001', 'region_code': 'HN', 'secondary_region_code': 'MNY',
            'SJD': 6.5, 'YJZ': 25, 'YXL': 30, 'SXJ': 150, 'TRRZ': 1.2,
            'GCZD': 'RT', 'GGNL': 'FS', 'PSNL': 'CM', 'DXBW': 'PLT', 'ZDGX': 'TLBC',
            'YXTCHD': 100, 'GCHD': 20,
            'SJDLSD': 1.0, 'YJZLSD': 1.0, 'YXLLSD': 0.8, 'SXJLSD': 0.8, 'TRRZLSD': 1.0,
            'GCZDLSD': 1.0, 'GGNLLSD': 1.0, 'PSNLLSD': 1.0, 'DXBWLSD': 1.0, 'ZDGXLSD': 1.0,
            'YXTCHDLSD': 1.0, 'GCHDLSD': 1.0,
            'ZHQZ': 0.85, 'GDZLDJ': '3',
        }
        storage.save_evaluation([eval_record])

        diag_record = {
            'parcel_id': 'test-001', 'ZALX': '无明显障碍',
            'ZYZAYS': '', 'CYZAYS': '无',
        }
        storage.save_diagnosis([diag_record])

        assert storage.is_ready()
```

- [x] **Step 2: 运行 storage 测试确认失败**

Run: `pytest tests/test_farmland_diagnosis.py -k "storage" -v`
Expected: FAIL（列名不存在 / save_evaluation 字段不匹配）

- [x] **Step 3: 重写 storage.py 表结构与 CRUD（绿）**

用以下内容完整替换 `src/ai_culti_demo/farmland_diagnosis/storage.py`：

```python
import sqlite3
import json
import os
from datetime import datetime
from typing import Optional, List, Dict, Any


# 标准指标码（与 config.ALL_INDICATORS 一致，此处本地声明避免循环导入）
_ALL_INDICATORS = ['SJD', 'YJZ', 'YXL', 'SXJ', 'TRRZ', 'GCZD', 'GGNL', 'PSNL', 'DXBW', 'ZDGX', 'YXTCHD', 'GCHD']
_DISCRETE_INDICATORS = {'GCZD', 'GGNL', 'PSNL', 'DXBW', 'ZDGX'}


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

        # evaluation_results：原始值列 + 隶属度列(xxxLSD) + 障碍等级列(xxxZADJ) + 障碍度列(xxxZAD) + ZHQZ + GDZLDJ
        eval_cols = [
            'parcel_id TEXT PRIMARY KEY',
            'region_code TEXT',
            'secondary_region_code TEXT',
        ]
        for ind in _ALL_INDICATORS:
            col_type = 'TEXT' if ind in _DISCRETE_INDICATORS else 'REAL'
            eval_cols.append(f'{ind} {col_type}')
        for ind in _ALL_INDICATORS:
            eval_cols.append(f'{ind}LSD REAL')
            eval_cols.append(f'{ind}ZADJ TEXT')
            eval_cols.append(f'{ind}ZAD REAL')
        eval_cols.append('ZHQZ REAL')
        eval_cols.append('GDZLDJ TEXT')
        eval_cols.append('created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP')
        eval_cols.append('updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP')

        cursor.execute(f'CREATE TABLE IF NOT EXISTS evaluation_results ({", ".join(eval_cols)})')

        # diagnosis_results：ZALX/ZYZAYS/CYZAYS + 各 xxxZADJ / xxxZAD
        diag_cols = [
            'parcel_id TEXT PRIMARY KEY REFERENCES evaluation_results(parcel_id)',
            'ZALX TEXT',
            'ZYZAYS TEXT',
            'CYZAYS TEXT',
        ]
        for ind in _ALL_INDICATORS:
            diag_cols.append(f'{ind}ZADJ TEXT')
            diag_cols.append(f'{ind}ZAD REAL')
        diag_cols.append('created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP')

        cursor.execute(f'CREATE TABLE IF NOT EXISTS diagnosis_results ({", ".join(diag_cols)})')

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

        original_cols = _ALL_INDICATORS
        lsd_cols = [f'{ind}LSD' for ind in _ALL_INDICATORS]
        zadj_cols = [f'{ind}ZADJ' for ind in _ALL_INDICATORS]
        zad_cols = [f'{ind}ZAD' for ind in _ALL_INDICATORS]
        all_data_cols = (['parcel_id', 'region_code', 'secondary_region_code']
                         + original_cols + lsd_cols + zadj_cols + zad_cols
                         + ['ZHQZ', 'GDZLDJ', 'updated_at'])
        placeholders = ', '.join(['?'] * len(all_data_cols))
        col_sql = ', '.join(all_data_cols)

        for record in records:
            values = (
                [record.get('parcel_id'), record.get('region_code'), record.get('secondary_region_code')]
                + [record.get(ind) for ind in original_cols]
                + [record.get(c) for c in lsd_cols]
                + [record.get(c) for c in zadj_cols]
                + [record.get(c) for c in zad_cols]
                + [record.get('ZHQZ'), record.get('GDZLDJ'), datetime.now()]
            )
            cursor.execute(
                f'INSERT OR REPLACE INTO evaluation_results ({col_sql}) VALUES ({placeholders})',
                values,
            )

        conn.commit()
        count = cursor.rowcount
        conn.close()
        return count

    def save_diagnosis(self, records: List[Dict[str, Any]]) -> int:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        zadj_cols = [f'{ind}ZADJ' for ind in _ALL_INDICATORS]
        zad_cols = [f'{ind}ZAD' for ind in _ALL_INDICATORS]
        all_data_cols = (['parcel_id', 'ZALX', 'ZYZAYS', 'CYZAYS']
                         + zadj_cols + zad_cols)
        placeholders = ', '.join(['?'] * len(all_data_cols))
        col_sql = ', '.join(all_data_cols)

        for record in records:
            values = (
                [record.get('parcel_id'), record.get('ZALX'), record.get('ZYZAYS'), record.get('CYZAYS')]
                + [record.get(c) for c in zadj_cols]
                + [record.get(c) for c in zad_cols]
            )
            cursor.execute(
                f'INSERT OR REPLACE INTO diagnosis_results ({col_sql}) VALUES ({placeholders})',
                values,
            )

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
                record.get('amendment_rate'), json.dumps(record.get('measures', [])), record.get('expected_effect'),
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
        # ZALX/ZYZAYS/CYZAYS 及 xxxZADJ/xxxZAD 均为标量列，不再 JSON loads
        return dict(zip(columns, row))

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

- [x] **Step 4: 删除旧 DB 文件以触发重建**

旧库列名与新 schema 不兼容，需删除现存 `farmland_diagnosis.db`（位于 `data/farmland_diagnosis/` 下；测试用 tempfile 不受影响）。执行：

```bash
python -c "import os; p='data/farmland_diagnosis/farmland_diagnosis.db'; os.remove(p) if os.path.exists(p) else print('no db to remove')"
```

Expected: 输出 `no db to remove` 或无输出（已删除）。注意：本步骤仅清理本地开发库；生产部署时由 `create_tables` 重建。

- [x] **Step 5: 运行 storage 测试确认通过**

Run: `pytest tests/test_farmland_diagnosis.py -k "storage" -v`
Expected: PASS

- [x] **Step 6: 提交**

```bash
git add src/ai_culti_demo/farmland_diagnosis/storage.py tests/test_farmland_diagnosis.py
git commit -m "refactor(model-3): storage.py 表结构重建为标准码列名，diagnosis 改 ZALX/ZYZAYS/CYZAYS"
```

---

### Task 3: evaluation.py 评价逻辑标准化 + translate_obstacle_level

**Files:**
- Modify: `src/ai_culti_demo/farmland_diagnosis/evaluation.py`
- Test: `tests/test_farmland_diagnosis.py`（evaluation 测试段：`test_evaluate_single` / `test_bulk_evaluate` / `test_bulk_evaluate_missing_columns` / `test_calc_continuous` / `test_calc_discrete`）

**Interfaces:**
- Consumes: Task 1 的 `REGION_MAP`/`SECONDARY_REGION_MAP`/`COEFFICIENTS`/`WEIGHTS`/`DISCRETE_CN_MAP`/`GRADE_CONFIG`/`ALL_INDICATORS`/`CONTINUOUS_INDICATORS`/`DISCRETE_INDICATORS`/`WEIGHTED_INDICATORS`/`calc_obstacle_level`；Task 2 的 `DiagnosisStorage`
- Produces: `calc_continuous`/`calc_discrete`（不变）、`translate_obstacle_level(ind, level, orig_val)`（新）、`evaluate_single(row, region_code, secondary_region_code) -> dict`（键为标准码 + `xxxLSD`/`xxxZADJ`/`xxxZAD`/`ZHQZ`/`GDZLDJ`）、`bulk_evaluate(input_csv, output_db_path) -> dict`（CSV 用标准码表头，无 COLUMN_RENAME）

- [x] **Step 1: 更新 evaluation 测试为标准码（红）**

把 `tests/test_farmland_diagnosis.py` 中 evaluation 测试段改为：

```python
# Evaluation tests
from src.ai_culti_demo.farmland_diagnosis.evaluation import bulk_evaluate, evaluate_single, calc_continuous, calc_discrete, translate_obstacle_level
import pandas as pd

def test_translate_obstacle_level_sjd_acidification():
    assert translate_obstacle_level('SJD', '中度障碍', 5.0) == '中度酸化'

def test_translate_obstacle_level_sjd_alkalization():
    assert translate_obstacle_level('SJD', '中度障碍', 8.8) == '中度碱化'

def test_translate_obstacle_level_trrz_compaction():
    assert translate_obstacle_level('TRRZ', '重度障碍', 1.5) == '重度板结'

def test_translate_obstacle_level_yjz_barren():
    assert translate_obstacle_level('YJZ', '重度障碍', 5.0) == '重度贫瘠'

def test_translate_obstacle_level_yxl_deficiency():
    assert translate_obstacle_level('YXL', '重度障碍', 5.0) == '重度缺乏'

def test_translate_obstacle_level_no_obstacle():
    assert translate_obstacle_level('SJD', '无障碍', 7.0) == '无障碍'

def test_evaluate_single():
    row = pd.Series({
        'YJNYQ': '华南区', 'EJNYQ': '闽南粤中农林水产区',
        'SJD': 6.5, 'YJZ': 25, 'YXL': 30, 'SXJ': 150, 'TRRZ': 1.2,
        'GCZD': 'RT', 'GGNL': 'FS', 'PSNL': 'CM', 'DXBW': 'PLT', 'ZDGX': 'TLBC',
        'YXTCHD': 100, 'GCHD': 20,
    })

    result = evaluate_single(row, 'HN', 'MNY')

    assert 'SJDLSD' in result
    assert 'ZHQZ' in result
    assert 'GDZLDJ' in result
    assert result['GDZLDJ'] == '1'
    # 原始值保留
    assert result['SJD'] == 6.5

def test_bulk_evaluate():
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_path = os.path.join(tmpdir, 'test.csv')
        # CSV 直接使用标准码表头（无中文列名）
        with open(csv_path, 'w', encoding='utf-8') as f:
            f.write('''YJNYQ,EJNYQ,SJD,YJZ,YXL,SXJ,TRRZ,GCZD,GGNL,PSNL,DXBW,ZDGX,YXTCHD,GCHD
华南区,闽南粤中农林水产区,6.5,25,30,150,1.2,壤土,充分满足,充分满足,平原低阶,上松下紧型,100,20
''')

        db_path = os.path.join(tmpdir, 'test.db')
        result = bulk_evaluate(csv_path, db_path)

        assert result['status'] == 'ok'
        assert result['processed'] == 1

        storage = DiagnosisStorage(db_path)
        eval_result = storage.get_evaluation('0')
        assert eval_result is not None
        assert eval_result['SJD'] == 6.5
        assert eval_result['GDZLDJ'] == '1'

def test_bulk_evaluate_missing_columns():
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_path = os.path.join(tmpdir, 'test.csv')
        with open(csv_path, 'w', encoding='utf-8') as f:
            f.write('SJD,YJZ\n6.5,25\n')

        result = bulk_evaluate(csv_path)
        assert result['status'] == 'error'
        assert 'Missing columns' in result['message']

def test_calc_continuous():
    params = {'a': 0.256941, 'c': 6.7, 'L': 4.0, 'U': 9.5}
    result = calc_continuous(6.5, params)
    assert 0.9 < result < 1.0

def test_calc_discrete():
    mapping = {'FS': 1, 'S': 0.8, 'BS': 0.6, 'US': 0.3}
    result = calc_discrete('FS', mapping)
    assert result == 1.0
```

- [x] **Step 2: 运行 evaluation 测试确认失败**

Run: `pytest tests/test_farmland_diagnosis.py -k "translate_obstacle_level or evaluate_single or bulk_evaluate or calc_continuous or calc_discrete" -v`
Expected: FAIL（ImportError: cannot import name 'translate_obstacle_level'；evaluate_single 仍用 PH）

- [x] **Step 3: 重写 evaluation.py（绿）**

用以下内容完整替换 `src/ai_culti_demo/farmland_diagnosis/evaluation.py`：

```python
import pandas as pd
import numpy as np
import os
from typing import Dict, Any, Optional
from .config import (
    REGION_MAP, SECONDARY_REGION_MAP,
    COEFFICIENTS, WEIGHTS, DISCRETE_CN_MAP, GRADE_CONFIG,
    ALL_INDICATORS, CONTINUOUS_INDICATORS, DISCRETE_INDICATORS, WEIGHTED_INDICATORS,
    INDICATOR_DISPLAY_MAP, calc_obstacle_level,
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
    required = ['YJNYQ', 'EJNYQ'] + ALL_INDICATORS
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
```

- [x] **Step 4: 运行 evaluation 测试确认通过**

Run: `pytest tests/test_farmland_diagnosis.py -k "translate_obstacle_level or evaluate_single or bulk_evaluate or calc_continuous or calc_discrete" -v`
Expected: PASS

- [x] **Step 5: 提交**

```bash
git add src/ai_culti_demo/farmland_diagnosis/evaluation.py tests/test_farmland_diagnosis.py
git commit -m "refactor(model-3): evaluation.py 移植 translate_obstacle_level，evaluate_single/bulk_evaluate 改标准码"
```

---

### Task 4: diagnosis.py 诊断三元组 + replace_abbr_in_text

**Files:**
- Modify: `src/ai_culti_demo/farmland_diagnosis/diagnosis.py`
- Test: `tests/test_farmland_diagnosis.py`（diagnosis 测试段：`test_diagnosis_row_*` / `test_diagnose_flow`）

**Interfaces:**
- Consumes: Task 1 的 `INDICATOR_DISPLAY_MAP`、`WEIGHTED_INDICATORS`；Task 2 的 `DiagnosisStorage`；Task 3 的 `evaluate_single`/`bulk_evaluate` 产出的 `evaluation_results`（含 `xxxZADJ`/`xxxZAD`）
- Produces: `parse_obstacle_level`（保留）、`diagnosis_row(row, indicator_names, level_cols, degree_cols) -> (ZALX, ZYZAYS, CYZAYS)`（返回字符串三元组，内部应用 `replace_abbr_in_text` 与"无"归一）、`replace_abbr_in_text(text, abbr_map)`（新）、`diagnose(db_path)`（存 `ZALX`/`ZYZAYS`/`CYZAYS` 及各 `xxxZADJ`/`xxxZAD`）、`query_parcel(parcel_id, db_path)`（返回标准字段名）

**关键设计决策（注意）：**
- `diagnosis_row` 改签名对齐 V2.0：参数为 `(row, indicator_names, level_cols, degree_cols)`，返回 `(ZALX, ZYZAYS, CYZAYS)` 字符串三元组。`level_cols` 用 `ind+'ZADJ'`、`degree_cols` 用 `ind+'ZAD'`，统一指标码前缀，根治大小写 bug（旧实现 level_cols 用中文 `xxx障碍等级`、degree_cols 用 `xxx_OD`，set 交集恒为空导致生产环境恒返回"无明显障碍"）。
- `diagnosis_row` 内部对 `ZYZAYS`/`CYZAYS` 应用 `replace_abbr_in_text`（缩写→中文显示名），并对空 `CYZAYS` 归一为 `'无'`（V2.0 行为，design 5.7）。
- **spec 场景"无明显障碍"措辞说明**：spec 描述"ZYZAYS 和 CYZAYS 为空"，但 design 5.7 明确要求 `CYZAYS` 空时显示 `'无'`（V2.0 行为）。本实现遵循 design 5.7：`无明显障碍` 时返回 `('无明显障碍', '', '无')`。`ZYZAYS` 保持空串。change owner 后续可酌情修订 spec 措辞，但实现以 design 为准。

- [ ] **Step 1: 更新 diagnosis 测试为标准码 + 三元组（红）**

把 `tests/test_farmland_diagnosis.py` 中 diagnosis 测试段改为：

```python
# Diagnosis tests
from src.ai_culti_demo.farmland_diagnosis.diagnosis import diagnosis_row, diagnose, query_parcel, replace_abbr_in_text
from src.ai_culti_demo.farmland_diagnosis.config import WEIGHTED_INDICATORS

def test_replace_abbr_in_text():
    text = 'SJD(中度酸化, 25.0%)；SXJ(重度缺乏, 26.5%)'
    out = replace_abbr_in_text(text, {'SJD': 'pH', 'SXJ': '速效钾'})
    assert out == 'pH(中度酸化, 25.0%)；速效钾(重度缺乏, 26.5%)'

def test_replace_abbr_in_text_empty():
    assert replace_abbr_in_text('', {'SJD': 'pH'}) == ''

def test_diagnosis_row_single_obstacle():
    row = pd.Series({
        'SJDZADJ': '中度酸化', 'SJDZAD': 0.25,
        'YJZZADJ': '无障碍', 'YJZZAD': 0.05,
    })
    level_cols = [ind + 'ZADJ' for ind in WEIGHTED_INDICATORS]
    degree_cols = [ind + 'ZAD' for ind in WEIGHTED_INDICATORS]
    zalx, zyzays, cyzays = diagnosis_row(row, WEIGHTED_INDICATORS, level_cols, degree_cols)

    assert zalx == '单一障碍'
    assert isinstance(zyzays, str)
    assert isinstance(cyzays, str)
    assert 'pH' in zyzays  # 缩写已替换为中文
    assert cyzays == '无'

def test_diagnosis_row_multi_obstacle():
    row = pd.Series({
        'SJDZADJ': '中度酸化', 'SJDZAD': 0.25,
        'YJZZADJ': '中度贫瘠', 'YJZZAD': 0.20,
        'YXLZADJ': '轻度缺乏', 'YXLZAD': 0.15,
    })
    level_cols = [ind + 'ZADJ' for ind in WEIGHTED_INDICATORS]
    degree_cols = [ind + 'ZAD' for ind in WEIGHTED_INDICATORS]
    zalx, zyzays, cyzays = diagnosis_row(row, WEIGHTED_INDICATORS, level_cols, degree_cols)

    assert zalx == '多障碍'
    assert isinstance(zyzays, str)
    assert zyzays.count('；') >= 1  # 至少两个主要因素

def test_diagnosis_row_no_obstacle():
    row = pd.Series({
        'SJDZADJ': '无障碍', 'SJDZAD': 0.05,
        'YJZZADJ': '无障碍', 'YJZZAD': 0.03,
    })
    level_cols = [ind + 'ZADJ' for ind in WEIGHTED_INDICATORS]
    degree_cols = [ind + 'ZAD' for ind in WEIGHTED_INDICATORS]
    zalx, zyzays, cyzays = diagnosis_row(row, WEIGHTED_INDICATORS, level_cols, degree_cols)

    assert zalx == '无明显障碍'
    assert zyzays == ''
    assert cyzays == '无'  # V2.0 行为：空 CYZAYS 归一为 '无'

def test_diagnose_flow():
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_path = os.path.join(tmpdir, 'test.csv')
        with open(csv_path, 'w', encoding='utf-8') as f:
            f.write('''YJNYQ,EJNYQ,SJD,YJZ,YXL,SXJ,TRRZ,GCZD,GGNL,PSNL,DXBW,ZDGX,YXTCHD,GCHD
华南区,闽南粤中农林水产区,4.5,10,5,50,1.8,黏土,基本满足,基本满足,丘陵上部,夹层型,60,15
''')

        db_path = os.path.join(tmpdir, 'test.db')
        bulk_evaluate(csv_path, db_path)
        result = diagnose(db_path)

        assert result['status'] == 'ok'
        assert result['diagnosed'] == 1

        query_result = query_parcel('0', db_path)
        assert query_result['status'] == 'ok'
        assert 'diagnosis' in query_result
        diag = query_result['diagnosis']
        assert 'ZALX' in diag
        assert 'ZYZAYS' in diag
        assert 'CYZAYS' in diag
```

- [ ] **Step 2: 运行 diagnosis 测试确认失败**

Run: `pytest tests/test_farmland_diagnosis.py -k "replace_abbr or diagnosis_row or diagnose_flow" -v`
Expected: FAIL（ImportError: cannot import name 'replace_abbr_in_text'；diagnosis_row 签名/返回不匹配）

- [ ] **Step 3: 重写 diagnosis.py（绿）**

用以下内容完整替换 `src/ai_culti_demo/farmland_diagnosis/diagnosis.py`：

```python
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
```

- [ ] **Step 4: 运行 diagnosis 测试确认通过**

Run: `pytest tests/test_farmland_diagnosis.py -k "replace_abbr or diagnosis_row or diagnose_flow" -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add src/ai_culti_demo/farmland_diagnosis/diagnosis.py tests/test_farmland_diagnosis.py
git commit -m "refactor(model-3): diagnosis_row 改三元组签名根治大小写 bug，新增 replace_abbr_in_text"
```

---

### Task 5: acidification.py 字段引用修正（顺带修读错列 bug）

**Files:**
- Modify: `src/ai_culti_demo/farmland_diagnosis/acidification.py`
- Test: `tests/test_farmland_diagnosis.py`（acidification 测试段：`test_classify_acidification_*` / `test_generate_amendment_*` / `test_evaluate_acidification_flow`）

**Interfaces:**
- Consumes: Task 2 的 `DiagnosisStorage`（读 `evaluation_results`，列含 `SJD`/`YJZ`/`region_code`）
- Produces: `evaluate_acidification` 改读 `row.get('SJD', 6.5)` / `row.get('YJZ', 20)` / `row.get('region_code', 'HN')`（顺带修旧 bug：原读 `'JY'` 但表中无 `JY` 列，导致恒回退到默认区 HN）。其余函数（classify_acidification / generate_amendment / calculate_lime_demand / calculate_amendment_rate / query_acidification）逻辑不变。

- [ ] **Step 1: 更新 acidification 测试（红）**

`test_classify_acidification_*` / `test_generate_amendment_*` 直接传 pH/有机质/region_code，无需改。仅 `test_evaluate_acidification_flow` 需把 CSV 表头改标准码，并新增一个 region_code 正确分区的断言。把 acidification 测试段改为：

```python
# Acidification tests
from src.ai_culti_demo.farmland_diagnosis.acidification import classify_acidification, generate_amendment, evaluate_acidification, query_acidification

def test_classify_acidification_severe():
    result = classify_acidification(4.0, 'HN')
    assert result['level'] == 'severe'
    assert result['description'] == '强酸性'

def test_classify_acidification_moderate():
    result = classify_acidification(5.0, 'HN')
    assert result['level'] == 'moderate'
    assert result['description'] == '酸性'

def test_classify_acidification_slight():
    result = classify_acidification(6.0, 'HN')
    assert result['level'] == 'slight'
    assert result['description'] == '微酸性'

def test_classify_acidification_neutral():
    result = classify_acidification(7.0, 'HN')
    assert result['level'] == 'neutral'
    assert result['description'] == '中性'

def test_generate_amendment_severe():
    result = generate_amendment(4.0, 10, 'HN')
    assert result['need_amendment'] == True
    assert len(result['amendment_plan']) > 0

def test_generate_amendment_no_need():
    result = generate_amendment(7.0, 20, 'HN')
    assert result['need_amendment'] == False
    assert result['amendment_plan'] == []

def test_evaluate_acidification_flow():
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_path = os.path.join(tmpdir, 'test.csv')
        # CSV 表头改标准码；用 CJ 一级区验证 region_code 正确分区（不再恒 HN）
        with open(csv_path, 'w', encoding='utf-8') as f:
            f.write('''YJNYQ,EJNYQ,SJD,YJZ,YXL,SXJ,TRRZ,GCZD,GGNL,PSNL,DXBW,ZDGX,YXTCHD,GCHD
长江中下游区,闽南粤中农林水产区,4.5,10,5,50,1.8,黏土,基本满足,基本满足,丘陵上部,夹层型,60,15
''')

        db_path = os.path.join(tmpdir, 'test.db')
        bulk_evaluate(csv_path, db_path)
        diagnose(db_path)  # 确保 is_ready 返回 True
        result = evaluate_acidification(db_path)

        assert result['status'] == 'ok'
        assert result['evaluated'] == 1

        query_result = query_acidification('0', db_path)
        assert query_result['status'] == 'ok'
        assert 'acidification' in query_result

def test_evaluate_acidification_uses_region_code():
    # 验证酸化评估按地块实际 region_code 分区，不恒回退 HN
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_path = os.path.join(tmpdir, 'test.csv')
        with open(csv_path, 'w', encoding='utf-8') as f:
            f.write('''YJNYQ,EJNYQ,SJD,YJZ,YXL,SXJ,TRRZ,GCZD,GGNL,PSNL,DXBW,ZDGX,YXTCHD,GCHD
长江中下游区,闽南粤中农林水产区,4.5,10,5,50,1.8,黏土,基本满足,基本满足,丘陵上部,夹层型,60,15
''')
        db_path = os.path.join(tmpdir, 'test.db')
        bulk_evaluate(csv_path, db_path)
        diagnose(db_path)
        evaluate_acidification(db_path)

        # 直接查 evaluation_results 确认 region_code 为 CJ
        storage = DiagnosisStorage(db_path)
        eval_row = storage.get_evaluation('0')
        assert eval_row['region_code'] == 'CJ'
        # CJ 区强酸性 pH=4.5 应触发改良
        acid = storage.get_acidification('0')
        assert acid is not None
        assert acid['acidification_level'] == '强酸性'
```

- [ ] **Step 2: 运行 acidification 测试确认失败**

Run: `pytest tests/test_farmland_diagnosis.py -k "acidification" -v`
Expected: FAIL（`test_evaluate_acidification_flow` CSV 表头非标准码导致 bulk_evaluate 报错；`test_evaluate_acidification_uses_region_code` 断言失败因旧实现读 'JY' 恒得 HN）

- [ ] **Step 3: 修正 acidification.py 字段引用（绿）**

仅修改 `evaluate_acidification` 函数中读取 row 的三行，其余不变。定位 `src/ai_culti_demo/farmland_diagnosis/acidification.py` 中：

```python
        pH = row.get('PH', 6.5)
        organic_matter = row.get('YJ', 20)
        region_code = row.get('JY', 'HN')
```

替换为：

```python
        pH = row.get('SJD', 6.5)
        organic_matter = row.get('YJZ', 20)
        region_code = row.get('region_code', 'HN')
```

同时移除文件顶部未使用的 `INDICATOR_NAME_MAP` 导入（如存在）。把：

```python
from .config import AMENDMENT_CONFIG, INDICATOR_NAME_MAP
```

改为：

```python
from .config import AMENDMENT_CONFIG
```

- [ ] **Step 4: 运行 acidification 测试确认通过**

Run: `pytest tests/test_farmland_diagnosis.py -k "acidification" -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add src/ai_culti_demo/farmland_diagnosis/acidification.py tests/test_farmland_diagnosis.py
git commit -m "fix(model-3): acidification 改读 SJD/YJZ/region_code，修复恒用 HN 区的读错列 bug"
```

---

### Task 6: __init__.py 导出更新

**Files:**
- Modify: `src/ai_culti_demo/farmland_diagnosis/__init__.py`

**Interfaces:**
- Consumes: Task 1-5 的产物
- Produces: 模块导出新增 `GRADE_CONFIG`/`INDICATOR_DISPLAY_MAP`/`DISCRETE_CN_MAP`/`ALL_INDICATORS`/`CONTINUOUS_INDICATORS`/`DISCRETE_INDICATORS`/`WEIGHTED_INDICATORS`/`translate_obstacle_level`/`replace_abbr_in_text`；移除 `COLUMN_RENAME`/`TEXT_VALUE_MAPS`/`INDICATOR_NAME_MAP` 导出。

- [ ] **Step 1: 重写 __init__.py**

用以下内容完整替换 `src/ai_culti_demo/farmland_diagnosis/__init__.py`：

```python
from .config import (
    REGION_MAP, SECONDARY_REGION_MAP,
    COEFFICIENTS, WEIGHTS, DISCRETE_CN_MAP, INDICATOR_DISPLAY_MAP,
    GRADE_CONFIG, ALL_INDICATORS, CONTINUOUS_INDICATORS,
    DISCRETE_INDICATORS, WEIGHTED_INDICATORS,
    AMENDMENT_CONFIG, calc_obstacle_level,
)
from .storage import DiagnosisStorage
from .evaluation import bulk_evaluate, evaluate_single, translate_obstacle_level
from .diagnosis import diagnosis_row, diagnose, query_parcel, replace_abbr_in_text
from .acidification import (
    classify_acidification, generate_amendment,
    evaluate_acidification, query_acidification,
)

__all__ = [
    'REGION_MAP', 'SECONDARY_REGION_MAP',
    'COEFFICIENTS', 'WEIGHTS', 'DISCRETE_CN_MAP', 'INDICATOR_DISPLAY_MAP',
    'GRADE_CONFIG', 'ALL_INDICATORS', 'CONTINUOUS_INDICATORS',
    'DISCRETE_INDICATORS', 'WEIGHTED_INDICATORS',
    'AMENDMENT_CONFIG', 'calc_obstacle_level',
    'DiagnosisStorage',
    'bulk_evaluate', 'evaluate_single', 'translate_obstacle_level',
    'diagnosis_row', 'diagnose', 'query_parcel', 'replace_abbr_in_text',
    'classify_acidification', 'generate_amendment',
    'evaluate_acidification', 'query_acidification',
]
```

- [ ] **Step 2: 验证导入无报错**

Run: `python -c "from src.ai_culti_demo.farmland_diagnosis import GRADE_CONFIG, INDICATOR_DISPLAY_MAP, DISCRETE_CN_MAP, ALL_INDICATORS, translate_obstacle_level, replace_abbr_in_text, diagnosis_row, query_parcel; print('import ok')"`
Expected: 输出 `import ok`

- [ ] **Step 3: 验证旧导出已移除**

Run: `python -c "from src.ai_culti_demo import farmland_diagnosis as m; assert not hasattr(m, 'COLUMN_RENAME'); assert not hasattr(m, 'TEXT_VALUE_MAPS'); assert not hasattr(m, 'INDICATOR_NAME_MAP'); print('old exports removed')"`
Expected: 输出 `old exports removed`

- [ ] **Step 4: 提交**

```bash
git add src/ai_culti_demo/farmland_diagnosis/__init__.py
git commit -m "refactor(model-3): __init__.py 导出新增标准码常量与诊断函数，移除旧导出"
```

---

### Task 7: problem_agent.py 消费端字段对齐

**Files:**
- Modify: `framework/agents/specialized/problem_agent.py`

**Interfaces:**
- Consumes: Task 4 的 `query_parcel` 返回的 `evaluation`（含 `GDZLDJ`）与 `diagnosis`（含 `ZALX`/`ZYZAYS`/`CYZAYS`，均为字符串）
- Produces: `answer_question` 改读 `evaluation.get("GDZLDJ")` / `diagnosis.get("ZALX")` / `diagnosis.get("ZYZAYS", "")`（字符串）/ `diagnosis.get("CYZAYS", "")`（字符串）；answer 文本拼接从 `'; '.join(list)` 改为直接用字符串；evidence 从 list 拆分改为直接引用字符串或按 `；` 切分取前几项。模拟数据回退路径（`MOCK_INDICATOR_GRADES`）不变。

- [ ] **Step 1: 修改 answer_question 真实诊断分支**

定位 `framework/agents/specialized/problem_agent.py` 中 `answer_question` 内 `if real_result:` 分支。把：

```python
            diagnosis = real_result.get("diagnosis", {})
            evaluation = real_result.get("evaluation", {})
            obstacle_type = diagnosis.get("obstacle_type", "无明显障碍")
            main_factors = diagnosis.get("main_factors", [])
            secondary_factors = diagnosis.get("secondary_factors", [])
            grade = evaluation.get("grade", "未知")
```

替换为：

```python
            diagnosis = real_result.get("diagnosis", {})
            evaluation = real_result.get("evaluation", {})
            obstacle_type = diagnosis.get("ZALX", "无明显障碍")
            main_factors_str = diagnosis.get("ZYZAYS", "")  # 已是 '；' 连接的可读字符串
            secondary_factors_str = diagnosis.get("CYZAYS", "")  # 已是 '；' 连接的可读字符串
            grade = evaluation.get("GDZLDJ", "未知")
            # 兼容 evidence 构造：按 '；' 切分为列表，空串/无 → 空列表
            main_factors = [f for f in main_factors_str.split('；') if f and f != '无'] if main_factors_str else []
            secondary_factors = [f for f in secondary_factors_str.split('；') if f and f != '无'] if secondary_factors_str else []
```

- [ ] **Step 2: 修改 answer 文本拼接（三个分支）**

在 `if real_result:` 分支内，三处 answer 文本当前用 `'; '.join(main_factors) if main_factors else '无'` 拼接。把这三处分别替换为直接使用 `main_factors_str` / `secondary_factors_str`：

第一处（"有没有问题"分支）：

```python
                answer = (
                    f"您的地块耕地质量诊断结果：障碍类型为{obstacle_type}。"
                    f"主要障碍因素：{main_factors_str or '无'}。"
                    f"耕地质量等级：{grade}级。"
                )
```

第二处（"县/乡镇/方面"分支）：

```python
                answer = (
                    f"障碍诊断结果：障碍类型为{obstacle_type}；"
                    f"主要障碍因素：{main_factors_str or '无'}；"
                    f"次要障碍因素：{secondary_factors_str or '无'}。"
                    f"耕地质量等级：{grade}级。"
                )
```

第三处（else 分支）：

```python
                answer = (
                    f"主要障碍因素：{main_factors_str or '无'}；"
                    f"次要障碍因素：{secondary_factors_str or '无'}。"
                    f"障碍类型：{obstacle_type}。"
                    f"耕地质量等级：{grade}级。"
                )
```

evidence 构造保持不变（仍用 `main_factors[:3]` / `secondary_factors[:3]`，因为上面已把字符串切分为列表）。

- [ ] **Step 3: 验证语法与导入**

Run: `python -c "import ast; ast.parse(open('framework/agents/specialized/problem_agent.py', encoding='utf-8').read()); print('syntax ok')"`
Expected: 输出 `syntax ok`

- [ ] **Step 4: 验证 problem_agent 可导入**

Run: `python -c "from framework.agents.specialized.problem_agent import ProblemIdentificationAgent; print('import ok')"`
Expected: 输出 `import ok`（若 framework 包结构需要特定导入方式，按项目实际方式导入）

- [ ] **Step 5: 提交**

```bash
git add framework/agents/specialized/problem_agent.py
git commit -m "refactor(model-3): problem_agent 消费端改读 GDZLDJ/ZALX/ZYZAYS/CYZAYS 标准字段"
```

---

### Task 8: 新增 4 个测试 + 全量测试通过

**Files:**
- Modify: `tests/test_farmland_diagnosis.py`

**Interfaces:**
- Consumes: Task 1-7 全部产物
- Produces: 新增 4 个测试（障碍度不覆盖原始值、diagnosis_row 返回字符串三元组、ZALX/ZYZAYS/CYZAYS 端到端、acidification 用 region_code 正确分区）；全量 `tests/test_farmland_diagnosis.py` 通过。

**说明：** Task 1-5 已分别更新对应模块的测试段。本任务新增 4 个跨模块/边界测试，并确保整文件全绿。其中"diagnosis_row 返回字符串三元组"与"acidification 用 region_code 正确分区"在 Task 4 / Task 5 已分别以 `test_diagnosis_row_single_obstacle`（断言 `isinstance(zyzays, str)`）和 `test_evaluate_acidification_uses_region_code` 形式覆盖。为避免重复，本任务新增的 4 个测试聚焦以下场景；若已存在等价测试则合并断言而非重复创建。

- [ ] **Step 1: 新增"障碍度不覆盖原始值"测试**

在 `tests/test_farmland_diagnosis.py` 末尾追加：

```python
def test_obstacle_degree_does_not_overwrite_original():
    # 障碍度存独立 xxxZAD 列，原始指标值 SJD/YJZ 等保持不变
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_path = os.path.join(tmpdir, 'test.csv')
        with open(csv_path, 'w', encoding='utf-8') as f:
            f.write('''YJNYQ,EJNYQ,SJD,YJZ,YXL,SXJ,TRRZ,GCZD,GGNL,PSNL,DXBW,ZDGX,YXTCHD,GCHD
华南区,闽南粤中农林水产区,4.5,10,5,50,1.8,黏土,基本满足,基本满足,丘陵上部,夹层型,60,15
''')
        db_path = os.path.join(tmpdir, 'test.db')
        bulk_evaluate(csv_path, db_path)

        storage = DiagnosisStorage(db_path)
        result = storage.get_evaluation('0')

        # 原始值未被覆盖
        assert result['SJD'] == 4.5
        assert result['YJZ'] == 10
        # 障碍度独立列存在
        assert 'SJDZAD' in result and result['SJDZAD'] is not None
        assert 'YJZZAD' in result and result['YJZZAD'] is not None
        # 障碍度列与原始值不同（原始值是测量值，障碍度是 0~1 占比）
        assert result['SJDZAD'] != result['SJD']
```

- [ ] **Step 2: 新增"diagnosis_row 返回字符串三元组"测试**

在 `tests/test_farmland_diagnosis.py` 末尾追加（与 Task 4 的 `test_diagnosis_row_single_obstacle` 互补，此处显式断言三元组类型与中文显示名）：

```python
def test_diagnosis_row_returns_string_triple():
    row = pd.Series({
        'SJDZADJ': '重度酸化', 'SJDZAD': 0.30,
        'SXJZADJ': '重度缺乏', 'SXJZAD': 0.25,
    })
    level_cols = [ind + 'ZADJ' for ind in WEIGHTED_INDICATORS]
    degree_cols = [ind + 'ZAD' for ind in WEIGHTED_INDICATORS]
    result = diagnosis_row(row, WEIGHTED_INDICATORS, level_cols, degree_cols)

    assert isinstance(result, tuple) and len(result) == 3
    zalx, zyzays, cyzays = result
    assert isinstance(zalx, str)
    assert isinstance(zyzays, str)
    assert isinstance(cyzays, str)
    # 缩写已替换为中文显示名
    assert 'pH' in zyzays
    assert '速效钾' in zyzays
    assert 'SJD' not in zyzays
    assert 'SXJ' not in zyzays
```

- [ ] **Step 3: 新增"ZALX/ZYZAYS/CYZAYS 端到端"测试**

在 `tests/test_farmland_diagnosis.py` 末尾追加：

```python
def test_end_to_end_zalx_zyzays_cyzays():
    # 端到端：bulk_evaluate → diagnose → query_parcel 返回 ZALX/ZYZAYS/CYZAYS
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_path = os.path.join(tmpdir, 'test.csv')
        with open(csv_path, 'w', encoding='utf-8') as f:
            f.write('''YJNYQ,EJNYQ,SJD,YJZ,YXL,SXJ,TRRZ,GCZD,GGNL,PSNL,DXBW,ZDGX,YXTCHD,GCHD
华南区,闽南粤中农林水产区,4.5,10,5,50,1.8,黏土,基本满足,基本满足,丘陵上部,夹层型,60,15
''')
        db_path = os.path.join(tmpdir, 'test.db')
        bulk_evaluate(csv_path, db_path)
        diagnose(db_path)

        result = query_parcel('0', db_path)
        assert result['status'] == 'ok'
        diag = result['diagnosis']
        eval_data = result['evaluation']

        # 诊断三字段均为字符串
        assert isinstance(diag['ZALX'], str)
        assert isinstance(diag['ZYZAYS'], str)
        assert isinstance(diag['CYZAYS'], str)
        # 评价返回标准字段
        assert 'GDZLDJ' in eval_data
        assert 'ZHQZ' in eval_data
        # 障碍地块应有非空 ZALX
        assert diag['ZALX'] in ('单一障碍', '多障碍', '无明显障碍')
        # CYZAYS 空时归一为 '无'
        assert diag['CYZAYS'] == '无' or diag['CYZAYS'] != ''
```

- [ ] **Step 4: 新增"acidification 用 region_code 正确分区"测试（如 Task 5 未覆盖）**

Task 5 的 `test_evaluate_acidification_uses_region_code` 已覆盖此场景。若该测试已存在则跳过本步；否则在末尾追加：

```python
def test_acidification_uses_region_code_not_jy():
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_path = os.path.join(tmpdir, 'test.csv')
        with open(csv_path, 'w', encoding='utf-8') as f:
            f.write('''YJNYQ,EJNYQ,SJD,YJZ,YXL,SXJ,TRRZ,GCZD,GGNL,PSNL,DXBW,ZDGX,YXTCHD,GCHD
长江中下游区,闽南粤中农林水产区,4.5,10,5,50,1.8,黏土,基本满足,基本满足,丘陵上部,夹层型,60,15
''')
        db_path = os.path.join(tmpdir, 'test.db')
        bulk_evaluate(csv_path, db_path)
        diagnose(db_path)
        evaluate_acidification(db_path)

        storage = DiagnosisStorage(db_path)
        eval_row = storage.get_evaluation('0')
        assert eval_row['region_code'] == 'CJ'  # 不再恒 HN
```

- [ ] **Step 5: 运行全量 model-3 测试**

Run: `pytest tests/test_farmland_diagnosis.py -v`
Expected: PASS（全部测试通过）

- [ ] **Step 6: 提交**

```bash
git add tests/test_farmland_diagnosis.py
git commit -m "test(model-3): 新增障碍度不覆盖原始值/三元组/端到端/region_code 分区测试"
```

---

### Task 9: 整体回归验证

**Files:**
- 无文件改动（仅验证）

**Interfaces:**
- Consumes: Task 1-8 全部产物
- Produces: 验证报告（单测全绿 + 整体回归无 model-1/model-7 破坏）

- [ ] **Step 1: 运行 model-3 单测确认全绿**

Run: `pytest tests/test_farmland_diagnosis.py -v`
Expected: PASS（所有测试通过，0 failed）

- [ ] **Step 2: 运行整体测试套件确认无回归**

Run: `pytest tests/ -v`
Expected: PASS（model-1 / model-7 等其他模型测试无回归；若存在跨模型集成测试，确认其通过或仅因本变更预期行为调整而需同步更新）

**注意：** 若整体套件中出现非 model-3 的失败，需逐一判断是否为本变更引入：
- 若失败测试引用了 `farmland_diagnosis` 的旧字段名（PH/YJ/_LD/_OD/obstacle_type/main_factors 等），需在该测试处同步改为标准码（属本变更范围）。
- 若失败测试与 model-3 无关，则不是本变更引入，记录但不在本任务修复。

- [ ] **Step 3: 验证标准测试数据输出字段名（可选 golden test）**

若 V2.0 测试数据 `test.csv` / `test_result.csv` 可访问，运行一次 `bulk_evaluate` 对照输出字段名：

Run: `python -c "import pandas as pd; df=pd.read_csv('D:/destkop/模型3_V2.0 (2)/模型3_V2.0/模型3_V2.0/test_result.csv'); print(list(df.columns))"`
Expected: 输出含 `SJDLSD`/`ZHQZ`/`GDZLDJ`/`SJDZAD`/`SJDZADJ`/`ZALX`/`ZYZAYS`/`CYZAYS` 等标准列名。本变更输出字段名应与此一致。

- [ ] **Step 4: 提交（如有回归修复）**

若 Step 2 触发了非 model-3 测试的同步字段更新：

```bash
git add <受影响的测试文件>
git commit -m "test(model-3): 同步跨模型测试中 model-3 字段引用为标准码"
```

若无改动，跳过本步。

---

### Task 10: 文档纳入确认

**Files:**
- Verify: `docs/model-integration-analysis.md`
- Verify: `docs/model-provider-spec.md`

**Interfaces:**
- Consumes: 无
- Produces: 确认两份文档已纳入版本控制（design 8.10 / tasks 8.1 要求）。

- [ ] **Step 1: 确认两份文档已在版本控制中**

Run: `git ls-files docs/model-integration-analysis.md docs/model-provider-spec.md`
Expected: 输出两行文件路径（均已被 git 跟踪）。若无输出，说明未纳入版本控制，执行 `git add docs/model-integration-analysis.md docs/model-provider-spec.md`。

- [ ] **Step 2: 确认文档无未提交改动（或属本变更预期）**

Run: `git status docs/model-integration-analysis.md docs/model-provider-spec.md`
Expected: 无未跟踪 / 或仅有本变更相关的预期改动。

- [ ] **Step 3: 若 Step 1 触发了 git add，提交**

```bash
git add docs/model-integration-analysis.md docs/model-provider-spec.md
git commit -m "docs(model-3): 纳入模型集成分析与模型提供方规范文档"
```

若无改动，跳过本步。

---

## Self-Review

**1. Spec coverage（delta spec 场景对照）：**
- "执行批量评价"（YJNYQ/EJNYQ/SJD/.../GCHD 必需字段 → xxxLSD/ZHQZ/GDZLDJ）→ Task 3 `bulk_evaluate`/`evaluate_single` + Task 3 测试 `test_bulk_evaluate`。✓
- "障碍度不覆盖原始值"（xxxZAD 独立列，原始值不变）→ Task 3 `evaluate_single`（`result[ind+'ZAD']` 独立，`result[ind]` 保留）+ Task 8 `test_obstacle_degree_does_not_overwrite_original`。✓
- "CSV 字段缺失"（返回缺失字段列表）→ Task 3 `bulk_evaluate` missing 检查 + Task 3 `test_bulk_evaluate_missing_columns`。✓
- "区域名称无效"（列出无效区域行号）→ Task 3 `bulk_evaluate` YJNYQ_code/EJNYQ_code isna 检查。✓
- "执行障碍诊断"（ZALX/ZYZAYS/CYZAYS，含中文指标名，无次要因素显示"无"）→ Task 4 `diagnosis_row` + `replace_abbr_in_text` + '无' 归一。✓
- "障碍度计算"（(1-LSD)×权重/总和，xxxZAD；障碍等级 xxxZADJ 含方向描述）→ Task 3 `evaluate_single`（ZAD）+ Task 3/4 `translate_obstacle_level`（方向）。✓
- "无明显障碍"（ZALX=无明显障碍）→ Task 4 `diagnosis_row` 返回 '无明显障碍'。（注：spec 措辞"ZYZAYS/CYZAYS 为空"与 design 5.7"CYZAYS=无"有张力，实现遵循 design 5.7，已在 Task 4 标注。）✓
- "单一障碍" / "多障碍" → Task 4 `diagnosis_row` 阈值逻辑（threshold_main=0.20 等）+ Task 4 测试。✓
- "识别障碍组合类型"（ZALX=多障碍，ZYZAYS 含组合描述）→ Task 4 + Task 8 端到端测试。✓
- "查询指定地块"（返回 ZALX/ZYZAYS/CYZAYS/GDZLDJ）→ Task 4 `query_parcel` + Task 8 端到端测试。✓
- "诊断数据未就绪"（status:not_ready）→ Task 2/4 `is_ready` + `query_parcel`。✓
- "酸化改良模块字段对齐"（SJD/YJZ/region_code，不引用 PH/YJ/JY）→ Task 5 + Task 5/8 region_code 测试。✓
- "导入新 CSV 数据" / "导入数据格式校验"（标准字段命名 YJNYQ/SJD/...）→ Task 3 `bulk_evaluate` required 检查（导入接口本身未改动，复用现有路由）。✓

**2. Placeholder scan：** 全部步骤含具体代码/命令/期望输出，无 TBD/TODO/"add error handling" 等占位。✓

**3. Type consistency：** `diagnosis_row` 签名 `(row, indicator_names, level_cols, degree_cols) -> (ZALX, ZYZAYS, CYZAYS)` 在 Task 4 定义、Task 4/8 测试、Task 7 消费端一致；`translate_obstacle_level(ind, level, orig_val)` 在 Task 3 定义、Task 3 测试一致；`replace_abbr_in_text(text, abbr_map)` 在 Task 4 定义、Task 4 测试一致；标准指标码常量 `ALL_INDICATORS`/`WEIGHTED_INDICATORS` 在 Task 1 定义、Task 2/3/4 消费一致；DB 列名 `xxxLSD`/`xxxZADJ`/`xxxZAD`/`ZHQZ`/`GDZLDJ`/`ZALX`/`ZYZAYS`/`CYZAYS` 在 Task 2-4、Task 7-8 一致。✓

