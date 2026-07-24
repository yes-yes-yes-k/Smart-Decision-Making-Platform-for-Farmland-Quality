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
