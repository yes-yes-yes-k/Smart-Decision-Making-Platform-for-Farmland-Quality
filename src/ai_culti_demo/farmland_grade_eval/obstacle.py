"""障碍度计算"""
from typing import List
from .config import EvaluationConfig
from .models import ObstacleItem

def calc_limiting_factors(config: EvaluationConfig, ejnyq: int, y: List[float]) -> List[float]:
    d = [1.0 - v for v in y]
    df = [d[i] * config.weights[ejnyq-1][i] for i in range(12)]
    total = sum(df)
    if total != 0.0:
        return [v / total for v in df]
    return [0.0] * 12

def compute_obstacle_factors(config: EvaluationConfig, ejnyq: int, y: List[float]) -> List[ObstacleItem]:
    lf = calc_limiting_factors(config, ejnyq, y)
    items = []
    for i, v in enumerate(lf):
        if v <= 0.0:
            degree = '无障碍    '
        elif v <= 0.1:
            degree = '轻度障碍  '
        elif v <= 0.2:
            degree = '中度障碍  '
        else:
            degree = '重度障碍  '
        items.append(ObstacleItem(config.indicator_names[i], v, degree))
    items.sort(key=lambda x: x.factor, reverse=True)
    return items
