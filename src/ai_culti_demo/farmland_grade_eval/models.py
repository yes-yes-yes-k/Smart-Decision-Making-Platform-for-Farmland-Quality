from dataclasses import dataclass, field
from typing import List

@dataclass
class Parcel:
    tybh: str
    jd: float
    wd: float
    mj: float
    sjd: float
    yjz: float
    yxl: float
    sxj: float
    trrz: float
    yxtchd: float
    gchd: float
    jhxllz: float
    jhxqlz: float
    ejnyq: int
    xqmc: int
    zdgc: int
    psnl: int
    ggnl: int
    dxbw: int
    zdgx: int

@dataclass
class QualityResult:
    y: List[float]
    quality_index: float
    grade: int

@dataclass
class ObstacleItem:
    name: str
    factor: float
    degree: str

# 用于潜力分析的返回结构
@dataclass
class PotentialItem:
    indicator_name: str
    original_value: str
    potential_value: str
    original_quality_index: float
    potential_quality_index: float
    original_grade: int
    potential_grade: int

@dataclass
class CountyStats:
    county_name: str
    parcel_count: int
    total_area: float
    avg_grade: float
    avg_ind: List[float]
    min_ind: List[float]
    max_ind: List[float]
    avg_lim_factors: List[float]
    sorted_avg_factors: List[float]
    sorted_names: List[str]
    cnt_grade: List[int]
    mj_grade: List[float]
    cnt_primary: List[int]
    mj_primary: List[float]

@dataclass
class CountyPotentialResult:
    scenario: int
    county_name: str
    parcel_count: int
    total_area: float
    avg_grade_pot: float
    avg_ind_pot: List[float]
    min_ind_pot: List[float]
    max_ind_pot: List[float]
    avg_lim_pot: List[float]
    sorted_avg_pot: List[float]
    sorted_names_pot: List[str]
    cnt_grade_pot: List[int]
    mj_grade_pot: List[float]
    cnt_primary_pot: List[int]
    mj_primary_pot: List[float]
    # 原始对比数据
    avg_grade_orig: float
    avg_ind_orig: List[float]
    avg_contrib_orig: List[float]
    avg_contrib_pot: List[float]
    cnt_grade_orig: List[int]
    mj_grade_orig: List[float]
