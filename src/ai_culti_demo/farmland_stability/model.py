import os
import sys
import warnings
from pathlib import Path

warnings.filterwarnings('ignore')

# 避免系统级 PROJ 配置覆盖当前 Conda 环境的坐标系数据库。
_PROJ_DATA_DIR = Path(sys.prefix) / 'Library' / 'share' / 'proj'
if _PROJ_DATA_DIR.is_dir():
    os.environ['PROJ_DATA'] = str(_PROJ_DATA_DIR)
    os.environ['PROJ_LIB'] = str(_PROJ_DATA_DIR)

import numpy as np
import pandas as pd
import geopandas as gpd
from scipy.spatial import cKDTree

MODEL_VERSION = 'model1_v2_20260801'

# 与模型1 v2（2026-08-01）Shapefile 的字段口径保持一致。
INDICATORS = ['SJD', 'YJZ', 'YXL', 'SXJ', 'TRRZ', 'GCZD', 'GGNL', 'PSNL', 'DXBW', 'ZDGX', 'YXTCHD', 'GCHD']
LSD_COLS = [x + 'LSD' for x in INDICATORS]
QZ_COLS = [x + 'QZ' for x in INDICATORS]


def require_columns(Data, cols, name='数据'):
    miss = [x for x in cols if x not in Data.columns]
    if miss:
        raise ValueError(f'{name}缺少字段：{miss}')


def to_grade(s):
    return pd.to_numeric(s.astype(str).str.extract(r'(\d+)')[0], errors='coerce')


def relative_rank(Data, value, region):
    r = pd.Series(np.nan, index=Data.index, dtype=float)
    v = pd.to_numeric(Data[value], errors='coerce')
    r.loc[v == 0] = 0
    m = v > 0
    r.loc[m] = Data.loc[m].groupby(region)[value].rank(pct=True)
    return r.round(4)


def calculate_boundary_safety(G, region='PJFQ', score='ZHQZ', grade='GDZLDJ'):
    G = G.copy()
    require_columns(G, [region, score, grade], '等级边界安全度')
    z = pd.to_numeric(G[score], errors='coerce')
    g = to_grade(G[grade])
    qmin = z.groupby(G[region], dropna=False).transform('min')
    qmax = z.groupby(G[region], dropna=False).transform('max')
    w = (qmax - qmin) / 10
    num = (z - qmax + g * w).to_numpy(float)
    den = w.to_numpy(float)
    s = np.divide(num, den, out=np.full(len(G), np.nan), where=np.isfinite(num) & np.isfinite(den) & (den > 0))
    G['SAFE_ABS'] = np.clip(s, 0, 1).round(4)
    return G


def calculate_support_balance(G, region='PJFQ'):
    G = G.copy()
    require_columns(G, [region] + LSD_COLS + QZ_COLS, '指标支撑均衡度')
    u = G[LSD_COLS].apply(pd.to_numeric, errors='coerce').to_numpy(float)
    w = G[QZ_COLS].apply(pd.to_numeric, errors='coerce').to_numpy(float)
    valid = np.isfinite(u).all(1) & np.isfinite(w).all(1) & (w.sum(1) > 0)
    wn = np.divide(w, w.sum(1, keepdims=True), out=np.zeros_like(w), where=w.sum(1, keepdims=True) > 0)
    m = (u * wn).sum(1, keepdims=True)
    v = (wn * (u - m) ** 2).sum(1)
    d = m[:, 0] * (1 - m[:, 0])
    b = np.full(len(G), np.nan)
    q = valid & (d > 0)
    b[q] = 1 - np.sqrt(np.clip(v[q] / d[q], 0, None))
    b[valid & (d == 0) & (v == 0)] = 1
    G['BAL_ABS'] = np.clip(b, 0, 1).round(4)
    G['BAL_REL'] = G.groupby(region, dropna=False)['BAL_ABS'].rank(pct=True).round(4)
    return G


