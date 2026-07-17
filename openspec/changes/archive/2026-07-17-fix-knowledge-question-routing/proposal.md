# Proposal: fix-knowledge-question-routing

## 问题描述

当用户提出知识性问题（如"耕地质量评价的标准是什么"）时，系统错误地将问题路由到多智能体计算模型（model-4/5/6），返回具体的计算数据（pH=5.5、石灰用量 50.0 kg/亩等），而非从 uploads 文档中检索相关知识回答。

## 根因分析

`framework/agents/nodes.py` 的 `_identify_question_type_keyword` 函数（L121-132）中，当问题包含相关关键词（如"耕地"，relevance >= 0.3）但不匹配任何具体计算类型关键词（type 1/2/3）时，**默认返回 type 1**（酸化评估），导致知识性问题被错误路由到 `execute_models` 路径而非 `rag_chat` 路径。

关键代码：
```python
# L131-132: 问题所在 — 不匹配任何类型时应返回 RAG(0) 而非酸化评估(1)
else:
    return 1, relevance
```

## 修复目标

知识性问题（不匹配具体计算类型的问题）应默认走 RAG 路径（question_type=0），从 uploads 文档检索回答，而非调用计算模型。
