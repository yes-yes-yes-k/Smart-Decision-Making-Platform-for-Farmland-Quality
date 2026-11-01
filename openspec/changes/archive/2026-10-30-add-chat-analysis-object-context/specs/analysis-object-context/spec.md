# analysis-object-context Specification (Delta)

## ADDED Requirements

### Requirement: 规范化通用空间分析对象

系统 SHALL 使用统一 `AnalysisObject` 表示当前空间分析对象。对象类型 SHALL 支持 `province`、`city`、`county`、`zone`、`parcel`，并包含后端规范化后的 `id`、`display_name`、`area_code`、`parent_path`、`source` 和 `validated_at`。

客户端提交的展示名称、区域编码和父级路径 SHALL NOT 直接作为可信对象信息；系统 SHALL 通过权威数据解析后生成最终对象。

#### Scenario: 地块对象被规范化

- **WHEN** 客户端提交 `{type: "parcel", id: "P001"}` 且 `parcel_info` 存在该记录
- **THEN** 系统 SHALL 返回规范地块名称、区域编码和省市县父级路径
- **AND** SHALL 将 `validated_at` 记录为本次验证时间

#### Scenario: 通用区域对象被规范化

- **WHEN** 客户端提交已登记的省、市、县或片区对象
- **THEN** 系统 SHALL 从区域目录返回规范名称和父级路径

### Requirement: 会话级分析对象生命周期

系统 SHALL 在单个会话内保存当前分析对象与单调递增的 `context_version`，支持 `set`、`inherit`、`clear`。系统 SHALL NOT 在不同会话之间自动继承对象。

#### Scenario: 设置并继承对象

- **WHEN** 用户在会话中成功设置地块 P001，随后发送未携带新对象的请求
- **THEN** 后续请求 SHALL 继承地块 P001
- **AND** 响应 SHALL 返回当前上下文版本

#### Scenario: 不同会话互不继承

- **WHEN** 用户在会话 A 设置地块 P001，并在会话 B 发起聊天
- **THEN** 会话 B SHALL NOT 自动获得会话 A 的对象

#### Scenario: 清空对象

- **WHEN** 客户端以正确 `expected_version` 提交 `action=clear`
- **THEN** 系统 SHALL 清空当前对象并递增 `context_version`

### Requirement: 分析上下文乐观并发控制

系统 SHALL 使用 `expected_version` 防止旧页面覆盖较新的会话对象。版本冲突 SHALL 返回 HTTP 409，并返回最新版本和对象，不得修改会话状态。

#### Scenario: 旧版本切换被拒绝

- **WHEN** 会话当前版本为 5，客户端以 `expected_version=4` 请求设置新对象
- **THEN** 系统 SHALL 返回 HTTP 409 和 `analysis_context_conflict`
- **AND** 会话对象 SHALL 保持不变

### Requirement: 空间对象精确验证

系统 SHALL 使用类型化解析器精确验证对象存在性和访问权限。地块 SHALL 查询 `parcel_info`；省、市、县、片区 SHALL 查询已登记区域目录。验证失败或依赖不可用时 SHALL NOT 使用默认区域、模拟地块或硬编码指标作为回退对象。

#### Scenario: 对象不存在

- **WHEN** 客户端显式提交未登记对象
- **THEN** 系统 SHALL 返回 HTTP 422 和 `analysis_object_invalid`
- **AND** SHALL NOT 修改会话当前对象

#### Scenario: 对象验证服务不可用

- **WHEN** 对象目录或数据库暂时不可用
- **THEN** 系统 SHALL 返回 HTTP 503 和 `analysis_object_validation_unavailable`
- **AND** SHALL NOT 回退到默认对象

### Requirement: 专业能力空间对象守卫

系统 SHALL 在问题类型识别后、任何 Function Calling 或专业 Agent 执行前，依据能力目录中的 `supported_object_types` 和 `requires_spatial_object` 校验当前对象。

#### Scenario: 地块级计算缺少地块

- **WHEN** 问题路由到要求 `parcel` 的能力，但当前对象为空或只有县级对象
- **THEN** 系统 SHALL 返回 HTTP 200 和 `interaction_state=needs_analysis_object`
- **AND** SHALL 返回 `required_object_types=["parcel"]`
- **AND** SHALL NOT 调用工具、专业 Agent 或总结 LLM
- **AND** SHALL NOT 生成模型执行日志或具体计算数值

#### Scenario: 县域统计接受县级对象

- **WHEN** 问题路由到支持 `county` 的统计能力且当前对象为合法县级对象
- **THEN** 空间对象守卫 SHALL 允许该能力执行

### Requirement: 显式情景试算

系统 SHALL 支持 `calculation_mode=scenario` 的无空间对象试算。只有能力声明 `supports_scenario=true` 且必需输入完整时才可执行。情景试算 SHALL NOT 读取或修改会话当前对象。

#### Scenario: 完整输入执行情景试算

- **WHEN** 用户显式选择 scenario 模式并提供能力要求的全部输入
- **THEN** 系统 SHALL 执行计算
- **AND** 响应 SHALL 包含 `scenario_result=true` 和 `spatial_object=null`
- **AND** SHALL 明确提示结果不对应具体地块

#### Scenario: 情景输入不足

- **WHEN** scenario 模式缺少必需输入
- **THEN** 系统 SHALL 返回 HTTP 200 和 `interaction_state=needs_scenario_inputs`
- **AND** SHALL 列出缺失字段
- **AND** SHALL NOT 执行模型

### Requirement: 结构化结果溯源

每个完成的专业计算响应 SHALL 包含后端生成的 `analysis_context` 和 `provenance`。`provenance` SHALL 包含 `trace_id`、模型标识、模型版本、数据时间或版本、计算时间和实际使用的关键输入。LLM SHALL NOT 生成或覆盖这些结构化字段。

#### Scenario: 空间分析结果可追溯

- **WHEN** 专业模型成功完成真实空间对象计算
- **THEN** 响应 SHALL 标明规范分析对象、实际关键输入、数据时间、模型版本、计算时间和 trace_id
- **AND** 回答标题 SHALL 由后端对象字段确定性生成

#### Scenario: LLM 润色失败

- **WHEN** 最终 LLM 润色失败或返回空内容
- **THEN** 系统 SHALL 保留结构化溯源和专业模型摘要

### Requirement: 流式与非流式上下文一致性

`POST /api/v1/chat/` 与 `POST /api/v1/chat/stream` SHALL 复用相同的上下文解析、空间守卫、情景试算校验和结果溯源服务。

#### Scenario: 同一请求的两种响应模式

- **WHEN** 相同会话、对象和问题分别通过非流式与 SSE 接口提交
- **THEN** 两种接口 SHALL 返回相同的对象版本、交互状态和溯源字段语义
