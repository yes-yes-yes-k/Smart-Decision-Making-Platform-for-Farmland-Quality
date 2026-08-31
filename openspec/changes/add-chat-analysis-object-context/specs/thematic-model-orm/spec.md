# thematic-model-orm Specification (Delta)

## ADDED Requirements

### Requirement: 空间区域目录

系统 SHALL 提供 `spatial_region_catalog` ORM 模型管理省、市、县和片区对象。模型 SHALL 包含 `object_type`（字符串 16）、`object_id`（字符串 64）、`display_name`（字符串 128）、`area_code`（字符串 32）、`parent_object_type`（字符串 16，可空）、`parent_object_id`（字符串 64，可空）、`layer_id`（大整数，可空）、`source`（字符串 32）、`metadata`（JSON）、`enabled`（布尔）和带时区时间戳。

`(object_type, object_id)` SHALL 唯一。地块 SHALL 继续使用 `parcel_info`，不得为会话上下文复制地块业务记录。

#### Scenario: 区域父子关系可解析

- **WHEN** 县级区域记录关联一个市级父对象
- **THEN** 系统 SHALL 能沿父级关系生成完整规范 `parent_path`

#### Scenario: 禁用区域不能作为分析对象

- **WHEN** 区域目录记录 `enabled=false`
- **THEN** 空间对象解析器 SHALL NOT 将其解析为有效当前对象

### Requirement: 模型执行日志记录分析对象与溯源

`model_execution_log` SHALL 记录 `user_id`、`conversation_id`、编排器 `trace_id`、`analysis_object_type`（字符串 16）、`analysis_object_id`（字符串 64）、`area_code`（字符串 32）、`context_version`（整数）、`analysis_context_snapshot`（JSON）、`model_version`（字符串 32）、`data_as_of`（字符串 32，可表达调查年度或 ISO 日期）和 `data_version`（字符串 32）。对象类型、对象 ID、区域编码和执行时间 SHALL 建立索引。

#### Scenario: 地块模型执行日志完整

- **WHEN** 地块级专业模型成功执行
- **THEN** 执行日志 SHALL 记录地块对象、父级路径快照、实际模型版本、数据时间和会话上下文版本
- **AND** `trace_id` SHALL 与聊天响应一致

#### Scenario: 对象不足不生成执行日志

- **WHEN** 请求被空间对象守卫拦截为 `needs_analysis_object`
- **THEN** 系统 SHALL NOT 创建 `model_execution_log`

### Requirement: 多级运行统计可索引

系统 SHALL 能使用执行日志的关系型字段按对象类型、区域编码、模型和时间聚合调用次数与执行状态。完整对象父级路径 SHALL 保存在快照中，业务指标统计 SHALL 继续以 `parcel_info` 和专题结果表为事实来源。

#### Scenario: 按县和模型统计调用

- **WHEN** 运维按县级 `area_code` 和 `agent_id` 查询执行日志
- **THEN** 系统 SHALL 能使用索引字段完成聚合，而无需扫描会话当前 JSON
