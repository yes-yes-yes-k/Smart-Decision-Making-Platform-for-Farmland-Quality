---
change: add-model-6-fertility-ml
design-doc: docs/superpowers/specs/2026-07-18-add-model-6-fertility-ml-design.md
base-ref: 44f423f8efbe18941fe740a56f2cbe0c0c87b2e2
---

# Model-6 耕地肥力 ML 预测 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 model-6 从占位 `ComprehensiveImprovementAgent` 替换为基于真实 ExtraTreesRegressor 模型的 `FertilityMLAgent`，实现 SOC（土壤有机碳）与 Dose（施用量）的机器学习预测，支持惰性加载、三层异常防线、范围校验拒绝与按需过滤。

**Architecture:** 底层计算引擎 `framework/domain/other_models/model_6.py` 通过惰性单例加载 `.joblib` 模型文件，提供 `model_6_execution(input_data)` 函数返回预测结果字典；`FertilityMLAgent` 作为薄包装封装该函数并处理 Dose/SOC/综合三种问答分支；`AgentManager` 新增 `_should_execute_agent` 按需过滤，非肥力问题跳过 model-6 执行；训练脚本 `scripts/train_fertility_models.py` 使用 hardcoded 最优超参数生成模型文件。

**Tech Stack:** Python 3.10+、scikit-learn >=1.3.0（ExtraTreesRegressor）、joblib >=1.3.0（模型序列化）、pandas >=2.0（特征 DataFrame）、pytest（monkeypatch 单元测试 + skipif 集成测试）

**设计文档：** [docs/superpowers/specs/2026-07-18-add-model-6-fertility-ml-design.md](../specs/2026-07-18-add-model-6-fertility-ml-design.md)

## Global Constraints

- 模型版本号统一为 `"ETR_v1_20260713"`（设计文档 2.3、5.3）
- SOC 模型 confidence = 0.91（来自 `metadata.metrics.test_r2`，round 2 位小数）；Dose 模型 confidence = 0.47（设计文档 2.3）
- Fallback 时 confidence 降为 0.3，使用训练集均值作为占位预测（设计文档 2.4）
- 模型文件路径用 `Path(__file__).resolve().parents[3] / "data" / "fertility" / "models"` 计算（设计文档 6.5；注意：设计文档原文写 `parents[4]` 但实际 `model_6.py` → `other_models` → `domain` → `framework` → 项目根 = 3 跳，应为 `parents[3]`）
- 特征名保留原始含空格形式（`"TN "`、`"TP "`），与训练时 `Xtrain.columns` 一致；用户输入层做 `strip()` 规范化（设计文档 2.2）
- 范围校验合法范围：pH(3-11)、SOCbe(0-100)、TN(0-10)、TP(0-10)、TK(0-100)、AP(0-200)、AK(0-500)、Gap(-10~50)、Dose(0-1000)、Fertilizer type(1-2)（设计文档 2.2）
- 任一特征越界即整体拒绝 `status: "rejected"`，不执行预测（设计文档 2.3）
- 任一模型文件缺失即整体降级 `status: "fallback"`，不混合正常+fallback（设计文档 2.4）
- Dose 单位统一为 t/ha（与训练数据 `变量注释.xlsx` 原始单位一致，修正 OpenSpec spec 中 "kg/亩" 的歧义）（设计文档 3.5）
- 模型加载用 double-checked locking + `threading.Lock` 保证线程安全；加载失败后不重试（`_SOC_LOAD_FAILED = True`）（设计文档 2.1）
- `model_6_execution` 函数签名与 `__init__.py` 导出名保持不变（向后兼容）（设计文档 1.1、tasks 3.9）
- 测试运行命令：`python -m pytest tests/ -v`（项目既有约定，无 conftest/pytest.ini）
- 现有测试文件风格：`sys.path.insert(0, ...)` + 纯函数 `def test_...()`；新测试文件可用 class 风格
- `pyproject.toml` 使用 Poetry 风格版本号 `^1.3.0`（与现有 `pandas = "^2.2.0"` 一致）
- 训练数据来源：`F:\BaiduNetdiskDownload\SOC（土壤有机碳）和Dose（施用量）预测模型\`

---

## 任务概览

| 计划任务 | 对应 tasks.md | 职责 |
|---------|--------------|------|
| Task 1 | 1.1-1.6 | 数据资产迁移与依赖声明 |
| Task 2 | 2.1-2.6 | 训练脚本与模型生成 |
| Task 3 | 3.1-3.9 | model_6.py 真实 ML 实现（特征准备、模型加载、预测、降级） |
| Task 4 | 4.1-4.6 | FertilityMLAgent 智能体 |
| Task 5 | 5.1-5.4 | AgentManager 集成与按需过滤 |
| Task 6 | 6.1-6.3 | ComprehensiveImprovementAgent 清理 |
| Task 7 | 7.1-7.4 | 测试套件整合与全量验证 |
| Task 8 | 8.1-8.6 | 端到端集成验证 |

---

### Task 1: 数据资产迁移与依赖声明

**Files:**
- Create: `data/fertility/`（目录）
- Create: `data/fertility/models/`（目录）
- Copy: `data/fertility/ML-data-SOC-RF_Manual_splits.xlsx`（从源路径）
- Copy: `data/fertility/ML-data-Dose-RF-Manual_splits.xlsx`（从源路径）
- Copy: `data/fertility/变量注释.xlsx`（从源路径）
- Modify: `.gitignore`
- Modify: `pyproject.toml`

**Interfaces:**
- Consumes: 无
- Produces: `data/fertility/` 目录含 3 个 xlsx 训练数据文件；`pyproject.toml` 新增 `scikit-learn` 与 `joblib` 依赖。Task 2 训练脚本读取这些 xlsx 文件，Task 3 model_6.py 加载 `data/fertility/models/` 下的产物。

- [x] **Step 1: 创建数据目录并复制训练数据文件**

在 PowerShell 中执行：

```powershell
New-Item -ItemType Directory -Force -Path "data\fertility\models"
Copy-Item "F:\BaiduNetdiskDownload\SOC（土壤有机碳）和Dose（施用量）预测模型\ML-data-SOC-RF_Manual_splits.xlsx" "data\fertility\"
Copy-Item "F:\BaiduNetdiskDownload\SOC（土壤有机碳）和Dose（施用量）预测模型\ML-data-Dose-RF-Manual_splits.xlsx" "data\fertility\"
Copy-Item "F:\BaiduNetdiskDownload\SOC（土壤有机碳）和Dose（施用量）预测模型\变量注释.xlsx" "data\fertility\"
```

- [x] **Step 2: 验证文件已复制且大小 <10MB**

```powershell
Get-Item data\fertility\*.xlsx | Select-Object Name, @{N='SizeMB';E={[math]::Round($_.Length/1MB,2)}}
```

Expected: 3 个文件均列出，SizeMB 均 < 10。

- [x] **Step 3: 更新 `.gitignore` 确保 `data/fertility/` 不被忽略**

在 `.gitignore` 末尾追加：

```gitignore

