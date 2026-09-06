## ADDED Requirements

### Requirement: Model-5 不可用定量字段不得被投影恢复

当 Model-5 没有真实模型依据时，规范结果及其所有公共投影 MUST 保持定量字段不可用。`public_full`、`chat_compact`、`llm_context`、审计以外的旧版兼容投影和自然语言生成层禁止根据默认值、旧字段或历史记录恢复施用量和提升量。

#### Scenario: 规范化规则降级结果

- **WHEN** 底层 OrganicMatterAgent 返回规则降级或缺少模型结果
- **THEN** 规范结果 SHALL 使用 `status=degraded` 或 `status=unavailable`
- **AND** `meta.simulated` SHALL 为 `true`
- **AND** `meta.data_source` SHALL 明确为 `rule_fallback`、`unavailable` 或其他非真实模型来源
- **AND** `issues` SHALL 包含 `MODEL5_QUANTITATIVE_UNAVAILABLE`
- **AND** Model-5 Schema 中不可用的预测和施用量字段 MUST 为 `null`

#### Scenario: 生成公共和聊天投影

- **WHEN** 系统从安全降级的 Model-5 规范结果生成 `public_full`、`chat_compact` 或 `llm_context`
- **THEN** 所有投影 MUST 保持对应定量字段为 `null`
- **AND** 投影 MUST NOT 从 `manure_dosage`、`potential_increase`、`dose`、数据库历史记录或本地默认值补造数字

#### Scenario: 请求旧版响应 Schema

- **WHEN** 调用方请求 `response_schema=1.0` 且 Model-5 只有规则降级结果
- **THEN** 兼容投影 MAY 保留旧字段名
- **AND** 旧字段值 MUST 为 `null`
- **AND** 弃用信息 SHALL 说明旧规则数字不再提供
