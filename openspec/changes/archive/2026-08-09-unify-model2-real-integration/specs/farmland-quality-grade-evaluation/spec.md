## MODIFIED Requirements

### Requirement: 耕地质量等级评价 Python 模型

系统 SHALL 通过纯 Python 实现（不依赖 Fortran exe 或二进制 `.dat` 文件）完成耕地质量等级评价，基于 GB/T 33469-2016 标准的隶属函数模型与权重加权指数和法计算质量综合指数与等级。该能力 SHALL 作为正式 `model-2/improvement-potential-assessment` 的真实计算引擎对外提供，`MODEL_VERSION` SHALL 为 `python_v1_20260801`。

#### Scenario: 核心评价查询
- **WHEN** 通过 `model-2` 调用质量等级评价且 CSV 数据文件已部署、地块代码存在
- **THEN** 系统 SHALL 返回 `status: "ok"`，包含 `parcel_code`、`parcel_info`（地块代码/经纬度/县区名称/二级农业区名称）、`indicators`（12 项含 name/code/raw_value）、`composite_index`（浮点）、`quality_grade`（如"10等"字符串）、`obstacle_degree`（12 项含 rank/indicator/degree/level，按 degree 降序）
- **AND** 返回结果 SHALL 标记 `simulated: false` 和规范 `model-2` 归属

#### Scenario: 数据文件未部署
- **WHEN** 通过 `model-2` 调用质量等级评价时 CSV 数据文件不存在或不可读
- **THEN** 系统 SHALL 返回 `status: "error"`，`error.code: "DEPLOYMENT_ERROR"`，`error.message` 说明 CSV 文件缺失

#### Scenario: 地块代码未找到
- **WHEN** 通过 `model-2` 调用质量等级评价且 `parcel_code` 在 CSV 数据中不存在
- **THEN** 系统 SHALL 返回 `status: "error"`，`error.code: "PARCEL_NOT_FOUND"`，`error.message` 包含未找到的地块代码

#### Scenario: 编码字段越界
- **WHEN** 地块的 ZDGC/PSNL/GGNL/DXBW/ZDGX/ejnyq 编码超出合法范围
- **THEN** 系统 SHALL 返回 `status: "error"`，`error.code` 标识越界字段，不返回部分结果

#### Scenario: 数值等价性
- **WHEN** 对 A0001 地块通过 `model-2` 执行 Python 评价
- **THEN** `composite_index` SHALL 与历史输出（0.6728）一致（浮点容差 < 0.01），`quality_grade` SHALL 为"10等"，`obstacle_degree` 各项 degree SHALL 与历史输出一致（容差 < 0.01）

### Requirement: 单地块潜力分析

系统 SHALL 通过 `model-2` 提供单地块潜力分析，基于真实地块数据按固定顺序（灌溉→排水→有机质→速效钾→有效磷→有效土层厚度→容重→pH→耕层厚度）模拟各指标改良后的潜在质量指数与等级提升，并计算全改良后的潜在质量指数与等级。

#### Scenario: 潜力分析查询
- **WHEN** 通过 `model-2` 调用潜力评估且地块代码存在
- **THEN** 系统 SHALL 返回各指标的原始值、潜力值、原始质量指数、潜在质量指数、原等级、潜在等级，以及全改良后的综合质量指数与等级
- **AND** SHALL NOT 以固定模拟指标替代该地块计算结果

