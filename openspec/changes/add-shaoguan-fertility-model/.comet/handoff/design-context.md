# Comet Design Handoff

- Change: add-shaoguan-fertility-model
- Phase: design
- Mode: compact
- Context hash: d4bbd18ae6fa0ca1ccbea2a32149f8c6e1a56c3835344f7f1831f149285c939b

Generated-by: comet-handoff.sh

OpenSpec remains the canonical capability spec. This handoff is a deterministic, source-traceable context pack, not an agent-authored summary.

## openspec/changes/add-shaoguan-fertility-model/proposal.md

- Source: openspec/changes/add-shaoguan-fertility-model/proposal.md
- Lines: 1-38
- SHA256: 11438b5e34859f7070a392e31fdd52d1ee479c1863ef0ddb2310a1119166f4fd

```md
## Why

当前 model-6 使用单全局 ExtraTreesRegressor 模型预测 Dose（施用量），训练样本仅 45 个、测试 R²=0.47，精度偏低。模型提供方已提供韶关（SG）区域专用的 RandomForestRegressor Dose 预测模型，按旱地/水田分别训练（旱地 185 样本），数据量更大、区域适配性更强。项目默认 area_code="lechang"（乐昌，韶关下辖县级市），本就在韶关区域运营，应接入 SG 模型提升本地 Dose 预测质量。

## What Changes

- 新增韶关区域 Dose 预测能力：基于 RandomForestRegressor 的旱地（upland）和水田（paddy）两个独立子模型，从模型提供方提供的预切分 xlsx 数据训练并保存为 `.joblib` 文件
- 新增区域路由机制：`model_6_execution` 根据 `area_code` 判断是否使用 SG 模型（lechang 等韶关区域 → SG RF 模型，其他区域 → 现有全局 ETR 模型，行为不变）
- **BREAKING** `model_6_execution` 新增可选 `land_type` 参数（"upland"/"paddy"）：SG 区域 Dose 预测时按此选择子模型；未传时默认 "upland"
- SG 区域 SOC 预测回退到现有全局 ETR SOC 模型（SG 模型仅覆盖 Dose）
- 统一有机指标命名：SOMbe（有机质）与 SOCbe（有机碳）视为同一指标，在输入层做名称映射，无需重新训练全局 ETR 模型
- 扩展训练脚本 `scripts/train_fertility_models.py` 支持 SG RF 模型训练
- 新增 SG 模型训练数据资产和 metadata.json

## Capabilities

### New Capabilities
（无）

### Modified Capabilities
- `fertility-ml-prediction`: Dose 预测能力新增区域路由（SG RF 模型 vs 全局 ETR 模型）和 land_type 参数；新增 SG 模型训练脚本和数据资产 requirement

## Impact

**受影响代码：**
- `framework/domain/other_models/model_6.py` — 新增区域路由逻辑、SG RF 模型惰性加载、land_type 参数处理、SOMbe↔SOCbe 名称映射
- `framework/agents/specialized/fertility_ml_agent.py` — 传递 area_code 和 land_type 到 model_6_execution
- `framework/api/routes/models.py`（或相关 API 层）— 请求 payload 新增 land_type 参数
- `scripts/train_fertility_models.py` — 扩展支持 SG RF 模型训练（旱地/水田分别训练）

**受影响数据资产：**
- `data/fertility/models/` — 新增 `sg_dose_upland_rf_model.joblib`、`sg_dose_paddy_rf_model.joblib` 及对应 metadata.json
- `data/fertility/` — 新增 SG 预切分训练数据 xlsx 文件

**不受影响：**
- 全局 ETR SOC/Dose 模型文件（保持不变，作为非韶关区域默认和 SG 区域 SOC 回退）
- thematic_models.py 的 organic-matter-improvement 占位 ModelSpec
- 其他模型（model-1/3/5/7）、RAG、LLM service、数据库结构

```

## openspec/changes/add-shaoguan-fertility-model/design.md

