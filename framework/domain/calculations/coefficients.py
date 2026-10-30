"""模型系数配置 — 移植自原始 模型2/config.py 和 模型3/mappings_config.py。

原始来源:
- D:\\destkop\\模型1-5\\模型2\\config.py (EvaluationConfig)
- D:\\destkop\\模型1-5\\模型3_V2.0\\mappings_config.py
"""
from __future__ import annotations

# area_code → 农业区映射。
#
# 与模型 2 原始 CSV 的 XQMCcode/EJNYQcode 对照保持一致：
# 韶关 10 个县级行政区中，武江区属 MNY，其余属 NL。
AREA_TO_REGION = {
    "440203": {"secondary": "MNY", "primary": "HN", "ejnyq_idx": 0},
    "440204": {"secondary": "NL", "primary": "HN", "ejnyq_idx": 3},
    "440205": {"secondary": "NL", "primary": "HN", "ejnyq_idx": 3},
    "440222": {"secondary": "NL", "primary": "HN", "ejnyq_idx": 3},
    "440224": {"secondary": "NL", "primary": "HN", "ejnyq_idx": 3},
    "440229": {"secondary": "NL", "primary": "HN", "ejnyq_idx": 3},
    "440232": {"secondary": "NL", "primary": "HN", "ejnyq_idx": 3},
    "440233": {"secondary": "NL", "primary": "HN", "ejnyq_idx": 3},
    "440281": {"secondary": "NL", "primary": "HN", "ejnyq_idx": 3},
    "440282": {"secondary": "NL", "primary": "HN", "ejnyq_idx": 3},
}

