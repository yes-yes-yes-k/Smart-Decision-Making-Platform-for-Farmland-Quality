"""构建时重训 RF 模型脚本 — 从原始 xlsx 读取训练数据，重训并保存为 .joblib。

使用方式:
    python scripts/train_dose_rf_models.py

输入:
    D:\\destkop\\模型1-5\\模型4-SG-旱地和水田-Dose预测模型\\SG-旱地和水田-Dose预测模型\\
        SG旱地-Dose-RF_Manual_splits.xlsx
        SG水田-Dose-RF_Manual_splits.xlsx

输出:
    data/model_artifacts/upland_dose_rf.joblib
    data/model_artifacts/paddy_dose_rf.joblib

注意:
    原始 xlsx 含 4 个 sheet (Xtrain/Xtest/Ytrain/Ytest)，特征列名带尾随空格
    (如 'TN '), 需 strip 后才能与 FEATURE_COLUMNS 匹配。本脚本会自动 strip 列名
    并合并 Xtrain + Ytrain 作为训练集。
"""
from __future__ import annotations
import os
import sys

import pandas as pd

FEATURE_COLUMNS = ["pH", "SOMbe", "AK", "AP", "TN"]
TARGET_COLUMN = "Dose"

ORIGINAL_DIR = r"D:\destkop\模型1-5\模型4-SG-旱地和水田-Dose预测模型\SG-旱地和水田-Dose预测模型"
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "model_artifacts")


def _load_training_frame(xlsx_path: str) -> pd.DataFrame:
    """读取 xlsx 的 Xtrain + Ytrain sheet，合并并 strip 列名。

    返回含 FEATURE_COLUMNS + TARGET_COLUMN 的 DataFrame。
    """
    xtrain = pd.read_excel(xlsx_path, sheet_name="Xtrain")
    ytrain = pd.read_excel(xlsx_path, sheet_name="Ytrain")

    # strip 列名尾随空格（原始 xlsx 中 'TN ' / 'TP ' / 'TK ' 带空格）
    xtrain = xtrain.rename(columns=lambda c: c.strip() if isinstance(c, str) else c)
    ytrain = ytrain.rename(columns=lambda c: c.strip() if isinstance(c, str) else c)

    df = pd.concat([xtrain.reset_index(drop=True), ytrain.reset_index(drop=True)], axis=1)
    return df


def train_and_save(xlsx_path: str, output_path: str) -> dict:
    """从 xlsx 读取训练数据，重训 RF 模型并保存。

    Args:
        xlsx_path: 原始 xlsx 路径（含 Xtrain/Xtest/Ytrain/Ytest sheets）。
        output_path: .joblib 输出路径。

    Returns:
        dict: 训练评估指标（RMSE, R2）。
    """
    from sklearn.ensemble import RandomForestRegressor
    import joblib

    df = _load_training_frame(xlsx_path)
    X = df[FEATURE_COLUMNS]
    y = df[TARGET_COLUMN]

    rf = RandomForestRegressor(n_estimators=100, random_state=230)
    rf.fit(X, y)

    # 训练集自评估
    y_pred = rf.predict(X)
    rmse = float((((y - y_pred) ** 2).mean()) ** 0.5)
    r2 = float(rf.score(X, y))

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    joblib.dump(rf, output_path)

    return {"rmse": rmse, "r2": r2, "n_samples": int(len(df))}


def main() -> int:
    # 检查 sklearn 可用性
    try:
        import sklearn  # noqa: F401
        import joblib  # noqa: F401
    except ImportError as e:
        print(f"警告: scikit-learn 或 joblib 不可用 ({e})，跳过训练", file=sys.stderr)
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        return 1

    configs = [
        ("upland", os.path.join(ORIGINAL_DIR, "SG旱地-Dose-RF_Manual_splits.xlsx")),
        ("paddy", os.path.join(ORIGINAL_DIR, "SG水田-Dose-RF_Manual_splits.xlsx")),
    ]

    trained = 0
    for land_type, xlsx_path in configs:
        if not os.path.exists(xlsx_path):
            print(f"警告: {xlsx_path} 不存在，跳过 {land_type}", file=sys.stderr)
            continue
        output_path = os.path.join(OUTPUT_DIR, f"{land_type}_dose_rf.joblib")
        metrics = train_and_save(xlsx_path, output_path)
        print(f"{land_type}: RMSE={metrics['rmse']:.4f}, R2={metrics['r2']:.4f}, n={metrics['n_samples']}")
        print(f"  已保存到 {output_path}")
        trained += 1

    if trained == 0:
        # 确保空目录存在以供 .gitkeep 跟踪
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        print("未训练任何模型，仅创建空目录", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
