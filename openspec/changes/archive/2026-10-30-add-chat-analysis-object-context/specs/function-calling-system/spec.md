# function-calling-system Specification (Delta)

## ADDED Requirements

### Requirement: 工具调用服从分析对象前置守卫

专业模型 Function Calling SHALL 只在 `AnalysisRequirementGuard` 校验通过后执行。工具默认参数 SHALL 来自已验证 `AnalysisObject` 或已验证 scenario 输入，LLM 和工具执行器 SHALL NOT 自行选择、猜测或补造空间对象。

#### Scenario: 缺少地块时不生成工具调用

- **WHEN** 用户问题需要地块级工具，但当前无合法 parcel 对象
- **THEN** 系统 SHALL 在工具选择前返回 `needs_analysis_object`
- **AND** SHALL NOT 调用 LLM function calling

#### Scenario: 默认工具参数来自规范对象

- **WHEN** 当前上下文包含已验证地块对象 P001
- **THEN** 工具默认 `parcel_id` SHALL 来自该规范对象
- **AND** SHALL NOT 从历史消息正文猜测其他地块

#### Scenario: 工具参数与当前对象冲突

- **WHEN** LLM 生成的工具参数包含与当前规范对象不同的地块标识
- **THEN** 工具执行器 SHALL 拒绝调用并返回对象冲突错误
