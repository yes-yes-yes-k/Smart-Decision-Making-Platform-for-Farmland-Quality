## ADDED Requirements

### Requirement: 实现 Random Forest 模型加载和预测

系统 SHALL 加载预训练的 Random Forest 模型文件（旱地和水田各一个 .joblib），从 DB 读取土壤指标（pH/SOMbe/AK/AP/TN 等），预测 Dose（推荐施肥量）。

#### Scenario: RF 模型可用时预测
- **WHEN** 模型文件存在且 soil_indicators 有完整的输入特征
- **THEN** 返回 status=ok、simulated=False、predicted Dose 值，持久化到 organic_matter_result 表

#### Scenario: RF 模型不可用时规则降级
- **WHEN** scikit-learn 未安装或模型文件不存在
- **THEN** 降级到规则计算（有机质分级 + 推荐施用量），simulated=True

### Requirement: 根据 land_type 选择模型

系统 SHALL 根据 parcel_info 的 land_type 字段选择对应的 RF 模型（旱地模型或水田模型）。

#### Scenario: 旱地地块
- **WHEN** land_type=upland
- **THEN** 使用旱地 RF 模型预测

#### Scenario: 水田地块
- **WHEN** land_type=paddy
- **THEN** 使用水田 RF 模型预测
