"""测试 SG RF Dose 训练函数。

用 pandas 构造临时 xlsx，端到端验证 train_sg_dose_model 的 SOMbe→SOCbe 重命名、
模型保存与 metadata 完整性。sklearn 不可用时整体跳过。
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
from pathlib import Path

import pytest

pd = pytest.importorskip("pandas")
sklearn = pytest.importorskip("sklearn")
joblib = pytest.importorskip("joblib")


def _make_sg_xlsx(path: Path, feature_cols: list[str], n_train: int = 40, n_test: int = 10):
    """构造含 Xtrain/Xtest/Ytrain/Ytest 四 sheet 的临时 xlsx。"""
    import numpy as np
    rng = np.random.RandomState(230)
    Xtrain = pd.DataFrame(rng.rand(n_train, len(feature_cols)), columns=feature_cols)
    Xtest = pd.DataFrame(rng.rand(n_test, len(feature_cols)), columns=feature_cols)
    Ytrain = pd.DataFrame({"Dose": rng.rand(n_train) * 100})
    Ytest = pd.DataFrame({"Dose": rng.rand(n_test) * 100})
    with pd.ExcelWriter(path) as w:
        Xtrain.to_excel(w, sheet_name="Xtrain", index=False)
        Xtest.to_excel(w, sheet_name="Xtest", index=False)
        Ytrain.to_excel(w, sheet_name="Ytrain", index=False)
        Ytest.to_excel(w, sheet_name="Ytest", index=False)


def test_train_sg_dose_model_renames_sombe_and_saves(tmp_path):
    from scripts.train_fertility_models import train_sg_dose_model

    feature_cols = ["pH", "SOMbe", "TN", "TP", "TK", "AP", "AK", "Gap", "Fertilizer type"]
    xlsx = tmp_path / "sg_test.xlsx"
    _make_sg_xlsx(xlsx, feature_cols)

    meta = train_sg_dose_model("upland", xlsx, tmp_path)

    # SOMbe 应被重命名为 SOCbe
    assert "SOMbe" not in meta["feature_names"]
    assert "SOCbe" in meta["feature_names"]
    assert len(meta["feature_names"]) == 9

    # 模型文件存在
    assert (tmp_path / "sg_dose_upland_rf_model.joblib").exists()
    assert (tmp_path / "sg_dose_upland_metadata.json").exists()

    # metadata 完整性
    assert meta["model_type"] == "RandomForestRegressor"
    assert "metrics" in meta and "test_r2" in meta["metrics"]
    assert "training_samples" in meta
    assert meta["training_samples"] == 40

    # 模型可加载
    model = joblib.load(tmp_path / "sg_dose_upland_rf_model.joblib")
    assert hasattr(model, "predict")


def test_train_sg_dose_model_paddy_naming(tmp_path):
    from scripts.train_fertility_models import train_sg_dose_model

    xlsx = tmp_path / "sg_paddy_test.xlsx"
    _make_sg_xlsx(xlsx, ["pH", "SOMbe", "TN", "TP", "TK", "AP", "AK", "Gap", "Fertilizer type"])

    meta = train_sg_dose_model("paddy", xlsx, tmp_path)
    assert (tmp_path / "sg_dose_paddy_rf_model.joblib").exists()
    assert (tmp_path / "sg_dose_paddy_metadata.json").exists()
    assert meta["model_type"] == "RandomForestRegressor"
