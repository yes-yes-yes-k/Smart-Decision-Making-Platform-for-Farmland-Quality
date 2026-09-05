## 上下文

Model-5 当前存在两条固定规则路径：`OrganicMatterAgent._rule_fallback()` 根据有机质等级表生成 `manure_dosage`，再用 `manure_dosage / 1000 * 1.5` 生成 `potential_increase`；`predict_dose()` 在 RF 模型不可用时也会通过固定阈值返回 `dose`。这些路径虽然标记为 `degraded` 或 `simulated`，但数值仍进入结果对象、执行日志、ORM 结果表和报告模板。

旧 `DiagnosisStorage` 还会创建 `acidification_results` SQLite 表，支持 `expected_effect` 自由文本及一组旧酸化结果的保存和读取。当前在线酸化路径已经按需调用 Python 过程模型，不依赖该结果表，因此继续保留活动读写只会让无来源历史内容被误复用。

生产环境可能同时存在 PostgreSQL 中的 Model-5 历史记录以及多个旧 `farmland_diagnosis.db` 文件。迁移必须避免把无依据值继续作为业务事实，同时保留必要的备份和执行审计。

## 目标 / 非目标

**目标：**

- 规则降级只表达能力不可用或定性分级，不输出任何固定施用量、提升量及其兼容别名。
- 真实 ML/RF 结果继续按现有统一模型输出契约返回，且必须保留模型版本、来源和模拟状态。
- 报告、聊天、单模型 API 和内部投影不再恢复或展示规则降级数值。
- 废弃旧 SQLite `acidification_results` 表及全部历史内容，保留障碍诊断仍需要的其他表。
- 提供可审计、可重复执行、默认 dry-run 的生产历史数据迁移流程。

**非目标：**

- 不重新训练 Model-5 模型，不调整真实模型公式、特征、置信度或性能指标。
- 不废弃整个 `farmland_diagnosis.db`，也不删除 `evaluation_results`、`diagnosis_results` 等仍在使用的数据。
- 不把旧规则值转换成真实预测值，不尝试通过数值模式反推其科学有效性。
- 不在本变更中重新设计 Model-5 的长期有机质响应预测模型。

## 决策

### 1. 规则降级采用空定量结果，而不是较低置信度数字

当 Model-5 没有真实模型输出时，所有施用量和提升量字段必须为 `null`。规范 Model-5 结果继续保持稳定字段集合，使用 `status=degraded` 或 `status=unavailable`、`meta.simulated=true` 和稳定 `issues` 代码说明原因。直接调用的旧字段 `manure_dosage`、`potential_increase`、`dose` 与 `dose_prediction` 在兼容期内可以保留键，但不得保留固定规则值。

选择空值而不是将经验数字降低置信度，是因为置信度不能补足缺失的数据来源、适用周期和模型依据。也不提供恢复旧规则数字的开关。

### 2. 只有真实输入存在时才保留定性有机质分级

如果输入包含可验证的有机质实测值，可以继续用已定义阈值生成“低/中/高”等定性分级；如果连实测值也不存在，禁止用 `MOCK_INPUTS` 默认值生成县域平均含量或等级，结果必须说明缺少输入。

这样既保留有数据依据的定性能力，又避免把默认 `22.0 g/kg` 描述成真实县域或地块现状。

### 3. 公共投影和报告实行来源门禁

规范化层必须把规则路径映射为统一空定量 Schema，并添加 `MODEL5_QUANTITATIVE_UNAVAILABLE`。`public_full`、`chat_compact`、`llm_context`、旧版兼容投影和自然语言答复不得自行补回数字。

报告读取 Model-5 记录时，只有关联执行日志满足 `simulated=false`、`model_version` 非空且来源不是 `rule_fallback`/`fallback`/`unknown`，才可以展示施用量。`potential_increase` 当前没有正式预测模型来源，进入废弃期后不再由报告读取，即使旧行非空也视为不可用。

### 4. Model-5 历史记录按来源废弃，不按数值猜测

