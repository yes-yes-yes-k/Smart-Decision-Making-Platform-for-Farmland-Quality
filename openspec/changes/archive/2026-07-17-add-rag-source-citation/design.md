# Design: add-rag-source-citation

## 实现说明

修改 `framework/rag/chain.py` 的 `_build_prompt` 方法，在 prompt 模板中增加引用来源的指示。

### 当前 prompt

```python
return f"""基于以下文档内容，回答用户的问题。如果文档中没有相关信息，请根据你的知识回答，并明确说明信息来源。

文档内容：
{context}

用户问题：
{query}

请以自然、专业的语言回答。"""
```

### 修改后 prompt

在回答要求中增加明确的来源引用指示：要求 LLM 在引用文档内容时标注文档名称（如"根据《文档名》..."）。

```python
return f"""基于以下文档内容，回答用户的问题。如果文档中没有相关信息，请根据你的知识回答，并明确说明信息来源。

文档内容：
{context}

用户问题：
{query}

请以自然、专业的语言回答。回答时必须在引用文档内容处标注来源，格式为"根据《文档名》..."。"""
```

### 影响分析

- 仅影响 RAG 路径（question_type == 0）的回答文本
- 不影响 sources 字段的结构和内容
- 不影响计算模型路径（question_type 1/2/3）
