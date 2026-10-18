# farmland-acidification-rf-api Specification

## Purpose
TBD - created by archiving change add-acidification-rf-http-api-and-parcel-prefill. Update Purpose after archive.
## Requirements
### Requirement: 酸化 RF HTTP 接口

系统 SHALL 提供 JWT 保护的酸化 RF HTTP 接口，至少包含模型清单、预测与地块预填三个端点。接口 SHALL 复用本地模型资产与已验证的在线语义，MUST NOT 转发或依赖旧系统 HTTP 服务。模型清单 MUST 只返回模型编号、数据类型与土地类型，不得暴露资产路径或哈希。预测接口 MUST 按请求的模型编号选择其真实训练特征集与列序，不得跨模型套用字段集。

#### Scenario: 查询可用模型

- **WHEN** 已认证调用方请求模型清单
- **THEN** 系统 SHALL 返回当前 manifest 登记的模型编号、`data_type` 与 `land_type`
- **AND** 响应 MUST NOT 包含模型文件路径、哈希或来源绝对路径

#### Scenario: 提交满足契约的预测请求

- **WHEN** 已认证调用方按模型对应字段提交完整输入
- **THEN** 系统 SHALL 返回 `status=success`、原始预测值、业务转换值与来源标识
- **AND** 结果 SHALL 标明所用模型编号、数据类型与土地类型

#### Scenario: 请求使用其他模型的字段集

- **WHEN** 请求为水田返酸模型但只提供旱地特征（含交换性氢、缺亚铁）
- **THEN** 系统 SHALL 返回 `status=rejected`，并在 `missing_fields` 指出缺少的字段
- **AND** 系统 MUST NOT 以旱地字段与列序继续执行预测

#### Scenario: 未认证或模型资产不可用

- **WHEN** 请求缺少有效凭证，或模型资产缺失、哈希不一致、manifest 无法读取
- **THEN** 未认证请求 SHALL 返回 401
- **AND** 资产问题 SHALL 返回 503 与机器可读原因
- **AND** 系统 MUST NOT 回退到 model-4 或离线结果

### Requirement: 地块输入预填与来源披露

系统 SHALL 按地块编号返回 RF 输入预填值。预填 SHALL 只包含已建立字段映射的指标，并 MUST 为每个已填字段披露来源（`measured`、`region_mean_backfill`、`default` 或 `unknown`）。地块数据中无对应字段的输入 MUST 列入 `missing_fields` 且不得写入预填数据，系统 MUST NOT 以零值、区域均值或训练分布推断补齐。

#### Scenario: 预填包含回填指标

- **WHEN** 地块的交换性氢、交换性铝或阳离子交换量为区域平均回填
- **THEN** 系统 SHALL 返回这些值，并在 `provenance` 标记 `region_mean_backfill`
- **AND** 响应 SHALL 在 `imputed_fields` 列出非实测字段
- **AND** `warnings` SHALL 提供可直接展示的中文说明

#### Scenario: 地块缺少模型必需字段

- **WHEN** 模型需要的输入在地块数据中无对应字段
- **THEN** 字段 SHALL 出现在 `missing_fields`，且 MUST NOT 出现在 `data`
- **AND** 整体 `status` SHALL 为 `need_input`

#### Scenario: 来源标注缺失

- **WHEN** 地块指标存在取值但没有 provenance 标注
- **THEN** 系统 SHALL 将该字段来源记为 `unknown`
- **AND** 系统 MUST NOT 将其默认标记为 `measured`

#### Scenario: 土地类型与模型不匹配

- **WHEN** 调用方指定的模型土地类型与地块土地类型不一致
- **THEN** 系统 SHALL 返回 400 与 `land_type_mismatch`
- **AND** 地块不存在时 SHALL 返回 404 与 `parcel_not_found`

### Requirement: 缺失字段参考值与采用降级

系统 SHALL 为缺失字段提供可选参考值，参考值 MUST 来自该模型对应训练集的统计量，并 MUST 同时给出依据类型、数据集标识、样本量与分布区间。参考值 SHALL 与预填数据分字段存放，不得自动写入 `data`。调用方采用参考值时 MUST 通过 `assumptions` 声明来源依据，预测结果 SHALL 因此标记为 `degraded` 并在 `assumed_fields` 回显。对于单位未经核验的指标，系统 MUST 以 `unit_status=unverified` 标注且不得给出具体单位。

#### Scenario: 提供参考值

- **WHEN** 预填结果存在缺失字段且该模型有对应训练集统计
- **THEN** 系统 SHALL 在 `suggestions` 返回中位数、`basis=training_median`、数据集、样本量、P25–P75 与 `unit_status`
- **AND** 参考值 MUST NOT 出现在 `data` 中
- **AND** `warnings` SHALL 说明该值为训练样本中位数而非实测

#### Scenario: 使用者未采用参考值

- **WHEN** 调用方未提交参考值，或提交时未带 `assumptions`
- **THEN** 结果 SHALL 按实际输入计算
- **AND** 系统 SHALL NOT 把缺失字段当作已填充

#### Scenario: 采用参考值并声明来源

- **WHEN** 调用方提交包含参考值的输入并附带 `assumptions`
- **THEN** 结果 `status` SHALL 为 `degraded`
- **AND** `assumed_fields` SHALL 回显字段与依据
- **AND** `assumptions` 非字典类型时 SHALL 返回 400 `invalid_assumptions`

#### Scenario: 单位未核验

- **WHEN** 训练集与旧系统的单位记录缺失
- **THEN** 参考值 SHALL 标注 `unit_status=unverified`
- **AND** 接口与报告 MUST NOT 为其标注具体单位

