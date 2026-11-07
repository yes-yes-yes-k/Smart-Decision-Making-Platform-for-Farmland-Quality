## ADDED Requirements

### Requirement: RAG 流式路径报告阶段进度
RAG 流式聊天 SHALL 在检索、重排/知识图谱增强及答案生成的阶段边界提供可供客户端展示的兼容进度事件；既有 token、meta、done、error 事件及其数据结构 MUST 保持兼容。

#### Scenario: 检索阶段较慢
- **WHEN** RAG 检索阶段尚未完成且请求超过配置的进度阈值
- **THEN** SSE SHALL 告知客户端当前处于检索阶段
- **AND** 进度事件 SHALL NOT 包含检索文档正文、内部查询或敏感权限信息

#### Scenario: 检索完成进入生成
- **WHEN** 已完成检索并准备调用 LLM
- **THEN** SSE SHALL 提供生成阶段进度
- **AND** 首个答案 token 到达后客户端 SHALL 转为呈现答案

#### Scenario: 进度与完成事件共存
- **WHEN** 客户端消费新版本流或旧版本流
- **THEN** 客户端 MUST 忽略不认识的可选 progress 事件而继续处理既有事件
- **AND** 完成后的来源及答案 SHALL 与非流式响应保持既有一致性

