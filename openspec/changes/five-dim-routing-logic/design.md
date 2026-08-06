## Context

五维路由在 v1 中（archived change `add-routing-exclusive-rules`）实现为「关键词排他规则 + 五维元数据声明」：`_extract_five_dim_context` 提取了 `scale`（省/县/片区/地块）和 `data_type`（指标数据/评价结果/处方用量），`ProfessionalCapability` 声明了 `analysis_scale`/`data_type` 字段，但 `apply_exclusive_rules` 的 `context` 参数完全未参与路由判定——该参数仅为兼容调用签名而保留。

当前 `apply_exclusive_rules` 仅使用问题文本关键词子串匹配（`EXCLUSIVE_CONDITION_KEYWORDS`），覆盖四组条件：现状评价、酸化调理剂、稳定性风险、质量等级评价。排他规则的 `ExclusiveRule` 结构有 `discriminator` 字段（声明判别维度）但判定逻辑不读取该字段，也不读取 `context` 中的维度值。

v1 设计文档明确记录：「后续如需让分析尺度/数据类型真正影响路由，需退回设计阶段扩展排他规则与测试」。本次变更即完成该升级。

## Goals / Non-Goals

**Goals:**
- 让五维特征（业务任务、分析尺度、数据类型、预期输出、模型依赖）真正参与路由判定
- 新增业务任务关键词表和预期输出关键词表，从问题文本独立提取维度标签
- 扩展 `ExclusiveRule` 判定逻辑，支持以分析尺度/数据类型/业务任务/预期输出作为判别条件
- 让 `apply_exclusive_rules` 的 `context` 参数真正参与路由判定
- 覆盖两组新增判别场景：地块评价 vs 地块诊断（model-1/5）、处方用量区分（model-2/3）
- 保持 `boundary_pending` 降级机制

**Non-Goals:**
- 不改变现有 `question_type` 关键词/向量路由的基础逻辑（作为兜底）
- 不引入机器学习模型做维度提取
- 不修改 API 响应结构
- 不新增独立的模型依赖判定步骤（模型依赖通过排他规则 pair 声明间接参与）

## Decisions

### 决策 A：维度提取扩展
在 `_extract_five_dim_context` 中新增业务任务和预期输出的提取：
- **业务任务**：新增 `BUSINESS_TASK_KEYWORDS` 关键词表，从问题文本提取（如"诊断/毛病"→障碍诊断，"治酸/调理剂"→酸化改良，"有机肥/培肥"→有机质培肥，"稳定性/退化"→稳定性评价，"等级/评价"→质量等级评价）
- **预期输出**：新增 `EXPECTED_OUTPUT_KEYWORDS` 关键词表，从问题文本提取（如"等级/指数"→评价结果，"施多少/每亩"→处方用量，"诊断/问题"→诊断报告）
- 分析尺度和数据类型沿用现有提取逻辑
- **理由**：用户确认业务任务和预期输出均通过新增关键词表提取，不从 data_type 推导

### 决策 B：排他规则判别条件扩展
扩展 `ExclusiveRule` 结构，增加 `dimension_conditions` 字段支持多维度判别：
- 现有 `condition`（问题文本关键词）保留，新增 `dimension_conditions: Dict[str, str]`（如 `{"scale": "地块", "data_type": "评价结果"}`）
- 判定逻辑：一条规则匹配当且仅当 `condition` 匹配（如有）**且**所有 `dimension_conditions` 匹配 context 中对应维度值
- 无 `condition` 的规则仅依赖维度条件；无 `dimension_conditions` 的规则仅依赖关键词（向后兼容）
- **理由**：用户确认扩展排他规则判别条件，维度作为 additional discriminators

### 决策 C：排他规则覆盖新增场景
在 `EXCLUSIVE_RULES` 中新增维度驱动的规则：
- model-1/5：`scale=地块 + data_type=评价结果 + 业务任务=质量等级评价` → model-5
- model-1/5：`scale=地块 + 业务任务=障碍诊断` → model-1
- model-2/3：`data_type=处方用量 + 业务任务=酸化改良` → model-2
- model-2/3：`data_type=处方用量 + 业务任务=有机质培肥` → model-3
- **理由**：用户确认需要地块评价 vs 地块诊断和处方用量区分两组场景

### 决策 D：模型依赖间接参与
模型依赖维度通过排他规则的 `pair` 声明间接参与——规则匹配过程本身就是模型依赖的体现。不新增独立判定步骤。
- **理由**：用户确认通过排他规则间接参与

### 决策 E：boundary_pending 保持
当维度条件无法消解歧义（多条规则命中不同 target，或维度信息不足以区分易混淆对）时，仍返回 `routing_status: "boundary_pending"`。
- **理由**：用户确认保持现有 boundary_pending 降级策略

## Risks / Trade-offs

- **[维度提取精度]** → 关键词表覆盖度有限，可能漏判或误判。缓解：测试集覆盖正例反例 ≥20 条/组
- **[规则冲突复杂度]** → 新增维度条件后规则间可能产生新的冲突路径。缓解：保持 `matched_targets > 1 → boundary_pending` 的冲突处理逻辑
- **[向后兼容]** → 现有纯关键词规则需保持行为不变。缓解：无 `dimension_conditions` 的规则仅依赖关键词，向后兼容
