# add-acidification-rf-http-api-and-parcel-prefill 提案

## Why

已归档的 `add-acidification-rf-prediction` 在"酸化 RF 非 HTTP、非离线批处理边界"要求中明确写道：**是否增加外部 HTTP API 由后续独立 change 决定**。本次前端联调需要可调用的接口，因此按该要求另立本 change 承接这个决定，同时把落地过程中核实出的两类事实写入规格：

1. 当前开发库 5491 个地块的指标来源经逐字段统计，`soil_ph`、`organic_matter` 为实测；`exchangeable_hydrogen`、`exchangeable_aluminum`、`cation_exchange_capacity` 全部 5491 条为区域平均回填；`NO3`、`NH4`、`FeO` 没有对应字段。地块级自动组装 RF 输入不具备数据条件。
2. 三个模型文件自身的 `feature_names_in_` 显示特征集并不相同：降酸为 `pH/H/Al/OM/NO3/NH4/CEC`，旱地返酸为 `H/Al/OM/NO3/NH4/CEC`，水田返酸为 `CEC/NH4/NO3/Al/FeO/OM`。按 `data_type` 统一字段集的实现会让水田模型收到错字段与错列序，预测结果不可信。

## What Changes

- 新增 JWT 保护的酸化 RF HTTP 接口：模型清单、预测、地块预填。
- 地块预填只映射已有既定语义的字段，逐字段披露 `provenance`，缺失字段列入 `missing_fields`，不做推测性填充。
- 对缺失字段给出可选参考值：按模型取对应训练集的中位数，附样本量、四分位区间、来源数据集与单位核验状态；参考值不写入预填数据。
- 预测接口支持 `assumptions`，采用参考值时结果强制降级并回显假定字段。
- 特征定义改为按模型维护，输入严格按各模型训练列序构造。
- 新增受控参考值资产 `data/model_artifacts/acidification_rf/reference_values.json`。
- 修改已归档的「酸化 RF 非 HTTP、非离线批处理边界」与「酸化 RF 输入适配与缺失值处理」两条要求，使其与实现一致。

## Capabilities

### New Capabilities

- `farmland-acidification-rf-api`：酸化 RF 的 HTTP 接口、地块输入预填与缺失字段参考值。

### Modified Capabilities

- `farmland-acidification-improvement-model`：补充"本项目自身 HTTP API"与"特征集按模型定义"的边界，修改两条既有要求。

## Impact

- 接口：新增 `/api/v1/acidification-rf/models`、`/api/v1/acidification-rf/predict`、`/api/v1/acidification-rf/parcels/<parcel_id>/prefill`；均需 JWT；不修改任何既有端点。
- 数据：只读 `parcel_info`；新增 `reference_values.json`（由旧系统 `dataset_77/81/94` 只读统计生成）。
- 行为：水田返酸预测的输入字段与列序被修正，此前结果为错序计算；不改变 model-4 过程模型。
- 测试：新增 domain 与路由测试，覆盖字段映射、来源披露、缺失不填充、参考值、假定字段、土地类型错配。

## Non-Goals

- 不做地块级自动映射：`NO3`、`NH4`、`FeO` 无地块字段，不通过插值、均值或训练分布反推补齐。
- 不引入空间插值或三普样点匹配，该方向另立 change。
- 不代理、不转发旧系统 HTTP 服务，不迁移离线 CSV 批处理。
- 不修改 model-4 过程模型，不建立 RF 与 model-4 的业务串联。
- 不实现前端页面，仅提供接口与契约。
