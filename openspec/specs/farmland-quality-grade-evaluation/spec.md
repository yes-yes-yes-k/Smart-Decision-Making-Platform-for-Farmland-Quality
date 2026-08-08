# farmland-quality-grade-evaluation Specification

## Purpose
TBD - created by archiving change replace-grade-eval-with-python-model. Update Purpose after archive.
## Requirements
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

### Requirement: 向后兼容的 API 签名
系统 SHALL 保持 `run_grade_evaluation(parcel_code, exe_path=None, dat_path=None)` 函数签名不变，其中 `dat_path` 参数语义改为 CSV 文件路径（默认 `bin/farmland_quality_eval/Farmland_quality_Level_Database.csv`），`exe_path` 参数 SHALL 被忽略且不报错。`FarmlandGradeRunner.__init__` SHALL 同理保持签名兼容。

#### Scenario: 默认路径调用
- **WHEN** 调用 `run_grade_evaluation("A0001")` 不传 dat_path
- **THEN** 系统 SHALL 使用默认 CSV 路径 `bin/farmland_quality_eval/Farmland_quality_Level_Database.csv` 加载数据

#### Scenario: 旧参数兼容
- **WHEN** 调用方传入 `exe_path` 和 `dat_path`（旧调用方式）
- **THEN** 系统 SHALL 忽略 `exe_path`，将 `dat_path` 解释为 CSV 路径，不抛出参数错误

### Requirement: 部署校验改为 CSV
`FarmlandGradeRunner.check_deployment()` SHALL 校验 CSV 数据文件存在且可读（非空、含标题行），不再校验 exe 或 .dat 文件。返回 dict SHALL 包含 `csv_exists`、`csv_path`、`ready` 字段。

#### Scenario: CSV 已部署
- **WHEN** CSV 文件存在于默认路径且非空
- **THEN** `check_deployment` SHALL 返回 `csv_exists: true`、`ready: true`

#### Scenario: CSV 未部署
- **WHEN** CSV 文件不存在
- **THEN** `check_deployment` SHALL 返回 `csv_exists: false`、`ready: false`

### Requirement: 单地块潜力分析

系统 SHALL 通过 `model-2` 提供单地块潜力分析，基于真实地块数据按固定顺序（灌溉→排水→有机质→速效钾→有效磷→有效土层厚度→容重→pH→耕层厚度）模拟各指标改良后的潜在质量指数与等级提升，并计算全改良后的潜在质量指数与等级。

#### Scenario: 潜力分析查询
- **WHEN** 通过 `model-2` 调用潜力评估且地块代码存在
- **THEN** 系统 SHALL 返回各指标的原始值、潜力值、原始质量指数、潜在质量指数、原等级、潜在等级，以及全改良后的综合质量指数与等级
- **AND** SHALL NOT 以固定模拟指标替代该地块计算结果

### Requirement: 县域统计与潜力情景分析
系统 SHALL 提供 `run_county_statistics(xqmc_code, csv_path=None)` 和 `run_county_potential(xqmc_code, scenario, csv_path=None)` 函数，实现县域常规统计与潜力情景分析（scenario=1 理想潜力、scenario=2 最佳潜力），返回等级分布、障碍度统计、首要障碍指标等结构化结果。

#### Scenario: 县域常规统计
- **WHEN** 调用 `run_county_statistics(8)`（武江区）且该县区有地块数据
- **THEN** 系统 SHALL 返回地块数量、总面积、平均等级、各指标统计、障碍度排序、等级分布、首要障碍指标统计

#### Scenario: 县域潜力情景
- **WHEN** 调用 `run_county_potential(8, 1)`（理想潜力）
- **THEN** 系统 SHALL 返回潜力情景下的等级分布、障碍度变化及原始对比数据

#### Scenario: 县区无数据
- **WHEN** 调用县域统计且该县区无地块数据
- **THEN** 系统 SHALL 返回 `status: "error"` 或空结果，标识无数据

### Requirement: 调理剂库函数（不接 API）
系统 SHALL 移植 model2 的 `calculate_soil_conditioner` 作为库函数（去除交互式 input，参数由函数签名传入），计算亿土康（YTK）和木本泥炭（MBNT）施用量。该函数 SHALL NOT 通过 HTTP API 暴露；调理剂 API 需求 SHALL 由 model-4 酸化模型处理。

#### Scenario: 库函数调用
- **WHEN** 在代码中直接调用 `calculate_soil_conditioner(config, tybh, mj, xqmc, ph_start, alex, hex_)`
- **THEN** 函数 SHALL 返回 YTK/MBNT 的单位施用量（kg/ha）和地块总施用量（tons）

