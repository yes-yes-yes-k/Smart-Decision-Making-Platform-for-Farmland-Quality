# Task 2 Brief — 训练脚本与模型生成

> **来源**：`docs/superpowers/plans/2026-07-18-add-model-6-fertility-ml.md` 第 129-329 行
> **OpenSpec 对应**：`openspec/changes/add-model-6-fertility-ml/tasks.md` 第 2.1-2.6 节
> **BASE commit**：`d75217d`（Task 1 派发后的最新提交）

## Files

- Create: `scripts/train_fertility_models.py`
- Generate: `data/fertility/models/soc_etr_model.joblib`
- Generate: `data/fertility/models/soc_metadata.json`
- Generate: `data/fertility/models/dose_etr_model.joblib`
- Generate: `data/fertility/models/dose_metadata.json`

## Interfaces

- **Consumes**: `data/fertility/ML-data-SOC-RF_Manual_splits.xlsx`、`data/fertility/ML-data-Dose-RF_Manual_splits.xlsx`（Task 1 产物）
- **Produces**: 4 个模型产物文件。Task 3 `model_6.py` 运行时通过 `joblib.load()` 加载 `.joblib` 文件，通过 `json.load()` 加载 `metadata.json` 文件。metadata schema 必须包含 `feature_names`（list[str]，保留含空格形式）、`feature_means`（dict[str, float]）、`metrics.test_r2`（float）、`hyperparameters`（dict）、`model_type`、`trained_at`、`model_version`。

## 步骤

### Step 1: 创建训练脚本 `scripts/train_fertility_models.py`

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

    # 注意：实际文件名是 ML-data-Dose-RF_Manual_splits.xlsx（RF 和 Manual 之间是下划线 _，不是连字符 -）
    # plan 原文写的是 RF-Manual（连字符），这是 plan 拼写错误，请用下划线版本
    soc_xlsx = data_dir / "ML-data-SOC-RF_Manual_splits.xlsx"
    dose_xlsx = data_dir / "ML-data-Dose-RF_Manual_splits.xlsx"

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

### Step 2: 运行训练脚本生成模型文件

```bash
python scripts/train_fertility_models.py --data-dir data/fertility --output-dir data/fertility/models
```

Expected: 控制台输出 SOC 和 Dose 的 5CV R²、Test R²、RMSE 与超参数；无报错。

### Step 3: 验证 4 个产物文件已生成

```powershell
Get-Item data\fertility\models\* | Select-Object Name, @{N='SizeKB';E={[math]::Round($_.Length/1KB,1)}}
```

Expected: 列出 `soc_etr_model.joblib`、`soc_metadata.json`、`dose_etr_model.joblib`、`dose_metadata.json` 4 个文件。

### Step 4: 验证 metadata.json 内容完整

```bash
python -c "import json; m=json.load(open('data/fertility/models/soc_metadata.json',encoding='utf-8')); print(m['model_type'], m['model_version'], m['metrics']['test_r2'], len(m['feature_names']), m['feature_names'])"
```

Expected: 输出 `ExtraTreesRegressor ETR_v1_20260713 0.9096 10 ['pH', 'SOCbe', 'TN ', 'TP ', 'TK ', 'AP', 'AK', 'Gap', 'Dose', 'Fertilizer type']`（test_r2 值可能略有差异但应接近 0.91）。

### Step 5: 提交

```bash
git add scripts/train_fertility_models.py data/fertility/models/
git commit -m "feat(fertility): 训练 SOC/Dose ETR 模型并生成 joblib 与 metadata 产物"
```

## Global Constraints（摘自 plan）

- 模型版本号统一为 `"ETR_v1_20260713"`（设计文档 2.3、5.3）
- SOC 模型 confidence = 0.91（来自 `metadata.metrics.test_r2`，round 2 位小数）；Dose 模型 confidence = 0.47（设计文档 2.3）
- 特征名保留原始含空格形式（`"TN "`、`"TP "`），与训练时 `Xtrain.columns` 一致；用户输入层做 `strip()` 规范化（设计文档 2.2）
- Dose 单位统一为 t/ha（与训练数据 `变量注释.xlsx` 原始单位一致）（设计文档 3.5）
- 训练脚本只读 xlsx + 生成 joblib/json，**不**实现业务逻辑（业务逻辑在 Task 3 `model_6.py`）

## 注意事项（Task 1 implementer 发现的 plan 拼写错误）

- **Dose 文件名是 `ML-data-Dose-RF_Manual_splits.xlsx`（下划线 `_`）**，plan 原文 line 281 写成 `ML-data-Dose-RF-Manual_splits.xlsx`（连字符 `-`），这是 plan 拼写错误。本 brief 中的代码已修正为下划线版本，请直接使用。
- `pip install -e .` 在 Task 1 已失败（pyproject.toml 使用 Poetry 风格 `key = "version"` 而非 PEP 621 数组格式）。这是预存在问题，不影响本任务。训练脚本依赖已通过 `pip install scikit-learn joblib` 装上（sklearn 1.5.1 / joblib 1.4.2 已验证可导入）。
- 训练脚本本身是工具脚本，不强制 TDD Red-Green-Refactor 循环（无单元测试可写）。但脚本必须能成功运行并生成 4 个产物文件，且 metadata.json schema 完整。

## 报告契约

implementer 完成后写入 `openspec/changes/add-model-6-fertility-ml/.comet/subagent-reports/task-2-report.md`，返回内容包含：
1. **Status**: DONE / DONE_WITH_CONCERNS / NEEDS_CONTEXT / BLOCKED
2. **Commits**: commit hash + 简短描述
3. **测试摘要**: 训练脚本运行输出（5CV R²、Test R²、RMSE）+ 4 个产物文件清单 + metadata.json 关键字段验证
4. **Concerns**: 任何顾虑（如训练耗时、CV 警告、test_r2 与预期 0.91 偏差等）
5. **风险信号自报**: 跨模块协调 / 安全敏感 / 并发 / 数据迁移 / API 变更 / DONE_WITH_CONCERNS / diff>200 行
