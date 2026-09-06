## 为什么

Model-5 在缺少模型特征或运行依赖时，仍会根据固定等级表返回 `manure_dosage`，并用固定比例生成 `potential_increase`；旧酸化 SQLite 还允许保存和读取无来源约束的 `expected_effect` 文本。这些值虽然可能带有降级或模拟标记，仍可被直接调用、持久化或报告模板消费，容易被误认为真实处方或预测结果，因此需要停止生成、停止消费并废弃生产环境中的无依据历史记录。

## 变更内容

- **BREAKING**：Model-5 规则降级不再返回非空 `manure_dosage`、`potential_increase`、`dose` 或 `dose_prediction`；兼容保留字段时值必须为 `null`，并通过统一 `issues`/元数据说明真实模型或可靠数据不可用。
- 保留有机质分级等定性提示，但禁止根据固定等级表输出施用量、提升量或其他看似精确的定量建议。
- 报告上下文、报告模板、聊天投影和单模型投影不得读取或展示规则降级、模拟或来源不可验证记录中的施用量和提升量。
- **BREAKING**：停止创建、写入和读取旧酸化 SQLite `acidification_results` 结果表；其中的 `expected_effect` 及其他历史结果只允许进入迁移备份，不得再作为活动业务数据返回。仍被障碍诊断使用的 `evaluation_results` 和 `diagnosis_results` 不在废弃范围内。
- 将生产环境中旧 `expected_effect` 内容以及可识别的 Model-5 规则降级定量记录标记为废弃数据：先盘点与备份，再从活动查询和报告数据源中隔离，并通过可重复执行的迁移工具清空或迁出不可信字段。
- 历史清理必须保留迁移审计摘要，不得把被废弃内容迁移成新的真实模型结果，也不得影响具备模型版本和可靠来源的 Model-5 真实预测记录。
- 更新接口、报告和运维迁移文档，说明可空字段、历史数据识别条件、回滚边界和生产执行顺序。

## 功能 (Capabilities)

### 新增功能

无。

### 修改功能

- `fertility-ml-prediction`: Model-5 缺少真实模型条件时只返回定性不可用状态，不再用固定规则生成施用量和预期提升量。
- `professional-model-agents`: `OrganicMatterAgent` 的直接调用、聊天和降级路径统一禁止暴露无依据定量建议。
- `thematic-model-output-contract`: Model-5 降级结果的可空字段、问题码和数据来源语义收紧，所有公共投影不得恢复废弃数值。
- `thematic-model-orm`: 规则降级历史记录不得作为有效 Model-5 结果复用，相关持久化字段进入兼容废弃期并需要数据迁移。
- `farmland-acidification-improvement-model`: 旧 SQLite `expected_effect` 停止读写，历史值从活动结果中隔离并废弃。

## 影响

- 代码：`framework/agents/specialized/organic_matter_agent.py`、Model-5 规范化适配与投影、`src/ai_culti_demo/report_context.py`、`src/ai_culti_demo/report_templates.py`。
- 存储：`organic_matter_result` 及关联执行日志、`src/ai_culti_demo/farmland_diagnosis/storage.py`、生产环境旧 `farmland_diagnosis.db` 文件。
- 运维：需要提供生产数据盘点、备份、dry-run、迁移和验证脚本；迁移不得依赖手工 SQL 猜测记录来源。
- API：旧客户端必须接受规则降级结果中的施用量和提升量为 `null`，不得使用本地默认数字回填。
- 报告：历史模拟记录不再显示为“已落库”的有效预期提升结果，可能改为“暂无可靠估计”。
