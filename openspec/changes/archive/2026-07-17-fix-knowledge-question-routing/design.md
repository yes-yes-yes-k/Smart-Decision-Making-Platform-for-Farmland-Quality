# Design: fix-knowledge-question-routing

## 修复方案

修改 `framework/agents/nodes.py` 中 `_identify_question_type_keyword` 函数的默认返回值：将不匹配任何具体计算类型时的默认返回从 `type 1`（酸化评估）改为 `type 0`（RAG）。

### 修改点

**文件**：`framework/agents/nodes.py`
**函数**：`_identify_question_type_keyword`（L121-132）

将 L131-132 的：
```python
else:
    return 1, relevance
```

改为：
```python
else:
    return 0, relevance
```

### 影响分析

- **正向影响**：知识性问题（如"耕地质量评价的标准是什么"）将正确路由到 RAG 路径，从 uploads 文档检索回答
- **风险评估**：之前默认返回 type 1 意味着不匹配关键词的相关问题都会走酸化评估。改为 type 0 后这些问题走 RAG，行为更合理——缺乏具体计算意图的问题应走知识检索而非计算
- **不影响的情况**：明确包含计算类型关键词的问题（type 1/2/3）不受影响，仍走对应计算路径
