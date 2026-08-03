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