# Model-2 系数（4 个二级农业区，移植自 EvaluationConfig）
# ejnyq_idx: 0=MNY 闽南粤中, 1=YXG 粤西桂南, 2=QN 琼雷, 3=NL 南岭
# 数值指标顺序: [SJD, YJZ, YXL, SXJ, TRRZ, YXTCHD, GCHD] (7 个)
MODEL2_COEFFICIENTS = {
    0: {
        "a": [0.221129, 0.002163, 0.003800, 0.000068, 2.786523, 0.000230, 0.019247],
        "c": [6.70, 38.0, 40.0, 205.0, 1.35, 100.0, 20.2],
        "ut1": [4.0, 6.0, 5.0, 30.0, 0.90, 10.0, 5.0],
        "ut2": [9.5, 38.0, 40.0, 205.0, 2.10, 100.0, 20.2],
        # 概念指标隶属度（已从 list 索引转为字符串代码为键的 dict）
        "mem_zdgc": {"SRST": 0.40, "SRT": 0.75, "RT": 1.00, "FRT": 0.95, "SNRT": 0.85,
                     "NRT": 0.80, "FNRT": 0.90, "SNT": 0.60, "RNT": 0.40, "FNT": 0.65,
                     "NT": 0.55, "ZNT": 0.50},
        "mem_psnl": {"CM": 1.0, "M": 0.8, "JM": 0.6, "BM": 0.3},
        "mem_ggnl": {"FS": 1.0, "S": 0.8, "BS": 0.6, "US": 0.3},
        "mem_dxbw": {"PLT": 1.0, "PMG": 0.9, "PUG": 0.8, "WVB": 0.9, "MB": 0.7,
                     "LHR": 0.6, "MPH": 0.5, "UHR": 0.4, "MSL": 0.5, "MSM": 0.3, "MSU": 0.2},
        "mem_zdgx": {"TLBC": 1.0, "St": 0.8, "IL": 0.7, "Ct": 0.5, "TCBL": 0.4, "TL": 0.3, "Lt": 0.2},
        "weights": [0.0668, 0.0958, 0.0574, 0.0736, 0.0596, 0.0716, 0.0585,
                    0.0827, 0.1057, 0.1253, 0.1240, 0.0790],
    },
    1: {  # YXG — 与 0 相同（原始 config 中 index 0-2 相同）
        "a": [0.221129, 0.002163, 0.003800, 0.000068, 2.786523, 0.000230, 0.019247],
        "c": [6.70, 38.0, 40.0, 205.0, 1.35, 100.0, 20.2],
        "ut1": [4.0, 6.0, 5.0, 30.0, 0.90, 10.0, 5.0],
        "ut2": [9.5, 38.0, 40.0, 205.0, 2.10, 100.0, 20.2],
        "mem_zdgc": {"SRST": 0.40, "SRT": 0.75, "RT": 1.00, "FRT": 0.95, "SNRT": 0.85,
                     "NRT": 0.80, "FNRT": 0.90, "SNT": 0.60, "RNT": 0.40, "FNT": 0.65,
                     "NT": 0.55, "ZNT": 0.50},
        "mem_psnl": {"CM": 1.0, "M": 0.8, "JM": 0.6, "BM": 0.3},
        "mem_ggnl": {"FS": 1.0, "S": 0.8, "BS": 0.6, "US": 0.3},
        "mem_dxbw": {"PLT": 1.0, "PMG": 0.9, "PUG": 0.8, "WVB": 0.9, "MB": 0.7,
                     "LHR": 0.6, "MPH": 0.5, "UHR": 0.4, "MSL": 0.5, "MSM": 0.3, "MSU": 0.2},
        "mem_zdgx": {"TLBC": 1.0, "St": 0.8, "IL": 0.7, "Ct": 0.5, "TCBL": 0.4, "TL": 0.3, "Lt": 0.2},
        "weights": [0.0668, 0.0958, 0.0574, 0.0736, 0.0596, 0.0716, 0.0585,
                    0.0827, 0.1057, 0.1253, 0.1240, 0.0790],
    },
    2: {  # QN — 与 0 相同
        "a": [0.221129, 0.002163, 0.003800, 0.000068, 2.786523, 0.000230, 0.019247],
        "c": [6.70, 38.0, 40.0, 205.0, 1.35, 100.0, 20.2],
        "ut1": [4.0, 6.0, 5.0, 30.0, 0.90, 10.0, 5.0],
        "ut2": [9.5, 38.0, 40.0, 205.0, 2.10, 100.0, 20.2],
        "mem_zdgc": {"SRST": 0.40, "SRT": 0.75, "RT": 1.00, "FRT": 0.95, "SNRT": 0.85,
                     "NRT": 0.80, "FNRT": 0.90, "SNT": 0.60, "RNT": 0.40, "FNT": 0.65,
                     "NT": 0.55, "ZNT": 0.50},
        "mem_psnl": {"CM": 1.0, "M": 0.8, "JM": 0.6, "BM": 0.3},
        "mem_ggnl": {"FS": 1.0, "S": 0.8, "BS": 0.6, "US": 0.3},
        "mem_dxbw": {"PLT": 1.0, "PMG": 0.9, "PUG": 0.8, "WVB": 0.9, "MB": 0.7,
                     "LHR": 0.6, "MPH": 0.5, "UHR": 0.4, "MSL": 0.5, "MSM": 0.3, "MSU": 0.2},
        "mem_zdgx": {"TLBC": 1.0, "St": 0.8, "IL": 0.7, "Ct": 0.5, "TCBL": 0.4, "TL": 0.3, "Lt": 0.2},
        "weights": [0.0668, 0.0958, 0.0574, 0.0736, 0.0596, 0.0716, 0.0585,
                    0.0827, 0.1057, 0.1253, 0.1240, 0.0790],
    },
    3: {  # NL 南岭（乐昌）— 不同系数
        "a": [0.221129, 0.001842, 0.002025, 0.000081, 2.236726, 0.000205, 0.019247],
        "c": [6.811204, 33.656446, 33.346824, 181.622535, 1.211674, 99.092342, 20.2],
        "ut1": [3.0, 0.0, 0.0, 0.0, 0.50, 10.0, 5.0],
        "ut2": [10.0, 33.7, 33.3, 192.0, 3.21, 99.9, 20.0],
        "mem_zdgc": {"SRST": 0.40, "SRT": 0.75, "RT": 1.00, "FRT": 0.95, "SNRT": 0.85,
                     "NRT": 0.80, "FNRT": 0.90, "SNT": 0.60, "RNT": 0.40, "FNT": 0.65,
                     "NT": 0.55, "ZNT": 0.50},
        "mem_psnl": {"CM": 1.0, "M": 0.8, "JM": 0.6, "BM": 0.3},
        "mem_ggnl": {"FS": 1.0, "S": 0.8, "BS": 0.6, "US": 0.3},
        "mem_dxbw": {"PLT": 1.0, "PMG": 0.95, "PUG": 0.9, "WVB": 0.95, "MB": 0.8,
                     "LHR": 0.8, "MPH": 0.6, "UHR": 0.7, "MSL": 0.68, "MSM": 0.45, "MSU": 0.3},
        "mem_zdgx": {"TLBC": 1.0, "St": 0.95, "Ct": 0.75, "IL": 0.85, "TCBL": 0.4, "TL": 0.55, "Lt": 0.3},
        "weights": [0.0704, 0.1046, 0.0557, 0.0681, 0.0494, 0.0579, 0.0594,
                    0.0905, 0.1070, 0.1369, 0.1270, 0.0731],
    },
}

