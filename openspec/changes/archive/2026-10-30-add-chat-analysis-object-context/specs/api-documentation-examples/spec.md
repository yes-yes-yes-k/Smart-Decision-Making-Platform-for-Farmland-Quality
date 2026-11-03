# api-documentation-examples Specification (Delta)

## ADDED Requirements

### Requirement: Chat Analysis Context API Documentation

OpenAPI 文档 SHALL 说明聊天接口的 `analysis_context`、`calculation_mode`、`interaction_state` 和 `provenance` 契约，并提供对象设置、继承、清空、情景试算、对象不足、版本冲突、对象无效和验证服务不可用示例。

#### Scenario: 文档展示对象设置请求

- **WHEN** 开发者查看 `POST /api/v1/chat/` 请求 schema
- **THEN** 文档 SHALL 展示 `action=set`、`expected_version` 和 `{type, id}` 对象示例

#### Scenario: 文档展示对象不足响应

- **WHEN** 开发者查看地块级问题缺少对象的响应
- **THEN** 文档 SHALL 展示 HTTP 200、`needs_analysis_object` 和 `required_object_types`
- **AND** 示例 SHALL NOT 包含任何模拟专业数值

#### Scenario: 文档标记旧字段弃用

- **WHEN** 开发者查看 `parcel_id`、`parcel_code`、`area_code`
- **THEN** 文档 SHALL 标记其为过渡期兼容字段
- **AND** SHALL 指引新客户端使用 `analysis_context.object`
