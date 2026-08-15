# 聊天关键词与专题模型路由说明

本文说明 `/api/v1/chat/` 如何从用户问题识别 `question_type`，以及不同问题类型最终调用哪个专题模型。当前系统使用 6 个正式专题模型；`model-6` 保留为占位能力，外部模型4_v2正式归属 `model-5`。

## 一、整体流程

聊天请求的处理顺序如下：

```text
用户消息
  -> 知识性问题预检
  -> 关键词优先匹配
  -> （未命中关键词时）向量相似度兜底
  -> question_type
  -> QuestionTypeRouter
  -> 单一专题模型或 RAG
```

### 1. 知识性问题优先进入 RAG

以下问题会先被识别为知识性问题，返回 `question_type=0`，进入 RAG，不调用专业模型：

- 以“什么是”“何为”“解释”开头；
- 包含“是什么意思”“什么意思”“定义”“概念”“含义”。

例如：

| 用户问题 | 结果 |
| --- | --- |
| 什么是土壤酸化？ | `type=0`，RAG |
| 耕地质量等级是什么意思？ | `type=0`，RAG |

知识性预检优先于专业关键词。因此，“耕地质量等级是什么意思”虽然包含“质量等级”，仍然不会调用模型2。

### 2. 专业关键词按固定优先级匹配

非知识性问题按以下顺序检查关键词：`type 1 -> type 2 -> type 3 -> type 4 -> type 5 -> type 6`。命中某一类型后立即停止继续匹配。

当前实现使用 Python 的字符串包含判断（`keyword in question`）：

- 不是正则表达式，也不会自动理解同义词；
- 中文关键词不做分词；
- `SOC`、`soc`、`Dose`、`dose` 是代码中分别列出的大小写形式；
- 一条问题同时命中多个类型时，由上面的优先级决定结果。

### 3. 无关键词时的兜底

如果没有命中任何专业关键词，且向量服务可用，系统会使用参考问题进行语义相似度匹配；无法达到匹配条件时按知识性/未路由问题处理。没有向量服务时，未命中关键词的问题返回 `type=0`，进入 RAG 或知识性处理链路。

## 二、关键词、问题类型与模型

| 问题类型 | 常用触发关键词 | 调用模型 | 实际计算/处理 |
| --- | --- | --- | --- |
| `0` | 知识性模式：什么是、何为、解释、是什么意思、定义、概念、含义 | RAG | 知识库检索与问答，不调用专题模型 |
| `1` | 等级稳定、稳定性、稳不稳、稳定吗、退化风险、关注清单、重点关注、临界状态、风险类型、掉级、等级边界安全度、历史变化趋势、持续低质风险等 | `model-1` | 耕地质量稳定性与退化风险评价；通常需要 `parcel_id` 或预计算结果 |
| `2` | 质量等级、等级评价、综合指数、障碍度排序、耕地质量等级、质量评价、等级评定、指标权重等 | `model-2` | 耕地质量等级、综合指数和障碍度评价 |
| `3` | 障碍因素、主要问题、障碍诊断、障碍组合、地块诊断、毛病、障碍等级、哪些问题、有问题、障碍识别、障碍程度、障碍因子等 | `model-3` | 耕地质量主要问题与障碍诊断 |
| `4` | 酸化程度、酸化等级、酸化现状、酸化治理、调理剂、石灰、pH提升、酸化改良等 | `model-4` | 土壤酸化评估、调理剂用量和改良方案计算 |
| `5` | 有机质、有机肥、秸秆、秸秆还田、培肥、培肥方案、有机肥施用、有机质含量等 | `model-5` | 真实/降级的 SOC 与 Dose 有机质培肥预测 |
| `6` | 当前无默认关键词，供显式 `question_type=6` 调用 | `model-6` | 占位能力，不加载肥力 RF |

当前代码中的完整关键词定义位于 [`framework/agents/nodes.py`](../framework/agents/nodes.py) 的 `QUESTION_TYPE_*_KEYWORDS` 常量。

## 三、model-5 与 model-6 边界

