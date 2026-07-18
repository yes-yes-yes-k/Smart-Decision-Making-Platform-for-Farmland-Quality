# Task 3 Brief — model_6.py 真实 ML 实现

> **来源**：`docs/superpowers/plans/2026-07-18-add-model-6-fertility-ml.md` 第 333-879 行
> **OpenSpec 对应**：`openspec/changes/add-model-6-fertility-ml/tasks.md` 第 3.1-3.9 节
> **BASE commit**：`b15ec3f`（Task 2 完成后的最新提交）

## Files

- Modify: `framework/domain/other_models/model_6.py`（完全重写，当前是占位 stub）
- Test: `tests/test_fertility_ml_prediction.py`（新文件）

## Interfaces

- **Consumes**: `data/fertility/models/*.joblib` 与 `*.json`（Task 2 产物）；`pandas`（已声明依赖）；`sklearn`/`joblib`（Task 1 新增依赖）
- **Produces**: `model_6_execution(input_data: Dict[str, Any]) -> Dict[str, Any]` 函数，返回字典含字段：`status`("success"|"fallback"|"rejected")、`soc_prediction`、`soc_confidence`、`dose_prediction`、`dose_confidence`、`dose_warning`、`imputed_features`、`imputation_applied`、`model_version`，fallback 时额外含 `fallback_reason`，rejected 时额外含 `reason` 与 `out_of_range_features`。
- **向后兼容**：`framework/domain/other_models/__init__.py` 的 `from .model_6 import model_6_execution` 保持不变（已确认现状为此 import）。

## 当前 model_6.py 现状（stub）

```python
from __future__ import annotations
from typing import Any, Dict

def model_6_execution(input_data: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "model_name": "model_6",
        "result": {},
        "status": "success",
        "message": "模型6执行成功（占位实现）",
    }
```

stub 返回的字典不含 `soc_prediction`/`soc_confidence` 等字段，所以 Step 2 运行测试会 FAIL（RED）。

## 步骤

### Step 1: 创建测试文件 `tests/test_fertility_ml_prediction.py`

