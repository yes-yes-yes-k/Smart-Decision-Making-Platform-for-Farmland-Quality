## Context

现有路由为两阶段路由（关键词优先 + 向量回退），实现在 `framework/agents/nodes.py` 的 `identify_question_type` 中。路由仅依赖 `question_type`（1-7 与 0=RAG）做 1:1 映射到单一 Agent，缺少对重叠模型之间判别所必需的路由特征。易混淆对包括：
- model-3（障碍诊断）与 model-7（质量等级评价）：共享"等级/评价"语义。
- model-2（提升潜力）与 model-7（质量等级评价）：均涉及"等级提升"。
- model-4（酸化调理剂）与 model-6（有机质投入量）：均涉及"投入量/用量"。

`ProfessionalCapability` 目前仅含 question_type、minimal_inputs 等元数据，无分析尺度（省/县/片区/地块）与数据类型（指标数据/评价结果/处方用量）维度。

## Goals / Non-Goals

**Goals:**
- 将路由升级为五维路由：业务任务、分析尺度、数据类型、预期输出、模型依赖。
- 建立可维护、可版本化的排他规则配置，消除三组易混淆对误选。
- 对未由专业团队确认的重叠关系返回「模型边界待确认」显式降级状态。
- 将路由判定逻辑从 nodes.py 模块化为独立路由模块。
- 扩充三组易混淆对测试集（各 ≥20 条正例与反例）。

**Non-Goals:**
- 不实现工具注册中心（4.2）、统一数据对象与适配器（4.3）、任务编排器（4.4）、调用状态机（4.5）、结果保护 Guardrails（4.6）、可观测性（4.7）、端到端流程（4.8）。
- 不改变 `question_type` 到 Agent 的既有 1:1 映射数据结构，仅在其之上叠加五维特征与排他规则。

## Decisions

### 决策 1：五维路由特征来源与判定顺序
- **判定顺序**：业务任务 → 分析尺度 → 数据类型 → 预期输出 → 模型依赖，逐级缩小候选 Agent 集合。
- **来源**：优先从 `request` 上下文（如 `parcel_id`、`area_code`、`scale`）与问题文本提取；文本无法确定时使用关键词/向量判定当前维度。
- **理由**：保持向后兼容，未显式提供某一维度时沿用现有 question_type 路由作为兜底，避免破坏现有 470 个测试。

### 决策 2：排他规则独立配置文件
- 在 `framework/agents/router.py` 同级新增 `exclusive_rules.py`（或 `routing_rules.py`），以数据驱动方式声明排他规则，规则可版本化、可单测。
- 每条规则声明：易混淆模型对、判别维度、判定条件、命中目标 Agent。
- **理由**：将规则从 nodes.py 硬编码判断中解耦，便于专业团队确认后增量维护。

### 决策 3：「模型边界待确认」降级状态
- 当排他规则无法消解重叠（优先级冲突或未配置）时，路由返回显式降级状态，标记 `routing_status: "boundary_pending"`，而非自行选择。
- 由 `identify_question_type` 返回可识别的降级信号，`route_models` 分支处理，最终在 API 响应中体现。
- **理由**：符合 docx 要求"对未确认的重叠关系系统返回'模型边界待确认'而非自行选择"。

### 决策 4：路由逻辑模块化
- 抽取 `framework/agents/nodes.py` 中 `identify_question_type`、`_identify_question_type_keyword`、`_identify_question_type_vector`、`check_relevance` 至独立路由模块（如 `framework/agents/routing.py`），nodes.py 保留图节点组装。
- **理由**：独立模块便于版本管理、回归测试，符合 docx 4.1 任务 5。

### 决策 5：测试集扩充方式
- 扩充 `tests/test_question_type_keywords.py`，新增三组混淆对测试模块（model-3/7、model-2/7、model-4/6），各 ≥20 条正例 + 反例。
- 正例断言路由到正确 Agent/question_type；反例断言不误选到易混淆对。

## Risks / Trade-offs

- [五维特征可能无法从问题文本提取] → 保持现有 question_type 兜底路由，未提供维度时降级为现状行为。
- [排他规则冲突导致误路由] → 「模型边界待确认」降级状态兜底，禁止静默选择；规则单测覆盖冲突场景。
- [模块化重构破坏现有测试] → 保持 `identify_question_type` 等对外函数签名不变，新增模块仅迁移内部实现。