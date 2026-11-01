## ADDED Requirements

### Requirement: Non-blocking Knowledge Graph Update Trigger

系统 SHALL 在获批公开文献完成原子 chunk 发布后，以非阻塞、可重放且幂等的方式触发知识图谱处理。文献上传、审核、索引和公开检索的完成语义 SHALL NOT 依赖知识图谱抽取是否成功。

#### Scenario: Completed approved literature triggers graph processing
- **WHEN** 获批文献完成全部解析和向量索引并进入 `completed`
- **THEN** 系统 SHALL 持久化一个可重放的图谱处理触发记录，并 SHALL 在提交完成事务后异步消费

#### Scenario: Graph queue is unavailable
- **WHEN** 文献已完成但图谱消费者或抽取服务暂时不可用
- **THEN** 文献 SHALL 保持 `completed` 且公开可检索，触发记录 SHALL 保留以供恢复消费

### Requirement: Document Knowledge Graph Status

文档入库状态响应 SHALL 为文献所有者和管理员返回独立的 `knowledge_graph` 状态对象，至少包含 `state`、最近任务 ID、graph schema 版本、可重试性和脱敏失败码。未授权用户不得通过该状态获知待审候选或私有提交信息。

#### Scenario: Owner polls a completed paper awaiting graph review
- **WHEN** 文献所有者查询一篇已完成索引但图谱候选尚待审核的论文
- **THEN** 响应 SHALL 保持文献 `completed`，并在 `knowledge_graph.state` 返回 `needs_review`

#### Scenario: Document type is not eligible for graph extraction
- **WHEN** 文档不属于配置允许的文献类型或领域
- **THEN** 响应 SHALL 返回 `knowledge_graph.state=not_applicable` 且不得创建图谱任务