- Source: openspec/changes/add-shaoguan-fertility-model/design.md
- Lines: 1-70
- SHA256: d0ce199eb7daa4d8cca6c71086e1c607d17db3d12d8b1336ee7c543d93d823ae

```md
## Context

现有 model-6（`framework/domain/other_models/model_6.py`）使用单全局 ExtraTreesRegressor 模型预测 SOC 和 Dose，训练数据仅 45 个样本（Dose），测试 R²=0.47。模型提供方已提供韶关（SG）区域专用的 RandomForestRegressor Dose 预测模型，按旱地（upland）和水田（paddy）分别训练，旱地 185 样本，数据量和区域适配性均优于全局模型。

项目默认 `area_code="lechang"`（乐昌，韶关下辖），本就在韶关区域运营。当前 `model_6_execution(input_data)` 无区域参数，无法区分区域选择模型。`FertilityMLAgent` 将 context data 直接传给 `model_6_execution`，API 层已有 `area_code` 参数。

SG 模型特征使用 `SOMbe`（有机质），现有模型使用 `SOCbe`（有机碳）——两者为同一土壤指标的不同命名，需在输入层统一。

## Goals / Non-Goals

**Goals:**
- `model_6_execution` 能根据 `area_code` 自动选择 SG RF 模型（韶关区域）或全局 ETR 模型（其他区域）
- SG 区域 Dose 预测支持 `land_type`（upland/paddy）选择子模型
- SG 区域 SOC 查询回退到全局 ETR SOC 模型
- SG RF 模型从提供方 xlsx 数据训练并保存为 `.joblib`，附带 metadata.json
- 输入层统一 SOMbe↔SOCbe 命名，无需重训全局 ETR 模型

**Non-Goals:**
- 不为 SG 区域训练新的 SOC 预测模型（提供方未提供 SOC 训练数据）
- 不修改全局 ETR 模型文件和行为（非韶关区域行为完全不变）
- 不修改 `thematic_models.py` 的 organic-matter-improvement 占位 ModelSpec
- 不新增独立 model_id（保持通过 area_code 路由，前端无感知）

## Decisions

### D1: 区域路由基于 area_code 映射

**选择**：维护 `SHAOGUAN_AREA_CODES` 集合（初始含 "lechang"），`model_6_execution` 从 input_data 中读取 `area_code`，命中集合时走 SG 路径。

**理由**：API 层已有 `area_code` 参数，无需新增独立参数或 model_id。前端无需改动，向后兼容。

**备选**：新增 `region` 参数（与 area_code 解耦）——被否决，因 area_code 已能表达区域归属，新增参数增加调用方负担。

### D2: land_type 作为 model_6_execution 的新参数

**选择**：`model_6_execution(input_data, land_type="upland")` 新增可选参数，默认 "upland"。SG 区域 Dose 预测时按此选择子模型；非 SG 区域忽略此参数。

**理由**：SG 模型按旱地/水田分别训练，需显式区分。默认 upland 覆盖韶关以旱地为主的常见场景。

**备选**：从输入数据自动推断土地类型——被否决，因推断逻辑不可靠且缺乏推断依据字段。

### D3: SOMbe↔SOCbe 输入层名称映射

**选择**：在 `_prepare_features` 之前做名称规范化：将 input_data 中的 `SOMbe` 映射为 `SOCbe`（或反向），使两套模型能消费同一输入。全局 ETR 模型 metadata 保持 `SOCbe` 不变；SG RF 模型 metadata 使用 `SOCbe`（训练时从 `SOMbe` 列重命名）。

**理由**：用户确认两者为同一指标。输入层映射避免修改已有模型文件和重训成本。

### D4: SG RF 模型训练与部署

**选择**：扩展 `scripts/train_fertility_models.py`，新增 SG Dose RF 模型训练逻辑：从提供方 xlsx（Xtrain/Xtest/Ytrain/Ytest sheets）读取数据，训练 `RandomForestRegressor(n_estimators=100, random_state=230)`，保存为 `data/fertility/models/sg_dose_upland_rf_model.joblib` 和 `sg_dose_paddy_rf_model.joblib`，附带 metadata.json。

**理由**：复用现有训练脚本基础设施，保持模型资产管理一致性。RF 超参数来自提供方 notebook。

### D5: SG 区域 SOC 回退到全局 ETR

**选择**：SG 区域执行 Dose 预测用 SG RF 模型，SOC 预测仍用全局 `soc_etr_model.joblib`。一次 `model_6_execution` 调用可混合使用 SG RF（Dose）+ 全局 ETR（SOC）。

**理由**：提供方未提供 SG SOC 训练数据。全局 ETR SOC 模型 R²=0.91，精度可靠，可作为 SG 区域 SOC 回退。

## Risks / Trade-offs

- **[风险] SG 水田模型样本量未知** → 训练时检查样本数，若 <30 则在 metadata 中标注低置信度，dose_warning 提示水田模型仅供参考
- **[风险] area_code 清单不完整** → `SHAOGUAN_AREA_CODES` 设计为可扩展集合，初始仅含 "lechang"，后续可追加；未命中 area_code 默认走全局 ETR，安全回退
- **[风险] land_type 未传时默认旱地** → 在 dose_warning 中标注"未指定 land_type，默认使用旱地模型"，提示调用方显式传入
- **[权衡] 混合模型路径增加复杂度** → SG 区域一次调用走两个模型（RF Dose + ETR SOC），但通过统一的 `_ensure_models_loaded` 惰性加载机制管理，不增加调用方感知

## Open Questions

- 韶关区域 area_code 完整清单（目前已知 "lechang"，是否还有其他？）
- SG 水田 Dose 模型的训练样本量和精度（需检查 `SG水田-Dose-RF_Manual_splits.xlsx`）

```