```python
"""测试 model_6_execution ML 预测引擎。

单元测试全部使用 monkeypatch mock sklearn/joblib/模型文件，CI 零依赖。
集成测试使用真实模型文件，通过 skipif 在 sklearn/模型不可用时跳过。
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest


# ---- 测试用 mock 数据 ----

class FakeModel:
    """模拟 sklearn ExtraTreesRegressor 的 predict 行为"""
    def predict(self, df):
        return [42.0]


FAKE_SOC_META = {
    "model_type": "ExtraTreesRegressor",
    "model_version": "ETR_v1_20260713",
    "feature_names": ["pH", "SOCbe", "TN ", "TP ", "TK ", "AP", "AK", "Gap", "Dose", "Fertilizer type"],
    "feature_means": {
        "pH": 7.0, "SOCbe": 12.0, "TN ": 0.8, "TP ": 0.5, "TK ": 30.0,
        "AP": 50.0, "AK": 100.0, "Gap": 10.0, "Dose": 100.0, "Fertilizer type": 1.5,
    },
    "metrics": {"cv_r2": 0.89, "cv_rmse": 2.15, "test_r2": 0.91, "test_rmse": 2.24},
}

FAKE_DOSE_META = {
    "model_type": "ExtraTreesRegressor",
    "model_version": "ETR_v1_20260713",
    "feature_names": ["pH", "SOCbe", "TN ", "TP ", "TK ", "AP", "AK", "Gap", "Fertilizer type"],
    "feature_means": {
        "pH": 7.0, "SOCbe": 12.0, "TN ": 0.8, "TP ": 0.5, "TK ": 30.0,
        "AP": 50.0, "AK": 100.0, "Gap": 10.0, "Fertilizer type": 1.5,
    },
    "metrics": {"cv_r2": 0.43, "cv_rmse": 55.0, "test_r2": 0.47, "test_rmse": 50.0},
}

FULL_VALID_INPUT = {
    "pH": 6.5, "SOCbe": 15.0, "TN": 1.2, "TP": 0.8, "TK": 25.0,
    "AP": 30.0, "AK": 80.0, "Gap": 5.0, "Dose": 200.0, "Fertilizer type": 1,
}


def _setup_mock_models(monkeypatch):
    """将 model_6 模块的状态变量设置为 mock 值，模拟模型已加载"""
    from framework.domain.other_models import model_6
    monkeypatch.setattr(model_6, "_SKLEARN_AVAILABLE", True)
    monkeypatch.setattr(model_6, "_SOC_MODEL", FakeModel())
    monkeypatch.setattr(model_6, "_DOSE_MODEL", FakeModel())
    monkeypatch.setattr(model_6, "_SOC_META", FAKE_SOC_META)
    monkeypatch.setattr(model_6, "_DOSE_META", FAKE_DOSE_META)
    monkeypatch.setattr(model_6, "_SOC_LOAD_FAILED", False)
    monkeypatch.setattr(model_6, "_DOSE_LOAD_FAILED", False)


# ---- 单元测试 ----

class TestModel6Execution:
    def test_success_full_features(self, monkeypatch):
        """完整 10 特征 → status=success"""
        _setup_mock_models(monkeypatch)
        from framework.domain.other_models.model_6 import model_6_execution
        result = model_6_execution(FULL_VALID_INPUT)
        assert result["status"] == "success"
        assert result["soc_prediction"] == 42.0
        assert result["dose_prediction"] == 42.0
        assert result["soc_confidence"] == 0.91
        assert result["dose_confidence"] == 0.47
        assert "dose_warning" in result
        assert result["imputation_applied"] is False
        assert result["imputed_features"] == []
        assert result["model_version"] == "ETR_v1_20260713"

    def test_success_partial_features_imputation(self, monkeypatch):
        """部分特征缺失 → imputation_applied=true, imputed_features 非空"""
        _setup_mock_models(monkeypatch)
        from framework.domain.other_models.model_6 import model_6_execution
        partial = {"pH": 6.5, "SOCbe": 15.0, "TN": 1.2}
        result = model_6_execution(partial)
        assert result["status"] == "success"
        assert result["imputation_applied"] is True
        assert len(result["imputed_features"]) > 0

    def test_fallback_sklearn_missing(self, monkeypatch):
        """sklearn 不可用 → status=fallback, fallback_reason=sklearn_missing"""
        from framework.domain.other_models import model_6
        monkeypatch.setattr(model_6, "_SKLEARN_AVAILABLE", False)
        result = model_6.model_6_execution(FULL_VALID_INPUT)
        assert result["status"] == "fallback"
        assert result["fallback_reason"] == "sklearn_missing"
        assert result["soc_confidence"] == 0.3
        assert result["dose_confidence"] == 0.3

    def test_fallback_model_file_missing(self, monkeypatch):
        """模型文件缺失 → status=fallback, fallback_reason=model_file_missing"""
        from framework.domain.other_models import model_6
        monkeypatch.setattr(model_6, "_SKLEARN_AVAILABLE", True)
        monkeypatch.setattr(model_6, "_SOC_MODEL", None)
        monkeypatch.setattr(model_6, "_DOSE_MODEL", None)
        monkeypatch.setattr(model_6, "_SOC_META", None)
        monkeypatch.setattr(model_6, "_DOSE_META", None)
        monkeypatch.setattr(model_6, "_SOC_LOAD_FAILED", True)
        monkeypatch.setattr(model_6, "_DOSE_LOAD_FAILED", True)
        result = model_6.model_6_execution(FULL_VALID_INPUT)
        assert result["status"] == "fallback"
        assert result["fallback_reason"] == "model_file_missing"
        assert result["soc_confidence"] == 0.3

    def test_rejected_out_of_range_ph(self, monkeypatch):
        """pH=99 → status=rejected, out_of_range_features 包含 pH"""
        _setup_mock_models(monkeypatch)
        from framework.domain.other_models.model_6 import model_6_execution
        bad_input = dict(FULL_VALID_INPUT, pH=99.0)
        result = model_6_execution(bad_input)
        assert result["status"] == "rejected"
        assert result["reason"] == "input_out_of_range"
        assert result["soc_prediction"] is None
        assert result["dose_prediction"] is None
        oor_features = [f["feature"] for f in result["out_of_range_features"]]
        assert "pH" in oor_features

    def test_rejected_fertilizer_type_invalid(self, monkeypatch):
        """Fertilizer type=3 → status=rejected"""
        _setup_mock_models(monkeypatch)
        from framework.domain.other_models.model_6 import model_6_execution
        bad_input = dict(FULL_VALID_INPUT, **{"Fertilizer type": 3})
        result = model_6_execution(bad_input)
        assert result["status"] == "rejected"
        oor_features = [f["feature"] for f in result["out_of_range_features"]]
        assert "Fertilizer type" in oor_features

    def test_empty_input_uses_all_means(self, monkeypatch):
        """空字典 → 全部特征用均值填充，imputed_features 非空"""
        _setup_mock_models(monkeypatch)
        from framework.domain.other_models.model_6 import model_6_execution
        result = model_6_execution({})
        assert result["status"] == "success"
        assert result["imputation_applied"] is True
        # SOC 10 特征全部填充
        assert len(result["imputed_features"]) >= 10

    def test_none_input_coerced_to_empty(self, monkeypatch):
        """None 输入 → coerce 为 {} 后走空字典路径"""
        _setup_mock_models(monkeypatch)
        from framework.domain.other_models.model_6 import model_6_execution
        result = model_6_execution(None)
        assert result["status"] == "success"
        assert result["imputation_applied"] is True

    def test_string_numeric_coercion(self, monkeypatch):
        """'1.5' 字符串 → float 转换成功，正常预测"""
        _setup_mock_models(monkeypatch)
        from framework.domain.other_models.model_6 import model_6_execution
        str_input = {k: str(v) for k, v in FULL_VALID_INPUT.items()}
        result = model_6_execution(str_input)
        assert result["status"] == "success"
        assert result["imputation_applied"] is False

    def test_string_non_numeric_uses_mean(self, monkeypatch):
        """'abc' 字符串 → 转换失败，用均值填充"""
        _setup_mock_models(monkeypatch)
        from framework.domain.other_models.model_6 import model_6_execution
        bad_str_input = dict(FULL_VALID_INPUT, pH="abc")
        result = model_6_execution(bad_str_input)
        assert result["status"] == "success"
        assert result["imputation_applied"] is True
        assert "pH" in result["imputed_features"]

    def test_feature_name_with_trailing_space(self, monkeypatch):
        """用户传 'TN'，模型 feature_names 含 'TN ' → 正确匹配"""
        _setup_mock_models(monkeypatch)
        from framework.domain.other_models.model_6 import model_6_execution
        result = model_6_execution(FULL_VALID_INPUT)
        assert result["status"] == "success"
        # TN 未被填充说明正确匹配了 'TN ' → 'TN'
        assert "TN" not in result["imputed_features"]

    def test_unexpected_error_fallback(self, monkeypatch):
        """model.predict 抛异常 → status=fallback, fallback_reason=unexpected_error"""
        _setup_mock_models(monkeypatch)
        from framework.domain.other_models import model_6

        class CrashModel:
            def predict(self, df):
                raise RuntimeError("predict crashed")
        monkeypatch.setattr(model_6, "_SOC_MODEL", CrashModel())
        result = model_6.model_6_execution(FULL_VALID_INPUT)
        assert result["status"] == "fallback"
        assert result["fallback_reason"] == "unexpected_error"

    def test_backward_compat_import(self):
        """__init__.py 的 from .model_6 import model_6_execution 仍可用"""
        from framework.domain.other_models import model_6_execution
        assert callable(model_6_execution)


# ---- 集成测试（真实模型，可跳过）----

def _check_integration_available():
    try:
        from framework.domain.other_models import model_6
        return (
            model_6._SKLEARN_AVAILABLE
            and model_6._ensure_models_loaded()
        )
    except Exception:
        return False


@pytest.mark.skipif(
    not _check_integration_available(),
    reason="sklearn 或模型文件不可用"
)
class TestModel6Integration:
    def test_real_soc_prediction_in_range(self):
        """真实预测：典型土壤样本 → SOC 在 0-50 g/kg 合理范围"""
        from framework.domain.other_models.model_6 import model_6_execution
        result = model_6_execution(FULL_VALID_INPUT)
        assert result["status"] == "success"
        assert 0.0 <= result["soc_prediction"] <= 50.0

    def test_real_dose_prediction_in_range(self):
        """真实预测：Dose 在 0-1000 t/ha 合理范围"""
        from framework.domain.other_models.model_6 import model_6_execution
        result = model_6_execution(FULL_VALID_INPUT)
        assert result["status"] == "success"
        assert 0.0 <= result["dose_prediction"] <= 1000.0

    def test_real_model_files_exist(self):
        """验证 .joblib 与 metadata.json 文件存在且可加载"""
        from framework.domain.other_models.model_6 import (
            _SOC_MODEL_PATH, _SOC_META_PATH, _DOSE_MODEL_PATH, _DOSE_META_PATH
        )
        assert _SOC_MODEL_PATH.exists()
        assert _SOC_META_PATH.exists()
        assert _DOSE_MODEL_PATH.exists()
        assert _DOSE_META_PATH.exists()
```

