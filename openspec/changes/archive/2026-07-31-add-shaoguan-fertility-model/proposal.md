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
