"""县域常规统计（返回数据）"""
from typing import List, Optional
from .config import EvaluationConfig
from .models import Parcel, CountyStats

def county_statistics_data(config: EvaluationConfig, parcels: List[Parcel], xqmc_code: int) -> Optional[CountyStats]:
    from .evaluation import evaluate_land_quality
    from .obstacle import calc_limiting_factors

    county_parcels = [p for p in parcels if p.xqmc == xqmc_code]
    n = len(county_parcels)
    if n == 0:
        return None

    sum_mj = 0.0
    sum_ind = [0.0]*12
    min_ind = [1e30]*12
    max_ind = [-1e30]*12
    cnt_grade = [0]*10
    mj_grade = [0.0]*10
    cnt_primary = [0]*12
    mj_primary = [0.0]*12
    lim_factors_all = []
    grades_list = []
    areas = []

    for p in county_parcels:
        mj = p.mj
        areas.append(mj)
        sum_mj += mj
        res = evaluate_land_quality(config, p)
        grades_list.append(res.grade)
        lf = calc_limiting_factors(config, p.ejnyq, res.y)
        lim_factors_all.append(lf)

        if 1 <= res.grade <= 10:
            cnt_grade[res.grade-1] += 1
            mj_grade[res.grade-1] += mj

        raw_vals = [p.sjd, p.yjz, p.yxl, p.sxj, p.trrz, p.yxtchd, p.gchd,
                    float(p.zdgc), float(p.psnl), float(p.ggnl), float(p.dxbw), float(p.zdgx)]
        for j in range(12):
            v = raw_vals[j]
            sum_ind[j] += v
            if v < min_ind[j]: min_ind[j] = v
            if v > max_ind[j]: max_ind[j] = v

    avg_ind = [sum_ind[j]/n for j in range(12)]
    avg_lim = [sum(lf[j] for lf in lim_factors_all)/n for j in range(12)]
    avg_grade = sum(grades_list)/n

    # 首要障碍统计
    for idx, lf in enumerate(lim_factors_all):
        max_val = -1.0
        max_idx = -1
        for j in range(12):
            if lf[j] > max_val:
                max_val = lf[j]
                max_idx = j
        if max_idx >= 0:
            cnt_primary[max_idx] += 1
            mj_primary[max_idx] += areas[idx]

    sorted_avg, sorted_names = zip(*sorted(zip(avg_lim, config.indicator_names), reverse=True))
    return CountyStats(
        county_name=config.xqmc_names[xqmc_code-1],
        parcel_count=n, total_area=sum_mj, avg_grade=avg_grade,
        avg_ind=avg_ind, min_ind=min_ind, max_ind=max_ind,
        avg_lim_factors=avg_lim,
        sorted_avg_factors=list(sorted_avg), sorted_names=list(sorted_names),
        cnt_grade=cnt_grade, mj_grade=mj_grade,
        cnt_primary=cnt_primary, mj_primary=mj_primary
    )