迁移通过 `organic_matter_result.execution_id` 关联 `model_execution_log`，将以下记录识别为不可信历史记录：结果行或执行日志标记 `simulated=true`，执行状态为降级/回退，或审计输出的数据来源为 `rule_fallback`、`fallback`、`unknown`。无法证明来源的孤立行按不可信处理。

迁移清空活动库中这些记录的 `organic_fertilizer_dosage`、`potential_increase` 和其他规则定量别名，并清理活动 `output_result` 中对应值；执行日志本身保留，以记录曾发生过一次降级执行。真实模型记录不按数值大小或公式相似度删除。

### 5. 废弃整个旧酸化结果表，而不是只隐藏 expected_effect

新建 SQLite 不再创建 `acidification_results`。`save_acidification()` 和 `get_acidification()` 停止作为可用存储 API；兼容调用必须返回明确的 deprecated/unavailable 状态，而不是访问旧表。当前 `query_acidification()` 继续从 `evaluation_results` 取得必要输入并调用正式 Python 过程模型。

生产迁移在备份后将旧 `acidification_results` 表导出到只读归档，再从活动 SQLite 中删除该表。这样 `expected_effect` 和其他旧结果都不会通过 `SELECT *` 意外回流，同时不会影响 Model-3 使用的评价与障碍诊断数据。

### 6. 迁移工具默认只盘点，显式 apply 才修改

提供项目脚本，使用项目指定 Python 解释器运行。默认模式输出：数据库标识、Schema 版本、待废弃记录数、识别原因分布、备份计划和不可判定项；不得修改数据。`--apply` 模式必须先创建带 SHA-256 校验值的备份，再在事务中执行清理，并写出 JSON 审计摘要。

脚本通过显式数据库连接和配置路径处理生产目标，禁止递归搜索并修改未知 SQLite 文件。重复执行必须幂等；备份失败、Schema 不匹配或记录分类存在未处理错误时必须中止。

### 7. 兼容期保留空键，不保留旧语义

API 和 ORM 列可以在一个兼容发布周期内继续保留 `potential_increase` 等字段，以避免旧客户端或旧数据库立即崩溃，但运行时只写 `null`、只读为不可用。SQLite `acidification_results` 因当前主链路已不依赖，可以在完成备份后直接从活动数据库移除。

## 风险 / 权衡

- [旧客户端假定施用量一定是数字] → OpenAPI 将字段改为可空，迁移说明要求展示“暂无可靠估计”，并增加兼容投影测试。
- [生产执行日志缺少足够来源信息] → 无法证明为真实模型的记录按不可信隔离，dry-run 单独统计“来源不明”数量，不按数值模式猜测。
- [删除 SQLite 旧表影响隐藏调用方] → 先搜索仓库引用并提供 deprecated 兼容方法；生产先部署停止读取版本，再执行表清理。
- [报告结果突然减少] → 明确显示不可用原因，真实模型重新执行后才能恢复定量展示。
- [备份包含已废弃敏感内容] → 备份进入受限只读归档并设置保留期，不作为应用查询数据源。
- [回滚代码后期待旧表存在] → 回滚必须同时恢复数据库备份；禁止只回滚应用版本后静默重建旧结果。

## 迁移计划

1. 部署运行时代码：停止生成规则数字、停止读取历史模拟记录、停止创建和访问 `acidification_results`。
2. 使用生产配置执行迁移脚本 dry-run，审查 PostgreSQL 和每个指定 SQLite 的待废弃数量与来源分类。
3. 在维护窗口执行 `--apply`：生成备份和校验清单，清空 Model-5 不可信活动字段，归档并删除 SQLite `acidification_results` 表。
4. 运行迁移后验证：活动查询不得返回废弃数字，报告不得展示历史 `potential_increase`，正式 ML/RF 记录仍可查询。
5. 观察一个发布周期后，另行决定是否物理删除 PostgreSQL 中已废弃的兼容列。

回滚时先停止新版本流量，再恢复应用和对应数据库备份。回滚仅用于恢复服务，不代表旧数字重新获得业务可信度；恢复后仍必须对外隐藏这些值。

## 开放问题

无。生产数据库目标由部署配置显式提供，迁移脚本不自行猜测路径或连接。
