## ADDED Requirements

### Requirement: Versioned benchmark retirement and provenance
系统 SHALL 保留历史参考、分数及哈希，将不适用的旧金标与银标登记为历史诊断资产；新正式评测 SHALL 使用独立版本并追溯源文件、数据库文档、解析输入及分块。

#### Scenario: Reconcile source directory with database
- **WHEN** 从 `D:\17417\Documents\知识库文献` 建立新评测总体
- **THEN** 系统 SHALL 输出文件哈希和文档/分块映射、独立论文与标准数量、重复及双向未匹配清单，不把 PDF 文件数等同于数据库论文数

#### Scenario: Preserve old benchmark
- **WHEN** 新基准建立或旧标签被发现有争议
- **THEN** 系统 SHALL 新建版本记录修订和适用范围，不覆盖旧标签、分区、输入或分数

### Requirement: Audited document isolation
系统 SHALL 在抽样和标注之前按论文身份、标准修订家族及近重复内容建立隔离组，记录曝光证据；同一组不得跨开发、校准、最终或两条评测轨道。

#### Scenario: Unresolved identity or exposure
- **WHEN** 文档身份、重复关系或历史曝光未解决
- **THEN** 系统 SHALL 阻止该文档进入最终验收，并报告隔离缺口而非静默降低要求

### Requirement: Representative and challenge sampling
系统 SHALL 使用冻结快照、种子和规则抽样，分别记录来源、主题、语言、位置、解析质量及抽样概率或权重；代表性轨和挑战轨 SHALL 分别报告。

#### Scenario: Representative coverage
- **WHEN** 生成目标 300 块、至少 100 组、每组最多 3 块的代表性轨
- **THEN** 系统 SHALL 将 60/240 块划为校准/最终，纳入短文档抽样资格并核验各分区四个位置区间的覆盖，禁止固定遗漏末尾四分位

#### Scenario: Challenge evidence is insufficient
- **WHEN** 最多 200 块挑战轨按 40/160 划分后，某关系未达到 30 个事实或 10 个最终文档组
- **THEN** 系统 SHALL 将该类型标为覆盖不足，保留无关系及困难负例，不把关键词命中视为已证实关系

### Requirement: Source-grounded annotation protocol
系统 SHALL 冻结领域边界与任务掩码，将实体字面片段、位置、类别、规范化和关系证据分开存储，区分原文件、解析输入和题名；不得通过评分时修复 OCR 或拼接跨栏来制造有效跨度。

#### Scenario: Pilot reveals conflicting annotation boundaries
- **WHEN** 开发侧 10 条试标或新控制题发现标准全称、实验步骤或指标介质边界冲突
- **THEN** 系统 SHALL 在批量标注前解决规则冲突并重新验证，保留证据及未知项，不以协议成功替代语义检查

#### Scenario: Independent AI proposals agree incorrectly
- **WHEN** 双份只见原文与手册的标注相互一致
- **THEN** 系统 SHALL 仍对一致项分层来源抽查，报告共同错误和同模型相关性，不宣称专家认证

#### Scenario: Disagreement requires adjudication
- **WHEN** 实体、关系、证据或排除范围有分歧
- **THEN** 系统 SHALL 由独立请求结合来源逐项裁决或明确未知，不采用简单多数票，也不向双标请求泄漏历史参考或候选预测

#### Scenario: Source text and selected position disagree
- **WHEN** 标注器返回实体或证据片段及其原文位置
- **THEN** 系统 SHALL 优先接收可逐字匹配原文的片段，由程序定位其出现位置；重复片段必须明确出现序号。片段无法精确匹配时 SHALL 保留失败，不移动坐标、修复字形或将候选计作有效。

#### Scenario: Reviewer sees materialized candidates
- **WHEN** 请求独立来源裁决
- **THEN** 系统 SHALL 展示候选的逐字表面、所在正文/题名块、原文匹配位置及完整支持窗口，不得只展示字符索引或候选类别。关系支持 SHALL 要求正文连续断言足以判断谓词、端点方向、否定和条件；仅复述端点不构成支持。

#### Scenario: New selector protocol fails controls or semantic review
- **WHEN** 新片段接口、实体/关系边界控制题或已知失败来源试验有系统性无效输出、共同漏项或错误裁决
- **THEN** 系统 SHALL 保留全部原始响应并暂停批量标注和参考发布；只记录未通过结果，不得把格式改进解释为语义正确。

### Requirement: Reproducible backend measurement
系统 SHALL 冻结真实 GraphRAG 后端及适配器、模型、提示、输入、本体、过滤器和评分器版本，在固定参考掩码上计算抽取质量。

#### Scenario: Missing or invalid prediction
- **WHEN** 后端缺失响应、截断、错源、重复或输出非法片段
- **THEN** 系统 SHALL 分别记录完成状态和错误原因，缺失事实计漏报，非法项不计正确，保留固定样本分母，不允许模型排除难题

#### Scenario: Report extraction metrics
- **WHEN** 评测完成
- **THEN** 系统 SHALL 分别报告实体及关系 P/R/F1、证据支持、跨度有效率、完成率、排除率、文档组不确定性区间，并拆分正文/题名、论文/标准及代表性/挑战轨

### Requirement: Calibration before final acceptance
系统 SHALL 先校准再提出数值门槛，包含精确率、证据支持、召回底线、完成率、排除率、支持数及允许错误数；最终运行 SHALL 等待用户确认并冻结规则。

#### Scenario: Final gate is not ready
- **WHEN** 阈值未确认、参考不可靠、关键类型覆盖不足、隔离冲突或后端不可用
- **THEN** 系统 SHALL 报告 inconclusive 并阻止正式通过结论，不依据最终结果降低门槛

#### Scenario: Extraction passes
- **WHEN** 冻结的全部抽取门槛和前置条件满足
- **THEN** 系统 SHALL 仅在声明的抽取范围报告 pass，不推断 GraphRAG 问答或生产图谱已经通过验收

### Requirement: Paused execution and shared budgets
系统 SHALL 遵守用户暂停状态和历史共享调用账本：依据用户明确批准“提高总上限至 2000 万 token”，总计不超过 2000 万 token 或 5000 次尝试，并发不超过 2。阶段额度按照用户最新授权执行；用户已允许在固定项目总额内自动调整阶段额度，调整 SHALL 留痕，不扩大样本规模。原1000万额度及新授权分别归档，更换模型或目录不得重置消耗。

#### Scenario: API is paused or budget cannot reserve request
- **WHEN** 用户未恢复调用、服务不可用或剩余预算无法预留本次输入输出
- **THEN** 系统 SHALL 保存检查点并停止模型调用，不后台续跑、不自动扩容，缺失用量按保守预留记录

#### Scenario: Provider rejects payment
- **WHEN** 服务返回 402
- **THEN** 系统 SHALL 停止调用而非重试；只有瞬时网络或限流等错误允许最多一次重试，且每次尝试均入账