# Model-2 原始等级分界（按二级农业区 ejnyq_idx）。
# 列表从 1 等到 9 等的下限降序排列，未达到最后一个下限时为 10 等。
MODEL2_GRADE_LIMITS = {
    0: [0.8850, 0.8619, 0.8388, 0.8157, 0.7926, 0.7695, 0.7464, 0.7233, 0.7002],
    1: [0.8850, 0.8619, 0.8388, 0.8157, 0.7926, 0.7695, 0.7464, 0.7233, 0.7002],
    2: [0.8850, 0.8619, 0.8388, 0.8157, 0.7926, 0.7695, 0.7464, 0.7233, 0.7002],
    3: [0.9170, 0.8924, 0.8678, 0.8431, 0.8185, 0.7939, 0.7693, 0.7446, 0.7200],
}

# Model-3 隶属度系数（按一级农业区 HN/CJ，移植自 COEFFICIENTS）
MODEL3_COEFFICIENTS = {
    "HN": {
        "SJD":   {"a": 0.256941, "c": 6.7, "L": 4.0, "U": 9.5},
        "YJZ":   {"a": 0.002163, "c": 38, "L": 6.0, "U": 38.0},
        "YXL":   {"a": 0.0038, "c": 40, "L": 5.0, "U": 40.0},
        "SXJ":   {"a": 0.000068, "c": 205, "L": 30, "U": 205},
        "TRRZ":  {"a": 2.786523, "c": 1.35, "L": 0.9, "U": 2.1},
        "YXTCHD":{"a": 0.00023, "c": 100, "L": 10, "U": 100},
        "GCHD":  {"a": 0.019247, "c": 20.2, "L": 5, "U": 20.2},
        "GCZD":  {"RT": 1, "FRT": 0.95, "FNRT": 0.9, "SNRT": 0.85, "NRT": 0.8, "SRT": 0.75,
                  "RNT": 0.7, "FNT": 0.65, "SNT": 0.6, "NT": 0.55, "ZNT": 0.5, "SRST": 0.4},
        "GGNL":  {"FS": 1, "S": 0.8, "BS": 0.6, "US": 0.3},
        "PSNL":  {"CM": 1, "M": 0.8, "JM": 0.6, "BM": 0.3},
        "DXBW":  {"MB": 0.7, "WVB": 0.9, "PLT": 1, "PMG": 0.9, "PUG": 0.8,
                  "UHR": 0.4, "MPH": 0.5, "LHR": 0.6, "MSU": 0.2, "MSM": 0.3, "MSL": 0.5},
        "ZDGX":  {"TL": 0.3, "Lt": 0.2, "Ct": 0.5, "IL": 0.7, "TCBL": 0.4, "TLBC": 1, "St": 0.8},
    },
    "CJ": {
        "SJD":   {"a": 0.221129, "c": 6.811204, "L": 3.0, "U": 10},
        "YJZ":   {"a": 0.0018842, "c": 33.656446, "L": 0, "U": 33.7},
        "YXL":   {"a": 0.002025, "c": 33.346824, "L": 4.0, "U": 33.3},
        "SXJ":   {"a": 0.000081, "c": 181.622535, "L": 0, "U": 182},
        "TRRZ":  {"a": 2.236726, "c": 1.211674, "L": 0.5, "U": 2.21},
        "YXTCHD":{"a": 0.000205, "c": 99.092342, "L": 10, "U": 99},
        "GCHD":  {"a": 0.008008, "c": 23.333126, "L": 0, "U": 23},
        "GCZD":  {"RT": 1, "FRT": 0.95, "FNRT": 0.85, "SNRT": 0.75, "NRT": 0.9, "SRT": 0.65,
                  "RNT": 0.65, "FNT": 0.8, "SNT": 0.6, "NT": 0.62, "ZNT": 0.55, "SRST": 0.5},
        "GGNL":  {"FS": 1, "S": 0.8, "BS": 0.6, "US": 0.3},
        "PSNL":  {"CM": 1, "M": 0.8, "JM": 0.6, "BM": 0.3},
        "DXBW":  {"MB": 0.8, "WVB": 0.95, "PLT": 1, "PMG": 0.95, "PUG": 0.9,
                  "UHR": 0.6, "MPH": 0.7, "LHR": 0.8, "MSU": 0.3, "MSM": 0.45, "MSL": 0.68},
        "ZDGX":  {"TL": 0.55, "Lt": 0.3, "Ct": 0.75, "IL": 0.85, "TCBL": 0.4, "TLBC": 1, "St": 0.95},
    },
}