## openspec/changes/add-shaoguan-fertility-model/tasks.md

- Source: openspec/changes/add-shaoguan-fertility-model/tasks.md
- Lines: 1-50
- SHA256: 5c0cfa0aa33a0acda7e4f7829e2545a5b05bf59c6fced38b0a242123c7b60b09

```md
## 1. SG 模型训练数据准备

- [ ] 1.1 将韶关旱地 Dose 预切分数据（`SG旱地-Dose-RF_Manual_splits.xlsx`）复制到 `data/fertility/` 目录
- [ ] 1.2 将韶关水田 Dose 预切分数据（`SG水田-Dose-RF_Manual_splits.xlsx`）复制到 `data/fertility/` 目录
- [ ] 1.3 检查水田模型训练样本量和特征列，确认与旱地一致（pH/SOMbe/TN/TP/TK/AP/AK/Gap/Fertilizer type）

## 2. 扩展训练脚本支持 SG RF 模型

- [ ] 2.1 在 `scripts/train_fertility_models.py` 中新增 SG Dose RF 训练函数：读取预切分 xlsx（Xtrain/Xtest/Ytrain/Ytest sheets），训练 `RandomForestRegressor(n_estimators=100, random_state=230)`
- [ ] 2.2 新增 `--sg` CLI 参数触发 SG 模型训练（旱地和水田分别训练）
- [ ] 2.3 训练时将特征列 `SOMbe` 重命名为 `SOCbe`，确保与全局模型特征名统一
- [ ] 2.4 保存 SG 模型为 `data/fertility/models/sg_dose_upland_rf_model.joblib` 和 `sg_dose_paddy_rf_model.joblib`，附带 metadata.json（含 model_type/feature_names/metrics/training_samples）
- [ ] 2.5 运行训练脚本生成 SG 模型文件，验证 metadata.json 内容完整

## 3. model_6.py 区域路由实现

- [ ] 3.1 定义 `SHAOGUAN_AREA_CODES` 集合常量（初始含 "lechang"，可扩展）
- [ ] 3.2 新增 SG RF 模型惰性加载逻辑：`_SG_UPLAND_MODEL`/`_SG_PADDY_MODEL` 及对应 metadata，复用 double-checked locking 模式
- [ ] 3.3 `model_6_execution` 新增可选 `land_type` 参数（默认 "upland"）
- [ ] 3.4 实现区域路由：从 `input_data` 读取 `area_code`，命中 `SHAOGUAN_AREA_CODES` 时 Dose 走 SG RF，SOC 始终走全局 ETR
- [ ] 3.5 实现输入层 `SOMbe`→`SOCbe` 名称映射（在 `_prepare_features` 之前规范化）
- [ ] 3.6 SG 区域 `dose_warning` 包含 "韶关旱地/水田 RF 模型" 标识和 R² 值；`land_type` 未传时追加默认提示
- [ ] 3.7 SG 模型文件缺失时返回 fallback 响应（`fallback_reason: "model_file_missing"`）

## 4. FertilityMLAgent 适配

- [ ] 4.1 `FertilityMLAgent.execute` 从 task/context 中提取 `area_code` 和 `land_type`，透传给 `model_6_execution`
- [ ] 4.2 `FertilityMLAgent.answer_question` 确保 context 中的 `area_code` 和 `land_type` 正确传入 execute

## 5. API 层适配

- [ ] 5.1 API 请求 payload 新增可选 `land_type` 参数（"upland"/"paddy"）
- [ ] 5.2 确保 `area_code` 和 `land_type` 从 API 层经 core_engine adapter 透传到 `model_6_execution`

## 6. 测试

- [ ] 6.1 测试非韶关区域 Dose 预测行为不变（area_code="other" → 全局 ETR，回归测试）
- [ ] 6.2 测试韶关区域旱地 Dose 预测使用 SG RF 模型（area_code="lechang", land_type="upland"）
- [ ] 6.3 测试韶关区域水田 Dose 预测使用 SG RF 模型（area_code="lechang", land_type="paddy"）
- [ ] 6.4 测试韶关区域 SOC 预测回退全局 ETR 模型
- [ ] 6.5 测试 SOMbe 输入名称映射为 SOCbe
- [ ] 6.6 测试 land_type 未传时默认 "upland" 并附 dose_warning 提示
- [ ] 6.7 测试 SG 模型文件缺失时返回 fallback 响应
- [ ] 6.8 测试 FertilityMLAgent 传递 area_code 和 land_type 到 model_6_execution

## 7. 验证

- [ ] 7.1 运行 model-6 相关全量测试通过
- [ ] 7.2 运行项目整体测试套件确认无回归（排除预先存在的失败）
- [ ] 7.3 验证 SG 模型预测结果数值合理（Dose 在合法范围内）

```

