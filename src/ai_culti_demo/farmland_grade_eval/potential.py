"""潜力分析（纯计算，不输出）"""
import math
from typing import List, Tuple, Optional
from .config import EvaluationConfig
from .models import Parcel, QualityResult, PotentialItem, CountyPotentialResult
from .evaluation import evaluate_land_quality

def compute_single_parcel_potential(config: EvaluationConfig, parcel: Parcel,
                                    y: List[float], quality_index: float, grade: int
                                   ) -> Tuple[List[PotentialItem], QualityResult]:
    """
    单个地块潜力分析。
    返回：
        (逐指标潜力项列表, 全改良后的 QualityResult)
    """
    idx_pool = [10, 9, 2, 4, 3, 6, 5, 1, 7]   # 改良顺序
    c_col    = [0, 0, 2, 4, 3, 6, 5, 1, 7]    # 数值型对应c矩阵列
    potential_ind_names = [
        '灌溉能力  ', '排水能力  ', '有机质    ', '速效钾    ', '有效磷    ',
        '有效土层厚度', '土壤容重  ', '酸碱度    ', '耕层厚度  '
    ]
    is_numeric = [False, False, True, True, True, True, True, True, True]

    # 计算每个指标的障碍度因子（用于跳过无影响的指标）
    d_total = sum((1.0 - v) * config.weights[parcel.ejnyq-1][i] for i, v in enumerate(y))
    if d_total != 0.0:
        lim_factor = [(1.0 - y[i]) * config.weights[parcel.ejnyq-1][i] / d_total for i in range(12)]
    else:
        lim_factor = [0.0] * 12

    potential_items = []

    for k, i in enumerate(idx_pool):
        if lim_factor[i-1] <= 1e-6:
            continue

        # 原始值/潜力值字符串
        if is_numeric[k]:
            orig_vals = [parcel.sjd, parcel.yjz, parcel.yxl, parcel.sxj, parcel.trrz,
                         parcel.yxtchd, parcel.gchd]
            orig = orig_vals[c_col[k]-1]
            poten = config.c[parcel.ejnyq-1][c_col[k]-1]
            orig_str = f"{orig:8.3f}"
            poten_str = f"{poten:8.3f}"
        else:
            if i == 10:
                orig_str = f"{config.ggnl_names[parcel.ggnl-1].strip():8}"
            else:
                orig_str = f"{config.psnl_names[parcel.psnl-1].strip():8}"
            poten_str = "充分满足"

        # 构造改良后的指标
        new_sjd, new_yjz, new_yxl, new_sxj = parcel.sjd, parcel.yjz, parcel.yxl, parcel.sxj
        new_trrz, new_yxtchd, new_gchd = parcel.trrz, parcel.yxtchd, parcel.gchd
        new_psnl, new_ggnl = parcel.psnl, parcel.ggnl

        if i == 1:
            new_sjd = config.c[parcel.ejnyq-1][0]
        elif i == 2:
            new_yjz = config.c[parcel.ejnyq-1][1]
        elif i == 3:
            new_yxl = config.c[parcel.ejnyq-1][2]
        elif i == 4:
            new_sxj = config.c[parcel.ejnyq-1][3]
        elif i == 5:
            new_trrz = config.c[parcel.ejnyq-1][4]
        elif i == 6:
            new_yxtchd = config.c[parcel.ejnyq-1][5]
        elif i == 7:
            new_gchd = config.c[parcel.ejnyq-1][6]
        elif i == 9:
            new_psnl = 1
        elif i == 10:
            new_ggnl = 1

        # 创建临时地块对象用于评价
        temp_parcel = Parcel(
            tybh=parcel.tybh, jd=parcel.jd, wd=parcel.wd, mj=parcel.mj,
            sjd=new_sjd, yjz=new_yjz, yxl=new_yxl, sxj=new_sxj,
            trrz=new_trrz, yxtchd=new_yxtchd, gchd=new_gchd,
            jhxllz=parcel.jhxllz, jhxqlz=parcel.jhxqlz,
            ejnyq=parcel.ejnyq, xqmc=parcel.xqmc,
            zdgc=parcel.zdgc, psnl=new_psnl, ggnl=new_ggnl,
            dxbw=parcel.dxbw, zdgx=parcel.zdgx
        )
        new_result = evaluate_land_quality(config, temp_parcel)

        potential_items.append(
            PotentialItem(
                indicator_name=potential_ind_names[k],
                original_value=orig_str,
                potential_value=poten_str,
                original_quality_index=quality_index,
                potential_quality_index=new_result.quality_index,
                original_grade=grade,
                potential_grade=new_result.grade
            )
        )

    # 全改良（所有9个指标同时改良）
    full_new_parcel = Parcel(
        tybh=parcel.tybh, jd=parcel.jd, wd=parcel.wd, mj=parcel.mj,
        sjd=config.c[parcel.ejnyq-1][0],
        yjz=config.c[parcel.ejnyq-1][1],
        yxl=config.c[parcel.ejnyq-1][2],
        sxj=config.c[parcel.ejnyq-1][3],
        trrz=config.c[parcel.ejnyq-1][4],
        yxtchd=config.c[parcel.ejnyq-1][5],
        gchd=config.c[parcel.ejnyq-1][6],
        jhxllz=parcel.jhxllz, jhxqlz=parcel.jhxqlz,
        ejnyq=parcel.ejnyq, xqmc=parcel.xqmc,
        zdgc=parcel.zdgc, psnl=1, ggnl=1,
        dxbw=parcel.dxbw, zdgx=parcel.zdgx
    )
    full_result = evaluate_land_quality(config, full_new_parcel)

    return potential_items, full_result


