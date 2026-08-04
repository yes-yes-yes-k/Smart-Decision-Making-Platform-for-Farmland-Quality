## 实现说明

本变更为 tweak 预设的轻量刷新，无需方案对比。生产训练管线 `scripts/train_fertility_models.py --sg` 已存在，本次仅升版本常量 + 重跑 + 1 处推理代码修正 + 测试 mock 同步。

### A. 升版本常量

`scripts/train_fertility_models.py:39`：
```python
SG_MODEL_VERSION = "SG_RF_v1_20260731"  # → "SG_RF_v2_20260804"
```
`SG_RF_PARAMS = {"n_estimators": 100, "random_state": 230}` 保持不变。

### B. 重训模型

用项目 venv 执行：
```
d:\17417\Documents\agent_culti_demo\.venv\Scripts\python.exe scripts\train_fertility_models.py --sg
```
脚本读取 `data/fertility/SG旱地-Dose-RF_Manual_splits.xlsx` 与 `SG水田-Dose-RF_Manual_splits.xlsx`（与 模型4_v2 包 CSV 同源，已验证 `feature_means` 差异=0.000e+00），训练 `RandomForestRegressor(n_estimators=100, random_state=230)`，覆盖输出 2 个 `.joblib` + 2 个 `metadata.json`。

预期结果：
- `trained_at` 更新为当前 ISO 时间戳；
- `model_version = SG_RF_v2_20260804`；
- 指标轻微漂移：旱地 `test_r2` 0.9616→~0.9611、`cv_r2` 0.9711→~0.97；水田 `test_r2` 0.9931→~0.9930（源于 sklearn 1.5.1→1.9.0 的 RF 树构建 RNG 差异，非数据差异）；
- `feature_means`、`training_samples`（185 / 1974）、`test_samples`（47 / 220）不变。

### C. model_6.py 韶关 dose 分支

在 `model_6_execution` 的 success 响应构造处（约 L363-373），韶关分支将 `model_version` 字段从固定 `_MODEL_VERSION` 改为 `sg_meta["model_version"]`。这样韶关 dose 响应返回实际 SG RF 模型版本号。

边界保持不变：
- 非韶关 dose 分支：仍返回 `_MODEL_VERSION`（全局 ETR 版本）；
- `_fallback_response`（fallback）：仍返回 `_MODEL_VERSION`；
- rejected 分支：仍返回 `_MODEL_VERSION`。

### D. 测试 mock 同步

`tests/test_fertility_ml_prediction.py` L354、L368：`FAKE_SG_UPLAND_META` / `FAKE_SG_PADDY_META` 的 `model_version` 由 `"SG_RF_v1_20260731"` 改为 `"SG_RF_v2_20260804"`。仅一致性更新——单元测试全 mock（`FakeModel` 返回 42.0），集成测试只断言 `0 <= dose_prediction <= 1000` 范围，重训与版本号变更均不破坏断言。

### E. 文档

历史 plan / report（`docs/superpowers/plans/2026-07-31-add-shaoguan-fertility-model.md`、`docs/superpowers/reports/2026-08-01-add-shaoguan-fertility-model-verify.md`）不篡改；v2 刷新事实记录于本 change 的 proposal / design。

## 风险与回滚

- 风险：sklearn 版本漂移导致逐样本预测漂移 ~3-4 单位，但 R²/RMSE 基本不变，集成测试范围断言不受影响。
- 回滚：`git checkout` 恢复 2 个 `.joblib` + 2 个 `metadata.json` + 代码改动即可回到 v1。
