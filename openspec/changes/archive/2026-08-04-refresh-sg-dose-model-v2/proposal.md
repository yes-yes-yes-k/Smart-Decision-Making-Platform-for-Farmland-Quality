## Why

韶关（SG）Dose RF 模型（`sg_dose_upland_rf_model.joblib` / `sg_dose_paddy_rf_model.joblib`，版本 `SG_RF_v1_20260731`）训练于 sklearn 1.5.1，需用当前项目 venv（sklearn 1.9.0）重训以统一运行时口径并刷新版本号；同时韶关 dose 成功响应当前返回全局 ETR 版本号（`ETR_v1_20260713`），未反映实际使用的 SG RF 模型版本，需修正让版本号对调用方可见。

前提：模型4_v2 包的 CSV 与当前部署模型训练数据已验证完全同源（9 特征均值差异=0.000e+00，样本量 185/47 与 1974/220 一致），本次为同源数据 + 新 sklearn 版本的重训刷新，不引入新数据。SOC 模型不在本次范围。

## What Changes

- 升 `scripts/train_fertility_models.py` 的 `SG_MODEL_VERSION` 常量为 `SG_RF_v2_20260804`。
- 用项目 venv 重跑 `python scripts/train_fertility_models.py --sg`，重新生成 `sg_dose_upland_rf_model.joblib` / `sg_dose_paddy_rf_model.joblib` 及对应 metadata.json（`trained_at` 更新、`model_version=v2`、指标随 sklearn 1.9.0 轻微漂移；`feature_means` 与样本量不变）。
- 修改 `framework/domain/other_models/model_6.py` 韶关 dose success 分支，返回 `sg_meta["model_version"]` 而非固定 `_MODEL_VERSION`；非韶关、fallback、rejected 分支保持不变。
- 同步 `tests/test_fertility_ml_prediction.py` 中 `FAKE_SG_*_META` 的 `model_version` 为 `SG_RF_v2_20260804`（纯一致性）。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `fertility-ml-prediction`: Dose 预测能力新增韶关 dose 成功响应 `model_version` 行为约束——返回所用 SG RF 模型的版本号，而非全局 ETR 版本号。

## Impact

- **代码**：`scripts/train_fertility_models.py`（1 行常量）、`framework/domain/other_models/model_6.py`（韶关 dose 分支 `model_version` 来源）、`tests/test_fertility_ml_prediction.py`（mock 版本字符串）。
- **模型产物**：`data/fertility/models/sg_dose_{upland,paddy}_rf_model.joblib` + 对应 `metadata.json`（重训覆盖）。
- **API**：响应 schema 不变；韶关 dose 响应的 `model_version` 字符串值由 `ETR_v1_20260713` 变为 `SG_RF_v2_20260804`（行为变更，非破坏性，无测试断言该值）。
- **不影响**：SOC 模型（`soc_etr_model.joblib` / `soc_metadata.json`）、全局 `dose_etr_model`、非韶关预测路径。
