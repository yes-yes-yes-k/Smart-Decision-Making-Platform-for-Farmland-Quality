## MODIFIED Requirements

### Requirement: Dose（施用量）ML 预测能力

系统 SHALL 通过 `model_6_execution` 函数提供 Dose（施用量）的机器学习预测能力，支持区域路由：非韶关区域使用预训练的全局 ExtraTreesRegressor 模型（保存在 `data/fertility/models/dose_etr_model.joblib`），韶关区域（`area_code` 命中 `SHAOGUAN_AREA_CODES` 集合）使用 RandomForestRegressor 模型（按 `land_type` 选择旱地或水田子模型）。Dose 模型输入 9 个土壤特征（pH、SOCbe、TN、TP、TK、AP、AK、Gap、Fertilizer type，不含 Dose 自身），返回 Dose 预测值（单位 t/ha）、置信度与质量警告信息。SOC 预测在所有区域均使用全局 ETR SOC 模型，不受区域路由影响。成功响应的 `model_version` 字段 SHALL 反映实际使用的模型版本：韶关区域返回所用 SG RF 模型的版本号（即 `sg_dose_{land_type}_metadata.json` 中的 `model_version`），非韶关区域返回全局 ETR 版本号。

#### Scenario: 非韶关区域完整特征输入的 Dose 预测

- **WHEN** 调用 `model_6_execution` 时 `area_code` 不在 `SHAOGUAN_AREA_CODES` 中，且 `input_data` 包含全部 9 个 Dose 模型所需特征
- **THEN** 系统 SHALL 加载 `data/fertility/models/dose_etr_model.joblib`，调用 `model.predict()` 返回 `dose_prediction`（float，单位 t/ha）、`dose_confidence`（值为 0.47）、`dose_warning`（值为 "Dose 模型 R²=0.47，预测结果仅供参考，建议结合田间试验校准"）、`model_version`（值为全局 ETR 版本号，如 "ETR_v1_20260713"）

#### Scenario: 韶关区域旱地 Dose 预测

- **WHEN** 调用 `model_6_execution` 时 `area_code` 命中 `SHAOGUAN_AREA_CODES`（如 "lechang"），且 `land_type` 为 "upland" 或未传（默认 "upland"）
- **THEN** 系统 SHALL 加载 `data/fertility/models/sg_dose_upland_rf_model.joblib`，使用 RandomForestRegressor 预测 Dose，返回 `dose_prediction`、`dose_confidence`（SG 旱地模型测试 R²）、`dose_warning`（含 "韶关旱地 RF 模型" 标识）、`model_version`（值为 `sg_dose_upland_metadata.json` 中的 `model_version`，如 "SG_RF_v2_20260804"），SOC 预测仍使用全局 ETR SOC 模型

#### Scenario: 韶关区域水田 Dose 预测

- **WHEN** 调用 `model_6_execution` 时 `area_code` 命中 `SHAOGUAN_AREA_CODES`，且 `land_type` 为 "paddy"
- **THEN** 系统 SHALL 加载 `data/fertility/models/sg_dose_paddy_rf_model.joblib`，使用 RandomForestRegressor 预测 Dose，返回 `dose_prediction`、`dose_confidence`（SG 水田模型测试 R²）、`dose_warning`（含 "韶关水田 RF 模型" 标识）、`model_version`（值为 `sg_dose_paddy_metadata.json` 中的 `model_version`，如 "SG_RF_v2_20260804"）

#### Scenario: 韶关区域 SOC 预测回退全局 ETR

- **WHEN** 调用 `model_6_execution` 时 `area_code` 命中 `SHAOGUAN_AREA_CODES`，无论 `land_type` 取值
- **THEN** SOC 预测 SHALL 使用全局 `data/fertility/models/soc_etr_model.joblib`（ExtraTreesRegressor），返回 `soc_prediction` 和 `soc_confidence`（值为 0.91），与非韶关区域 SOC 预测行为一致

#### Scenario: SOMbe 输入名称映射

- **WHEN** 调用 `model_6_execution` 时 `input_data` 中有机指标字段名为 `SOMbe`（而非 `SOCbe`）
- **THEN** 系统 SHALL 在输入层将 `SOMbe` 映射为 `SOCbe`，使全局 ETR 和 SG RF 模型均能正确消费该特征，`imputed_features` 中使用统一名 `SOCbe`

#### Scenario: Dose 预测时显式标注低置信度

- **WHEN** Dose 模型预测被执行且 `status` 为 "success"
- **THEN** 响应 SHALL 包含 `dose_warning` 字段，明文标注模型类型和 R² 值（全局 ETR: "Dose 模型 R²=0.47..."；SG RF: 含 "韶关" 和对应 R²），`dose_confidence` 字段值为对应模型的测试 R²，单位为 t/ha

#### Scenario: 部分特征缺失的 Dose 预测

- **WHEN** 调用 `model_6_execution` 时部分 Dose 模型特征缺失
- **THEN** 系统 SHALL 使用对应模型（全局 ETR 或 SG RF）的训练集均值填充缺失特征，在 `imputed_features` 中累计列出 SOC 与 Dose 模型各自被填充的特征，附带 `imputation_applied: true`

#### Scenario: Dose 模型文件缺失时的降级回退

- **WHEN** 所需 Dose 模型文件不存在（全局 `dose_etr_model.joblib` 或 SG `sg_dose_*_rf_model.joblib`）
- **THEN** 系统 SHALL 返回 `dose_prediction` 为训练集 Dose 均值，`status: "fallback"`，`fallback_reason: "model_file_missing"`，`dose_confidence: 0.3`，`model_version` 返回全局 ETR 版本号

#### Scenario: 韶关 Dose 响应返回 SG 模型版本号

- **WHEN** 韶关区域 Dose 预测成功执行（`status` 为 "success"），无论 `land_type` 为 "upland" 或 "paddy"
- **THEN** 响应的 `model_version` 字段 SHALL 等于实际加载的 SG RF 模型 metadata（`sg_dose_upland_metadata.json` 或 `sg_dose_paddy_metadata.json`）中的 `model_version` 值，而非全局 ETR 版本号 `_MODEL_VERSION`