# Model-3 权重（按二级农业区 MNY/YXG/NL/QN，移植自 WEIGHTS）
MODEL3_WEIGHTS = {
    "MNY": {"GGNL": 0.1253, "DXBW": 0.124, "PSNL": 0.1057, "YJZ": 0.0958,
            "GCZD": 0.0827, "ZDGX": 0.079, "SXJ": 0.0736, "YXTCHD": 0.0716,
            "SJD": 0.0668, "TRRZ": 0.0596, "YXL": 0.0574, "GCHD": 0.0585},
    "YXG": {"GGNL": 0.1249, "DXBW": 0.1233, "PSNL": 0.1003, "YJZ": 0.1,
            "GCZD": 0.0815, "ZDGX": 0.0737, "SXJ": 0.0791, "YXTCHD": 0.0726,
            "SJD": 0.0678, "TRRZ": 0.0576, "YXL": 0.0602, "GCHD": 0.059},
    "NL": {"GGNL": 0.1369, "DXBW": 0.127, "PSNL": 0.107, "YJZ": 0.1046,
           "GCZD": 0.0905, "ZDGX": 0.0731, "SXJ": 0.0681, "YXTCHD": 0.05779,
           "SJD": 0.0704, "TRRZ": 0.0494, "YXL": 0.0577, "GCHD": 0.0594},
    "QN": {"GGNL": 0.1266, "DXBW": 0.1025, "PSNL": 0.1154, "YJZ": 0.1039,
           "GCZD": 0.08, "ZDGX": 0.0814, "SXJ": 0.0775, "YXTCHD": 0.0604,
           "SJD": 0.0726, "TRRZ": 0.0631, "YXL": 0.0607, "GCHD": 0.0499},
}

# 综合等级划分（按一级农业区，移植自 GRADE_CONFIG）
# (bounds, labels): qi >= bounds[i] → grade labels[i]
GRADE_CONFIG = {
    "HN": ([0, 0.6650, 0.6900, 0.7150, 0.7400, 0.7650, 0.7900, 0.8150, 0.8400, 0.8650, float("inf")],
           ["10", "9", "8", "7", "6", "5", "4", "3", "2", "1"]),
    "CJ": ([0, 0.6960, 0.7224, 0.7488, 0.7751, 0.8015, 0.8279, 0.8543, 0.8806, 0.9070, float("inf")],
           ["10", "9", "8", "7", "6", "5", "4", "3", "2", "1"]),
}

# 障碍等级阈值（移植自 calc_obstacle_level 函数逻辑）
# 每个指标按阈值返回: "重度障碍" / "中度障碍" / "轻度障碍" / "无障碍"
OBSTACLE_THRESHOLDS = {
    "SJD": {"heavy": [(None, 4.5), (9.5, None)], "moderate": [(4.5, 5.5), (8.5, 9.5)],
            "light": [(5.5, 6.5), (7.5, 8.5)], "none": [(6.5, 7.5)]},
    "YJZ": {"heavy": [(None, 10)], "moderate": [(10, 20)], "light": [(20, 25)], "none": [(25, None)]},
    "YXL": {"heavy": [(None, 10)], "moderate": [(10, 20)], "light": [(20, 35)], "none": [(35, None)]},
    "SXJ": {"heavy": [(None, 50)], "moderate": [(50, 100)], "light": [(100, 150)], "none": [(150, None)]},
    "TRRZ": {"heavy": [(None, 0.9), (1.4, None)], "moderate": [(0.9, 0.95), (1.3, 1.4)],
             "light": [(0.95, 1.0), (1.2, 1.3)], "none": [(1.0, 1.2)]},
    "GCHD": {"heavy": [(None, 10)], "moderate": [(10, 15)], "light": [(15, 20)], "none": [(20, None)]},
    "YXTCHD": {"heavy": [(None, 60)], "moderate": [(60, 80)], "light": [(80, 100)], "none": [(100, None)]},
    # 概念指标障碍等级按代码映射
    "GGNL": {"heavy": ["US"], "moderate": ["BS"], "light": ["S"], "none": ["FS"]},
    "PSNL": {"heavy": ["BM"], "moderate": ["JM"], "light": ["M"], "none": ["CM"]},
    "ZDGX": {"heavy": ["TCBL", "TL", "Lt"], "moderate": ["Ct"], "light": ["IL"], "none": ["TLBC", "St"]},
    # GCZD/DXBW 按隶属度判定（calc_obstacle_level 中特殊处理）
    "GCZD": "by_membership",  # 0.4-0.6 重度, 0.6-0.7 中度, 0.75-0.85 轻度, 0.9-1.0 无
    "DXBW": "by_membership",  # 0.2-0.5 重度, 0.5-0.68 中度, 0.7-0.8 轻度, 0.9-1.0 无
}