## openspec/changes/add-shaoguan-fertility-model/specs/fertility-ml-prediction/spec.md

- Source: openspec/changes/add-shaoguan-fertility-model/specs/fertility-ml-prediction/spec.md
- Lines: 1-87
- SHA256: 1f4b15750a21a3698ab58569bc5751aeb53119aaaf2ace220f7188c382b76739

[TRUNCATED]

```md
## MODIFIED Requirements

### Requirement: Dose（施用量）ML 预测能力
系统 SHALL 通过 `model_6_execution` 函数提供 Dose（施用量）的机器学习预测能力，支持区域路由：非韶关区域使用预训练的全局 ExtraTreesRegressor 模型（保存在 `data/fertility/models/dose_etr_model.joblib`），韶关区域（`area_code` 命中 `SHAOGUAN_AREA_CODES` 集合）使用 RandomForestRegressor 模型（按 `land_type` 选择旱地或水田子模型）。Dose 模型输入 9 个土壤特征（pH、SOCbe、TN、TP、TK、AP、AK、Gap、Fertilizer type，不含 Dose 自身），返回 Dose 预测值（单位 t/ha）、置信度与质量警告信息。SOC 预测在所有区域均使用全局 ETR SOC 模型，不受区域路由影响。

#### Scenario: 非韶关区域完整特征输入的 Dose 预测
- **WHEN** 调用 `model_6_execution` 时 `area_code` 不在 `SHAOGUAN_AREA_CODES` 中，且 `input_data` 包含全部 9 个 Dose 模型所需特征
- **THEN** 系统 SHALL 加载 `data/fertility/models/dose_etr_model.joblib`，调用 `model.predict()` 返回 `dose_prediction`（float，单位 t/ha）、`dose_confidence`（值为 0.47）、`dose_warning`（值为 "Dose 模型 R²=0.47，预测结果仅供参考，建议结合田间试验校准"）

#### Scenario: 韶关区域旱地 Dose 预测
- **WHEN** 调用 `model_6_execution` 时 `area_code` 命中 `SHAOGUAN_AREA_CODES`（如 "lechang"），且 `land_type` 为 "upland" 或未传（默认 "upland"）
- **THEN** 系统 SHALL 加载 `data/fertility/models/sg_dose_upland_rf_model.joblib`，使用 RandomForestRegressor 预测 Dose，返回 `dose_prediction`、`dose_confidence`（SG 旱地模型测试 R²）、`dose_warning`（含 "韶关旱地 RF 模型" 标识），SOC 预测仍使用全局 ETR SOC 模型

#### Scenario: 韶关区域水田 Dose 预测
- **WHEN** 调用 `model_6_execution` 时 `area_code` 命中 `SHAOGUAN_AREA_CODES`，且 `land_type` 为 "paddy"
- **THEN** 系统 SHALL 加载 `data/fertility/models/sg_dose_paddy_rf_model.joblib`，使用 RandomForestRegressor 预测 Dose，返回 `dose_prediction`、`dose_confidence`（SG 水田模型测试 R²）、`dose_warning`（含 "韶关水田 RF 模型" 标识）

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
- **THEN** 系统 SHALL 返回 `dose_prediction` 为训练集 Dose 均值，`status: "fallback"`，`fallback_reason: "model_file_missing"`，`dose_confidence: 0.3`

### Requirement: 训练脚本可重训模型
系统 SHALL 提供 `scripts/train_fertility_models.py` 作为独立 CLI 脚本，支持两类模型训练：(1) 从原始 xlsx 训练数据训练全局 SOC 和 Dose 两个 ExtraTreesRegressor 模型，执行 7 步网格搜索确定最优超参数；(2) 从韶关预切分 xlsx 数据训练 SG Dose RandomForestRegressor 模型（旱地和水田分别训练），使用提供方 notebook 指定的超参数（n_estimators=100, random_state=230）。训练好的模型保存为 `.joblib` 文件并附带 metadata.json。

#### Scenario: 重新训练全局 ETR 模型
- **WHEN** 运行 `python scripts/train_fertility_models.py`（无参数或带 `--data-dir data/fertility` 参数）
- **THEN** 系统 SHALL 读取 `data/fertility/ML-data-SOC-RF_Manual_splits.xlsx` 与 `data/fertility/ML-data-Dose-RF_Manual_splits.xlsx`，按 7 步网格搜索流程训练两个 ETR 模型，保存到 `data/fertility/models/soc_etr_model.joblib` 与 `dose_etr_model.joblib`，并打印每个模型的 5CV R² 与测试集 R²

#### Scenario: 训练韶关 RF Dose 模型
- **WHEN** 运行 `python scripts/train_fertility_models.py --sg`（或带韶关数据路径参数）
- **THEN** 系统 SHALL 读取韶关旱地和水田 Dose 预切分 xlsx（含 Xtrain/Xtest/Ytrain/Ytest sheets），分别训练 RandomForestRegressor(n_estimators=100, random_state=230)，保存为 `data/fertility/models/sg_dose_upland_rf_model.joblib` 和 `sg_dose_paddy_rf_model.joblib`，附带 metadata.json（含 model_type、feature_names、metrics、training_samples），并打印 5CV R² 和测试集 R²

#### Scenario: 训练数据文件缺失时报错
- **WHEN** 训练数据 xlsx 文件不存在
- **THEN** 系统 SHALL 输出明确的错误信息指明缺失文件路径，并以非零退出码退出，不创建任何 `.joblib` 文件

### Requirement: 训练数据资产可追溯
系统 SHALL 在 `data/fertility/` 目录中保留完整的训练数据资产，包括全局训练数据（xlsx 文件）、韶关训练数据（xlsx 文件）与训练好的模型文件（.joblib 文件），并在模型文件旁附带 JSON 格式的元数据文件记录训练时间、模型版本、超参数与性能指标。

#### Scenario: 全局训练数据完整性
- **WHEN** 检查 `data/fertility/` 目录
- **THEN** 目录 SHALL 包含 `ML-data-SOC-RF_Manual_splits.xlsx`、`ML-data-Dose-RF_Manual_splits.xlsx`、`变量注释.xlsx` 三个全局训练数据文件，以及 `models/soc_etr_model.joblib`、`models/dose_etr_model.joblib`、`models/soc_metadata.json`、`models/dose_metadata.json` 四个全局生成产物

#### Scenario: 韶关训练数据完整性
- **WHEN** 检查 `data/fertility/` 目录
- **THEN** 目录 SHALL 包含韶关预切分训练数据文件（`SG旱地-Dose-RF_Manual_splits.xlsx`、`SG水田-Dose-RF_Manual_splits.xlsx`），以及 `models/sg_dose_upland_rf_model.joblib`、`models/sg_dose_paddy_rf_model.joblib`、`models/sg_dose_upland_metadata.json`、`models/sg_dose_paddy_metadata.json` 四个韶关生成产物

#### Scenario: 韶关模型元数据可读
- **WHEN** 读取 `data/fertility/models/sg_dose_upland_metadata.json` 文件
- **THEN** 文件 SHALL 包含 `model_type`（"RandomForestRegressor"）、`trained_at`（ISO 8601 时间戳）、`model_version`（如 "SG_RF_v1_20260722"）、`hyperparameters`（含 n_estimators=100、random_state=230）、`metrics`（含 cv_r2、test_r2、test_rmse）、`feature_names`（含 pH、SOCbe、TN、TP、TK、AP、AK、Gap、Fertilizer type）、`training_samples` 字段

## ADDED Requirements

### Requirement: 韶关区域路由与 land_type 参数支持
系统 SHALL 在 `model_6_execution` 中维护 `SHAOGUAN_AREA_CODES` 集合（初始包含 "lechang"，可扩展），根据 `input_data` 中的 `area_code` 字段判断是否使用韶关区域模型路径。韶关区域 Dose 预测 SHALL 接受可选 `land_type` 参数（"upland"/"paddy"），未传时默认 "upland" 并在 `dose_warning` 中标注默认提示。非韶关区域 SHALL 忽略 `land_type`，使用全局 ETR 模型。

#### Scenario: area_code 命中韶关集合
- **WHEN** `model_6_execution` 的 `input_data` 中 `area_code` 值为 "lechang"（在 `SHAOGUAN_AREA_CODES` 中）
- **THEN** 系统 SHALL 走韶关区域路径：Dose 使用 SG RF 模型，SOC 使用全局 ETR 模型

#### Scenario: area_code 未命中韶关集合
- **WHEN** `model_6_execution` 的 `input_data` 中 `area_code` 值为 "other" 或未提供
- **THEN** 系统 SHALL 走全局路径：Dose 和 SOC 均使用全局 ETR 模型，行为与变更前完全一致


```

Full source: openspec/changes/add-shaoguan-fertility-model/specs/fertility-ml-prediction/spec.md
