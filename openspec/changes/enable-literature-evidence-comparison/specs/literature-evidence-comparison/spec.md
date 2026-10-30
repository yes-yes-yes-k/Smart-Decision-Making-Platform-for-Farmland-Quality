## ADDED Requirements

### Requirement: Source-bound Research Records

系统 SHALL 为任务相关研究记录保留文献、内容版本、原文位置及措施、指标、结果表述、原文明示的条件；剂量、时长、效应值、单位、否定与不确定性有则保存。缺失 SHALL 明确未知，不由其他文献或常识补齐；同文献不同试验 SHALL 可区分。

#### Scenario: A study omits treatment dose
- **WHEN** 来源未明确给出剂量
- **THEN** 记录 SHALL 保留未知，不将其作为任意剂量匹配，不生成数值

#### Scenario: Results differ across studies
- **WHEN** 两篇文献的条件或结果不同
- **THEN** 系统 SHALL 并列保留各自记录和原文，不合并为无条件因果或自动汇总效应

### Requirement: Candidate Recall Trust Boundary

待审候选 SHALL 仅在既有权限内辅助内部召回和原文定位，保留待审身份。对照内容 SHALL 逐项有当前有效原文支持；首期新增研究断言 SHALL NOT 自动审核或发布为已确认知识。

#### Scenario: A pending candidate is retrieved
- **WHEN** 待审候选帮助定位相关原文
- **THEN** 系统 SHALL 保留其未审核状态，基于原文生成对照，不创建发布事件或增加已发布断言量

#### Scenario: Candidate or source becomes invalid
- **WHEN** 候选被拒绝、证据失效或来源不再可见
- **THEN** 系统 SHALL NOT 将其作为有效候选线索或继续返回失效原文

### Requirement: Explicit Asynchronous Evidence Comparison

文献检索 SHALL 可同步独立返回。跨论文对照 SHALL 单独发起，有界执行并提供明确的运行、失败、取消及失效状态；结果 SHALL 包含逐文献结果、条件与原文位置，不将未检索到解释为事实被否定。

#### Scenario: Comparison is slow or partially fails
- **WHEN** 对照尚未完成或部分处理失败
- **THEN** 普通检索 SHALL 保持可用，对照 SHALL 展示进度及缺口，不冒称结果完整

#### Scenario: Evidence is insufficient
- **WHEN** 来源不足以支持某项结论或请求条件
- **THEN** 对照 SHALL 明确不足或条件未知，不以图谱无边、候选缺失或模型常识补写结论

### Requirement: Versioned Comparison Reuse

对照复用 SHALL 绑定请求条件、来源版本、记录/生成版本、相关候选状态和权限范围，并在返回前验证当前有效性。

#### Scenario: Source changes after result generation
- **WHEN** 文献撤回、正文更新或权限收紧
- **THEN** 旧对照 SHALL 失效或重新验证，不因缓存命中继续泄露或引用失效内容

### Requirement: Separate Capacity and Semantic Coverage

系统 SHALL 分别报告文献容量、抽取覆盖及已发布断言量，并记录真实/合成数据、分块/图/任务规模与资源。十篇候选对照试点 SHALL NOT 等同AGE审核发布试点或十万篇真实语义构图验收。

#### Scenario: Synthetic capacity passes
- **WHEN** 隔离合成负载满足已冻结容量目标
- **THEN** 报告 SHALL 仅证明相应容量，不能增加真实论文抽取覆盖或已发布断言数量

### Requirement: Version-bound Two-stage Research Selection

任务抽取候选 SHALL 先按原文位置枚举研究归属和实体，再引用已校验实体判定关系。原文提及、规范化、关系结果证据 SHALL 分开保存。v2证据 SHALL 同时绑定文件、解析及分块版本；每个选取跨度 SHALL 与指定块精确相等。研究、实体及关系的规则符合 SHALL NOT 被解释为语义支持认证。

#### Scenario: A repeated mention has an explicit position
- **WHEN** 同一块有多处相同实体文字，模型提供其中一处准确跨度
- **THEN** 系统 SHALL 按位置定位该提及，不要求改写名称消歧，不因文字重复删除准确提及

#### Scenario: A relation combines different studies
- **WHEN** 关系端点属于不同study ID或类型方向不符合契约
- **THEN** 编译 SHALL 拒绝该关系，不将同文献误当同试验；其他语义归属问题 SHALL 保持待核实

#### Scenario: A source is reparsed
- **WHEN** 同一原文件使用新的解析及分块版本
- **THEN** 新证据 SHALL 使用新版本身份；无法精确映射的旧跨度 SHALL NOT 自动转移，新候选 SHALL 保持待审