### Step 2: 运行测试确认失败

```bash
python -m pytest tests/test_fertility_ml_prediction.py -v -k "not Integration"
```

Expected: FAIL，`model_6_execution` 返回的 stub 字典不含 `soc_prediction`、`soc_confidence` 等字段，断言失败。

### Step 3: 实现 `framework/domain/other_models/model_6.py` 完整重写

```python
from __future__ import annotations
import json
import logging
import threading
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pandas as pd

logger = logging.getLogger(__name__)

# ---- 模型文件路径（项目相对）----
# model_6.py 位于 framework/domain/other_models/model_6.py
# parents[0]=other_models, [1]=domain, [2]=framework, [3]=项目根
_MODELS_DIR = Path(__file__).resolve().parents[3] / "data" / "fertility" / "models"
_SOC_MODEL_PATH = _MODELS_DIR / "soc_etr_model.joblib"
_SOC_META_PATH = _MODELS_DIR / "soc_metadata.json"
_DOSE_MODEL_PATH = _MODELS_DIR / "dose_etr_model.joblib"
_DOSE_META_PATH = _MODELS_DIR / "dose_metadata.json"

# ---- 尝试导入 sklearn / joblib ----
try:
    import joblib
    _SKLEARN_AVAILABLE = True
except ImportError:
    _SKLEARN_AVAILABLE = False

logger.info("model_6 module imported, sklearn_available=%s", _SKLEARN_AVAILABLE)

# ---- 惰性单例状态 ----
_SOC_MODEL = None
_DOSE_MODEL = None
_SOC_META = None
_DOSE_META = None
_SOC_LOAD_FAILED = False
_DOSE_LOAD_FAILED = False
_LOAD_LOCK = threading.Lock()

_MODEL_VERSION = "ETR_v1_20260713"

# ---- 特征合法范围 ----
FEATURE_RANGES = {
    "pH":              (3.0,    11.0),
    "SOCbe":           (0.0,    100.0),
    "TN":              (0.0,    10.0),
    "TP":              (0.0,    10.0),
    "TK":              (0.0,    100.0),
    "AP":              (0.0,    200.0),
    "AK":              (0.0,    500.0),
    "Gap":             (-10.0,  50.0),
    "Dose":            (0.0,    1000.0),
    "Fertilizer type": (1,      2),
}


def _prepare_features(
    input_data: Dict[str, Any],
    feature_names: List[str],
    feature_means: Dict[str, float],
) -> Tuple[pd.DataFrame, List[str], List[Dict[str, Any]]]:
    """准备特征 DataFrame，返回 (df, imputed_list, out_of_range_list)。

    - input_data 的 key 做 strip() 规范化（兼容 "TN " / "TN"）
    - 缺失/转换失败的字段用 feature_means 填充，加入 imputed_list
    - 越界字段加入 out_of_range_list，同时用均值填充
    """
    normalized = {
        k.strip(): v for k, v in (input_data or {}).items() if v is not None
    }
    row: Dict[str, Any] = {}
    imputed: List[str] = []
    out_of_range: List[Dict[str, Any]] = []

    for fname in feature_names:
        fname_stripped = fname.strip()
        if fname_stripped in normalized:
            try:
                value = float(normalized[fname_stripped])
                lo, hi = FEATURE_RANGES.get(fname_stripped, (None, None))
                if lo is not None and (value < lo or value > hi):
                    out_of_range.append({
                        "feature": fname,
                        "value": value,
                        "valid_range": [lo, hi],
                    })
                    row[fname] = feature_means[fname]
                    imputed.append(fname)
                else:
                    row[fname] = value
                continue
            except (ValueError, TypeError):
                pass
        row[fname] = feature_means[fname]
        imputed.append(fname)

    return pd.DataFrame([row], columns=feature_names), imputed, out_of_range


def _load_model_and_meta(model_path: Path, meta_path: Path):
    """加载 .joblib 模型与 metadata.json"""
    model = joblib.load(model_path)
    with open(meta_path, "r", encoding="utf-8") as f:
        meta = json.load(f)
    return model, meta


def _ensure_models_loaded() -> bool:
    """惰性加载模型，double-checked locking 保证线程安全。返回是否加载成功。"""
    global _SOC_MODEL, _DOSE_MODEL, _SOC_META, _DOSE_META
    global _SOC_LOAD_FAILED, _DOSE_LOAD_FAILED

    if _SOC_LOAD_FAILED or _DOSE_LOAD_FAILED:
        return False

    if _SOC_MODEL is None and not _SOC_LOAD_FAILED:
        with _LOAD_LOCK:
            if _SOC_MODEL is None and not _SOC_LOAD_FAILED:
                try:
                    _SOC_MODEL, _SOC_META = _load_model_and_meta(
                        _SOC_MODEL_PATH, _SOC_META_PATH
                    )
                    logger.info(
                        "SOC model loaded, feature_names=%s, test_r2=%.4f",
                        _SOC_META["feature_names"],
                        _SOC_META["metrics"]["test_r2"],
                    )
                except Exception:
                    _SOC_LOAD_FAILED = True
                    logger.exception("Failed to load SOC model")

    if _DOSE_MODEL is None and not _DOSE_LOAD_FAILED:
        with _LOAD_LOCK:
            if _DOSE_MODEL is None and not _DOSE_LOAD_FAILED:
                try:
                    _DOSE_MODEL, _DOSE_META = _load_model_and_meta(
                        _DOSE_MODEL_PATH, _DOSE_META_PATH
                    )
                    logger.info(
                        "Dose model loaded, feature_names=%s, test_r2=%.4f",
                        _DOSE_META["feature_names"],
                        _DOSE_META["metrics"]["test_r2"],
                    )
                except Exception:
                    _DOSE_LOAD_FAILED = True
                    logger.exception("Failed to load Dose model")

    if _SOC_LOAD_FAILED or _DOSE_LOAD_FAILED:
        return False
    return True


def _fallback_response(input_data: Dict[str, Any], reason: str) -> Dict[str, Any]:
    """构造 fallback 响应，使用训练集均值作为粗估。"""
    return {
        "status": "fallback",
        "soc_prediction": _SOC_META["feature_means"].get("SOCbe", 12.0) if _SOC_META else 12.0,
        "soc_confidence": 0.3,
        "dose_prediction": _DOSE_META["feature_means"].get("Dose", 100.0) if _DOSE_META else 100.0,
        "dose_confidence": 0.3,
        "dose_warning": "模型不可用，返回训练集均值估算" if reason != "input_out_of_range" else "输入值越界，未执行预测",
        "imputed_features": [],
        "imputation_applied": False,
        "model_version": _MODEL_VERSION,
        "fallback_reason": reason,
    }


def model_6_execution(input_data: Dict[str, Any]) -> Dict[str, Any]:
    """SOC + Dose ML 预测主入口。

    输入：特征字典（key 可含/不含尾随空格，可缺字段）
    输出：预测结果字典，含 status/soc_prediction/dose_prediction 等字段
    """
    try:
        # 1. 检查 sklearn 可用性
        if not _SKLEARN_AVAILABLE:
            return _fallback_response(input_data or {}, reason="sklearn_missing")

        # 2. 检查模型加载状态（首次触发加载）
        if not _ensure_models_loaded():
            return _fallback_response(input_data or {}, reason="model_file_missing")

        # 3. 准备 SOC 特征（10 因子）
        soc_df, soc_imputed, soc_oor = _prepare_features(
            input_data or {}, _SOC_META["feature_names"], _SOC_META["feature_means"]
        )

        # 4. 准备 Dose 特征（9 因子，去掉 Dose 自身）
        dose_input = {
            k: v for k, v in (input_data or {}).items() if k.strip() != "Dose"
        }
        dose_df, dose_imputed, dose_oor = _prepare_features(
            dose_input, _DOSE_META["feature_names"], _DOSE_META["feature_means"]
        )

        # 5. 范围校验：任一越界即拒绝
        all_oor = soc_oor + dose_oor
        if all_oor:
            return {
                "status": "rejected",
                "reason": "input_out_of_range",
                "out_of_range_features": all_oor,
                "soc_prediction": None,
                "soc_confidence": 0.0,
                "dose_prediction": None,
                "dose_confidence": 0.0,
                "dose_warning": "输入值越界，未执行预测",
                "imputed_features": [],
                "imputation_applied": False,
                "model_version": _MODEL_VERSION,
            }

        # 6. 执行预测
        soc_pred = float(_SOC_MODEL.predict(soc_df)[0])
        dose_pred = float(_DOSE_MODEL.predict(dose_df)[0])

        logger.info(
            "model_6_execution success: SOC=%.4f, Dose=%.4f", soc_pred, dose_pred
        )

        # 7. 构造响应
        return {
            "status": "success",
            "soc_prediction": round(soc_pred, 4),
            "soc_confidence": round(_SOC_META["metrics"]["test_r2"], 2),
            "dose_prediction": round(dose_pred, 4),
            "dose_confidence": round(_DOSE_META["metrics"]["test_r2"], 2),
            "dose_warning": "Dose 模型 R²=0.47，预测结果仅供参考，建议结合田间试验校准",
            "imputed_features": sorted(set(soc_imputed + dose_imputed)),
            "imputation_applied": bool(soc_imputed or dose_imputed),
            "model_version": _MODEL_VERSION,
        }

    except Exception as e:
        logger.exception(f"model_6_execution unexpected error: {e}")
        return _fallback_response(input_data or {}, reason="unexpected_error")
```

