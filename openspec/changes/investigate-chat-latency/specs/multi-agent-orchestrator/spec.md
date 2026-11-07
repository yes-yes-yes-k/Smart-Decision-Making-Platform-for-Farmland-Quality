## ADDED Requirements

### Requirement: 专业执行向 SSE 报告阶段进度
专业模型路线 SHALL 在阻塞式专业执行、专业证据检索及总结生成的边界发送语义化进度，并在各阶段记录耗时；不得将敏感执行上下文或内部提示暴露给客户端。

#### Scenario: 专业执行尚未产生答案 token
- **WHEN** 专业 Agent 或工具仍在执行
- **THEN** SSE SHALL 在配置阈值内告知客户端处于专业分析阶段
- **AND** 客户端 SHALL 能区分进度消息与答案 token

#### Scenario: 专业结果进入证据检索和总结
- **WHEN** 专业计算完成并开始检索证据或总结生成
- **THEN** trace SHALL 分别记录这些阶段及其耗时
- **AND** SSE SHALL 在阶段切换时提供进度事件

### Requirement: 独立专业 Agent 有界并行
当多个专业 Agent 之间不存在数据依赖且其结果可独立计算时，编排器 SHALL 在配置的有界并发度内并行执行；存在依赖的 Agent SHALL 在前置结果完成后执行。并行执行 MUST 保留当前结果契约、trace 关联和单个 Agent 失败处理语义。

#### Scenario: 多个独立 Agent
- **WHEN** 请求路由到多个互相独立的专业 Agent
- **THEN** 编排器 SHALL 并发执行并记录各 Agent 的排队及运行耗时
- **AND** 最大并发数 SHALL 受配置限制

#### Scenario: Agent 间存在依赖
- **WHEN** 某 Agent 需要另一 Agent 的结果
- **THEN** 编排器 SHALL 在依赖完成后执行该 Agent
- **AND** 汇总 SHALL 保持正确的依赖顺序和结果

#### Scenario: 并发执行部分失败
- **WHEN** 一个 Agent 失败但其他 Agent 成功
- **THEN** 系统 SHALL 保留成功结果并按现有错误语义标记失败 Agent
- **AND** 不得因取消无关任务而丢弃已完成的专业结果

