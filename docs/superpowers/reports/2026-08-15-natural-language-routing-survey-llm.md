---
title: 专题模型自然语言提问路由调研报告（LLM 辅助模式）
generated_at: 2026-08-15
routing_mode: llm (Config.ROUTING_MODE="llm")
llm_model: deepseek-ai/DeepSeek-V3
survey_script: scripts/survey_natural_language_routing_llm.py
data_source: docs/superpowers/reports/natural-language-routing-survey-llm.json
---

# 专题模型自然语言提问路由调研报告（LLM 辅助模式）

## 1. 背景与目标

在上一份报告（keyword 模式）中，我们通过扩充关键词词典实现了 100% 命中。但用户提出关键问题：**实际运行环境默认启用 LLM 辅助路由（`ROUTING_MODE=llm`），LLM 是否真的在帮助路由？命中率如何？**

本报告通过显式启用 LLM 模式重新调研，记录 LLM 实际参与情况、路由方法分布和命中率，并与纯 keyword 模式对比。

## 2. 调研方法

### 2.1 调研脚本

[survey_natural_language_routing_llm.py](file:///d:/17417/Documents/agent_culti_demo/scripts/survey_natural_language_routing_llm.py) — 显式设置 `Config.ROUTING_MODE = "llm"`，保留向量匹配作为回退，记录每次调用的 `router_method`（keyword/vector/llm）。

### 2.2 路由优先级（routing.py:184-211）

```
1. 知识性问题检查 → type=0
2. _identify_question_type_keyword(question) → base_type
3. if Config.ROUTING_MODE == "llm" and LLM_AVAILABLE and llm_service.is_available():
       llm_result = _identify_question_type_llm(question, context)
       if llm_result is not None:  # LLM 返回有效 JSON
           base_type, base_rel = llm_result  # 采用 LLM 结果
           _last_router_method = "llm"
       else:  # LLM 失败/返回 None
           _last_router_method = "keyword"
           if base_type == 0:  # keyword 也未命中
               尝试 vector
   else:
       # keyword 模式：keyword → vector
4. apply_exclusive_rules（排他规则兜底）
```

### 2.3 问题设计

与 keyword 模式报告一致：5 个模型 × 4 类问题（classic/colloquial/with-parcel/boundary）= 32 题（含 5 个边界样本）。

## 3. 调研结果总览

| 维度 | 数据 |
|------|------|
| 模型覆盖 | model-1 ~ model-5 |
| 问题总数 | 32（含 5 个边界样本） |
| LLM 调用次数 | 32 次（每次成功响应，平均耗时 ~2s） |
| **非边界样本命中率** | **23/27 = 85.2%** |
| 路由方法分布 | keyword: 25 次，vector: 7 次，**llm: 0 次** |

### 关键发现

1. **LLM 被调用 32 次，每次 HTTP 响应成功（耗时 1.6-2.8s）**
2. **但 `router_method` 从未记录为 "llm"**，全部回退到 keyword (25) 或 vector (7)
3. **命中率 85.2%，低于纯 keyword 模式的 100%**

这说明 `_identify_question_type_llm` 每次都返回 `None`（LLM 响应无法解析为有效 JSON 或类型越界），导致始终走回退路径。**LLM 调用成功但结果不可用，徒增 ~2s 延迟却未改善路由**。

## 4. 分模型详细结果

### 4.1 model-1：耕地质量稳定性与退化风险评价（type=1）

| 问题类别 | 问题 | 实际 type | 相关度 | 方法 | 判定 |
|---------|------|----------|--------|------|------|
| classic | 查询区域内耕地质量等级整体稳定吗？ | 1 | 1.000 | keyword | 命中 |
| classic | 查询区域内哪些高等级耕地存在退化风险？ | 1 | 1.000 | keyword | 命中 |
| colloquial | 我的这块田质量等级稳不稳？ | 1 | 1.000 | keyword | 命中 |
| colloquial | 这地块会不会掉级 | 1 | 0.667 | keyword | 命中 |
| with-parcel | @001地块 稳定性怎么样，有没有退化风险 | 1 | 1.000 | keyword | 命中 |
| boundary | 全省耕地质量怎么样 | 3 | 0.908 | vector | 边界样本（路由到 model-3） |

**分析**：5/5 非边界命中。keyword 路径完整覆盖。边界样本"全省耕地质量怎么样"经 vector 匹配到 model-3（合理，询问"存在哪些问题"）。

### 4.2 model-2：耕地质量等级评价（type=2）

| 问题类别 | 问题 | 实际 type | 相关度 | 方法 | 判定 |
|---------|------|----------|--------|------|------|
| classic | 我的田耕地质量等级是多少？ | 2 | 1.000 | keyword | 命中 |
| classic | 查询地块的综合指数和障碍度排序 | 2 | 1.000 | keyword | 命中 |
| colloquial | 这块地质量怎么样 | 2 | 0.820 | **vector** | 命中（向量匹配） |
| colloquial | 这块地肥力怎么样 | 2 | 0.761 | **vector** | 命中（向量匹配） |
| colloquial | 这块地肥力如何 | 2 | 0.765 | **vector** | 命中（向量匹配） |
| with-parcel | @001地块 帮我看看等级评价 | 2 | 1.000 | keyword | 命中 |
| boundary | 今天天气怎么样 | 0 | 0.532 | keyword | 边界样本（正确落入 RAG） |

**分析**：6/6 非边界命中。3 个口语化问题经 **vector 路径**命中（keyword 未命中"质量怎么样"等口语词？需核实），相关度 0.76-0.82 高于阈值 0.75。

### 4.3 model-3：耕地质量主要问题与障碍诊断（type=3）

| 问题类别 | 问题 | 实际 type | 相关度 | 方法 | 判定 |
|---------|------|----------|--------|------|------|
| classic | 全省耕地质量存在哪些问题？ | 3 | 1.000 | keyword | 命中 |
| classic | 查询区域内耕地主要障碍因素有哪些 | 3 | 1.000 | keyword | 命中 |
| colloquial | 我这块地到底有啥毛病？ | 3 | 0.667 | keyword | 命中 |
| colloquial | 这块地有什么问题 | 3 | 0.901 | **vector** | 命中（向量匹配） |
| with-parcel | @001地块 帮我诊断一下有哪些障碍 | **0** | 0.690 | keyword | **❌ 未命中（落入 RAG）** |
| boundary | 全省耕地质量怎么样 | 3 | 0.908 | vector | 边界样本（路由到 model-3） |

**分析**：4/5 非边界命中。**1 个 MISS**："@001地块 帮我诊断一下有哪些障碍" → type=0。keyword 路径未命中"诊断一下"（尽管 keyword 模式报告中新增了该词，但 LLM 模式下回退路径似乎未采用新增词典？需核实），vector 也未命中。

### 4.4 model-4：耕地土壤酸化改良（type=4）

| 问题类别 | 问题 | 实际 type | 相关度 | 方法 | 判定 |
|---------|------|----------|--------|------|------|
| classic | 查询区域内农用地土壤酸化程度如何？ | 4 | 1.000 | keyword | 命中 |
| classic | 我的田酸化了，pH是5.0，我要施加多少碱性调理剂可以治理好？ | 4 | 1.000 | keyword | 命中 |
| colloquial | 我的田酸化严重吗？ | 4 | 0.667 | keyword | 命中 |
| colloquial | 这地酸了怎么治 | **0** | 0.691 | keyword | **❌ 未命中（落入 RAG）** |
| with-parcel | @001地块 酸化了吗，要下多少石灰 | 4 | 1.000 | keyword | 命中 |
| boundary | 我的田质量怎么样 | 1 | 0.803 | vector | 边界样本（路由到 model-1） |

**分析**：4/5 非边界命中。**1 个 MISS**："这地酸了怎么治" → type=0。keyword 未命中"酸了"（新增口语词），vector 也未命中。

### 4.5 model-5：耕地土壤有机质培肥提升（type=5）

| 问题类别 | 问题 | 实际 type | 相关度 | 方法 | 判定 |
|---------|------|----------|--------|------|------|
| classic | 为了提升耕地土壤有机质，有机肥或者秸秆每亩施用量多少？ | 5 | 1.000 | keyword | 命中 |
| classic | 全省耕地土壤有机质含量如何？ | 5 | 1.000 | keyword | 命中 |
| colloquial | 提高有机质 | 5 | 0.333 | keyword | 命中 |
| colloquial | 希望提升土壤肥力 | **0** | 0.677 | keyword | **❌ 未命中（落入 RAG）** |
| colloquial | 帮我出个施肥方案 | **0** | 0.666 | keyword | **❌ 未命中（落入 RAG）** |
| with-parcel | @001地块 有机质太低了，想培肥 | 5 | 1.000 | keyword | 命中 |
| boundary | 我的田酸化严重吗 | 4 | 0.667 | keyword | 边界样本（正确路由到 model-4） |

**分析**：4/6 非边界命中。**2 个 MISS**："希望提升土壤肥力"和"帮我出个施肥方案" → type=0。keyword 未命中新增的"提升土壤肥力"、"施肥方案"等口语词。

## 5. 关键问题分析

### 5.1 LLM 调用 32 次但 `router_method` 从未为 "llm"

**证据**：
- 运行日志显示 32 次 `[LLM] 调用成功 - 耗时: 1.6-2.8s`
- JSON 数据显示 `router_method` 分布：keyword=25，vector=7，**llm=0**

**结论**：`_identify_question_type_llm` 每次都返回 `None`（LLM 响应无法解析为有效 JSON 或类型越界），导致始终走回退路径。**LLM 调用成功但结果不可用**。

**影响**：
- 每次路由增加 ~2s 延迟（LLM 调用耗时）
- 命中率未提升（反而因回退路径差异低于纯 keyword 模式）

### 5.2 命中率对比：LLM 模式 85.2% vs keyword 模式 100%

| 模式 | 非边界命中率 | 4 个 MISS 问题 |
|------|-------------|----------------|
| keyword 模式（上一轮报告） | 27/27 = 100% | 0 |
| **LLM 模式（本报告）** | **23/27 = 85.2%** | **4** |

**4 个 MISS 问题**：
1. "@001地块 帮我诊断一下有哪些障碍"（model-3）
2. "这地酸了怎么治"（model-4）
3. "希望提升土壤肥力"（model-5）
4. "帮我出个施肥方案"（model-5）

**根因推测**：上一轮 keyword 模式报告中新增的口语关键词（"诊断一下"、"酸了"、"提升土壤肥力"、"施肥方案"）在 LLM 模式下未被 keyword 路径采用。可能原因：
- LLM 模式下，`_identify_question_type_keyword` 的 base_type 命中后，LLM 返回 None 覆盖了 base_type？
- 或 keyword 路径在 LLM 模式下的执行顺序与纯 keyword 模式不同

**需进一步调查**：routing.py:184-198 的回退逻辑是否正确保留了 keyword 的 base_type。

### 5.3 边界样本分析

5 个边界样本表现：

| 边界问题 | 实际路由 | 方法 | 是否合理 |
|---------|---------|------|---------|
| 全省耕地质量怎么样（model-1 边界） | → model-3 | vector | 合理：询问"存在哪些问题" |
| 今天天气怎么样（model-2 边界） | → RAG (type=0) | keyword | 合理：无关问题落入 RAG |
| 全省耕地质量怎么样（model-3 边界） | → model-3 | vector | 合理：同上 |
| 我的田质量怎么样（model-4 边界） | → model-1 | vector | 合理：询问稳定性 |
| 我的田酸化严重吗（model-5 边界） | → model-4 | keyword | 合理：酸化问题路由到酸化模型 |

**边界样本无干扰**：5 个边界样本均未误路由到非目标专业模型或误落入 RAG。

## 6. 路由方法分布统计

| 路由方法 | 次数 | 占比 | 说明 |
|---------|------|------|------|
| keyword | 25 | 78.1% | 关键词匹配命中 |
| vector | 7 | 21.9% | 向量相似度匹配命中（阈值 0.75） |
| **llm** | **0** | **0%** | **LLM 初判从未被采用** |

**关键结论**：在本次调研中，LLM 辅助路由**完全没有发挥作用**。所有路由都由 keyword 和 vector 完成，LLM 仅增加了 ~2s/次的延迟。

## 7. 验证证据

### 7.1 调研脚本执行

命令：`python scripts/survey_natural_language_routing_llm.py`
退出码：0
输出摘要：
```
Hit rate (non-boundary): 23/27 = 85.2%
Router methods used: {'keyword': 25, 'vector': 7}
```

### 7.2 LLM 调用日志（32 次）

```
[LLM] 调用开始 - 模型: deepseek-ai/DeepSeek-V3, 提示长度: 417-443, 历史消息: 0
[LLM] 调用成功 - 耗时: 1.6-2.8s
```
（共 32 次调用，每次成功响应）

### 7.3 JSON 数据产物

[natural-language-routing-survey-llm.json](file:///d:/17417/Documents/agent_culti_demo/docs/superpowers/reports/natural-language-routing-survey-llm.json) — 32 条完整调研记录（含 router_method 字段）

## 8. 结论

### 8.1 LLM 辅助路由的实际效果

**问题"LLM 辅助下的路由结果如何？"的回答：**

1. **LLM 被调用 32 次，每次 HTTP 响应成功**（耗时 1.6-2.8s/次）
2. **但 LLM 结果从未被采用**（`router_method` 全部是 keyword/vector，llm=0）
3. **命中率 85.2%**（23/27），低于纯 keyword 模式的 100%
4. **4 个口语化提问未命中**：诊断请求、酸化口语、培肥口语

### 8.2 LLM 路由的问题

LLM 调用成功但 `_identify_question_type_llm` 返回 None，导致：
- **性能损耗**：每次路由增加 ~2s LLM 调用延迟
- **命中率未提升**：反而因回退路径与纯 keyword 模式不一致，命中率下降 14.8%
- **非确定性**：LLM 响应质量不稳定，可能导致不同运行结果不同

### 8.3 建议

1. **排查 LLM 返回 None 的根因**：检查 `_identify_question_type_llm` 的 JSON 解析逻辑，确认 LLM 返回的格式是否符合预期
2. **评估 LLM 路由的 ROI**：若 LLM 结果不可用，应考虑关闭 LLM 模式（`ROUTING_MODE=keyword`）以避免延迟
3. **统一 keyword 词典**：确保 LLM 模式下的 keyword 回退路径与纯 keyword 模式使用相同的关键词词典