# 原始中文→代码映射（移植自 DISCRETE_CN_MAP）
DISCRETE_CN_MAP = {
    "GCZD": {"壤土": "RT", "粉(砂)质壤土": "FRT", "粉(砂)质黏壤土": "FNRT", "砂质黏壤土": "SNRT",
             "黏壤土": "NRT", "砂质壤土": "SRT", "壤质黏土": "RNT", "粉(砂)质黏土": "FNT",
             "砂质黏土": "SNT", "黏土": "NT", "重黏土": "ZNT", "砂土及壤质砂土": "SRST"},
    "GGNL": {"充分满足": "FS", "满足": "S", "基本满足": "BS", "不满足": "US"},
    "PSNL": {"充分满足": "CM", "满足": "M", "基本满足": "JM", "不满足": "BM"},
    "DXBW": {"山间盆地": "MB", "宽谷盆地": "WVB", "平原低阶": "PLT", "平原中阶": "PMG",
             "平原高阶": "PUG", "丘陵上部": "UHR", "丘陵中部": "MPH", "丘陵下部": "LHR",
             "山地坡上": "MSU", "山地坡中": "MSM", "山地坡下": "MSL"},
    "ZDGX": {"薄层型": "TL", "松散型": "Lt", "紧实型": "Ct", "夹层型": "IL",
             "上紧下松型": "TCBL", "上松下紧型": "TLBC", "海绵型": "St"},
}

# 新增英文→代码映射（DB 实际存储英文值）
DISCRETE_EN_MAP = {
    "GCZD": {"loam": "RT", "sandy_loam": "SRT", "clay_loam": "NRT", "sandy_clay_loam": "SNRT",
             "silty_loam": "FRT", "silty_clay_loam": "FNRT", "clay": "NT", "sandy_clay": "SNT",
             "silty_clay": "FNT", "silt": "ZNT", "loamy_sand": "SRST"},
    "GGNL": {"dry": "US", "basic": "BS", "satisfied": "S", "irrigated": "FS"},
    "PSNL": {"dry": "BM", "basic": "JM", "satisfied": "M", "irrigated": "CM"},
    "DXBW": {"lower": "LHR", "middle": "MPH", "upper": "UHR"},
    "ZDGX": {"loose": "Lt", "compact": "Ct", "interlayer": "IL", "thin_layer": "TL",
             "upper_loose_lower_compact": "TCBL", "upper_compact_lower_loose": "TLBC", "sponge": "St"},
}

# 缩写 → 中文显示名（用于障碍因素描述，移植自 INDICATOR_DISPLAY_MAP）
INDICATOR_DISPLAY_MAP = {
    "SJD": "pH", "YJZ": "有机质", "YXL": "有效磷", "SXJ": "速效钾",
    "TRRZ": "容重", "GCZD": "耕层质地", "GGNL": "灌溉能力", "PSNL": "排水能力",
    "DXBW": "地形部位", "ZDGX": "质地构型", "YXTCHD": "有效土层", "GCHD": "耕层厚度",
}

# 12 指标缩写顺序（数值7 + 概念5）
NUMERIC_INDICATORS = ["SJD", "YJZ", "YXL", "SXJ", "TRRZ", "YXTCHD", "GCHD"]
CONCEPT_INDICATORS = ["GCZD", "GGNL", "PSNL", "DXBW", "ZDGX"]
ALL_INDICATORS = NUMERIC_INDICATORS + CONCEPT_INDICATORS  # 12 个

# 峰型指标索引（0-based）：SJD(0) 和 TRRZ(4) 为峰型，其余戒上型
PEAK_TYPE_INDICES = {0, 4}
