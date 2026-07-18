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
