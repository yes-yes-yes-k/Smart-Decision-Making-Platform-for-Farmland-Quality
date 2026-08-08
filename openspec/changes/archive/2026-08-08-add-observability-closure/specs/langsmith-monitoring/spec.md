# langsmith-monitoring Specification

## ADDED Requirements

### Requirement: 本地持久化调用日志

在 LangSmith 远端追踪基础上，系统 SHALL 提供本地持久化调用日志，将路由判定与 Agent 调用记录到本地 JSON 行式文件，与远端 trace 并行覆盖。

#### Scenario: 本地日志与远端 trace 并行

- **WHEN** 一次智能体问答请求完成
- **AND** LangSmith 追踪已启用
- **THEN** 远端生成 trace，同时本地日志文件追加对应记录
- **AND** 本地记录与远端 trace 共享同一 trace_id，便于对账

#### Scenario: 无 LangSmith 时本地日志仍可用

- **WHEN** 未配置 `LANGCHAIN_API_KEY`（远端追踪关闭）
- **THEN** 本地调用日志仍正常写入
- **AND** 主流程不受影响