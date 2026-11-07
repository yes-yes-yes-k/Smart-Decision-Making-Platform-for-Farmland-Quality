## ADDED Requirements

### Requirement: 对话请求端到端阶段计时
系统 SHALL 为非流式和 SSE 对话请求记录可按同一 trace_id 关联的阶段耗时，覆盖请求准备、问题路由与守卫、检索、专业执行/工具调用、LLM 调用、结果持久化及请求完成；每个阶段 SHALL 记录开始/结束或耗时、状态和路由类型。

#### Scenario: RAG 对话分段
- **WHEN** 用户问题进入 RAG 路径
- **THEN** trace SHALL 区分 query rewrite/category、hybrid retrieval、rerank、知识图谱检索（启用时）、来源元数据查询、LLM 首 chunk、LLM 完成和结果持久化耗时

#### Scenario: 专业模型对话分段
- **WHEN** 用户问题进入专业模型路径
- **THEN** trace SHALL 记录守卫、每个 Agent/工具及其重试、专业证据检索、总结 LLM 首 chunk/完成和持久化阶段

#### Scenario: 慢阶段与失败可归因
- **WHEN** 任一阶段超时、重试、失败或耗时超过配置阈值
- **THEN** 系统 SHALL 在 trace 中标注阶段、结果、尝试次数和耗时，并保留原始请求 trace_id
- **AND** 系统 SHALL NOT 将问题正文、提示词、访问令牌或敏感空间对象信息写入指标标签

### Requirement: 区分 TTFT 与端到端响应时间
系统 SHALL 分别度量服务端首个可见 SSE 事件、首个答案 token 和请求完成耗时；客户端 SHALL 分别度量首事件收到、首 token 呈现和完成事件收到时间。

#### Scenario: 服务端先完成同步准备
- **WHEN** SSE 请求在 Response 返回或首次 yield 前执行同步准备
- **THEN** 系统 SHALL 将准备阶段耗时和首事件延迟单独记录

#### Scenario: 端到端时间关联
- **WHEN** 浏览器收到首 token 或 done 事件
- **THEN** 客户端计时 SHALL 通过 trace_id 与服务端阶段数据关联
- **AND** SHALL 区分服务端生成/发送耗时与代理、网络及浏览器呈现耗时

### Requirement: 分路由延迟基线与 SLO
系统 SHALL 分别统计 RAG、单/多专业模型、综合工作流和交互恢复路线的 TTFT、总时长及 p50/p95/p99，并统计错误、超时、重试和各阶段时长分布。

#### Scenario: 路由分布可比较
- **WHEN** 看板或报告计算延迟分位数
- **THEN** 统计 SHALL 按路由和成功/失败状态分组
- **AND** SHALL 避免使用用户 ID、会话 ID等高基数字段作为聚合标签

#### Scenario: SLO 设定依赖基线
- **WHEN** 项目确定延迟目标
- **THEN** 目标 SHALL 标明适用路由、TTFT 或总时长、分位数和测量窗口
- **AND** SHALL 在收集基线前将未知阈值标记为待确认

