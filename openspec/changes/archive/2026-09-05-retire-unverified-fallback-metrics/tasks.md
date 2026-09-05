## 1. Model-5 规则降级安全化

- [x] 1.1 移除 `OrganicMatterAgent._rule_fallback` 对默认 `MOCK_INPUTS` 的业务结果补值，只有真实有机质输入存在时才允许生成定性等级
- [x] 1.2 将规则路径中的 `manure_dosage`、`potential_increase`、`dose` 和 `dose_prediction` 改为 `null` 或规范响应中的不可用字段，并删除固定等级施用量与 `1.5` 提升公式
- [x] 1.3 修改 `predict_dose` 的 RF 不可用分支，停止调用固定阈值 `degrade_to_rules` 返回数值，改为显式定量不可用结果
- [x] 1.4 为缺模型、缺依赖、缺输入和预测异常定义稳定原因码，确保状态、`simulated`、数据来源和模型版本语义一致
- [x] 1.5 保持真实 ML/RF 路径的 SOC/Dose、置信度、实际模型版本和来源输出不变

## 2. Agent、统一输出与报告消费

- [x] 2.1 更新 `OrganicMatterAgent.execute/analyze`，使直接调用、单模型接口和聊天链路共享同一安全降级业务结构
- [x] 2.2 更新 `answer_question`，删除默认县域平均值、固定每亩施用量和规则提升量措辞，只返回缺失输入及核验建议
- [x] 2.3 更新 Model-5 规范化适配，为无可靠定量结果添加 `MODEL5_QUANTITATIVE_UNAVAILABLE`，并保持完整业务 Schema 中对应字段为 `null`
- [x] 2.4 检查 `public_full`、`chat_compact`、`llm_context` 和 Schema 1.0 兼容投影，确保任何投影都不会从旧别名或默认值恢复数字
- [x] 2.5 收紧 `report_context` 的 Model-5 历史结果门禁，只接受 `simulated=false`、真实模型来源且模型版本完整的记录
- [x] 2.6 更新报告模板，对不可用施用量和提升量显示“暂无可靠估计”，不再把历史 `potential_increase` 显示为有效预期提升

## 3. 旧酸化 SQLite 结果表退役

- [x] 3.1 修改 `DiagnosisStorage` 初始化逻辑，使新 SQLite 不再创建 `acidification_results` 表
- [x] 3.2 停止 `save_acidification` 和 `get_acidification` 的表读写，并为兼容调用返回明确 deprecated/unavailable 状态
- [x] 3.3 检查 `query_acidification`、专题模型适配和导入路径，确保当前酸化计算只使用评价输入与正式 Python 过程模型
- [x] 3.4 删除活动 API、报告、测试夹具和文档中对 `expected_effect` 的业务字段依赖，不影响 `evaluation_results` 与 `diagnosis_results`

## 4. 历史数据废弃与迁移工具

- [x] 4.1 新增使用项目指定 Python 环境运行的迁移 CLI，要求通过显式 PostgreSQL 连接和 SQLite 路径参数指定目标，默认执行 dry-run
- [x] 4.2 实现 Model-5 历史记录分类，通过 `execution_id` 关联执行日志并按 `simulated`、状态、数据来源和模型版本识别不可信记录及来源不明记录
- [x] 4.3 实现 SQLite dry-run，报告旧 `acidification_results` 表结构、总记录数、非空 `expected_effect` 数量和其他表保护检查
- [x] 4.4 实现 apply 前备份与 SHA-256 校验，备份或 Schema 校验失败时必须在修改前中止
- [x] 4.5 实现 PostgreSQL/当前 ORM 数据清理：清空不可信 Model-5 活动定量字段及活动执行输出中的旧规则值，同时保留执行审计事实
- [x] 4.6 实现 SQLite 清理：将旧酸化结果导出到受限归档后删除 `acidification_results` 表，保持其他业务表和数据不变
- [x] 4.7 生成 JSON 迁移审计摘要，包含目标标识、分类数量、备份校验值、处理时间、执行模式和最终状态
- [x] 4.8 保证迁移重复执行幂等，并编写生产执行、迁移后验证、备份保留和数据库恢复说明

## 5. 接口与运维文档

- [x] 5.1 更新 OpenAPI 和 API 文档，将 Model-5 降级施用量及提升量定义为可空，并说明 `MODEL5_QUANTITATIVE_UNAVAILABLE`
- [x] 5.2 更新 Schema 1.0 迁移说明，要求旧客户端处理 `null` 且禁止本地回填历史固定数字
- [x] 5.3 更新报告文档，说明只有真实模型来源可以展示施用量，`potential_increase` 在新预测模型建立前保持不可用
- [x] 5.4 编写生产历史数据废弃 runbook，明确 dry-run、审批、备份、apply、验证和回滚顺序

## 6. 自动化验证

- [x] 6.1 更新 Model-5 Agent 测试，验证缺输入、DB 未命中和模型不可用时所有规则定量字段均为空且不出现默认有机质均值
- [x] 6.2 增加真实 ML/RF 路径回归测试，验证成功预测、置信度、模型版本和 `simulated=false` 不受影响
- [x] 6.3 增加统一输出和兼容投影测试，验证 `MODEL5_QUANTITATIVE_UNAVAILABLE` 被传播且旧别名不能恢复数值
- [x] 6.4 增加报告回归测试，验证模拟、规则和来源不明历史记录不会显示施用量或预期提升量
- [x] 6.5 增加 SQLite 测试，验证新库不创建旧表、兼容方法不读写、正式酸化按需计算和其他诊断表不受影响
- [x] 6.6 增加迁移工具测试，覆盖 dry-run 无修改、备份失败中止、apply 分类清理、SQLite 表删除、真实记录保留及重复执行幂等
- [x] 6.7 使用 `rg` 检查固定 `MANURE_DOSAGE_RULES`、`/ 1000 * 1.5`、活动 `expected_effect` 读写和报告恢复逻辑，并运行相关定向测试
- [x] 6.8 使用项目指定 Python 解释器运行完整测试集，记录无法执行的外部数据库或部署环境验证，并完成 OpenSpec 严格校验
