# api-documentation-examples Specification (Delta)

## ADDED Requirements

### Requirement: 县域诊断安全响应与迁移文档

系统 MUST 在县域诊断 API 文档中说明模板建议、真实定量结果和错误响应的差异，并展示旧 `period`、`improve`、`effect`、`cost` 和问题 `percent` 字段从固定占位值迁移为可空字段的方式。

#### Scenario: 文档展示定量不可用响应

- **WHEN** 开发者查看县域诊断模板回退示例
- **THEN** 文档 MUST 展示 HTTP 200、`status=degraded`、`result_kind=advisory_only` 和定量字段 `null`
- **AND** MUST 展示字段级不可用原因和 `predictive=false`
- **AND** 示例 MUST NOT 包含固定治理周期、提升率、效果、成本或占比

#### Scenario: 文档展示真实定量结果要求

- **WHEN** 开发者查看非空定量字段示例
- **THEN** 文档 MUST 同时展示单位、数据来源、计算方法、计算时间、适用范围以及适用时的模型版本

#### Scenario: 文档说明旧客户端迁移

- **WHEN** 开发者查看县域诊断兼容性说明
- **THEN** 文档 MUST 指引客户端处理 `null`、`degraded` 和空重点区域列表
- **AND** MUST 指引客户端显示“暂无可靠估计”而不是回填本地默认数字
