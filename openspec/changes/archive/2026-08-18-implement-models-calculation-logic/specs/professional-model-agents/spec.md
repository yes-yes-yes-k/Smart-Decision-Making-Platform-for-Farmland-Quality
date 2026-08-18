## ADDED Requirements

### Requirement: 统一 soil_indicators 键名映射

系统 SHALL 在 ParcelDataAccessor 中实现 V3.0 英文 snake_case 字段名到各模型计算所需输入参数的统一映射。映射表覆盖全部 5 个模型的输入字段。

#### Scenario: Model-2/3 映射
- **WHEN** Agent 为 model-2 或 model-3
- **THEN** soil_ph→SJD, organic_matter→YJZ, available_phosphorus→YXL, available_potassium→SXJ, bulk_density→TRRZ, topsoil_thickness→YXTCHD, plow_layer_thickness→GCHD 等映射生效

#### Scenario: Model-4 映射
- **WHEN** Agent 为 model-4
- **THEN** soil_ph→SJD, exchangeable_hydrogen→Hex, exchangeable_aluminum→Alex 映射生效

#### Scenario: Model-5 映射
- **WHEN** Agent 为 model-5
- **THEN** soil_ph→pH, organic_matter→SOMbe, available_potassium→AK, available_phosphorus→AP, total_nitrogen→TN 映射生效

### Requirement: 离散指标英文/中文值转代码

系统 SHALL 将 soil_indicators 中的离散指标值转换为模型计算所需的代码。DB 实际存储英文值（如 "loam"、"dry"、"lower"），也可能存储中文值（如「壤土」、「充分满足」）。系统先查 `DISCRETE_EN_MAP`（英文→代码），未命中再查 `DISCRETE_CN_MAP`（中文→代码）。

#### Scenario: 英文质地映射
- **WHEN** soil_texture 值为 "loam"
- **THEN** 转换为代码 RT，用于隶属度查找

#### Scenario: 英文灌溉映射
- **WHEN** irrigation_condition 值为 "dry"
- **THEN** 转换为代码 US（GGNL）/ BM（PSNL）

#### Scenario: 中文值回退
- **WHEN** soil_texture 值为「壤土」（英文映射未命中）
- **THEN** 通过 DISCRETE_CN_MAP 转换为代码 RT

#### Scenario: 未知值降级
- **WHEN** 离散值既不在英文映射也不在中文映射中
- **THEN** 返回 None，该指标隶属度降级为默认值 0.5