def calculate_key_criticality(G, region='PJFQ', score='ZHQZ', grade='GDZLDJ'):
    G = G.copy()
    require_columns(G, [region, score, grade] + LSD_COLS + QZ_COLS, '关键指标临界度')
    z = pd.to_numeric(G[score], errors='coerce')
    g = to_grade(G[grade])
    q0 = z.groupby(G[region], dropna=False).transform('min')
    q1 = z.groupby(G[region], dropna=False).transform('max')
    h = (q1 - q0) / 10
    margin = (z - (q1 - g * h)).clip(lower=0).to_numpy(float)[:, None]
    u = G[LSD_COLS].apply(pd.to_numeric, errors='coerce').to_numpy(float)
    w = G[QZ_COLS].apply(pd.to_numeric, errors='coerce').to_numpy(float)
    c0 = u * w
    cs = np.nansum(c0, axis=1, keepdims=True)
    c = np.divide(c0, cs, out=np.zeros_like(c0), where=np.isfinite(cs) & (cs > 0)) * z.to_numpy(float)[:, None]
    ratio = np.divide(margin, c, out=np.full_like(c, np.inf), where=np.isfinite(c) & (c > 0))
    k = 1 - np.clip(ratio, 0, 1)
    valid = g.notna().to_numpy() & (g.to_numpy() < 10) & h.notna().to_numpy() & (h.to_numpy() > 0) & np.isfinite(c).all(1) & (c.sum(1) > 0)
    idx = np.argmax(k, axis=1)
    G['KEY_FAC'] = None
    G.loc[valid, 'KEY_FAC'] = np.array(INDICATORS, dtype=object)[idx[valid]]
    G['KEY_ABS'] = np.where(valid, np.max(k, axis=1), np.nan).round(4)
    G['KEY_REL'] = G.groupby(region, dropna=False)['KEY_ABS'].rank(pct=True).round(4)
    return G


def calculate_neighbor_consistency(G, k=8, region='PJFQ', grade='GDZLDJ'):
    G = G.copy()
    require_columns(G, [region, grade], '空间邻域一致性')
    if G.crs is None:
        raise ValueError('空间邻域一致性：地块数据缺少坐标系')
    if len(G) < 2:
        raise ValueError('空间邻域一致性：地块数量不能少于2个')
    if k < 1:
        raise ValueError('空间邻域一致性：k必须大于0')
    P = G.to_crs(G.estimate_utm_crs()) if G.crs.is_geographic else G
    c = P.geometry.centroid
    xy = np.c_[c.x.to_numpy(), c.y.to_numpy()]
    kk = min(int(k), len(G) - 1)
    d, j = cKDTree(xy).query(xy, k=kk + 1)
    d, j = d[:, 1:], j[:, 1:]
    g = to_grade(G[grade]).to_numpy(float)
    s = np.clip(1 - np.abs(g[:, None] - g[j]) / 2, 0, 1)
    w = np.where(np.isfinite(s) & np.isfinite(d), 1 / (d + 1), 0)
    nbr = np.divide(np.nansum(s * w, axis=1), w.sum(1), out=np.full(len(G), np.nan), where=w.sum(1) > 0)
    G['NBR_ABS'] = np.clip(nbr, 0, 1).round(4)
    G['NBR_REL'] = G.groupby(region, dropna=False)['NBR_ABS'].rank(pct=True).round(4)
    G['NBR_N'] = kk
    return G


def calculate_history_trend(G, history_data, years, id_col='ID', region='PJFQ', score='ZHQZ', grade='GDZLDJ', score_scale=1, tol=0.01):
    G = G.copy()
    if len(history_data) != 3 or len(years) != 3:
        raise ValueError('历史变化趋势：必须输入3个年份的数据')
    if len(set(years)) < 3 or score_scale <= 0:
        raise ValueError('历史变化趋势：年份必须不同且score_scale必须大于0')
    require_columns(G, [id_col, region], '历史变化趋势当前数据')
    if not G[id_col].is_unique:
        raise ValueError('历史变化趋势：当前数据ID必须唯一')
    order = np.argsort(years)
    years = np.asarray(years, dtype=int)[order]
    history_data = [history_data[i] for i in order]
    H = None
    for D, y in zip(history_data, years):
        require_columns(D, [id_col, score, grade], f'{y}年历史数据')
        if not D[id_col].is_unique:
            raise ValueError(f'历史变化趋势：{y}年ID必须唯一')
        T = D[[id_col, score, grade]].copy().rename(columns={score: f'Q{y}', grade: f'G{y}'})
        H = T if H is None else H.merge(T, on=id_col, how='outer', validate='one_to_one')
    new_cols = [x for x in H.columns if x != id_col]
    G = G.drop(columns=[x for x in new_cols if x in G.columns], errors='ignore').merge(H, on=id_col, how='left', validate='one_to_one')
    z = G[[f'Q{y}' for y in years]].apply(pd.to_numeric, errors='coerce').to_numpy(float)
    g = G[[f'G{y}' for y in years]].apply(to_grade).to_numpy(float)
    t = years.astype(float)
    tc = t - t.mean()
    valid = np.isfinite(z).all(1)
    b = np.full(len(G), np.nan)
    b[valid] = ((z[valid] - z[valid].mean(1, keepdims=True)) * tc).sum(1) / (tc ** 2).sum()
    delta = b * (t[-1] - t[0]) / score_scale
    dz = np.diff(z / score_scale, axis=1)
    G['H_SLOPE'] = np.round(b, 6)
    G['H_ABS'] = np.clip((1 - delta) / 2, 0, 1).round(4)
    G['H_REL'] = G.groupby(region, dropna=False)['H_ABS'].rank(pct=True).round(4)
    typ = np.full(len(G), '数据不足', dtype=object)
    typ[valid & (np.abs(delta) <= tol)] = '基本稳定'
    typ[valid & (delta < -tol)] = '波动退化'
    typ[valid & (delta > tol)] = '波动改善'
    typ[valid & (dz[:, 0] < -tol) & (dz[:, 1] < -tol)] = '持续退化'
    typ[valid & (dz[:, 0] > tol) & (dz[:, 1] > tol)] = '持续改善'
    G['H_TYPE'] = typ
    vg = np.isfinite(g).all(1)
    G['G_CHANGE'] = np.where(vg, g[:, -1] - g[:, 0], np.nan)
    G['DROP_N'] = np.where(vg, (np.diff(g, axis=1) > 0).sum(1), np.nan)
    return G