# Fertility ML 训练数据与模型文件（入库，不忽略）
!data/fertility/
!data/fertility/**

# 忽略训练过程临时文件
*.pkl.bak
```

- [x] **Step 4: 修改 `pyproject.toml` 新增依赖**

在 `[project.dependencies]` 的 `waitress = "^3.0.0"` 行后追加两行：

```toml
scikit-learn = "^1.3.0"
joblib = "^1.3.0"
```

- [x] **Step 5: 安装依赖并验证**

```bash
pip install -e .
python -c "import sklearn; import joblib; print(sklearn.__version__, joblib.__version__)"
```

Expected: 输出两个版本号，均 >= 1.3.0，无 ImportError。

- [x] **Step 6: 提交**

```bash
git add data/fertility/ .gitignore pyproject.toml
git commit -m "feat(fertility): 迁移训练数据资产并声明 scikit-learn/joblib 依赖"
```

---

### Task 2: 训练脚本与模型生成

**Files:**
- Create: `scripts/train_fertility_models.py`
- Generate: `data/fertility/models/soc_etr_model.joblib`
- Generate: `data/fertility/models/soc_metadata.json`
- Generate: `data/fertility/models/dose_etr_model.joblib`
- Generate: `data/fertility/models/dose_metadata.json`

**Interfaces:**
- Consumes: `data/fertility/ML-data-SOC-RF_Manual_splits.xlsx`、`data/fertility/ML-data-Dose-RF-Manual_splits.xlsx`（Task 1 产物）
- Produces: 4 个模型产物文件。Task 3 `model_6.py` 运行时通过 `joblib.load()` 加载 `.joblib` 文件，通过 `json.load()` 加载 `metadata.json` 文件。metadata schema 必须包含 `feature_names`（list[str]，保留含空格形式）、`feature_means`（dict[str, float]）、`metrics.test_r2`（float）、`hyperparameters`（dict）、`model_type`、`trained_at`、`model_version`。

- [ ] **Step 1: 创建训练脚本 `scripts/train_fertility_models.py`**

```python
"""训练 SOC 和 Dose ExtraTreesRegressor 模型并保存为 .joblib 文件。

用法：
    python scripts/train_fertility_models.py \
        --data-dir data/fertility \
        --output-dir data/fertility/models
"""
from __future__ import annotations
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import ExtraTreesRegressor
from sklearn.metrics import mean_squared_error
from sklearn.model_selection import cross_val_score

# notebook 已确定的最优超参数（hardcoded，不重跑网格搜索）
SOC_BEST_PARAMS = {
    "n_estimators": 30, "max_depth": 10,
    "min_samples_split": 2, "min_samples_leaf": 1,
    "max_features": None, "criterion": "squared_error",
    "random_state": 0, "n_jobs": -1,
}
DOSE_BEST_PARAMS = {
    "n_estimators": 290, "max_depth": 10,
    "min_samples_split": 10, "min_samples_leaf": 1,
    "max_features": 0.7, "criterion": "friedman_mse",
    "random_state": 86, "n_jobs": -1,
}

MODEL_VERSION = "ETR_v1_20260713"


def load_manual_splits(xlsx_path: Path):
    """读取手动划分的 xlsx，返回 (Xtrain, Xtest, Ytrain, Ytest)。

    xlsx 文件应含 Xtrain/Xtest/Ytrain/Ytest 四个 sheet（容错大小写/空格）。
    """
    xl = pd.ExcelFile(xlsx_path)
    expected = ["Xtrain", "Xtest", "Ytrain", "Ytest"]
    sheet_map = {}
    for exp in expected:
        for actual in xl.sheet_names:
            if actual.strip().lower().replace(" ", "") == exp.lower():
                sheet_map[exp] = actual
                break
    missing = [s for s in expected if s not in sheet_map]
    if missing:
        raise ValueError(
            f"{xlsx_path} 缺少 sheet: {missing}，现有 sheets: {xl.sheet_names}"
        )
    Xtrain = pd.read_excel(xlsx_path, sheet_name=sheet_map["Xtrain"])
    Xtest = pd.read_excel(xlsx_path, sheet_name=sheet_map["Xtest"])
    Ytrain = pd.read_excel(xlsx_path, sheet_name=sheet_map["Ytrain"]).values.ravel()
    Ytest = pd.read_excel(xlsx_path, sheet_name=sheet_map["Ytest"]).values.ravel()
    return Xtrain, Xtest, Ytrain, Ytest


def train_one_model(name: str, xlsx_path: Path, params: dict, output_dir: Path) -> dict:
    print(f"\n=== 训练 {name} 模型 ===")
    Xtrain, Xtest, Ytrain, Ytest = load_manual_splits(xlsx_path)
    print(f"训练集: {Xtrain.shape[0]} 样本, {Xtrain.shape[1]} 特征")
    print(f"测试集: {Xtest.shape[0]} 样本")
    print(f"特征名: {list(Xtrain.columns)}")

    model = ExtraTreesRegressor(**params)
    model.fit(Xtrain, Ytrain)

    # 5-fold CV（n_jobs=1 避免 Windows 并行开销）
    cv_params = {k: v for k, v in params.items() if k != "n_jobs"}
    cv_r2_scores = cross_val_score(
        ExtraTreesRegressor(**cv_params), Xtrain, Ytrain, cv=5, scoring="r2"
    )
    cv_r2 = float(np.mean(cv_r2_scores))
    cv_mse_scores = cross_val_score(
        ExtraTreesRegressor(**cv_params), Xtrain, Ytrain, cv=5,
        scoring="neg_mean_squared_error",
    )
    cv_rmse = float(np.sqrt(-np.mean(cv_mse_scores)))

    # 测试集
    Ypred = model.predict(Xtest)
    test_r2 = float(model.score(Xtest, Ytest))
    test_rmse = float(np.sqrt(mean_squared_error(Ytest, Ypred)))

    print(f"5CV R²: {cv_r2:.4f}, 5CV RMSE: {cv_rmse:.4f}")
    print(f"Test R²: {test_r2:.4f}, Test RMSE: {test_rmse:.4f}")
    print(f"超参数: {params}")

    # 保存模型
    model_path = output_dir / f"{name.lower()}_etr_model.joblib"
    joblib.dump(model, model_path)
    print(f"模型已保存: {model_path}")

    # 保存元数据
    hyperparams_for_meta = {k: v for k, v in params.items() if k != "n_jobs"}
    meta = {
        "model_type": "ExtraTreesRegressor",
        "trained_at": datetime.now().isoformat(timespec="seconds"),
        "model_version": MODEL_VERSION,
        "hyperparameters": hyperparams_for_meta,
        "metrics": {
            "cv_r2": round(cv_r2, 4),
            "cv_rmse": round(cv_rmse, 4),
            "test_r2": round(test_r2, 4),
            "test_rmse": round(test_rmse, 4),
        },
        "feature_names": list(Xtrain.columns),
        "feature_means": {k: float(v) for k, v in Xtrain.mean().items()},
        "training_samples": int(Xtrain.shape[0]),
        "test_samples": int(Xtest.shape[0]),
    }
    meta_path = output_dir / f"{name.lower()}_metadata.json"
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    print(f"元数据已保存: {meta_path}")

    return meta


def main():
    parser = argparse.ArgumentParser(description="训练 SOC 和 Dose ETR 模型")
    parser.add_argument("--data-dir", default="data/fertility", help="训练数据目录")
    parser.add_argument("--output-dir", default="data/fertility/models", help="模型输出目录")
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    soc_xlsx = data_dir / "ML-data-SOC-RF_Manual_splits.xlsx"
    dose_xlsx = data_dir / "ML-data-Dose-RF-Manual_splits.xlsx"

    for xlsx in [soc_xlsx, dose_xlsx]:
        if not xlsx.exists():
            print(f"错误: 训练数据文件不存在: {xlsx}", file=sys.stderr)
            sys.exit(1)

    soc_meta = train_one_model("SOC", soc_xlsx, SOC_BEST_PARAMS, output_dir)
    dose_meta = train_one_model("Dose", dose_xlsx, DOSE_BEST_PARAMS, output_dir)

    print("\n=== 训练完成 ===")
    print(f"SOC test_r2: {soc_meta['metrics']['test_r2']}")
    print(f"Dose test_r2: {dose_meta['metrics']['test_r2']}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 运行训练脚本生成模型文件**

```bash
python scripts/train_fertility_models.py --data-dir data/fertility --output-dir data/fertility/models
```

Expected: 控制台输出 SOC 和 Dose 的 5CV R²、Test R²、RMSE 与超参数；无报错。

- [ ] **Step 3: 验证 4 个产物文件已生成**

```powershell
Get-Item data\fertility\models\* | Select-Object Name, @{N='SizeKB';E={[math]::Round($_.Length/1KB,1)}}
```

Expected: 列出 `soc_etr_model.joblib`、`soc_metadata.json`、`dose_etr_model.joblib`、`dose_metadata.json` 4 个文件。

- [ ] **Step 4: 验证 metadata.json 内容完整**

```bash
python -c "import json; m=json.load(open('data/fertility/models/soc_metadata.json',encoding='utf-8')); print(m['model_type'], m['model_version'], m['metrics']['test_r2'], len(m['feature_names']), m['feature_names'])"
```

Expected: 输出 `ExtraTreesRegressor ETR_v1_20260713 0.9096 10 ['pH', 'SOCbe', 'TN ', 'TP ', 'TK ', 'AP', 'AK', 'Gap', 'Dose', 'Fertilizer type']`（test_r2 值可能略有差异但应接近 0.91）。

- [ ] **Step 5: 提交**

```bash
git add scripts/train_fertility_models.py data/fertility/models/
git commit -m "feat(fertility): 训练 SOC/Dose ETR 模型并生成 joblib 与 metadata 产物"
```

---

### Task 3: model_6.py 真实 ML 实现

**Files:**
- Modify: `framework/domain/other_models/model_6.py`（完全重写）
- Test: `tests/test_fertility_ml_prediction.py`（新文件）

**Interfaces:**
- Consumes: `data/fertility/models/*.joblib` 与 `*.json`（Task 2 产物）；`pandas`（已声明依赖）；`sklearn`/`joblib`（Task 1 新增依赖）
- Produces: `model_6_execution(input_data: Dict[str, Any]) -> Dict[str, Any]` 函数，返回字典含字段：`status`("success"|"fallback"|"rejected")、`soc_prediction`、`soc_confidence`、`dose_prediction`、`dose_confidence`、`dose_warning`、`imputed_features`、`imputation_applied`、`model_version`，fallback 时额外含 `fallback_reason`，rejected 时额外含 `reason` 与 `out_of_range_features`。Task 4 `FertilityMLAgent` 调用此函数；`framework/domain/other_models/__init__.py` 的 `from .model_6 import model_6_execution` 保持不变。

- [ ] **Step 1: 创建测试文件 `tests/test_fertility_ml_prediction.py`**

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

@pytest.mark.skipif(
    True,  # 占位，下方动态替换
    reason="placeholder"
)
class TestModel6Integration:
    pass


def _check_integration_available():
    try:
        from framework.domain.other_models import model_6
        return (
            model_6._SKLEARN_AVAILABLE
            and model_6._ensure_models_loaded()
        )
    except Exception:
        return False


# 动态设置 skipif 条件
TestModel6Integration = pytest.mark.skipif(
    not _check_integration_available(),
    reason="sklearn 或模型文件不可用"
)(TestModel6Integration)


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

- [ ] **Step 2: 运行测试确认失败**

```bash
python -m pytest tests/test_fertility_ml_prediction.py -v -k "not Integration"
```

Expected: FAIL，`model_6_execution` 返回的 stub 字典不含 `soc_prediction`、`soc_confidence` 等字段，断言失败。

- [ ] **Step 3: 实现 `framework/domain/other_models/model_6.py` 完整重写**

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

- [ ] **Step 4: 运行单元测试确认通过**

```bash
python -m pytest tests/test_fertility_ml_prediction.py -v -k "not Integration"
```

Expected: 13 个单元测试全部 PASS（含 `test_backward_compat_import`）。

- [ ] **Step 5: 运行集成测试（如有真实模型文件）**

```bash
python -m pytest tests/test_fertility_ml_prediction.py -v -k "Integration"
```

Expected: 3 个集成测试 PASS（如果 sklearn 与模型文件可用）；否则 SKIP。

- [ ] **Step 6: 验证 `__init__.py` 向后兼容**

```bash
python -c "from framework.domain.other_models import model_6_execution; print(callable(model_6_execution))"
```

Expected: 输出 `True`。

- [ ] **Step 7: 提交**

```bash
git add framework/domain/other_models/model_6.py tests/test_fertility_ml_prediction.py
git commit -m "feat(model-6): 实现 model_6_execution ML 预测引擎（惰性加载+三层异常防线+范围校验）"
```

---

### Task 4: FertilityMLAgent 智能体

**Files:**
- Create: `framework/agents/specialized/fertility_ml_agent.py`
- Modify: `framework/agents/specialized/__init__.py`
- Test: `tests/test_agent_specialized.py`（既有文件，新增测试函数）

**Interfaces:**
- Consumes: `model_6_execution`（Task 3 产物）；`BaseAgent`（既有）；`MockDataLoader.mark_simulated`（既有）
- Produces: `FertilityMLAgent(BaseAgent)` 类，`model_id="model-6"`，`domain="fertility_ml"`，`dependencies=[]`。`execute(task)` 返回 `{status, result, metadata}` 结构；`answer_question(question, context)` 返回 `{answer, evidence, sources}` 结构，按 Dose/SOC/综合 三分支格式化。Task 5 `AgentManager._load_real_agents` 导入并实例化此类。

- [ ] **Step 1: 在 `tests/test_agent_specialized.py` 末尾（`if __name__` 之前）新增 FertilityMLAgent 测试**

```python
def test_fertility_ml_agent_execute_structure(monkeypatch):
    """execute 返回结构包含 status/result/metadata 三层"""
    from framework.agents.specialized.fertility_ml_agent import FertilityMLAgent
    from framework.domain.other_models import model_6
    # mock model_6_execution 返回 success
    monkeypatch.setattr(
        "framework.agents.specialized.fertility_ml_agent.model_6_execution",
        lambda data: {
            "status": "success",
            "soc_prediction": 12.5,
            "soc_confidence": 0.91,
            "dose_prediction": 150.0,
            "dose_confidence": 0.47,
            "dose_warning": "Dose 模型 R²=0.47，预测结果仅供参考",
            "imputed_features": [],
            "imputation_applied": False,
            "model_version": "ETR_v1_20260713",
        }
    )
    agent = FertilityMLAgent()
    assert agent.model_id == "model-6"
    assert agent.dependencies == []
    result = agent.execute({"pH": 6.5})
    assert "status" in result
    assert "result" in result
    assert "metadata" in result
    assert result["result"]["soc_prediction"] == 12.5
    print("✓ FertilityMLAgent.execute 返回三层结构")


def test_fertility_ml_agent_answer_dose_keywords(monkeypatch):
    """问'施用量' → 仅返回 Dose 预测"""
    from framework.agents.specialized.fertility_ml_agent import FertilityMLAgent
    monkeypatch.setattr(
        "framework.agents.specialized.fertility_ml_agent.model_6_execution",
        lambda data: {
            "status": "success",
            "soc_prediction": 12.5,
            "soc_confidence": 0.91,
            "dose_prediction": 150.0,
            "dose_confidence": 0.47,
            "dose_warning": "Dose 模型 R²=0.47",
            "imputed_features": [],
            "imputation_applied": False,
            "model_version": "ETR_v1_20260713",
        }
    )
    agent = FertilityMLAgent()
    out = agent.answer_question("我这块地需要施多少肥？", {"data": {"pH": 6.5}})
    assert "施肥" in out["answer"] or "t/ha" in out["answer"]
    # evidence 应包含 dose_prediction 但不应包含 soc_prediction
    metrics = [e.get("metric") for e in out["evidence"]]
    assert "dose_prediction" in metrics
    assert "soc_prediction" not in metrics
    print("✓ FertilityMLAgent 施用量问题返回 Dose 预测")


def test_fertility_ml_agent_answer_soc_keywords(monkeypatch):
    """问'有机碳' → 仅返回 SOC 预测"""
    from framework.agents.specialized.fertility_ml_agent import FertilityMLAgent
    monkeypatch.setattr(
        "framework.agents.specialized.fertility_ml_agent.model_6_execution",
        lambda data: {
            "status": "success",
            "soc_prediction": 12.5,
            "soc_confidence": 0.91,
            "dose_prediction": 150.0,
            "dose_confidence": 0.47,
            "dose_warning": "Dose 模型 R²=0.47",
            "imputed_features": [],
            "imputation_applied": False,
            "model_version": "ETR_v1_20260713",
        }
    )
    agent = FertilityMLAgent()
    out = agent.answer_question("我的田有机碳含量多少？", {"data": {"pH": 6.5}})
    assert "SOC" in out["answer"] or "有机碳" in out["answer"]
    metrics = [e.get("metric") for e in out["evidence"]]
    assert "soc_prediction" in metrics
    assert "dose_prediction" not in metrics
    print("✓ FertilityMLAgent 有机碳问题返回 SOC 预测")


def test_fertility_ml_agent_answer_fertility_keywords(monkeypatch):
    """问'肥力' → 返回 SOC + Dose 综合诊断"""
    from framework.agents.specialized.fertility_ml_agent import FertilityMLAgent
    monkeypatch.setattr(
        "framework.agents.specialized.fertility_ml_agent.model_6_execution",
        lambda data: {
            "status": "success",
            "soc_prediction": 12.5,
            "soc_confidence": 0.91,
            "dose_prediction": 150.0,
            "dose_confidence": 0.47,
            "dose_warning": "Dose 模型 R²=0.47",
            "imputed_features": [],
            "imputation_applied": False,
            "model_version": "ETR_v1_20260713",
        }
    )
    agent = FertilityMLAgent()
    out = agent.answer_question("我的田肥力怎么样？", {"data": {"pH": 6.5}})
    metrics = [e.get("metric") for e in out["evidence"]]
    assert "soc_prediction" in metrics
    assert "dose_prediction" in metrics
    print("✓ FertilityMLAgent 肥力问题返回综合诊断")


def test_fertility_ml_agent_answer_fallback_status(monkeypatch):
    """status=fallback → answer 标注'模型不可用'"""
    from framework.agents.specialized.fertility_ml_agent import FertilityMLAgent
    monkeypatch.setattr(
        "framework.agents.specialized.fertility_ml_agent.model_6_execution",
        lambda data: {
            "status": "fallback",
            "soc_prediction": 12.0,
            "soc_confidence": 0.3,
            "dose_prediction": 100.0,
            "dose_confidence": 0.3,
            "dose_warning": "模型不可用，返回训练集均值估算",
            "imputed_features": [],
            "imputation_applied": False,
            "model_version": "ETR_v1_20260713",
            "fallback_reason": "model_file_missing",
        }
    )
    agent = FertilityMLAgent()
    out = agent.answer_question("我的田肥力怎么样？", {"data": {}})
    assert "模型不可用" in out["answer"] or "训练集均值" in out["answer"]
    print("✓ FertilityMLAgent fallback 时标注模型不可用")


def test_fertility_ml_agent_answer_rejected_status(monkeypatch):
    """status=rejected → answer 标注越界特征"""
    from framework.agents.specialized.fertility_ml_agent import FertilityMLAgent
    monkeypatch.setattr(
        "framework.agents.specialized.fertility_ml_agent.model_6_execution",
        lambda data: {
            "status": "rejected",
            "reason": "input_out_of_range",
            "out_of_range_features": [
                {"feature": "pH", "value": 99.0, "valid_range": [3.0, 11.0]}
            ],
            "soc_prediction": None,
            "soc_confidence": 0.0,
            "dose_prediction": None,
            "dose_confidence": 0.0,
            "dose_warning": "输入值越界，未执行预测",
            "imputed_features": [],
            "imputation_applied": False,
            "model_version": "ETR_v1_20260713",
        }
    )
    agent = FertilityMLAgent()
    out = agent.answer_question("我的田肥力怎么样？", {"data": {"pH": 99.0}})
    assert "越界" in out["answer"] or "异常" in out["answer"]
    assert "pH" in out["answer"]
    assert out["evidence"] == []
    print("✓ FertilityMLAgent rejected 时标注越界特征")
```

同时在 `if __name__ == "__main__":` 块中追加调用：

```python
    test_fertility_ml_agent_execute_structure(None)  # monkeypatch 通过 pytest 注入，直接调用传 None
```

注意：直接运行脚本时 `monkeypatch` 参数传 `None` 会导致错误，因此 `if __name__` 块中仅保留原有 comprehensive 测试调用（这些将在 Task 6/7 中移除）。**新增的 FertilityMLAgent 测试仅通过 pytest 运行。**

- [ ] **Step 2: 运行测试确认失败**

```bash
python -m pytest tests/test_agent_specialized.py -v -k "fertility_ml"
```

Expected: FAIL，`ModuleNotFoundError: No module named 'framework.agents.specialized.fertility_ml_agent'`。

- [ ] **Step 3: 创建 `framework/agents/specialized/fertility_ml_agent.py`**

```python
from __future__ import annotations
from typing import Any, Dict, List

from ..base import BaseAgent
from ..mock_data import MockDataLoader
from ...domain.other_models.model_6 import model_6_execution


# 肥力相关关键词（与 AgentManager.FERTILITY_KEYWORDS 保持一致）
FERTILITY_KEYWORDS = [
    "有机碳", "SOC", "soc",
    "施用量", "施肥量", "施肥", "Dose", "dose", "剂量", "施多少肥",
    "肥力", "综合肥力",
    "秸秆", "有机肥", "培肥",
]

# Dose 关键词（优先级 1）
DOSE_KEYWORDS = ["施用量", "施肥量", "Dose", "剂量", "施多少肥", "施肥"]

# SOC 关键词（优先级 2）
SOC_KEYWORDS = ["有机碳", "SOC"]


class FertilityMLAgent(BaseAgent):
    """模型6：基于 ML 的耕地肥力 SOC/Dose 预测。"""

    def __init__(self):
        super().__init__(
            name="FertilityMLAgent",
            description="基于 ML 的耕地肥力 SOC/Dose 预测",
            model_id="model-6",
            domain="fertility_ml",
        )
        self.dependencies = []  # 独立 ML 模型，不依赖 model-4/5

    def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """调用 model_6_execution 执行 ML 预测，包装为三层结构。"""
        result = model_6_execution(task or {})
        return MockDataLoader.mark_simulated({
            "status": result["status"],
            "result": {
                "soc_prediction": result["soc_prediction"],
                "soc_confidence": result["soc_confidence"],
                "dose_prediction": result["dose_prediction"],
                "dose_confidence": result["dose_confidence"],
                "dose_warning": result["dose_warning"],
                "imputed_features": result["imputed_features"],
                "imputation_applied": result["imputation_applied"],
            },
            "metadata": {
                "model_version": result["model_version"],
                "fallback_reason": result.get("fallback_reason"),
                "reason": result.get("reason"),
                "out_of_range_features": result.get("out_of_range_features"),
            },
        })

    def answer_question(self, question: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """按关键词优先级处理问答：Dose > SOC > 综合/默认。"""
        exec_result = self.execute(
            context.get("data", {}) or context.get("task", {}) or {}
        )
        pred = exec_result["result"]

        q_lower = question.lower()

        # 优先级 1：明确问 Dose / 施用量
        if any(kw.lower() in q_lower for kw in DOSE_KEYWORDS):
            return self._format_dose_only(pred, exec_result)

        # 优先级 2：明确问 SOC / 有机碳
        if any(kw.lower() in q_lower for kw in SOC_KEYWORDS):
            return self._format_soc_only(pred, exec_result)

        # 优先级 3：肥力 / 综合 / 其他
        return self._format_both(pred, exec_result)

    def _format_rejected(self, exec_result: Dict[str, Any]) -> Dict[str, Any]:
        """越界拒绝的统一格式化"""
        oor = exec_result["metadata"].get("out_of_range_features", [])
        oor_text = "; ".join([
            f"{f['feature']}={f['value']}（合法范围 {f['valid_range'][0]}-{f['valid_range'][1]}）"
            for f in oor
        ])
        return MockDataLoader.mark_simulated({
            "answer": f"输入值异常，无法预测。越界特征：{oor_text}。请检查输入后重试。",
            "evidence": [],
            "sources": [],
        })

    def _format_soc_only(self, pred: Dict[str, Any], exec_result: Dict[str, Any]) -> Dict[str, Any]:
        if exec_result["status"] == "rejected":
            return self._format_rejected(exec_result)

        if exec_result["status"] == "fallback":
            confidence_text = "（模型不可用，返回训练集均值估算）"
        else:
            confidence_text = f"（置信度 {pred['soc_confidence']:.0%}）"

        return MockDataLoader.mark_simulated({
            "answer": f"基于 ML 预测，您的土壤有机碳（SOC）预测值约 {pred['soc_prediction']:.2f} g/kg{confidence_text}",
            "evidence": [
                {"metric": "soc_prediction", "value": pred["soc_prediction"], "unit": "g/kg"},
                {"metric": "soc_confidence", "value": pred["soc_confidence"]},
            ],
            "sources": [],
        })

    def _format_dose_only(self, pred: Dict[str, Any], exec_result: Dict[str, Any]) -> Dict[str, Any]:
        if exec_result["status"] == "rejected":
            return self._format_rejected(exec_result)

        if exec_result["status"] == "fallback":
            confidence_text = "（模型不可用，返回训练集均值估算）"
        else:
            confidence_text = f"（置信度 {pred['dose_confidence']:.0%}，{pred['dose_warning']}）"

        return MockDataLoader.mark_simulated({
            "answer": f"基于 ML 预测，建议施肥量约 {pred['dose_prediction']:.2f} t/ha{confidence_text}",
            "evidence": [
                {"metric": "dose_prediction", "value": pred["dose_prediction"], "unit": "t/ha"},
                {"metric": "dose_confidence", "value": pred["dose_confidence"]},
            ],
            "sources": [],
        })

    def _format_both(self, pred: Dict[str, Any], exec_result: Dict[str, Any]) -> Dict[str, Any]:
        if exec_result["status"] == "rejected":
            return self._format_rejected(exec_result)

        imputation_note = (
            "\n（注：部分特征用训练集均值填充，已标注于 imputed_features）"
            if pred["imputation_applied"] else ""
        )
        fallback_note = (
            "\n（模型不可用，以上为训练集均值估算）"
            if exec_result["status"] == "fallback" else ""
        )

        return MockDataLoader.mark_simulated({
            "answer": (
                f"基于 ML 预测的综合肥力诊断：\n"
                f"- SOC（土壤有机碳）：{pred['soc_prediction']:.2f} g/kg（置信度 {pred['soc_confidence']:.0%}）\n"
                f"- Dose（施肥量）：{pred['dose_prediction']:.2f} t/ha（置信度 {pred['dose_confidence']:.0%}，{pred['dose_warning']}）"
                f"{imputation_note}{fallback_note}"
            ),
            "evidence": [
                {"metric": "soc_prediction", "value": pred["soc_prediction"], "unit": "g/kg"},
                {"metric": "soc_confidence", "value": pred["soc_confidence"]},
                {"metric": "dose_prediction", "value": pred["dose_prediction"], "unit": "t/ha"},
                {"metric": "dose_confidence", "value": pred["dose_confidence"]},
            ],
            "sources": [],
        })
```

- [ ] **Step 4: 更新 `framework/agents/specialized/__init__.py`**

将文件内容替换为（在 `comprehensive_agent` 导入保留的情况下新增 `fertility_ml_agent` 导入——Task 6 会移除 comprehensive）：

```python
from .stability_risk_agent import StabilityRiskAgent
from .potential_agent import PotentialAssessmentAgent
from .problem_agent import ProblemIdentificationAgent
from .acidification_agent import AcidificationRemediationAgent
from .organic_matter_agent import OrganicMatterAgent
from .comprehensive_agent import ComprehensiveImprovementAgent
from .fertility_ml_agent import FertilityMLAgent

__all__ = [
    "StabilityRiskAgent",
    "PotentialAssessmentAgent",
    "ProblemIdentificationAgent",
    "AcidificationRemediationAgent",
    "OrganicMatterAgent",
    "ComprehensiveImprovementAgent",
    "FertilityMLAgent",
]
```

- [ ] **Step 5: 运行 FertilityMLAgent 测试确认通过**

```bash
python -m pytest tests/test_agent_specialized.py -v -k "fertility_ml"
```

Expected: 6 个测试全部 PASS。

- [ ] **Step 6: 提交**

```bash
git add framework/agents/specialized/fertility_ml_agent.py framework/agents/specialized/__init__.py tests/test_agent_specialized.py
git commit -m "feat(agent): 实现 FertilityMLAgent（Dose/SOC/综合三分支问答+fallback/rejected 格式化）"
```

---

### Task 5: AgentManager 集成与按需过滤

**Files:**
- Modify: `framework/agents/manager.py`
- Test: `tests/test_agent_manager.py`（既有文件，新增测试函数）

**Interfaces:**
- Consumes: `FertilityMLAgent`（Task 4 产物）；`FERTILITY_KEYWORDS` 关键词列表（与 Task 4 一致）
- Produces: `AgentManager._should_execute_agent(agent_id, question) -> bool` 方法；`_load_real_agents` 中 model-6 加载 `FertilityMLAgent`；`_register_agents` 中 model-6 specs 更新；`process` 方法在执行前过滤；`_summarize` 中 model-6 skipped 状态处理。Task 7 测试套件依赖这些变更。

- [ ] **Step 1: 在 `tests/test_agent_manager.py` 末尾（`if __name__` 之前）新增过滤测试**

```python
def test_should_execute_model6_fertility_question():
    """问'肥力' → _should_execute_agent('model-6', ...) = True"""
    from framework.agents.manager import AgentManager, FERTILITY_KEYWORDS
    mgr = AgentManager()
    assert mgr._should_execute_agent("model-6", "我的田肥力怎么样？") is True
    assert mgr._should_execute_agent("model-6", "有机碳含量多少？") is True
    assert mgr._should_execute_agent("model-6", "需要施多少肥？") is True
    print("✓ 肥力相关问题触发 model-6 执行")


def test_should_skip_model6_non_fertility_question():
    """问'pH' → _should_execute_agent('model-6', ...) = False"""
    from framework.agents.manager import AgentManager
    mgr = AgentManager()
    assert mgr._should_execute_agent("model-6", "我的田pH如何？") is False
    assert mgr._should_execute_agent("model-6", "你好") is False
    print("✓ 非肥力问题跳过 model-6")


def test_should_execute_other_agents_always():
    """非 model-6 的 agent 始终执行"""
    from framework.agents.manager import AgentManager
    mgr = AgentManager()
    assert mgr._should_execute_agent("model-4", "任何问题") is True
    assert mgr._should_execute_agent("model-5", "任何问题") is True
    print("✓ 非 model-6 agent 始终执行")


def test_model6_dependencies_empty():
    """model-6 dependencies=[]，不依赖 model-4/5"""
    from framework.agents.manager import AgentManager
    mgr = AgentManager()
    assert mgr.agents["model-6"].dependencies == []
    print("✓ model-6 依赖为空")


def test_topological_sort_model6_no_dep():
    """model-6 dependencies=[]，拓扑排序不强制 model-6 在最后"""
    from framework.agents.manager import AgentManager
    mgr = AgentManager()
    ordered = mgr._topological_sort(["model-4", "model-5", "model-6"])
    assert set(ordered) == {"model-4", "model-5", "model-6"}
    # model-6 不再依赖 model-4/5，不强制排最后
    assert ordered[-1] != "model-6" or len(ordered) == 1
    print("✓ model-6 在拓扑排序中无依赖约束")


def test_model6_skipped_in_details_for_non_fertility():
    """非肥力问题 → details['model-6'] 含 skipped 状态"""
    from framework.agents.manager import AgentManager
    mgr = AgentManager()
    result = mgr.process("我的田pH如何？", {})
    details = result["data"]["details"]
    # model-6 应被跳过（status 标记或 skipped 标记）
    m6 = details.get("model-6", {})
    assert m6.get("status") == "skipped" or m6.get("simulated") is True
    print("✓ 非肥力问题 model-6 被跳过")


def test_manager_loads_fertility_ml_agent():
    """_load_real_agents 加载 FertilityMLAgent"""
    from framework.agents.manager import AgentManager
    mgr = AgentManager()
    agent = mgr.agents["model-6"]
    assert agent.__class__.__name__ == "FertilityMLAgent"
    print("✓ AgentManager 加载 FertilityMLAgent")
```

- [ ] **Step 2: 运行测试确认失败**

```bash
python -m pytest tests/test_agent_manager.py -v -k "should_execute or should_skip or dependencies_empty or topological_sort_model6 or skipped_in_details or loads_fertility"
```

Expected: FAIL，`_should_execute_agent` 方法不存在、`dependencies` 仍为 `["model-4", "model-5"]`、model-6 仍是 `ComprehensiveImprovementAgent`。

- [ ] **Step 3: 修改 `framework/agents/manager.py`**

在文件顶部 `from .base import BaseAgent` 后新增关键词常量：

```python
from .base import BaseAgent
from .router import RoleRouter

# 肥力相关关键词（与 FertilityMLAgent.FERTILITY_KEYWORDS 保持一致）
FERTILITY_KEYWORDS = [
    "有机碳", "SOC", "soc",
    "施用量", "施肥量", "施肥", "Dose", "dose", "剂量", "施多少肥",
    "肥力", "综合肥力",
    "秸秆", "有机肥", "培肥",
]
```

修改 `_register_agents` 中 model-6 的 spec 行（第 46 行附近）：

```python
        specs = [
            ("model-1", "StabilityRiskAgent", "耕地质量等级稳定性与退化风险识别", "stability"),
            ("model-2", "PotentialAssessmentAgent", "耕地质量提升潜力评估", "potential"),
            ("model-3", "ProblemIdentificationAgent", "耕地质量主要问题精准识别", "problem"),
            ("model-4", "AcidificationRemediationAgent", "耕地土壤酸化改良", "acidification"),
            ("model-5", "OrganicMatterAgent", "耕地土壤有机质培肥提升", "organic_matter"),
            ("model-6", "FertilityMLAgent", "耕地肥力 SOC/Dose ML 预测", "fertility_ml"),
        ]
```

修改依赖声明（第 62 行附近）：

```python
        self.agents["model-6"].dependencies = []
```

修改 `_load_real_agents` 中 model-6 加载逻辑（第 92-96 行替换为）：

```python
        try:
            from .specialized.fertility_ml_agent import FertilityMLAgent
            real["model-6"] = FertilityMLAgent()
        except ImportError:
            pass
        return real
```

在 `_topological_sort` 方法之后、`_summarize` 方法之前新增 `_should_execute_agent` 方法：

```python
    def _should_execute_agent(self, agent_id: str, question: str) -> bool:
        """问题感知过滤：model-6 仅在肥力相关问题时执行。"""
        if agent_id == "model-6":
            q_lower = (question or "").lower()
            return any(kw.lower() in q_lower for kw in FERTILITY_KEYWORDS)
        return True
```

修改 `process` 方法，在执行前加入过滤逻辑：

```python
    def process(self, question: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """处理用户问题，返回综合结果。"""
        role = self.router.identify_role(question)
        agent_ids = self.router.get_agents_for_role(role)
        results = self._execute_with_dependencies(agent_ids, question, context)
        return {
            "status": "ok",
            "data": self._summarize(role, agent_ids, results),
        }

    def _execute_with_dependencies(
        self, agent_ids: List[str], question: str, context: Dict[str, Any]
    ) -> Dict[str, Dict[str, Any]]:
        """按依赖关系顺序执行智能体，前序输出累积到 context。"""
        ordered = self._topological_sort(agent_ids)
        accumulated = dict(context)
        results: Dict[str, Dict[str, Any]] = {}

        for agent_id in ordered:
            # 按需过滤：非肥力问题跳过 model-6
            if not self._should_execute_agent(agent_id, question):
                results[agent_id] = {
                    "status": "skipped",
                    "reason": "question_not_related",
                    "answer": "",
                    "evidence": [],
                    "confidence": 0.0,
                    "simulated": True,
                }
                accumulated[agent_id] = results[agent_id]
                continue

            agent = self.agents[agent_id]
            try:
                result = agent.answer_question(question, accumulated)
            except Exception as exc:
                result = {
                    "answer": f"智能体执行失败: {exc}",
                    "evidence": [],
                    "confidence": 0.0,
                    "simulated": True,
                    "error": str(exc),
                }
            results[agent_id] = result
            accumulated[agent_id] = result

        return results
```

- [ ] **Step 4: 运行新增测试确认通过**

```bash
python -m pytest tests/test_agent_manager.py -v -k "should_execute or should_skip or dependencies_empty or topological_sort_model6 or skipped_in_details or loads_fertility"
```

Expected: 7 个测试全部 PASS。

- [ ] **Step 5: 运行既有 AgentManager 测试确认兼容**

```bash
python -m pytest tests/test_agent_manager.py -v
```

Expected: 既有 `test_manager_topological_sort_farmer` 可能失败（原断言 `ordered[-1] == "model-6"` 不再成立），这将在 Task 7 中修复。其他测试应 PASS。

- [ ] **Step 6: 提交**

```bash
git add framework/agents/manager.py tests/test_agent_manager.py
git commit -m "feat(manager): AgentManager 集成 FertilityMLAgent 并新增按需过滤"
```

---

### Task 6: ComprehensiveImprovementAgent 清理

**Files:**
- Delete: `framework/agents/specialized/comprehensive_agent.py`
- Modify: `framework/agents/specialized/__init__.py`（移除 comprehensive 导入）
- Modify: `tests/test_agent_specialized.py`（移除 comprehensive 测试）

**Interfaces:**
- Consumes: Task 4 已新增 `FertilityMLAgent` 导入与测试，Task 5 已修改 `manager.py` 不再引用 `ComprehensiveImprovementAgent`
- Produces: 仓库中无 `ComprehensiveImprovementAgent` 残留引用。`__init__.py` 仅导出 6 个有效 agent（含 `FertilityMLAgent`，不含 `ComprehensiveImprovementAgent`）。

- [ ] **Step 1: 从 `framework/agents/specialized/__init__.py` 移除 comprehensive 导入**

```python
from .stability_risk_agent import StabilityRiskAgent
from .potential_agent import PotentialAssessmentAgent
from .problem_agent import ProblemIdentificationAgent
from .acidification_agent import AcidificationRemediationAgent
from .organic_matter_agent import OrganicMatterAgent
from .fertility_ml_agent import FertilityMLAgent

__all__ = [
    "StabilityRiskAgent",
    "PotentialAssessmentAgent",
    "ProblemIdentificationAgent",
    "AcidificationRemediationAgent",
    "OrganicMatterAgent",
    "FertilityMLAgent",
]
```

- [ ] **Step 2: 从 `tests/test_agent_specialized.py` 移除 comprehensive 测试函数**

删除以下三个测试函数（以及 `if __name__` 块中对它们的调用）：
- `test_comprehensive_agent_execute`
- `test_comprehensive_agent_answer_question_farmer_plot`
- `test_comprehensive_agent_consumes_upstream_results`

同时从 `if __name__ == "__main__":` 块中移除对这三个函数的调用。

- [ ] **Step 3: 删除 `framework/agents/specialized/comprehensive_agent.py` 文件**

使用 DeleteFile 工具删除：
```
framework/agents/specialized/comprehensive_agent.py
```

- [ ] **Step 4: 搜索仓库确认无残留引用**

```bash
python -c "import subprocess; r=subprocess.run(['git','grep','-l','ComprehensiveImprovement'],capture_output=True,text=True); print(r.stdout or '无残留引用'); print(r.stderr)"
```

Expected: 输出"无残留引用"或仅在 `openspec/changes/` 归档文档中出现（归档文档不需修改）。

如果发现代码或测试中有残留，逐一修复。

- [ ] **Step 5: 验证模块导入正常**

```bash
python -c "from framework.agents.specialized import FertilityMLAgent; print('OK')"
python -c "from framework.agents.manager import AgentManager; m=AgentManager(); print(m.agents['model-6'].__class__.__name__)"
```

Expected: 第一行输出 `OK`；第二行输出 `FertilityMLAgent`。

- [ ] **Step 6: 提交**

```bash
git add framework/agents/specialized/__init__.py framework/agents/specialized/comprehensive_agent.py tests/test_agent_specialized.py
git commit -m "refactor(agent): 删除 ComprehensiveImprovementAgent 占位实现，清理残留引用"
```

---

### Task 7: 测试套件整合与全量验证

**Files:**
- Modify: `tests/test_agent_specialized.py`（已在 Task 4/6 调整，本任务做最终验证）
- Modify: `tests/test_agent_manager.py`（修复 Task 5 导致的既有测试失败）
- Test: `tests/test_fertility_ml_prediction.py`（Task 3 已创建）

**Interfaces:**
- Consumes: Task 3-6 的所有实现产物
- Produces: 全量测试通过，无破坏既有用例。`test_agent_manager.py` 中 `test_manager_topological_sort_farmer` 断言更新为 model-6 无依赖。

- [ ] **Step 1: 修复 `tests/test_agent_manager.py` 中 `test_manager_topological_sort_farmer`**

原断言 `assert ordered[-1] == "model-6"` 不再成立（model-6 依赖为空）。修改为：

```python
def test_manager_topological_sort_farmer():
    """farmer 角色 [model-4, model-5, model-6]，model-6 依赖为空，
    三个 agent 均无互相依赖，拓扑排序包含全部三个。"""
    mgr = AgentManager()
    ordered = mgr._topological_sort(["model-4", "model-5", "model-6"])
    assert set(ordered) == {"model-4", "model-5", "model-6"}
    print("✓ 拓扑排序包含 farmer 角色全部三个智能体")
```

- [ ] **Step 2: 修复 `tests/test_agent_manager.py` 中 `test_manager_process_farmer_returns_structured_result`**

原断言 `assert payload.get("simulated") is True` 对所有 agent 强制要求 simulated 标记。model-6 在非肥力问题时返回 skipped 状态（含 simulated），在肥力问题时 FertilityMLAgent 也通过 `mark_simulated` 添加标记。但为稳健起见，将断言修改为仅检查非 skipped 的 agent：

```python
def test_manager_process_farmer_returns_structured_result():
    """process 返回符合 API 规范的结构化字典"""
    mgr = AgentManager()
    result = mgr.process("我的田施氮肥施多少", {"area_code": "lechang"})
    assert result["status"] == "ok"
    data = result["data"]
    assert data["role"] == "farmer"
    assert data["agents_invoked"] == ["model-4", "model-5", "model-6"]
    assert "summary" in data and isinstance(data["summary"], str)
    assert "details" in data and isinstance(data["details"], dict)
    assert "recommendations" in data and isinstance(data["recommendations"], list)
    # details 中每个智能体结果应包含 simulated 标记
    for agent_id, payload in data["details"].items():
        assert payload.get("simulated") is True
    print("✓ AgentManager.process 返回符合规范的结构化结果")
```

注意：此测试的问题 "我的田施氮肥施多少" 包含 "施" 但不含完整肥力关键词 "施肥"。"施氮肥" 不在 `FERTILITY_KEYWORDS` 中（关键词是 "施肥" 不是 "施氮肥"），所以 model-6 会被跳过。跳过时返回 `{status: "skipped", ..., simulated: True}`，断言仍成立。如果需要确保 model-6 执行，应改为包含肥力关键词的问题。将问题改为 "我的田施肥施多少" 以确保 model-6 执行：

```python
    result = mgr.process("我的田施肥施多少", {"area_code": "lechang"})
```

- [ ] **Step 3: 运行全量测试套件**

```bash
python -m pytest tests/ -v
```

Expected: 所有测试 PASS（集成测试可能 SKIP）。重点关注：
- `test_agent_base.py`：应全部 PASS（未修改）
- `test_agent_specialized.py`：6 个 FertilityMLAgent 测试 PASS，原有 5 个 agent 测试 PASS，comprehensive 测试已移除
- `test_agent_manager.py`：所有测试 PASS
- `test_fertility_ml_prediction.py`：13 个单元测试 PASS，3 个集成测试 PASS 或 SKIP
- `test_agent_integration.py`、`test_multi_agent.py`：如有 model-6 相关断言可能需要调整

- [ ] **Step 4: 如有其他测试文件因 model-6 变更失败，逐一修复**

检查 `test_agent_integration.py` 和 `test_multi_agent.py` 中是否有对 `ComprehensiveImprovementAgent` 或 `details["model-6"]` 旧结构的断言。如果有，更新为新的 FertilityMLAgent 结构。

```bash
python -m pytest tests/test_agent_integration.py tests/test_multi_agent.py -v
```

Expected: PASS 或明确标识需修复的测试。

- [ ] **Step 5: 提交**

```bash
git add tests/test_agent_manager.py tests/test_agent_integration.py tests/test_multi_agent.py
git commit -m "test(agent): 修复 model-6 重构导致的既有测试断言，全量测试通过"
```

---

### Task 8: 端到端集成验证

**Files:**
- 无代码变更（纯验证任务）

**Interfaces:**
- Consumes: Task 1-7 的全部实现产物
- Produces: 验证报告（口头/日志确认），确认 `/api/chat` 响应中 model-6 字段为新 ML 预测结构

- [ ] **Step 1: 验证 AgentManager 正常初始化**

```bash
python -c "from framework.agents.manager import agent_manager; print(agent_manager.agents['model-6'].__class__.__name__)"
```

Expected: 输出 `FertilityMLAgent`，无 ImportError。

- [ ] **Step 2: 验证 model_6_execution 真实预测**

```bash
python -c "
from framework.domain.other_models.model_6 import model_6_execution
result = model_6_execution({'pH': 6.5, 'SOCbe': 15.0, 'TN': 1.2, 'TP': 0.8, 'TK': 25.0, 'AP': 30.0, 'AK': 80.0, 'Gap': 5.0, 'Dose': 200.0, 'Fertilizer type': 1})
print('status:', result['status'])
print('soc_prediction:', result['soc_prediction'])
print('dose_prediction:', result['dose_prediction'])
print('soc_confidence:', result['soc_confidence'])
print('dose_confidence:', result['dose_confidence'])
"
```

Expected: `status: success`，soc_prediction 与 dose_prediction 为 float 值，confidences 分别为 0.91 和 0.47。

- [ ] **Step 3: 验证非肥力问题跳过 model-6**

```bash
python -c "
from framework.agents.manager import AgentManager
mgr = AgentManager()
result = mgr.process('我的田pH如何？', {})
m6 = result['data']['details']['model-6']
print('model-6 status:', m6.get('status'))
print('model-6 reason:', m6.get('reason'))
"
```

Expected: `model-6 status: skipped`，`model-6 reason: question_not_related`。

- [ ] **Step 4: 验证肥力问题触发 model-6 ML 预测**

```bash
python -c "
from framework.agents.manager import AgentManager
mgr = AgentManager()
result = mgr.process('我的田肥力怎么样？', {'data': {'pH': 6.5, 'SOCbe': 15.0, 'TN': 1.2, 'TP': 0.8, 'TK': 25.0, 'AP': 30.0, 'AK': 80.0, 'Gap': 5.0, 'Dose': 200.0, 'Fertilizer type': 1}})
m6 = result['data']['details']['model-6']
print('answer:', m6.get('answer', '')[:100])
print('has evidence:', len(m6.get('evidence', [])) > 0)
"
```

Expected: answer 包含 "SOC" 和 "Dose" 预测值，evidence 非空。

- [ ] **Step 5: 验证 fallback 降级（临时重命名模型文件）**

```powershell
Rename-Item data\fertility\models\soc_etr_model.joblib soc_etr_model.joblib.bak
```

```bash
python -c "
from framework.domain.other_models import model_6
model_6._SOC_LOAD_FAILED = False
model_6._DOSE_LOAD_FAILED = False
model_6._SOC_MODEL = None
model_6._DOSE_MODEL = None
result = model_6.model_6_execution({'pH': 6.5})
print('status:', result['status'])
print('fallback_reason:', result.get('fallback_reason'))
print('soc_confidence:', result['soc_confidence'])
"
```

Expected: `status: fallback`，`fallback_reason: model_file_missing`，`soc_confidence: 0.3`。

恢复文件：

```powershell
Rename-Item data\fertility\models\soc_etr_model.joblib.bak soc_etr_model.joblib
```

- [ ] **Step 6: 启动开发服务器验证 /api/chat 接口（可选，如服务器可用）**

```bash
python start_http_server.py
```

在另一个终端调用：

```bash
curl -X POST http://localhost:5000/api/auth/login -H "Content-Type: application/json" -d "{\"username\":\"admin\",\"password\":\"admin\"}"
```

用返回的 token 调用：

```bash
curl -X POST http://localhost:5000/api/chat -H "Content-Type: application/json" -H "Authorization: Bearer <token>" -d "{\"message\":\"我的田肥力怎么样？\"}"
```

Expected: 响应 `data.details["model-6"]` 包含 ML 预测结果（非 `diagnosis`/`zoning_suggestions` 旧结构）。

- [ ] **Step 7: 最终全量测试确认**

```bash
python -m pytest tests/ -v
```

Expected: 所有测试 PASS 或 SKIP（集成测试），无 FAIL。

---

## Self-Review 检查清单

### 1. Spec 覆盖率

| Spec 要求 | 对应任务 | 状态 |
|-----------|---------|------|
| SOC ML 预测（10 因子，R²=0.91） | Task 3 | ✓ |
| Dose ML 预测（9 因子，R²=0.47，dose_warning） | Task 3 | ✓ |
| 模型文件缺失降级（fallback_reason=model_file_missing） | Task 3 | ✓ |
| sklearn 缺失降级（fallback_reason=sklearn_missing） | Task 3 | ✓ |
| 输入越界拒绝（status=rejected） | Task 3 | ✓ |
| 部分特征缺失均值填充（imputation_applied） | Task 3 | ✓ |
| 训练脚本（hardcoded 超参数，7 步网格搜索不重跑） | Task 2 | ✓ |
| metadata.json 完整 schema | Task 2 | ✓ |
| 依赖声明 scikit-learn + joblib | Task 1 | ✓ |
| FertilityMLAgent（execute + answer_question 三分支） | Task 4 | ✓ |
| Agent 独立执行无依赖（dependencies=[]） | Task 4, 5 | ✓ |
| 非肥力问题跳过 model-6（_should_execute_agent） | Task 5 | ✓ |
| 输入越界时 Agent 返回拒绝响应 | Task 4 | ✓ |
| ComprehensiveImprovementAgent 删除 | Task 6 | ✓ |
| __init__.py 导出更新 | Task 4, 6 | ✓ |
| manager.py _load_real_agents 更新 | Task 5 | ✓ |
| 全量测试通过 | Task 7 | ✓ |
| 端到端验证 | Task 8 | ✓ |

### 2. 占位符扫描

- 无 "TBD"、"TODO"、"implement later" 占位符
- 所有代码步骤包含完整实现代码
- 所有测试步骤包含完整测试代码
- 所有命令包含预期输出

### 3. 类型一致性

- `model_6_execution(input_data: Dict[str, Any]) -> Dict[str, Any]`：Task 3 定义，Task 4 调用 ✓
- `FertilityMLAgent.__init__()`：Task 4 定义 `model_id="model-6"`、`domain="fertility_ml"`、`dependencies=[]`，Task 5 `_register_agents` specs 匹配 ✓
- `FERTILITY_KEYWORDS`：Task 4 定义于 `fertility_ml_agent.py`，Task 5 定义于 `manager.py`，两处列表内容一致 ✓
- `DOSE_KEYWORDS` / `SOC_KEYWORDS`：Task 4 定义并使用 ✓
- `_should_execute_agent(agent_id: str, question: str) -> bool`：Task 5 定义，Task 5 测试调用 ✓
- metadata schema 字段：Task 2 生成 `feature_names`/`feature_means`/`metrics.test_r2`，Task 3 读取这些字段 ✓
- `_prepare_features` 返回三元组 `(df, imputed, out_of_range)`：Task 3 定义并使用 ✓
- `_fallback_response(input_data, reason)` 返回字典含 `fallback_reason`：Task 3 定义，Task 4 读取 `result.get("fallback_reason")` ✓
