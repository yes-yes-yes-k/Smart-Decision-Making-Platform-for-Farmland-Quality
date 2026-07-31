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
ALL_INDICATORS = ['SJD', 'YJZ', 'YXL', 'SXJ', 'TRRZ', 'GCZD', 'GGNL', 'PSNL', 'DXBW', 'ZDGX', 'YXTCHD', 'GCHD', 'JHX', 'JLA']
CONTINUOUS_INDICATORS = ['SJD', 'YJZ', 'YXL', 'SXJ', 'TRRZ', 'YXTCHD', 'GCHD', 'JHX', 'JLA']
DISCRETE_INDICATORS = ['GCZD', 'GGNL', 'PSNL', 'DXBW', 'ZDGX']
WEIGHTED_INDICATORS = ALL_INDICATORS  # 参与加权和障碍诊断

# 酸化模型专用指标（非耕地质量评价必填，bulk_evaluate 中作为可选列）
ACIDIFICATION_INDICATORS = ['JHX', 'JLA']

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
    'JHX': '交换性氢',
    'JLA': '交换性铝',
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