def calculate_drop_risk(G, region='PJFQ', safety='SAFE_ABS', history='H_ABS', score='ZHQZ', grade='GDZLDJ'):
    G = G.copy()
    require_columns(G, [region, history, score, grade], '掉级风险')
    if safety in G.columns:
        s = pd.to_numeric(G[safety], errors='coerce').clip(0, 1)
    else:
        z = pd.to_numeric(G[score], errors='coerce')
        g = to_grade(G[grade])
        q0 = z.groupby(G[region], dropna=False).transform('min')
        q1 = z.groupby(G[region], dropna=False).transform('max')
        w = (q1 - q0) / 10
        num = (z - q1 + g * w).to_numpy(float)
        den = w.to_numpy(float)
        s = pd.Series(np.divide(num, den, out=np.full(len(G), np.nan), where=np.isfinite(num) & np.isfinite(den) & (den > 0)), index=G.index).clip(0, 1)
    h = pd.to_numeric(G[history], errors='coerce').clip(0, 1)
    G['DROP_ABS'] = ((1 - s) * (2 * (h - 0.5)).clip(0, 1)).round(4)
    G['DROP_REL'] = relative_rank(G, 'DROP_ABS', region)
    return G


def calculate_factor_degradation(G, history_data, years, id_col='ID', region='PJFQ'):
    G = G.copy()
    if len(history_data) != 3 or len(years) != 3:
        raise ValueError('关键因子退化风险：必须输入3个年份的数据')
    require_columns(G, [id_col, region] + QZ_COLS, '关键因子退化风险当前数据')
    if not G[id_col].is_unique:
        raise ValueError('关键因子退化风险：当前数据ID必须唯一')
    order = np.argsort(years)
    years = np.asarray(years, dtype=int)[order]
    history_data = [history_data[i] for i in order]
    u = []
    for D, y in zip(history_data, years):
        require_columns(D, [id_col] + LSD_COLS, f'{y}年历史数据')
        if not D[id_col].is_unique:
            raise ValueError(f'关键因子退化风险：{y}年ID必须唯一')
        T = G[[id_col]].merge(D[[id_col] + LSD_COLS], on=id_col, how='left', validate='one_to_one')
        u.append(T[LSD_COLS].apply(pd.to_numeric, errors='coerce').to_numpy(float))
    u = np.stack(u, axis=1)
    w = G[QZ_COLS].apply(pd.to_numeric, errors='coerce').to_numpy(float)
    w = np.where(np.isfinite(w) & (w > 0), w, 0)
    ws = w.sum(1, keepdims=True)
    wn = np.divide(w, ws, out=np.zeros_like(w), where=ws > 0)
    c = u * wn[:, None, :]
    t = years.astype(float)
    tc = t - t.mean()
    valid = np.isfinite(c).all(1) & (ws > 0)
    b = ((c - c.mean(1, keepdims=True)) * tc[None, :, None]).sum(1) / (tc ** 2).sum()
    b[~valid] = np.nan
    risk = np.clip(-b * (t[-1] - t[0]), 0, 1)
    rr = np.where(np.isfinite(risk), risk, -1)
    idx = rr.argmax(1)
    vmax = rr.max(1)
    ok = np.isfinite(risk).any(1)
    name = np.full(len(G), None, dtype=object)
    name[ok & (vmax <= 0)] = '无明显退化'
    m = ok & (vmax > 0)
    name[m] = np.array(INDICATORS, dtype=object)[idx[m]]
    G['KFD_FACTOR'] = name
    G['KFD_ABS'] = np.where(ok, np.clip(vmax, 0, 1), np.nan).round(4)
    G['KFD_REL'] = relative_rank(G, 'KFD_ABS', region)
    return G


