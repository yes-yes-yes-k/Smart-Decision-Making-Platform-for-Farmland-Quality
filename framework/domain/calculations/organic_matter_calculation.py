"""Model-5 有机质培肥 - RF 模型预测 Dose（推荐施肥量）。

构建时由 scripts/train_dose_rf_models.py 重训并保存 .joblib。
运行时延迟加载；模型、依赖或输入不可用时不生成替代数值。
"""
from __future__ import annotations
from dataclasses import dataclass
import hashlib
import os
import logging
from typing import Iterator, Optional

logger = logging.getLogger(__name__)

# 模型产物目录: 项目根/data/model_artifacts
# 本文件位于 framework/domain/calculations/，需上溯 3 级到项目根
MODEL_ARTIFACTS_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "data", "model_artifacts"
)

# 训练时使用的特征顺序（必须与 train_dose_rf_models.py 的 FEATURE_COLUMNS 一致）
FEATURE_COLUMNS = ["pH", "SOMbe", "AK", "AP", "TN"]

_model_cache = {}
_version_cache = {}


MODEL5_INPUT_MISSING = "MODEL5_INPUT_MISSING"
MODEL5_DEPENDENCY_UNAVAILABLE = "MODEL5_DEPENDENCY_UNAVAILABLE"
MODEL5_MODEL_UNAVAILABLE = "MODEL5_MODEL_UNAVAILABLE"
MODEL5_PREDICTION_FAILED = "MODEL5_PREDICTION_FAILED"


@dataclass(frozen=True)
class DosePredictionResult:
    """Dose 预测结果；迭代兼容旧的 ``dose, simulated = ...`` 调用。"""

    dose: Optional[float]
    simulated: bool
    status: str
    reason: Optional[str]
    model_version: Optional[str]
    data_source: str

    def __iter__(self) -> Iterator[object]:
        yield self.dose
        yield self.simulated

    def __len__(self) -> int:
        return 2

    def __getitem__(self, index: int) -> object:
        return (self.dose, self.simulated)[index]


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


def _artifact_version(model_path: str) -> str:
    """使用模型文件摘要作为可验证版本，不依赖猜测式版本常量。"""
    if model_path not in _version_cache:
        digest = hashlib.sha256()
        with open(model_path, "rb") as model_file:
            for chunk in iter(lambda: model_file.read(1024 * 1024), b""):
                digest.update(chunk)
        _version_cache[model_path] = f"{os.path.basename(model_path)}:sha256:{digest.hexdigest()[:16]}"
    return _version_cache[model_path]


def predict_dose(indicators: dict, land_type: str) -> DosePredictionResult:
    """RF 模型预测 Dose。

    Args:
        indicators: 映射后的指标 dict（pH/SOMbe/AK/AP/TN）。
        land_type: "upland" 或 "paddy"。

    Returns:
        带状态、原因、模型版本和来源的预测结果。
    """
    model_path = os.path.join(MODEL_ARTIFACTS_DIR, f"{land_type}_dose_rf.joblib")

    missing = [name for name in FEATURE_COLUMNS if indicators.get(name) is None]
    if missing:
        logger.warning("RF 输入缺失 (land_type=%s, missing=%s)", land_type, missing)
        return DosePredictionResult(
            dose=None,
            simulated=True,
            status="degraded",
            reason=MODEL5_INPUT_MISSING,
            model_version=None,
            data_source="unavailable",
        )

    if not _scikit_learn_available():
        logger.warning("RF 运行依赖不可用 (land_type=%s)", land_type)
        return DosePredictionResult(
            dose=None,
            simulated=True,
            status="degraded",
            reason=MODEL5_DEPENDENCY_UNAVAILABLE,
            model_version=None,
            data_source="unavailable",
        )

    if not os.path.exists(model_path):
        logger.warning("RF 模型文件不可用 (land_type=%s)", land_type)
        return DosePredictionResult(
            dose=None,
            simulated=True,
            status="degraded",
            reason=MODEL5_MODEL_UNAVAILABLE,
            model_version=None,
            data_source="unavailable",
        )

    try:
        rf = _load_model(model_path)
        # 严格按 FEATURE_COLUMNS 顺序提取特征
        features = [[
            indicators["pH"],
            indicators["SOMbe"],
            indicators["AK"],
            indicators["AP"],
            indicators["TN"],
        ]]
        dose = float(rf.predict(features)[0])
        return DosePredictionResult(
            dose=dose,
            simulated=False,
            status="ok",
            reason=None,
            model_version=_artifact_version(model_path),
            data_source="rf_model",
        )
    except Exception as e:
        logger.warning("RF 预测失败 (land_type=%s): %s", land_type, e)
        return DosePredictionResult(
            dose=None,
            simulated=True,
            status="degraded",
            reason=MODEL5_PREDICTION_FAILED,
            model_version=None,
            data_source="unavailable",
        )
