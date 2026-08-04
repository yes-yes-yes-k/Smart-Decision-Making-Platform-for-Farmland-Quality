# Tasks

## T1: 升版本常量

- [x] 将 `scripts/train_fertility_models.py:39` 的 `SG_MODEL_VERSION` 由 `"SG_RF_v1_20260731"` 改为 `"SG_RF_v2_20260804"`（`SG_RF_PARAMS` 保持不变）。

## T2: 重训韶关 Dose 模型

- [x] 用项目 venv 执行 `d:\17417\Documents\agent_culti_demo\.venv\Scripts\python.exe scripts\train_fertility_models.py --sg`，重新生成 `sg_dose_upland_rf_model.joblib`、`sg_dose_paddy_rf_model.joblib` 及对应 `metadata.json`。
- [x] 核对两个 metadata.json：`model_version == "SG_RF_v2_20260804"`、`trained_at` 为当前时间、`feature_means` 与重训前一致、`training_samples`(185/1974) 与 `test_samples`(47/220) 不变、`test_r2` 在 0.96/0.99 量级。

## T3: 修正 model_6.py 韶关 dose 版本号

- [x] 在 `framework/domain/other_models/model_6.py` 的 `model_6_execution` 韶关 dose success 响应构造处，将 `model_version` 从 `_MODEL_VERSION` 改为 `sg_meta["model_version"]`。
- [x] 确认非韶关 dose 分支、`_fallback_response`、rejected 分支仍返回 `_MODEL_VERSION` 不变。

## T4: 同步测试 mock 版本字符串

- [x] 将 `tests/test_fertility_ml_prediction.py` 中 `FAKE_SG_UPLAND_META`（L354）与 `FAKE_SG_PADDY_META`（L368）的 `model_version` 由 `"SG_RF_v1_20260731"` 改为 `"SG_RF_v2_20260804"`。

## T5: 验证

- [x] 用项目 venv 运行 `pytest tests/test_fertility_ml_prediction.py -q`，确认全部通过（单元测试 mock + 集成测试范围断言）。
- [x] 跑一次真实韶关 dose 集成预测（`model_6_execution` with `area_code="lechang"`，upland + paddy），核对 `model_version` 返回 `SG_RF_v2_20260804`、`dose_prediction` 在 0-1000 范围、`dose_warning` 含 "韶关"。