def calculate_degradation_cluster(G, k=8, region='PJFQ', risk='KFD_ABS'):
    G = G.copy()
    require_columns(G, [region, risk], '退化空间集聚风险')
    if G.crs is None:
        raise ValueError('退化空间集聚风险：地块数据缺少坐标系')
    if len(G) < 2:
        raise ValueError('退化空间集聚风险：地块数量不能少于2个')
    if k < 1:
        raise ValueError('退化空间集聚风险：k必须大于0')
    P = G.to_crs(G.estimate_utm_crs()) if G.crs.is_geographic else G
    c = P.geometry.centroid
    xy = np.c_[c.x.to_numpy(), c.y.to_numpy()]
    kk = min(int(k), len(G) - 1)
    d, j = cKDTree(xy).query(xy, k=kk + 1)
    d, j = d[:, 1:], j[:, 1:]
    r = pd.to_numeric(G[risk], errors='coerce').clip(0, 1).to_numpy(float)
    rn = r[j]
    w = np.where(np.isfinite(rn) & np.isfinite(d), 1 / (d + 1), 0)
    nbr = np.divide(np.nansum(rn * w, axis=1), w.sum(1), out=np.full(len(G), np.nan), where=w.sum(1) > 0)
    cluster = np.where(np.isfinite(r) & np.isfinite(nbr), r * nbr, np.nan)
    G['DGR_NBR'] = np.clip(nbr, 0, 1).round(4)
    G['DGR_ABS'] = np.clip(cluster, 0, 1).round(4)
    G['DGR_REL'] = relative_rank(G, 'DGR_ABS', region)
    return G


def calculate_persistent_low_quality(G, history_data, years, id_col='ID', region='PJFQ', score='ZHQZ', grade='GDZLDJ', low_grade=5, score_scale=1):
    G = G.copy()
    if len(history_data) != len(years) or len(years) < 2:
        raise ValueError('持续低质风险：历史文件和年份数量必须一致，且不少于2期')
    if score_scale <= 0:
        raise ValueError('持续低质风险：score_scale必须大于0')
    require_columns(G, [id_col, region], '持续低质风险当前数据')
    if not G[id_col].is_unique:
        raise ValueError('持续低质风险：当前数据ID必须唯一')
    order = np.argsort(years)
    years = np.asarray(years, dtype=int)[order]
    history_data = [history_data[i] for i in order]
    z = []
    g = []
    for D, y in zip(history_data, years):
        require_columns(D, [id_col, score, grade], f'{y}年历史数据')
        if not D[id_col].is_unique:
            raise ValueError(f'持续低质风险：{y}年ID必须唯一')
        T = G[[id_col]].merge(D[[id_col, score, grade]], on=id_col, how='left', validate='one_to_one')
        z.append(pd.to_numeric(T[score], errors='coerce').to_numpy(float))
        g.append(to_grade(T[grade]).to_numpy(float))
    z = np.stack(z, axis=1)
    g = np.stack(g, axis=1)
    valid = np.isfinite(z) & np.isfinite(g)
    low = (g >= low_grade) & valid
    severity = np.where(low, np.clip(1 - z / score_scale, 0, 1), 0)
    n = valid.sum(1)
    low_n = low.sum(1)
    low_rate = np.divide(low_n, n, out=np.full(len(G), np.nan), where=n > 0)
    risk = np.divide(severity.sum(1), n, out=np.full(len(G), np.nan), where=n > 0)
    G['LOW_N'] = np.where(n > 0, low_n, np.nan)
    G['LOW_RATE'] = np.round(low_rate, 4)
    G['LOW_ABS'] = np.round(risk, 4)
    G['LOW_REL'] = relative_rank(G, 'LOW_ABS', region)
    return G