`type=5` 只调用 `model-5/OrganicMatterAgent`。提供 `area_code=lechang`、`land_type` 和土壤特征时，Agent 调用 `model_5_execution`：韶关旱地/水田使用对应 RF，非韶关使用全局 ETR；响应包含 `model_version`、`dose_confidence`、`simulated` 和 `fallback` 元数据。外部字段 `SJD/YJZ/TD/TL/TJ/YXL/SXJ/YJZTSZ/YJFLX` 会先转换为规范字段。

`type=6` 保留 `model-6/placeholder` 占位能力，只用于显式类型调用，不加载或调用任何肥力 RF 引擎。

## 四、典型问题示例

| 用户问题 | 识别结果 | 需要注意的输入 |
| --- | --- | --- |
| 我的田耕地质量等级是多少？ | `type=2` -> `model-2` | 提供 `parcel_code`，例如 `A0001` |
| 查询这块地的综合指数和障碍度排序 | `type=2` -> `model-2` | 提供 `parcel_code` |
| 我的田酸化严重吗？ | `type=4` -> `model-4` | 酸化评估所需的地块或结构化指标 |
| 我的田肥力怎么样？ | `type=5` -> `model-5` | 提供 `area_code`、`land_type` 和土壤特征 |
| 这块地到底有什么问题？ | `type=3` -> `model-3` | 障碍诊断所需的 `parcel_id` 或数据 |
| 为了提升有机质，每亩有机肥施多少？ | `type=5` -> `model-5` | 提供规范字段或外部字段后执行真实 RF |
| 显式调用占位模型 | `type=6` -> `model-6` | 仅返回占位结果，不调用 RF |

## 五、关键词冲突与提问建议

由于系统采用“先命中先返回”，同一句话中的多个关键词可能触发优先级更高的类型：

| 问题 | 可能命中的关键词 | 实际类型 |
| --- | --- | --- |
| 我的田质量等级稳不稳？ | `稳不稳`（type 1）和“质量等级”（type 2） | `type=1` -> `model-1` |
| 这块地酸化改良方案怎么做？ | “酸化”“改良方案” | `type=4` -> `model-4` |
| 我的田肥力和有机质怎么样？ | “肥力”和“有机质”（均属于 type 5） | `type=5` -> `model-5` |

建议在提问时明确唯一目标：

- 要查等级、综合指数或障碍度：使用“质量等级”“综合指数”“障碍度排序”；
- 要查提升潜力：使用“提升潜力”“潜力评估”“目标等级”；
- 要查稳定性：使用“退化风险”“等级稳定性”“掉级风险”；
- 要查有机质培肥：使用“有机肥”“秸秆还田”“培肥方案”，避免同时加入“肥力预测”。

## 六、接口中的显式类型

如果调用方已经明确知道问题类型，可以在编排上下文或模型执行接口中直接传入 `question_type`，避免依赖关键词识别：

```json
{
  "model_id": "organic-matter-improvement",
  "question_type": 5,
  "area_code": "lechang",
  "land_type": "upland",
  "indicators": {
    "pH": 6.2,
    "SOCbe": 22.0,
    "TN": 1.1,
    "TP": 0.8,
    "TK": 18.0,
    "AP": 25.0,
    "AK": 80.0,
    "Gap": 5.0,
    "Fertilizer type": 1
  }
}
```

聊天接口仍以用户消息自动识别为主；模型执行接口可以显式传递 `question_type`、`area_code`、`land_type`、规范指标或外部字段。`type=6` 仅保留 model-6 占位路由。

## 七、相关实现与接口文档

- 关键词和问题识别：[`framework/agents/nodes.py`](../framework/agents/nodes.py)
- 类型到 Agent 的路由：[`framework/agents/router.py`](../framework/agents/router.py)
- 正式能力目录：[`framework/agents/capabilities.py`](../framework/agents/capabilities.py)
- 模型2真实计算：[`framework/agents/specialized/potential_agent.py`](../framework/agents/specialized/potential_agent.py)
- 聊天 API：[`docs/api.md`](api.md)
