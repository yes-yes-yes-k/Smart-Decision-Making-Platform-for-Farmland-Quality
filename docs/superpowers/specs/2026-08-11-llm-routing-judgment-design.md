---
comet_change: llm-routing-judgment
role: technical-design
canonical_spec: openspec
---

# Design Doc: LLM 路由判定

## 架构概述

在现有确定性路由流水线（关键词 → embedding 向量 → 排他规则）基础上，新增 LLM 全量初判路径。通过 `ROUTING_MODE` 开关控制，默认 `llm`，可回退 `keyword`。LLM 判定失败时自动回退关键词，排他规则仍作为最终兜底。

## 数据流

```
用户问题
  ├─ _is_knowledge_question? → type 0 (不调 LLM)
  ├─ ROUTING_MODE=llm && LLM 可用?
  │   ├─ YES → _identify_question_type_llm
  │   │         ├─ 动态读 capabilities.py 构造 prompt
  │   │         ├─ llm_service.generate(prompt, temperature=0.0)
  │   │         ├─ _safe_parse_llm_result → 成功?
  │   │         │   ├─ YES → router_method=llm
  │   │         │   └─ NO  → 回退关键词, router_method=keyword
  │   └─ NO → _identify_question_type_keyword, router_method=keyword
  ├─ base_type=0 && embedding? → _identify_question_type_vector
  └─ context? → apply_exclusive_rules
```

## 组件设计

### 1. Config 新增 ROUTING_MODE

```python
# framework/config.py
ROUTING_MODE = os.environ.get("ROUTING_MODE", "llm")  # llm | keyword
```

### 2. _identify_question_type_llm (routing.py 新增)

- 从 `PROFESSIONAL_CAPABILITIES` 动态读取 6 模型能力名称+描述
- 构造 prompt：模型能力列表 + 五维上下文 + JSON 输出格式要求
- 调用 `llm_service.generate(prompt, temperature=0.0)`
- 调用 `_safe_parse_llm_result` 解析
- 返回 `(question_type, relevance, reason)` 或 `None`（回退）

### 3. _safe_parse_llm_result (routing.py 新增)

- `json.loads` 解析 LLM 返回内容
- 校验 `question_type` 字段存在、为 int、0..6 范围
- 任何异常返回 `None`
- 不向调用方抛出异常

### 4. identify_question_type 修改

- `_is_knowledge_question` 预判不变（命中则 type 0，不调 LLM）
- `ROUTING_MODE=llm` 且 LLM 可用时：先 LLM 判定，成功用 LLM 结果，失败回退关键词
- `ROUTING_MODE=keyword` 或 LLM 不可用：走现有关键词/向量路径
- 设置模块级 `_last_router_method`、`_last_llm_reason` 供观测层读取
- 排他规则叠加不变

### 5. observe.py 增强

- 日志 entry 新增字段：`router_method`、`llm_reason`、`llm_duration_ms`
- 从 routing 模块读取 `_last_router_method`、`_last_llm_reason`
- `ROUTING_RESULT_VERSION` 递增至 `v1.2`

### 6. 测试策略

- `tests/test_llm_routing.py`：mock LLM 固定输出，覆盖开关/可用/不可用/解析失败/越界/排他规则叠加
- 现有测试在 `ROUTING_MODE=keyword` 下全部不变
- 混淆矩阵回归脚本支持 mock LLM

### 7. 文档更新

- docx 新增 P10 章节（LLM 路由判断）
- 补充混淆矩阵方法说明与结果表
- P1-P9 模型表同步为 6 模型编号

## 错误处理

| 场景 | 处理 |
|------|------|
| LLM 服务不可用 | 回退关键词，router_method=keyword |
| LLM 返回非 JSON | 回退关键词，记录 llm_failure_reason |
| question_type 越界 | 回退关键词 |
| LLM 超时 | generate() 已有超时配置，超时后回退 |

## 向后兼容

- `ROUTING_MODE=keyword` 完全保留现有行为
- `identify_question_type` 对外签名不变 `(question, context) → (int, float)`
- 排他规则语义不变