def county_potential_statistics_data(config: EvaluationConfig, parcels: List[Parcel],
                                     xqmc_code: int, scenario: int) -> Optional[CountyPotentialResult]:
    """
    计算县域潜力统计数据（不打印）。
    scenario = 1: 理想潜力（均值调整）
    scenario = 2: 最佳潜力（最大值调整）
    返回 CountyPotentialResult 对象，若无数据则返回 None。
    """
    county_p = [p for p in parcels if p.xqmc == xqmc_code]
    n = len(county_p)
    if n == 0:
        return None

    # ---- 第一步：计算原始指标的县域平均值、最大值 ----
    sum_sjd = sum_yjz = sum_yxl = sum_sxj = sum_trrz = sum_yxtchd = sum_gchd = 0.0
    sum_psnl = sum_ggnl = 0.0
    max_yjz = max_yxl = max_sxj = max_yxtchd = max_gchd = -1e30
    sum_grade_orig = 0.0
    cnt_grade_orig = [0] * 10
    mj_grade_orig = [0.0] * 10
    sum_contrib_orig = [0.0] * 12
    sum_contrib_pot = [0.0] * 12
    sum_ind_orig = [0.0] * 12
    min_ind_orig = [1e30] * 12
    max_ind_orig = [-1e30] * 12

    for p in county_p:
        ejnyq = p.ejnyq
        sum_sjd += p.sjd
        sum_yjz += p.yjz
        sum_yxl += p.yxl
        sum_sxj += p.sxj
        sum_trrz += p.trrz
        sum_yxtchd += p.yxtchd
        sum_gchd += p.gchd
        sum_psnl += float(p.psnl)
        sum_ggnl += float(p.ggnl)
        max_yjz = max(max_yjz, p.yjz)
        max_yxl = max(max_yxl, p.yxl)
        max_sxj = max(max_sxj, p.sxj)
        max_yxtchd = max(max_yxtchd, p.yxtchd)
        max_gchd = max(max_gchd, p.gchd)

        # 原始评价
        orig_result = evaluate_land_quality(config, p)
        sum_grade_orig += orig_result.grade
        contrib_orig = [orig_result.y[i] * config.weights[ejnyq-1][i] for i in range(12)]
        for j in range(12):
            sum_contrib_orig[j] += contrib_orig[j]

        if 1 <= orig_result.grade <= 10:
            cnt_grade_orig[orig_result.grade-1] += 1
            mj_grade_orig[orig_result.grade-1] += p.mj

        raw_vals = [p.sjd, p.yjz, p.yxl, p.sxj, p.trrz,
                    p.yxtchd, p.gchd, float(p.zdgc), float(p.psnl),
                    float(p.ggnl), float(p.dxbw), float(p.zdgx)]
        for j in range(12):
            sum_ind_orig[j] += raw_vals[j]
            if raw_vals[j] < min_ind_orig[j]:
                min_ind_orig[j] = raw_vals[j]
            if raw_vals[j] > max_ind_orig[j]:
                max_ind_orig[j] = raw_vals[j]

    avg_sjd = sum_sjd / n
    avg_yjz = sum_yjz / n
    avg_yxl = sum_yxl / n
    avg_sxj = sum_sxj / n
    avg_trrz = sum_trrz / n
    avg_yxtchd = sum_yxtchd / n
    avg_gchd = sum_gchd / n
    avg_psnl = sum_psnl / n
    avg_ggnl = sum_ggnl / n

    # ---- 第二步：逐地块调整并重新评价 ----
    sum_mj = 0.0
    sum_ind = [0.0] * 12
    min_ind = [1e30] * 12
    max_ind = [-1e30] * 12
    cnt_grade = [0] * 10
    mj_grade = [0.0] * 10
    cnt_primary = [0] * 12
    mj_primary = [0.0] * 12
    lim_factors_all = []
    grades_list = []
    areas = []

    for p in county_p:
        mj = p.mj
        areas.append(mj)
        sum_mj += mj
        ejnyq = p.ejnyq

        # 初始化新指标为原始值
        new_sjd = p.sjd
        new_yjz = p.yjz
        new_yxl = p.yxl
        new_sxj = p.sxj
        new_trrz = p.trrz
        new_yxtchd = p.yxtchd
        new_gchd = p.gchd
        new_psnl = p.psnl
        new_ggnl = p.ggnl

        if scenario == 1:   # 理想潜力
            if new_yjz < avg_yjz: new_yjz = avg_yjz
            if new_yxl < avg_yxl: new_yxl = avg_yxl
            if new_sxj < avg_sxj: new_sxj = avg_sxj
            if new_yxtchd < avg_yxtchd: new_yxtchd = avg_yxtchd
            if new_gchd < avg_gchd: new_gchd = avg_gchd

            # 峰型指标调整
            d_val = abs(avg_sjd - config.c[ejnyq-1][0])
            th_low = config.c[ejnyq-1][0] - d_val
            th_high = config.c[ejnyq-1][0] + d_val
            new_sjd = max(new_sjd, th_low)
            new_sjd = min(new_sjd, th_high)

            d_val = abs(avg_trrz - config.c[ejnyq-1][4])
            th_low = config.c[ejnyq-1][4] - d_val
            th_high = config.c[ejnyq-1][4] + d_val
            new_trrz = max(new_trrz, th_low)
            new_trrz = min(new_trrz, th_high)

            new_psnl = max(int(avg_psnl), p.psnl)
            new_ggnl = max(int(avg_ggnl), p.ggnl)

        elif scenario == 2:   # 最佳潜力
            if new_yjz < max_yjz:
                new_yjz = max(max_yjz, config.ut2[ejnyq-1][1])
            if new_yxl < max_yxl:
                new_yxl = max(max_yxl, config.ut2[ejnyq-1][2])
            if new_sxj < max_sxj:
                new_sxj = max(max_sxj, config.ut2[ejnyq-1][3])
            if new_yxtchd < max_yxtchd:
                new_yxtchd = max(max_yxtchd, config.ut2[ejnyq-1][5])
            if new_gchd < max_gchd:
                new_gchd = max(max_gchd, config.ut2[ejnyq-1][6])

            d_val = 1.0 / (2.0 * math.sqrt(config.a[ejnyq-1][0]))
            th_low = config.c[ejnyq-1][0] - d_val
            th_high = config.c[ejnyq-1][0] + d_val
            new_sjd = max(new_sjd, th_low)
            new_sjd = min(new_sjd, th_high)

            d_val = 1.0 / (2.0 * math.sqrt(config.a[ejnyq-1][4]))
            th_low = config.c[ejnyq-1][4] - d_val
            th_high = config.c[ejnyq-1][4] + d_val
            new_trrz = max(new_trrz, th_low)
            new_trrz = min(new_trrz, th_high)

            if new_psnl != 1: new_psnl = 1
            if new_ggnl != 1: new_ggnl = 1

        # 构造调整后的地块并评价
        adj_parcel = Parcel(
            tybh=p.tybh, jd=p.jd, wd=p.wd, mj=p.mj,
            sjd=new_sjd, yjz=new_yjz, yxl=new_yxl, sxj=new_sxj,
            trrz=new_trrz, yxtchd=new_yxtchd, gchd=new_gchd,
            jhxllz=p.jhxllz, jhxqlz=p.jhxqlz,
            ejnyq=p.ejnyq, xqmc=p.xqmc,
            zdgc=p.zdgc, psnl=new_psnl, ggnl=new_ggnl,
            dxbw=p.dxbw, zdgx=p.zdgx
        )
        pot_result = evaluate_land_quality(config, adj_parcel)
        grades_list.append(pot_result.grade)

        # 贡献累加
        contrib_pot = [pot_result.y[i] * config.weights[ejnyq-1][i] for i in range(12)]
        for j in range(12):
            sum_contrib_pot[j] += contrib_pot[j]

        # 障碍度因子
        d = [1.0 - v for v in pot_result.y]
        df = [d[i] * config.weights[ejnyq-1][i] for i in range(12)]
        total = sum(df)
        if total != 0.0:
            lf = [v / total for v in df]
        else:
            lf = [0.0] * 12
        lim_factors_all.append(lf)

        if 1 <= pot_result.grade <= 10:
            cnt_grade[pot_result.grade-1] += 1
            mj_grade[pot_result.grade-1] += mj

        raw_vals_new = [new_sjd, new_yjz, new_yxl, new_sxj, new_trrz,
                        new_yxtchd, new_gchd, float(p.zdgc), float(new_psnl),
                        float(new_ggnl), float(p.dxbw), float(p.zdgx)]
        for j in range(12):
            sum_ind[j] += raw_vals_new[j]
            if raw_vals_new[j] < min_ind[j]:
                min_ind[j] = raw_vals_new[j]
            if raw_vals_new[j] > max_ind[j]:
                max_ind[j] = raw_vals_new[j]

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

    avg_grade_orig = sum_grade_orig / n
    avg_ind_orig = [sum_ind_orig[j]/n for j in range(12)]
    avg_contrib_orig = [sum_contrib_orig[j]/n for j in range(12)]
    avg_contrib_pot = [sum_contrib_pot[j]/n for j in range(12)]

    # 排序平均障碍度因子
    combined = list(zip(avg_lim, config.indicator_names))
    combined.sort(key=lambda x: x[0], reverse=True)
    sorted_avg, sorted_names = zip(*combined)

    return CountyPotentialResult(
        scenario=scenario,
        county_name=config.xqmc_names[xqmc_code-1],
        parcel_count=n,
        total_area=sum_mj,
        avg_grade_pot=avg_grade,
        avg_ind_pot=avg_ind,
        min_ind_pot=min_ind,
        max_ind_pot=max_ind,
        avg_lim_pot=avg_lim,
        sorted_avg_pot=list(sorted_avg),
        sorted_names_pot=list(sorted_names),
        cnt_grade_pot=cnt_grade,
        mj_grade_pot=mj_grade,
        cnt_primary_pot=cnt_primary,
        mj_primary_pot=mj_primary,
        avg_grade_orig=avg_grade_orig,
        avg_ind_orig=avg_ind_orig,
        avg_contrib_orig=avg_contrib_orig,
        avg_contrib_pot=avg_contrib_pot,
        cnt_grade_orig=cnt_grade_orig,
        mj_grade_orig=mj_grade_orig
    )
