"""核心评价函数"""
from typing import List
from .config import EvaluationConfig
from .models import Parcel, QualityResult

def membership_numeric(config: EvaluationConfig, u: float, idx: int, ejnyq: int) -> float:
    j = idx - 1
    pa = config.a[ejnyq-1][j]
    pc = config.c[ejnyq-1][j]
    u1 = config.ut1[ejnyq-1][j]
    u2 = config.ut2[ejnyq-1][j]

    if idx in (1, 5):  # 峰型
        if u <= u1 or u >= u2:
            return 0.0
        return 1.0 / (1.0 + pa * (u - pc)**2)
    else:  # 戒上型
        if u <= u1:
            return 0.0
        if u < pc:
            return 1.0 / (1.0 + pa * (u - pc)**2)
        return 1.0

def evaluate_land_quality(config: EvaluationConfig, parcel: Parcel) -> QualityResult:
    ejnyq = parcel.ejnyq
    if ejnyq < 1 or ejnyq > config.max_ejnyq:
        raise ValueError(f"无效的二级农业区代码 {ejnyq}")

    y = [0.0] * 12
    y[0] = membership_numeric(config, parcel.sjd, 1, ejnyq)
    y[1] = membership_numeric(config, parcel.yjz, 2, ejnyq)
    y[2] = membership_numeric(config, parcel.yxl, 3, ejnyq)
    y[3] = membership_numeric(config, parcel.sxj, 4, ejnyq)
    y[4] = membership_numeric(config, parcel.trrz, 5, ejnyq)
    y[5] = membership_numeric(config, parcel.yxtchd, 6, ejnyq)
    y[6] = membership_numeric(config, parcel.gchd, 7, ejnyq)

    if not (1 <= parcel.zdgc <= 12):
        raise ValueError("ZDGC 编码超出范围")
    if not (1 <= parcel.psnl <= 4):
        raise ValueError("PSNL 编码超出范围")
    if not (1 <= parcel.ggnl <= 4):
        raise ValueError("GGNL 编码超出范围")
    if not (1 <= parcel.dxbw <= 11):
        raise ValueError("DXBW 编码超出范围")
    if not (1 <= parcel.zdgx <= 7):
        raise ValueError("ZDGX 编码超出范围")

    y[7]  = config.mem_zdgc[ejnyq-1][parcel.zdgc-1]
    y[8]  = config.mem_psnl[ejnyq-1][parcel.psnl-1]
    y[9]  = config.mem_ggnl[ejnyq-1][parcel.ggnl-1]
    y[10] = config.mem_dxbw[ejnyq-1][parcel.dxbw-1]
    y[11] = config.mem_zdgx[ejnyq-1][parcel.zdgx-1]

    qi = sum(y[i] * config.weights[ejnyq-1][i] for i in range(12))

    grade = 10
    for i in range(9):
        if qi >= config.limits[ejnyq-1][i]:
            grade = i + 1
            break
    return QualityResult(y=y, quality_index=qi, grade=grade)
