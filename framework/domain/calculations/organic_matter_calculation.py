"""Model-5 有机质培肥 — RF 模型预测 Dose（推荐施肥量）。

构建时由 scripts/train_dose_rf_models.py 重训并保存 .joblib。
运行时延迟加载，scikit-learn 不可用时降级到规则。
"""
from __future__ import annotations
import os
import logging
from typing import Tuple

logger = logging.getLogger(__name__)

# 模型产物目录: 项目根/data/model_artifacts
# 本文件位于 framework/domain/calculations/，需上溯 3 级到项目根
MODEL_ARTIFACTS_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "data", "model_artifacts"
)

# 训练时使用的特征顺序（必须与 train_dose_rf_models.py 的 FEATURE_COLUMNS 一致）
FEATURE_COLUMNS = ["pH", "SOMbe", "AK", "AP", "TN"]

_model_cache = {}


def _load_model(model_path: str):
    """延迟加载 RF 模型（模块级缓存）。"""
    if model_path not in _model_cache:
        import joblib
        _model_cache[model_path] = joblib.load(model_path)
    return _model_cache[model_path]


def _scikit_learn_available() -> bool:
    """检查 scikit-learn 是否可用。"""
    try:
        import sklearn  # noqa: F401
        return True
    except ImportError:
        return False


def degrade_to_rules(indicators: dict) -> float:
    """降级规则: 根据有机质分级推荐施用量。

    Args:
        indicators: 映射后的指标 dict（pH/SOMbe/AK/AP/TN）。

    Returns:
        推荐 Dose 值。
    """
    som = indicators.get("SOMbe", 0) or 0
    # 简单规则: 有机质越低施用量越高
    if som < 10:
        return 225.0  # 低有机质，高施用量
    elif som < 20:
        return 180.0
    elif som < 30:
        return 135.0
    else:
        return 90.0  # 高有机质，低施用量


def predict_dose(indicators: dict, land_type: str) -> Tuple[float, bool]:
    """RF 模型预测 Dose。

    Args:
        indicators: 映射后的指标 dict（pH/SOMbe/AK/AP/TN）。
        land_type: "upland" 或 "paddy"。

    Returns:
        (dose, simulated): 推荐施用量、是否为降级模拟值。
    """
    model_path = os.path.join(MODEL_ARTIFACTS_DIR, f"{land_type}_dose_rf.joblib")

    if not _scikit_learn_available() or not os.path.exists(model_path):
        logger.warning("RF 模型不可用 (land_type=%s)，降级到规则", land_type)
        return degrade_to_rules(indicators), True

    try:
        rf = _load_model(model_path)
        # 严格按 FEATURE_COLUMNS 顺序提取特征
        features = [[
            indicators.get("pH", 0) or 0,
            indicators.get("SOMbe", 0) or 0,
            indicators.get("AK", 0) or 0,
            indicators.get("AP", 0) or 0,
            indicators.get("TN", 0) or 0,
        ]]
        dose = float(rf.predict(features)[0])
        return dose, False
    except Exception as e:
        logger.warning("RF 预测失败 (land_type=%s): %s，降级到规则", land_type, e)
        return degrade_to_rules(indicators), True
