## ADDED Requirements

### Requirement: External benchmark admission and provenance
系统 SHALL 以外部公开参考作为主评测依据，优先审查AgriNER、Re-DocRED以及独立问答候选QASPER、MultiHop-RAG；每项须登记发布来源、版本、文件哈希、数据许可、标注方法、任务、官方划分和评分器。公开可下载和代码开源 SHALL NOT 自动视为数据已授权。

#### Scenario: Dataset cannot be admitted
- **WHEN** 数据许可、原始标注内容、划分或评分依据无法确认
- **THEN** 系统 SHALL 标记该数据集blocked并登记缺口，不将其作为正式基准或静默更换数据

#### Scenario: Freeze external assets
- **WHEN** 数据通过准入并被下载或引用
- **THEN** 系统 SHALL 保存可重取来源、版本及SHA256，并在许可允许范围内保存只读原始文件，转换记录可追溯到原样本和原文位置

### Requirement: Internal reference scope migration
系统 SHALL 将旧内部500条输入、100条冻结校准参考及最终草稿保留为历史和领域诊断资产；完成内部批量双标 SHALL NOT 是本变更的交付目标或外部评测前置条件。

#### Scenario: Switch primary evaluation workflow
- **WHEN** 当前change转向外部评测
- **THEN** 系统 SHALL 归档旧规范及哈希、使用新的外部产物目录和待办，保持内部参考发布拦截，不恢复内部批量队列或覆盖旧标签

### Requirement: Native tasks and faithful backend adaptation
系统 SHALL 保留外部原生本体、实体簇、关系方向、文档上下文和评分语义，分别声明实体识别、给定实体关系判定及可支持的端到端任务，冻结真实后端与适配器、模型、提示、参数、预算和评分器版本。

#### Scenario: Given entities are part of native task
- **WHEN** 运行Re-DocRED等给定实体任务
- **THEN** 系统 SHALL 单列给定实体关系成绩，不把其当作端到端抽取或穷尽NER的验证，端到端候选输入不包含参考实体或关系

#### Scenario: Production ontology differs
- **WHEN** 外部标签与生产土壤本体无法一一对应
- **THEN** 系统 SHALL 使用明确声明的原生标签任务配置或报告不支持，映射结果另作诊断，不通过改写参考获得原生基准成绩

#### Scenario: Long documents require chunking
- **WHEN** 文档超出后端上下文限制
- **THEN** 系统 SHALL 冻结切块及聚合方式、验证位置和实体簇映射、披露跨块限制，不剔除长文档来抬分

### Requirement: Split isolation and reproducible sampling
系统 SHALL 优先保留官方划分，在被测调用前冻结开发、校准和最终分区、源文档及重复审计结果；有曝光或隔离冲突时不得发布正式通过结论。

#### Scenario: Official split is absent
- **WHEN** 候选数据没有可靠官方划分
- **THEN** 系统 SHALL 在来源身份和近重复分组上确定性划分并记录种子，标明自定义划分；身份不足以证明隔离时仅作诊断

#### Scenario: Pilot or public data exposure
- **WHEN** 选择试跑样本或报告公开集成绩
- **THEN** 系统 SHALL 仅从非最终分区按固定规则试跑，登记本地曝光，不根据候选表现换样或宣称模型训练数据盲测

### Requirement: Native scoring and complete denominators
系统 SHALL 核对官方评分器与适配评分逐项一致；无官方实现时固定并声明补充实现。系统 SHALL 分别报告实体及关系P/R/F1、文档级区间、完成率、排除率、任务覆盖及错误归因，不混合不同本体得分。

#### Scenario: Missing invalid or duplicate predictions
- **WHEN** 预测缺失、截断、错源、重复或跨度非法
- **THEN** 系统 SHALL 保留固定参考分母，计漏报及未完成，非法和重复项不得增加TP，模型不得自行排除样本

#### Scenario: Evidence or reference is incomplete
- **WHEN** 外部任务没有可靠证据真值或发现参考缺陷
- **THEN** 系统 SHALL 明确不可测范围并登记问题，不让模型生成参考证据冒充官方金标，不原地修改官方答案；修订版须单列非官方诊断结果

### Requirement: Independent evidence-grounded QA evaluation
系统 SHALL 使用QASPER及MultiHop-RAG建立独立问答配置，比较真实向量基线与GraphRAG，冻结相同语料、回答模型、生成参数及检索预算，图谱由被测抽取流程建立。

#### Scenario: Prevent answer leakage in graph construction
- **WHEN** 从外部语料构建索引和图谱
- **THEN** 系统 SHALL 仅输入语料，不注入参考问题、答案、实体或关系，保留建图与查询成本及输入追踪

#### Scenario: Score answer evidence and abstention
- **WHEN** 运行问答评测
- **THEN** 系统 SHALL 报告官方答案和证据指标及有依据可计算的Recall@5、引用支持、可答完成率、正确拒答率，保留多答案和题型分母，区分证据否定、资料不足及检索未找到

#### Scenario: Unsupported evidence modality or missing backend
- **WHEN** 后端不能处理图表证据或真实GraphRAG服务不可运行
- **THEN** 系统 SHALL 保留完整任务分母并披露受限子集与覆盖，未完成GraphRAG项为inconclusive，不以模拟结果代替

#### Scenario: Dataset lacks a refusal category
- **WHEN** 原生数据没有错误前提或某类不可答题
- **THEN** 系统 SHALL 标记覆盖缺口，不宣称该类已验收，不将额外合成题混入官方成绩；补充语义裁判须独立请求并记录同模型偏差

### Requirement: Pilot before confirmed final acceptance
系统 SHALL 先完成离线适配和非最终有界试跑，提交按数据集及任务划分的成本、门槛建议、支持数、允许错误数和适用范围；用户确认数值门槛后才运行最终验收。

#### Scenario: Final gate is not ready
- **WHEN** 授权、参考、隔离、覆盖、预算、后端或阈值确认不足
- **THEN** 系统 SHALL 报告inconclusive并保存缺口，不发布pass、不依据最终表现降低门槛

#### Scenario: External benchmark passes
- **WHEN** 某原生任务满足全部冻结门槛
- **THEN** 系统 SHALL 仅对该数据集和任务报告pass，抽取、问答各自验收，不将公开集通过推断为本地千篇论文库或生产图谱通过

### Requirement: Explicit new budget scope and isolated execution
系统 SHALL 按用户2026-10-29新授权建立从零计量的external-benchmark-v1独立账本，本作用域累计不超过2000万token或5000次尝试，并发不超过2；原内部历史账本只读留存且不计入新额度。阶段可按既有授权在本作用域总额内调整并留痕；本次授权后换数据集、模型或目录不得再次重置消耗。所有运行 SHALL 使用隔离评测存储，不修改生产数据库、索引、图谱或公共API。

#### Scenario: Cost exceeds remaining balance
- **WHEN** 试跑估算表明完整计划无法在余额内预留，或下一次请求无法预留
- **THEN** 系统 SHALL 保存进度并报告缺口，不自动增加总额或将缩小后的子集冒称全量完成

#### Scenario: Failed request accounting
- **WHEN** 请求超时、用量缺失、网络/限流失败或402
- **THEN** 系统 SHALL 保守记账，仅瞬时网络/限流最多重试一次且每次入账，402停止；用户暂停或达到上限时不后台续跑