### Step 4: 运行单元测试确认通过

```bash
python -m pytest tests/test_fertility_ml_prediction.py -v -k "not Integration"
```

Expected: 13 个单元测试全部 PASS（含 `test_backward_compat_import`）。

### Step 5: 运行集成测试（如有真实模型文件）

```bash
python -m pytest tests/test_fertility_ml_prediction.py -v -k "Integration"
```

Expected: 3 个集成测试 PASS（sklearn 与模型文件都可用，Task 2 已生成）；否则 SKIP。

### Step 6: 验证 `__init__.py` 向后兼容

```bash
python -c "from framework.domain.other_models import model_6_execution; print(callable(model_6_execution))"
```

Expected: 输出 `True`。

### Step 7: 提交

```bash
git add framework/domain/other_models/model_6.py tests/test_fertility_ml_prediction.py
git commit -m "feat(model-6): 实现 model_6_execution ML 预测引擎（惰性加载+三层异常防线+范围校验）"
```

## Global Constraints（摘自 plan）

- 模型版本号统一为 `"ETR_v1_20260713"`（设计文档 2.3、5.3）
- SOC 模型 confidence = 0.91（来自 `metadata.metrics.test_r2`，round 2 位小数）；Dose 模型 confidence = 0.47（设计文档 2.3）
- Fallback 时 confidence 降为 0.3，使用训练集均值作为占位预测（设计文档 2.4）
- 模型文件路径用 `Path(__file__).resolve().parents[3] / "data" / "fertility" / "models"` 计算（设计文档 6.5）
- 特征名保留原始含空格形式（`"TN "`、`"TP "`），与训练时 `Xtrain.columns` 一致；用户输入层做 `strip()` 规范化（设计文档 2.2）
- 范围校验合法范围：pH(3-11)、SOCbe(0-100)、TN(0-10)、TP(0-10)、TK(0-100)、AP(0-200)、AK(0-500)、Gap(-10~50)、Dose(0-1000)、Fertilizer type(1-2)（设计文档 2.2）
- 任一特征越界即整体拒绝 `status: "rejected"`，不执行预测（设计文档 2.3）
- 任一模型文件缺失即整体降级 `status: "fallback"`，不混合正常+fallback（设计文档 2.4）
- Dose 单位统一为 t/ha（与训练数据 `变量注释.xlsx` 原始单位一致）（设计文档 3.5）
- 模型加载用 double-checked locking + `threading.Lock` 保证线程安全；加载失败后不重试（`_SOC_LOAD_FAILED = True`）（设计文档 2.x）

