# professional-model-agents Specification (Delta)

## ADDED Requirements

### Requirement: 生产聊天禁止无合法对象的地块级具体数值

通过生产聊天链路调用 Model-1 至 Model-5 时，每个专业 Agent SHALL 只接受编排器传入的已验证分析上下文或已通过完整性校验的 scenario 输入。要求地块对象的能力在缺少合法 parcel 对象时 SHALL NOT 使用 MOCK、默认指标、任意县内地块或历史请求残留生成具体结果。

#### Scenario: 酸化问题缺少地块

- **WHEN** 生产聊天中的酸化问题要求地块级用量，但当前无合法 parcel 对象且未选择 scenario 模式
- **THEN** AcidificationRemediationAgent SHALL NOT 使用 `MOCK_INPUTS` 计算 YTK、MBNT、pH 或其他具体数值
- **AND** 请求 SHALL 在进入 Agent 前被守卫转换为 `needs_analysis_object`

#### Scenario: 地块查询失败

- **WHEN** 已提交 parcel 对象但 `parcel_info` 查询失败或验证依赖不可用
- **THEN** 专业 Agent SHALL NOT 将该状态降级为用户输入、CSV、SQLite 或 MOCK 地块结果
- **AND** 系统 SHALL 返回与失败原因对应的对象或服务错误

#### Scenario: 合法情景试算

- **WHEN** 能力支持 scenario 且用户提供全部必需输入
- **THEN** Agent SHALL 使用实际提供的输入执行
- **AND** 输出 SHALL 标记为情景试算而非地块真实结果

### Requirement: 专业能力声明空间对象要求

每个正式专业能力 SHALL 在统一能力目录中声明 `supported_object_types`、`requires_spatial_object`、`supports_scenario` 和 `required_scenario_inputs`。聊天守卫与单模型入口的输入校验 SHALL 复用这些声明。

#### Scenario: 地块模型能力元数据

- **WHEN** 系统读取一个仅支持地块计算的能力
- **THEN** 其 `supported_object_types` SHALL 包含 `parcel`
- **AND** `requires_spatial_object` SHALL 为 true

#### Scenario: 县域统计能力元数据

- **WHEN** 能力支持县域聚合统计
- **THEN** 其 `supported_object_types` SHALL 明确包含 `county`
- **AND** 守卫 SHALL NOT 错误要求 parcel

### Requirement: 专业结果提供实际数据与模型时间信息

专业 Agent 的结构化分析结果 SHALL 提供实际 `model_version`、`data_as_of` 或 `data_version` 以及本次实际关键输入，供统一溯源构建器使用。未知值 SHALL 明确为 null 或 unknown，不得编造时间和版本。

#### Scenario: 地块历史数据计算

- **WHEN** 模型使用某调查年度的地块历史快照
- **THEN** 结构化结果 SHALL 将该调查年度作为 `data_as_of`

#### Scenario: 模型版本不可获得

- **WHEN** Agent 无法确定实际模型版本
- **THEN** SHALL 返回 `model_version=unknown`
- **AND** SHALL NOT使用能力目录版本冒充实际运行版本