def run_all_models(current_file, history_files, years, k=8, id_col='ID', region='PJFQ', score='ZHQZ', grade='GDZLDJ', low_grade=5, score_scale=1, tol=0.01):
    if len(history_files) != len(years):
        raise ValueError('历史文件数量与年份数量不一致')
    G = gpd.read_file(current_file)
    H = [gpd.read_file(x) for x in history_files]
    require_columns(G, [id_col, region, score, grade] + LSD_COLS + QZ_COLS, '当前地块数据')
    if not G[id_col].is_unique:
        raise ValueError('当前地块数据ID必须唯一')
    G = calculate_boundary_safety(G, region, score, grade)
    G = calculate_support_balance(G, region)
    G = calculate_key_criticality(G, region, score, grade)
    G = calculate_neighbor_consistency(G, k, region, grade)
    G = calculate_history_trend(G, H, years, id_col, region, score, grade, score_scale, tol)
    G = calculate_drop_risk(G, region, 'SAFE_ABS', 'H_ABS', score, grade)
    G = calculate_factor_degradation(G, H, years, id_col, region)
    G = calculate_degradation_cluster(G, k, region, 'KFD_ABS')
    G = calculate_persistent_low_quality(G, H, years, id_col, region, score, grade, low_grade, score_scale)
    return G


RESULT_CN = {
    'SAFE_ABS': '等级边界安全度',
    'BAL_ABS': '指标支撑均衡度_绝对',
    'BAL_REL': '指标支撑均衡度_相对',
    'KEY_FAC': '关键临界指标',
    'KEY_ABS': '关键指标临界度_绝对',
    'KEY_REL': '关键指标临界度_相对',
    'NBR_ABS': '空间邻域一致性_绝对',
    'NBR_REL': '空间邻域一致性_相对',
    'NBR_N': '邻域地块数',
    'H_SLOPE': '历史年均变化斜率',
    'H_ABS': '历史变化趋势_绝对',
    'H_REL': '历史变化趋势_相对',
    'H_TYPE': '历史变化类型',
    'G_CHANGE': '历史等级变化',
    'DROP_N': '历史掉级次数',
    'DROP_ABS': '掉级风险_绝对',
    'DROP_REL': '掉级风险_相对',
    'KFD_FACTOR': '关键退化因子',
    'KFD_ABS': '关键因子退化风险_绝对',
    'KFD_REL': '关键因子退化风险_相对',
    'DGR_NBR': '邻域平均退化风险',
    'DGR_ABS': '退化空间集聚风险_绝对',
    'DGR_REL': '退化空间集聚风险_相对',
    'LOW_N': '低质年份数',
    'LOW_RATE': '持续低质比例',
    'LOW_ABS': '持续低质风险_绝对',
    'LOW_REL': '持续低质风险_相对'
}


def save_final_results(G, shp_file, xlsx_file, years):
    shp_file = Path(shp_file)
    xlsx_file = Path(xlsx_file)
    shp_file.parent.mkdir(parents=True, exist_ok=True)
    xlsx_file.parent.mkdir(parents=True, exist_ok=True)
    for ext in ['.shp', '.shx', '.dbf', '.prj', '.cpg', '.sbn', '.sbx', '.qix', '.fix']:
        p = shp_file.with_suffix(ext)
        if p.exists():
            p.unlink()
    G.to_file(shp_file, driver='ESRI Shapefile', encoding='utf-8', index=False)
    rename = RESULT_CN.copy()
    rename.update({f'Q{int(y)}': f'综合权重_{int(y)}' for y in years})
    rename.update({f'G{int(y)}': f'质量等级_{int(y)}' for y in years})
    G.drop(columns='geometry').rename(columns=rename).to_excel(xlsx_file, index=False)


MODULE_FIELDS = {
    1: ['SAFE_ABS'],
    2: ['BAL_ABS', 'BAL_REL'],
    3: ['KEY_FAC', 'KEY_ABS', 'KEY_REL'],
    4: ['NBR_ABS', 'NBR_REL', 'NBR_N'],
    5: ['H_SLOPE', 'H_ABS', 'H_REL', 'H_TYPE', 'G_CHANGE', 'DROP_N'],
    6: ['DROP_ABS', 'DROP_REL'],
    7: ['KFD_FACTOR', 'KFD_ABS', 'KFD_REL'],
    8: ['DGR_NBR', 'DGR_ABS', 'DGR_REL'],
    9: ['LOW_N', 'LOW_RATE', 'LOW_ABS', 'LOW_REL']
}


def get_parcel_result(G, parcel_id, module, id_col='ID', region='PJFQ', score='ZHQZ', grade='GDZLDJ'):
    if module not in MODULE_FIELDS:
        raise ValueError('module必须为1—9')
    require_columns(G, [id_col] + MODULE_FIELDS[module], '地块查询结果')
    m = G[id_col].astype(str).str.strip() == str(parcel_id).strip()
    if not m.any():
        raise ValueError(f'未找到地块ID：{parcel_id}')
    base = [x for x in [id_col, region, score, grade] if x in G.columns]
    R = G.loc[m, base + MODULE_FIELDS[module]].copy()
    return R.rename(columns=RESULT_CN)
