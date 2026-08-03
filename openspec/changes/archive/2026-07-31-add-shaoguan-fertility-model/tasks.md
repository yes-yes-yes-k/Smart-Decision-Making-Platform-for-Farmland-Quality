## 1. SG 模型训练数据准备

- [x] 1.1 将韶关旱地 Dose 预切分数据（`SG旱地-Dose-RF_Manual_splits.xlsx`）复制到 `data/fertility/` 目录
- [x] 1.2 将韶关水田 Dose 预切分数据（`SG水田-Dose-RF_Manual_splits.xlsx`）复制到 `data/fertility/` 目录
- [x] 1.3 检查水田模型训练样本量和特征列，确认与旱地一致（pH/SOMbe/TN/TP/TK/AP/AK/Gap/Fertilizer type）

## 2. 扩展训练脚本支持 SG RF 模型

- [x] 2.1 在 `scripts/train_fertility_models.py` 中新增 SG Dose RF 训练函数：读取预切分 xlsx（Xtrain/Xtest/Ytrain/Ytest sheets），训练 `RandomForestRegressor(n_estimators=100, random_state=230)`
- [x] 2.2 新增 `--sg` CLI 参数触发 SG 模型训练（旱地和水田分别训练）
- [x] 2.3 训练时将特征列 `SOMbe` 重命名为 `SOCbe`，确保与全局模型特征名统一
- [x] 2.4 保存 SG 模型为 `data/fertility/models/sg_dose_upland_rf_model.joblib` 和 `sg_dose_paddy_rf_model.joblib`，附带 metadata.json（含 model_type/feature_names/metrics/training_samples）
- [x] 2.5 运行训练脚本生成 SG 模型文件，验证 metadata.json 内容完整

## 3. model_6.py 区域路由实现

- [x] 3.1 定义 `SHAOGUAN_AREA_CODES` 集合常量（初始含 "lechang"，可扩展）
- [x] 3.2 新增 SG RF 模型惰性加载逻辑：`_SG_UPLAND_MODEL`/`_SG_PADDY_MODEL` 及对应 metadata，复用 double-checked locking 模式
- [x] 3.3 `model_6_execution` 新增可选 `land_type` 参数（默认 None，未传时由模型层默认 upland 并追加提示）
- [x] 3.4 实现区域路由：从 `input_data` 读取 `area_code`，命中 `SHAOGUAN_AREA_CODES` 时 Dose 走 SG RF，SOC 始终走全局 ETR
- [x] 3.5 实现输入层 `SOMbe`→`SOCbe` 名称映射（在 `_prepare_features` 之前规范化）
- [x] 3.6 SG 区域 `dose_warning` 包含 "韶关旱地/水田 RF 模型" 标识和 R² 值；`land_type` 未传时追加默认提示（spec L82-83）
- [x] 3.7 SG 模型文件缺失时返回 fallback 响应（`fallback_reason: "model_file_missing"`）

## 4. FertilityMLAgent 适配

- [x] 4.1 `FertilityMLAgent.execute` 从 task/context 中提取 `area_code` 和 `land_type`，透传给 `model_6_execution`
- [x] 4.2 `FertilityMLAgent.answer_question` 确保 context 中的 `area_code` 和 `land_type` 正确传入 execute

## 5. API 层适配

- [x] 5.1 API 请求 payload 新增可选 `land_type` 参数（"upland"/"paddy"）
- [x] 5.2 确保 `area_code` 和 `land_type` 从 API 层经 core_engine adapter 透传到 `model_6_execution`

## 6. 测试

- [x] 6.1 测试非韶关区域 Dose 预测行为不变（area_code="other" → 全局 ETR，回归测试）
- [x] 6.2 测试韶关区域旱地 Dose 预测使用 SG RF 模型（area_code="lechang", land_type="upland"）
- [x] 6.3 测试韶关区域水田 Dose 预测使用 SG RF 模型（area_code="lechang", land_type="paddy"）
- [x] 6.4 测试韶关区域 SOC 预测回退全局 ETR 模型
- [x] 6.5 测试 SOMbe 输入名称映射为 SOCbe
- [x] 6.6 测试 land_type 未传时默认 "upland" 并附 dose_warning 提示
- [x] 6.7 测试 SG 模型文件缺失时返回 fallback 响应
- [x] 6.8 测试 FertilityMLAgent 传递 area_code 和 land_type 到 model_6_execution

## 7. 验证

- [x] 7.1 运行 model-6 相关全量测试通过
- [x] 7.2 运行项目整体测试套件确认无回归（排除预先存在的失败）
- [x] 7.3 验证 SG 模型预测结果数值合理（Dose 在合法范围内）