## 注意事项（plan 已修复的 bug）

- **集成测试类去重**：plan 原文 line 547-575 有一个 placeholder `class TestModel6Integration: pass` 然后再次 `class TestModel6Integration:` 定义真实测试。这会导致 Python 类重定义，第二个类覆盖第一个，skipif 装饰器丢失。本 brief 中已修复——直接使用 `@pytest.mark.skipif(not _check_integration_available(), reason="...")` 装饰真实集成测试类。请使用 brief 中的代码版本。
- **`_check_integration_available()` 副作用**：此函数会触发 `model_6._ensure_models_loaded()`，即首次调用会真正尝试加载模型文件。这是预期行为，集成测试需要真实模型才能跑。
- **TDD Red-Green**：Step 1 创建测试 → Step 2 运行确认 RED → Step 3 实现 → Step 4 运行确认 GREEN。必须严格按此顺序，不得跳过 RED 阶段。

## 风险信号预估（主会话预判，implementer 仍需自报）

- **diff > 200 行**：命中（test ~270 行 + model ~240 行 = ~510 行）
- **并发**：命中（`threading.Lock` + double-checked locking）
- **跨模块**：弱命中（重写 `framework/domain/other_models/model_6.py`，但 `__init__.py` 的 import 不变，向后兼容）
- 其他信号（安全/数据迁移/API 变更）：不命中

按 `review_mode: standard`，diff>200 + 并发命中 → 主会话将在 implementer 完成后派发 reviewer。

## 报告契约

implementer 完成后写入 `openspec/changes/add-model-6-fertility-ml/.comet/subagent-reports/task-3-report.md`，包含：
1. **Status**: DONE / DONE_WITH_CONCERNS / NEEDS_CONTEXT / BLOCKED
2. **Commits**: commit hash + 简短描述
3. **测试摘要**:
   - RED 阶段输出（Step 2 失败的测试列表）
   - GREEN 阶段输出（Step 4 通过的 13 个测试列表）
   - 集成测试结果（Step 5，PASS 或 SKIP 及数量）
4. **Concerns**: 任何顾虑（如 test_r2 实际值与 0.91/0.47 偏差、CV 警告等）
5. **风险信号自报**: 跨模块协调 / 安全敏感 / 并发 / 数据迁移 / API 变更 / DONE_WITH_CONCERNS / diff>200 行
