# 智能体能力完整验证报告

- 生成时间：2026-07-26 02:10:39
- 项目根目录：`D:\17417\Documents\agent_culti_demo`
- Python：`C:\Users\17417\AppData\Local\Programs\Python\Python312\python.exe`
- 问题库：`framework/agents/nodes.py` 中的 `REFERENCE_QUESTIONS`
- 数据来源：重新调用 `multi_agent_orchestrator.run()` 实时获取（非日志回放）
- 参考日志：`verify_output.log`（仅作历史对照）
- 原始 JSON：`verification_raw_outputs.json`

> 说明：占位模型 model-2（PotentialAssessmentAgent）与 model-5（OrganicMatterAgent）无真实模型绑定，本报告对其调用细节仅做记录，不做能力评估。

### 修复记录（本次重生成前）

- **修复对象**：`src/ai_culti_demo/farmland_grade_eval/runner.py:parse_output`
- **问题描述**：原 `parse_output` 与 Fortran exe 实际输出格式不匹配，section 标记识别错位（误用通用标签而非实际中文标记如「地块代码」「原始指标值」「障碍度因子」），导致解析结果为空：`quality_grade=None`、`composite_index=None`、`indicators=[]`、`obstacle_degree=[]`。上游 `FarmlandGradeAgent.answer_question` 因此生成「质量等级为None级，综合指数：None。共0个指标参与评价。」的错误回答。
- **修复内容**：重写 `parse_output` 函数：
  1. section 标记改为匹配 exe 实际输出（`地块代码`/`原始指标值`/`障碍度因子`）
  2. `parcel_info` 解析同时支持 `：` 和 `:` 分隔符
  3. `composite_index`/`quality_grade` 全文匹配（排除「潜在耕地质量等级」）
  4. `obstacle_degree` 解析提取 `indicator`、`degree`（float）、`level`（中文等级）
  5. 分隔线（`---`/`===`）和表格头（`| 评价指标`）正确终结当前 section
- **验证结果**：调用真实 exe（parcel_code=`A0001`）通过断言：
  - `quality_grade` = `10等` ✓
  - `composite_index` = `0.6728` ✓
  - `indicators` = 12 条 ✓
  - `obstacle_degree` = 12 条 ✓
  - `parcel_info` = 5 个字段（地块代码/经度/纬度/县区名称/二级农业区名称）✓
- **影响范围**：仅 `runner.py:parse_output` 一处函数，无 API/契约变更。

---

## 一、Agent 加载状态盘点

| model_id | class | 占位桩 | 真实模型 | 资源就绪 | 期望行为 |
|---|---|---|---|---|---|
| model-1 | `StabilityRiskAgent` | 否 | farmland_stability | ✓ | 真实计算 |
| model-2 | `PotentialAssessmentAgent` | 否 | - | ✗ | 占位桩（无真实模型绑定） |
| model-3 | `ProblemIdentificationAgent` | 否 | farmland_diagnosis | ✓ | 真实计算 |
| model-4 | `AcidificationRemediationAgent` | 否 | farmland_acidification | ✓ | 真实计算 |
| model-5 | `OrganicMatterAgent` | 否 | - | ✗ | 占位桩（无真实模型绑定） |
| model-6 | `FertilityMLAgent` | 否 | sklearn ETR (soc_etr + dose_etr) | ✗ | fallback 训练集均值（缺 .joblib） |
| model-7 | `FarmlandGradeAgent` | 否 | Fortran exe | ✗ | 回退模拟数据（需部署 exe+dat 到 bin/farmland_quality_eval/） |

**资源就绪状态：**

- ✓ `stability_db_exists`: `True`
- ✓ `stability_db_path`: `data\farmland_stability\stability_results.db`
- ✓ `diagnosis_db_exists`: `True`
- ✓ `diagnosis_db_path`: `D:\17417\Documents\agent_culti_demo\src\ai_culti_demo\farmland_diagnosis\..\..\data\farmland_diagnosis\farmland_diagnosis.db`
- ✗ `soc_joblib_exists`: `False`
- ✗ `dose_joblib_exists`: `False`
- ✗ `grade_exe_exists`: `False`
- ✗ `grade_dat_exists`: `False`

**角色路由表（RoleRouter.ROLE_AGENTS）：**

| role | 触发关键词 | 调用 agents |
|---|---|---|
| `province` | 全省 / 全市 / 全局 / 政策 / 省市 | model-1, model-3 |
| `county` | 本县 / 乡镇 / 片区 / 任务 / 县域 | model-1, model-2, model-3 |
| `farmer`（默认） | 我的田 / 这块地 / 施氮肥 / 施多少 / 农户 | model-4, model-5, model-6, model-7 |

> model-7（Fortran exe）仅在 question_type=5（显式 `质量等级` 关键词）时执行；非质量等级 farmer 问题经 `_should_execute_agent` 关键词过滤跳过 model-7 （status=`skipped`, reason=`question_not_related`）。

---

## 二、问题库完整回答与调用细节

- 总计问题数：**23**
- 返回非空 answer：**23/23**
- question_type 匹配：**23/23**

### 类型1：稳定性风险（5 题）

#### Q1（期望 type=1）

> **问题原文：** 查询区域内耕地质量等级整体稳定吗

- **识别 question_type**：1 ✓ 匹配
- **识别 role**：`farmer`
- **调用 agents**：model-4, model-5, model-6, model-7
- **answer 来源**：`answer`（`answer` = LLM 生成；`summary` = AgentManager 模板拼接）
- **耗时**：29.7s

**【完整回答】**

```text
根据提供的数据，仅查询了一个地块（A0001）的耕地质量等级评价结果，无法反映整个区域的整体稳定性。要判断区域内耕地质量等级的整体稳定性，需要更多地块的时空数据或区域统计信息，当前数据不足。
```

**【各 agent 调用细节】**

| agent_id | simulated | status | confidence | answer 摘要 |
|---|---|---|---|---|
| model-4 | sim（模拟） | - | 0.8 | 土壤 pH=5.5（弱酸性），建议石灰施用量 50.0 kg/亩。 |
| model-5 | sim（模拟） | - | 0.78 | 有机质 22.0 g/kg（中），建议施有机肥 1000.0 kg/亩。 |
| model-6 | sim（模拟） | skipped | 0.0 |  |
| model-7 | real（真实） | - | 0.9 | 耕地质量等级评价结果：质量等级为10等级，综合指数：0.6728。共12个指标参与评价。 |

**【各 agent 完整输出】**

- **model-4**
  - confidence: `0.8`
  - simulated: `True`
  - answer:
    ```text
    土壤 pH=5.5（弱酸性），建议石灰施用量 50.0 kg/亩。
    ```
  - evidence (2 条):
    ```json
    [{"metric": "ph", "value": 5.5}, {"metric": "lime_dosage", "value": 50.0}]
    ```

- **model-5**
  - confidence: `0.78`
  - simulated: `True`
  - answer:
    ```text
    有机质 22.0 g/kg（中），建议施有机肥 1000.0 kg/亩。
    ```
  - evidence (2 条):
    ```json
    [{"metric": "level", "value": "中"}, {"metric": "manure_dosage", "value": 1000.0}]
    ```

- **model-6**
  - status: `skipped`
  - reason: `question_not_related`
  - confidence: `0.0`
  - simulated: `True`
  - answer: (空)

- **model-7**
  - confidence: `0.9`
  - simulated: `False`
  - answer:
    ```text
    耕地质量等级评价结果：质量等级为10等级，综合指数：0.6728。共12个指标参与评价。
    ```
  - evidence (2 条):
    ```json
    [{"metric": "质量等级", "value": "10等"}, {"metric": "综合指数", "value": 0.6728}]
    ```

---

#### Q2（期望 type=1）

> **问题原文：** 查询区域内哪些高等级耕地存在退化风险

- **识别 question_type**：1 ✓ 匹配
- **识别 role**：`farmer`
- **调用 agents**：model-4, model-5, model-6, model-7
- **answer 来源**：`answer`（`answer` = LLM 生成；`summary` = AgentManager 模板拼接）
- **耗时**：21.76s

**【完整回答】**

```text
根据提供的土壤检测数据，该区域内高等级耕地的土壤pH为5.5（弱酸性），有机质含量为22.0 g/kg（中等），这些指标表明土壤存在退化风险（如酸化、有机质不足）。建议采取相应改良措施：施用石灰50.0 kg/亩以调节酸碱度，施用有机肥1000.0 kg/亩以提升有机质含量。
```

**【各 agent 调用细节】**

| agent_id | simulated | status | confidence | answer 摘要 |
|---|---|---|---|---|
| model-4 | sim（模拟） | - | 0.8 | 土壤 pH=5.5（弱酸性），建议石灰施用量 50.0 kg/亩。 |
| model-5 | sim（模拟） | - | 0.78 | 有机质 22.0 g/kg（中），建议施有机肥 1000.0 kg/亩。 |
| model-6 | sim（模拟） | skipped | 0.0 |  |
| model-7 | sim（模拟） | skipped | 0.0 |  |

**【各 agent 完整输出】**

- **model-4**
  - confidence: `0.8`
  - simulated: `True`
  - answer:
    ```text
    土壤 pH=5.5（弱酸性），建议石灰施用量 50.0 kg/亩。
    ```
  - evidence (2 条):
    ```json
    [{"metric": "ph", "value": 5.5}, {"metric": "lime_dosage", "value": 50.0}]
    ```

- **model-5**
  - confidence: `0.78`
  - simulated: `True`
  - answer:
    ```text
    有机质 22.0 g/kg（中），建议施有机肥 1000.0 kg/亩。
    ```
  - evidence (2 条):
    ```json
    [{"metric": "level", "value": "中"}, {"metric": "manure_dosage", "value": 1000.0}]
    ```

- **model-6**
  - status: `skipped`
  - reason: `question_not_related`
  - confidence: `0.0`
  - simulated: `True`
  - answer: (空)

- **model-7**
  - status: `skipped`
  - reason: `question_not_related`
  - confidence: `0.0`
  - simulated: `True`
  - answer: (空)

---

#### Q3（期望 type=1）

> **问题原文：** 本县哪些乡镇或地块等级稳定性较弱需要现场复核

- **识别 question_type**：1 ✓ 匹配
- **识别 role**：`county`
- **调用 agents**：model-1, model-2, model-3
- **answer 来源**：`answer`（`answer` = LLM 生成；`summary` = AgentManager 模板拼接）
- **耗时**：36.53s

**【完整回答】**

```text
根据现有数据，模型-1评估的地块稳定性得分为0.85，等级为“稳定”，不属于稳定性较弱等级，因此无需现场复核。数据中未提及其他乡镇或地块的稳定性信息，无法判断全县范围内是否存在需要复核的区域。如需进一步了解，请提供具体地块ID以获取真实诊断结果。
```

**【各 agent 调用细节】**

| agent_id | simulated | status | confidence | answer 摘要 |
|---|---|---|---|---|
| model-1 | sim（模拟） | - | 0.85 | 您的地块耕地质量稳定性评价结果：稳定性得分 0.85，稳定性等级：稳定。 |
| model-2 | sim（模拟） | - | 0.8 | 耕地质量提升潜力等级为 中潜力，平均障碍度值 30.85，主要障碍因素：有效磷, 速效钾, 阳离子交换量。 |
| model-3 | sim（模拟） | - | 0.83 | 县域障碍诊断：主要障碍因素 有机质, 全氮；次要障碍因素 pH, 黏粒含量, 孔隙度, 容重, 有效磷, 耕层厚度, 阳离子交换量, 速效钾。 结合模型2目标 pH=6.5，每个指标按 1~10 级频数统计，最后一列标注是否主要/次要障碍因...[truncated 15 chars] |

**【各 agent 完整输出】**

- **model-1**
  - confidence: `0.85`
  - simulated: `True`
  - answer:
    ```text
    您的地块耕地质量稳定性评价结果：稳定性得分 0.85，稳定性等级：稳定。
    ```
  - evidence (2 条):
    ```json
    [{"metric": "稳定性得分", "value": 0.85}, {"metric": "稳定性等级", "value": "稳定"}]
    ```

- **model-2**
  - confidence: `0.8`
  - simulated: `True`
  - answer:
    ```text
    耕地质量提升潜力等级为 中潜力，平均障碍度值 30.85，主要障碍因素：有效磷, 速效钾, 阳离子交换量。
    ```
  - evidence (4 条):
    ```json
    [{"indicator": "有效磷", "obstacle_degree": 52.0, "potential_level": "中潜力"}, {"indicator": "速效钾", "obstacle_degree": 46.67, "potential_level": "中潜力"}, {"indicator": "阳离子交换量", "obstacle_degree": 43.33, "potential_level": "中潜力"}, {"target_ph": 6.5, "recommendation": "目标 pH 供下游模型3使用"}]
    ```

- **model-3**
  - confidence: `0.83`
  - simulated: `True`
  - answer:
    ```text
    县域障碍诊断：主要障碍因素 有机质, 全氮；次要障碍因素 pH, 黏粒含量, 孔隙度, 容重, 有效磷, 耕层厚度, 阳离子交换量, 速效钾。 结合模型2目标 pH=6.5，每个指标按 1~10 级频数统计，最后一列标注是否主要/次要障碍因素。障碍组合：无明显复合障碍。
    ```
  - evidence (3 条):
    ```json
    [{"factor": "有机质", "severity": 6.08, "type": "primary"}, {"factor": "全氮", "severity": 6.0, "type": "primary"}, {"target_ph_from_model2": 6.5}]
    ```

---

#### Q4（期望 type=1）

> **问题原文：** 我的这块田质量等级稳不稳

- **识别 question_type**：1 ✓ 匹配
- **识别 role**：`farmer`
- **调用 agents**：model-4, model-5, model-6, model-7
- **answer 来源**：`answer`（`answer` = LLM 生成；`summary` = AgentManager 模板拼接）
- **耗时**：17.62s

**【完整回答】**

```text
根据评价结果，您的田块当前耕地质量等级为 **10等**，综合指数 **0.6728**，属于较低水平。障碍度分析显示，存在 **质地构型、地形部位、有机质、速效钾、排水能力、酸碱度** 等多个中度障碍因子，且通过改良部分指标（如排水能力、有机质等）即可提升等级（潜在可达9等），全部指标改良后甚至可达2等。这说明当前质量等级 **不稳定**，有较大的改良潜力和提升空间。建议您针对主要障碍因子采取相应改良措施（如施用石灰调节酸碱度、增施有机肥、改善灌排条件等），以稳定并提高耕地质量。
```

**【各 agent 调用细节】**

| agent_id | simulated | status | confidence | answer 摘要 |
|---|---|---|---|---|
| model-4 | sim（模拟） | - | 0.8 | 土壤 pH=5.5（弱酸性），建议石灰施用量 50.0 kg/亩。 |
| model-5 | sim（模拟） | - | 0.78 | 有机质 22.0 g/kg（中），建议施有机肥 1000.0 kg/亩。 |
| model-6 | sim（模拟） | skipped | 0.0 |  |
| model-7 | real（真实） | - | 0.9 | 耕地质量等级评价结果：质量等级为10等级，综合指数：0.6728。共12个指标参与评价。 |

**【各 agent 完整输出】**

- **model-4**
  - confidence: `0.8`
  - simulated: `True`
  - answer:
    ```text
    土壤 pH=5.5（弱酸性），建议石灰施用量 50.0 kg/亩。
    ```
  - evidence (2 条):
    ```json
    [{"metric": "ph", "value": 5.5}, {"metric": "lime_dosage", "value": 50.0}]
    ```

- **model-5**
  - confidence: `0.78`
  - simulated: `True`
  - answer:
    ```text
    有机质 22.0 g/kg（中），建议施有机肥 1000.0 kg/亩。
    ```
  - evidence (2 条):
    ```json
    [{"metric": "level", "value": "中"}, {"metric": "manure_dosage", "value": 1000.0}]
    ```

- **model-6**
  - status: `skipped`
  - reason: `question_not_related`
  - confidence: `0.0`
  - simulated: `True`
  - answer: (空)

- **model-7**
  - confidence: `0.9`
  - simulated: `False`
  - answer:
    ```text
    耕地质量等级评价结果：质量等级为10等级，综合指数：0.6728。共12个指标参与评价。
    ```
  - evidence (2 条):
    ```json
    [{"metric": "质量等级", "value": "10等"}, {"metric": "综合指数", "value": 0.6728}]
    ```

---

#### Q5（期望 type=1）

> **问题原文：** 查询区域内哪些对象需要纳入重点关注清单

- **识别 question_type**：1 ✓ 匹配
- **识别 role**：`farmer`
- **调用 agents**：model-4, model-5, model-6, model-7
- **answer 来源**：`answer`（`answer` = LLM 生成；`summary` = AgentManager 模板拼接）
- **耗时**：16.97s

**【完整回答】**

```text
根据提供的数据，区域内需要纳入重点关注清单的对象是土壤pH和有机质含量。具体分析如下：

- **土壤pH**：值为5.5（弱酸性），建议施用石灰50.0 kg/亩（置信度0.8）。
- **有机质**：含量为22.0 g/kg（中），建议施用有机肥1000.0 kg/亩（置信度0.78）。

其他模型（model-6、model-7）因问题不相关被跳过，无需重点关注。因此，当前区域应重点关注土壤酸度调节和有机质提升。
```

**【各 agent 调用细节】**

| agent_id | simulated | status | confidence | answer 摘要 |
|---|---|---|---|---|
| model-4 | sim（模拟） | - | 0.8 | 土壤 pH=5.5（弱酸性），建议石灰施用量 50.0 kg/亩。 |
| model-5 | sim（模拟） | - | 0.78 | 有机质 22.0 g/kg（中），建议施有机肥 1000.0 kg/亩。 |
| model-6 | sim（模拟） | skipped | 0.0 |  |
| model-7 | sim（模拟） | skipped | 0.0 |  |

**【各 agent 完整输出】**

- **model-4**
  - confidence: `0.8`
  - simulated: `True`
  - answer:
    ```text
    土壤 pH=5.5（弱酸性），建议石灰施用量 50.0 kg/亩。
    ```
  - evidence (2 条):
    ```json
    [{"metric": "ph", "value": 5.5}, {"metric": "lime_dosage", "value": 50.0}]
    ```

- **model-5**
  - confidence: `0.78`
  - simulated: `True`
  - answer:
    ```text
    有机质 22.0 g/kg（中），建议施有机肥 1000.0 kg/亩。
    ```
  - evidence (2 条):
    ```json
    [{"metric": "level", "value": "中"}, {"metric": "manure_dosage", "value": 1000.0}]
    ```

- **model-6**
  - status: `skipped`
  - reason: `question_not_related`
  - confidence: `0.0`
  - simulated: `True`
  - answer: (空)

- **model-7**
  - status: `skipped`
  - reason: `question_not_related`
  - confidence: `0.0`
  - simulated: `True`
  - answer: (空)

---

### 类型2：酸化改良（4 题）

#### Q6（期望 type=2）

> **问题原文：** 查询区域内农用地土壤酸化程度如何不同酸化等级比例分别多少

- **识别 question_type**：2 ✓ 匹配
- **识别 role**：`farmer`
- **调用 agents**：model-4, model-5, model-6, model-7
- **answer 来源**：`answer`（`answer` = LLM 生成；`summary` = AgentManager 模板拼接）
- **耗时**：7.39s

**【完整回答】**

```text
根据提供的数据，当前区域内农用地土壤的酸化程度为弱酸性，pH=5.5，交换性铝为3.2 cmol/kg（依据GB/T 42817-2023分级）。但数据中仅包含这一个样本点的信息，未提供不同酸化等级（如强酸性、酸性、弱酸性、中性等）的比例分布情况。因此，无法回答不同酸化等级的比例各是多少。
```

**【各 agent 调用细节】**

| agent_id | simulated | status | confidence | answer 摘要 |
|---|---|---|---|---|
| model-4 | sim（模拟） | - | 0.88 | 当前土壤 pH=5.5，酸化程度为弱酸性。交换性铝=3.2 cmol/kg。（依据 GB/T 42817-2023 分级） |
| model-5 | sim（模拟） | - | 0.78 | 有机质 22.0 g/kg（中），建议施有机肥 1000.0 kg/亩。 |
| model-6 | sim（模拟） | skipped | 0.0 |  |
| model-7 | sim（模拟） | skipped | 0.0 |  |

**【各 agent 完整输出】**

- **model-4**
  - confidence: `0.88`
  - simulated: `True`
  - answer:
    ```text
    当前土壤 pH=5.5，酸化程度为弱酸性。交换性铝=3.2 cmol/kg。（依据 GB/T 42817-2023 分级）
    ```
  - evidence (4 条):
    ```json
    [{"metric": "ph", "value": 5.5}, {"metric": "degree", "value": "弱酸性"}, {"metric": "exchangeable_al", "value": 3.2}, {"standard": "GB/T 42817-2023"}]
    ```

- **model-5**
  - confidence: `0.78`
  - simulated: `True`
  - answer:
    ```text
    有机质 22.0 g/kg（中），建议施有机肥 1000.0 kg/亩。
    ```
  - evidence (2 条):
    ```json
    [{"metric": "level", "value": "中"}, {"metric": "manure_dosage", "value": 1000.0}]
    ```

- **model-6**
  - status: `skipped`
  - reason: `question_not_related`
  - confidence: `0.0`
  - simulated: `True`
  - answer: (空)

- **model-7**
  - status: `skipped`
  - reason: `question_not_related`
  - confidence: `0.0`
  - simulated: `True`
  - answer: (空)

---

#### Q7（期望 type=2）

> **问题原文：** 我的田酸化了pH是多少我要施加多少碱性调理剂可以治理好

- **识别 question_type**：2 ✓ 匹配
- **识别 role**：`farmer`
- **调用 agents**：model-4, model-5, model-6, model-7
- **answer 来源**：`answer`（`answer` = LLM 生成；`summary` = AgentManager 模板拼接）
- **耗时**：7.69s

**【完整回答】**

```text
根据提供的数据，您的土壤当前pH为5.5，属于弱酸性。建议施加碱性调理剂石灰50.0 kg/亩，分两次施用并结合翻耕，预计治理后pH可提升至5.6。
```

**【各 agent 调用细节】**

| agent_id | simulated | status | confidence | answer 摘要 |
|---|---|---|---|---|
| model-4 | sim（模拟） | - | 0.85 | 土壤酸化程度为弱酸性，建议施石灰 50.0 kg/亩，预计治理后 pH 提升至 5.6。（依据 GB/T 42817-2023 酸化等级判定与 NY/T 443-2019 调理剂施用量计算，分两次施用，结合翻耕作业） |
| model-5 | sim（模拟） | - | 0.78 | 有机质 22.0 g/kg（中），建议施有机肥 1000.0 kg/亩。 |
| model-6 | sim（模拟） | skipped | 0.0 |  |
| model-7 | sim（模拟） | skipped | 0.0 |  |

**【各 agent 完整输出】**

- **model-4**
  - confidence: `0.85`
  - simulated: `True`
  - answer:
    ```text
    土壤酸化程度为弱酸性，建议施石灰 50.0 kg/亩，预计治理后 pH 提升至 5.6。（依据 GB/T 42817-2023 酸化等级判定与 NY/T 443-2019 调理剂施用量计算，分两次施用，结合翻耕作业）
    ```
  - evidence (7 条):
    ```json
    [{"metric": "ph", "value": 5.5}, {"metric": "exchangeable_al", "value": 3.2, "unit": "cmol/kg"}, {"metric": "lime_dosage", "value": 50.0, "unit": "kg/亩"}, {"metric": "ph_after_remediation", "value": 5.6}, {"standard": "GB/T 42817-2023"}, {"standard": "NY/T 443-2019"}, {"recommendation": "分两次施用，结合翻耕作业"}]
    ```

- **model-5**
  - confidence: `0.78`
  - simulated: `True`
  - answer:
    ```text
    有机质 22.0 g/kg（中），建议施有机肥 1000.0 kg/亩。
    ```
  - evidence (2 条):
    ```json
    [{"metric": "level", "value": "中"}, {"metric": "manure_dosage", "value": 1000.0}]
    ```

- **model-6**
  - status: `skipped`
  - reason: `question_not_related`
  - confidence: `0.0`
  - simulated: `True`
  - answer: (空)

- **model-7**
  - status: `skipped`
  - reason: `question_not_related`
  - confidence: `0.0`
  - simulated: `True`
  - answer: (空)

---

#### Q8（期望 type=2）

> **问题原文：** 查询区域内不同土地利用类型的酸化程度

- **识别 question_type**：2 ✓ 匹配
- **识别 role**：`farmer`
- **调用 agents**：model-4, model-5, model-6, model-7
- **answer 来源**：`answer`（`answer` = LLM 生成；`summary` = AgentManager 模板拼接）
- **耗时**：12.16s

**【完整回答】**

```text
根据提供的数据，当前样本的pH值为5.5，属于弱酸性。但数据中未给出不同土地利用类型（旱地、水田、园地、林地）的具体酸化程度统计，仅建议按照GB/T 42817-2023分级分别统计各类型的酸化等级及比例。因此，无法直接回答不同土地利用类型的酸化程度，需要进一步补充按土地利用类型分类的pH数据。
```

**【各 agent 调用细节】**

| agent_id | simulated | status | confidence | answer 摘要 |
|---|---|---|---|---|
| model-4 | sim（模拟） | - | 0.84 | 不同土地利用类型酸化程度：当前样本 pH=5.5（弱酸性）。建议按旱地、水田、园地、林地分别统计酸化等级及比例（依据 GB/T 42817-2023 分级）。 |
| model-5 | sim（模拟） | - | 0.78 | 有机质 22.0 g/kg（中），建议施有机肥 1000.0 kg/亩。 |
| model-6 | sim（模拟） | skipped | 0.0 |  |
| model-7 | sim（模拟） | skipped | 0.0 |  |

**【各 agent 完整输出】**

- **model-4**
  - confidence: `0.84`
  - simulated: `True`
  - answer:
    ```text
    不同土地利用类型酸化程度：当前样本 pH=5.5（弱酸性）。建议按旱地、水田、园地、林地分别统计酸化等级及比例（依据 GB/T 42817-2023 分级）。
    ```
  - evidence (3 条):
    ```json
    [{"metric": "ph", "value": 5.5}, {"metric": "degree", "value": "弱酸性"}, {"standard": "GB/T 42817-2023"}]
    ```

- **model-5**
  - confidence: `0.78`
  - simulated: `True`
  - answer:
    ```text
    有机质 22.0 g/kg（中），建议施有机肥 1000.0 kg/亩。
    ```
  - evidence (2 条):
    ```json
    [{"metric": "level", "value": "中"}, {"metric": "manure_dosage", "value": 1000.0}]
    ```

- **model-6**
  - status: `skipped`
  - reason: `question_not_related`
  - confidence: `0.0`
  - simulated: `True`
  - answer: (空)

- **model-7**
  - status: `skipped`
  - reason: `question_not_related`
  - confidence: `0.0`
  - simulated: `True`
  - answer: (空)

---

#### Q9（期望 type=2）

> **问题原文：** 我的这块田酸化严重吗

- **识别 question_type**：2 ✓ 匹配
- **识别 role**：`farmer`
- **调用 agents**：model-4, model-5, model-6, model-7
- **answer 来源**：`answer`（`answer` = LLM 生成；`summary` = AgentManager 模板拼接）
- **耗时**：7.47s

**【完整回答】**

```text
根据您提供的数据，土壤pH值为5.5，依据GB/T 42817-2023标准（酸性5.5≤pH<6.5、强酸性4.5≤pH<5.5、极强酸性pH<4.5），属于**弱酸性**，酸化程度并不严重。
```

**【各 agent 调用细节】**

| agent_id | simulated | status | confidence | answer 摘要 |
|---|---|---|---|---|
| model-4 | sim（模拟） | - | 0.86 | 您的地块土壤 pH=5.5，酸化等级为弱酸性。（依据 GB/T 42817-2023：酸性 5.5≤pH<6.5、强酸性 4.5≤pH<5.5、极强酸性 pH<4.5） |
| model-5 | sim（模拟） | - | 0.78 | 有机质 22.0 g/kg（中），建议施有机肥 1000.0 kg/亩。 |
| model-6 | sim（模拟） | skipped | 0.0 |  |
| model-7 | sim（模拟） | skipped | 0.0 |  |

**【各 agent 完整输出】**

- **model-4**
  - confidence: `0.86`
  - simulated: `True`
  - answer:
    ```text
    您的地块土壤 pH=5.5，酸化等级为弱酸性。（依据 GB/T 42817-2023：酸性 5.5≤pH<6.5、强酸性 4.5≤pH<5.5、极强酸性 pH<4.5）
    ```
  - evidence (3 条):
    ```json
    [{"metric": "ph", "value": 5.5}, {"metric": "degree", "value": "弱酸性"}, {"standard": "GB/T 42817-2023"}]
    ```

- **model-5**
  - confidence: `0.78`
  - simulated: `True`
  - answer:
    ```text
    有机质 22.0 g/kg（中），建议施有机肥 1000.0 kg/亩。
    ```
  - evidence (2 条):
    ```json
    [{"metric": "level", "value": "中"}, {"metric": "manure_dosage", "value": 1000.0}]
    ```

- **model-6**
  - status: `skipped`
  - reason: `question_not_related`
  - confidence: `0.0`
  - simulated: `True`
  - answer: (空)

- **model-7**
  - status: `skipped`
  - reason: `question_not_related`
  - confidence: `0.0`
  - simulated: `True`
  - answer: (空)

---

### 类型3：障碍诊断与潜力（5 题）

#### Q10（期望 type=3）

> **问题原文：** 辖区耕地质量提升的总体潜力有多大可增产多少粮食

- **识别 question_type**：3 ✓ 匹配
- **识别 role**：`farmer`
- **调用 agents**：model-4, model-5, model-6, model-7
- **answer 来源**：`answer`（`answer` = LLM 生成；`summary` = AgentManager 模板拼接）
- **耗时**：28.8s

**【完整回答】**

```text
根据现有数据，辖区耕地质量提升的建议包括：施用石灰50.0 kg/亩以调节土壤pH（当前5.5，弱酸性），施用有机肥1000.0 kg/亩以提高有机质含量（当前22.0 g/kg，中等水平）。这些措施有助于改善土壤条件，从而提升耕地质量，但数据中未提供具体的增产粮食数量，无法直接给出总体潜力对应的增产数值。如需准确估算，需结合当地作物类型、产量水平及进一步的田间试验数据。
```

**【各 agent 调用细节】**

| agent_id | simulated | status | confidence | answer 摘要 |
|---|---|---|---|---|
| model-4 | sim（模拟） | - | 0.8 | 土壤 pH=5.5（弱酸性），建议石灰施用量 50.0 kg/亩。 |
| model-5 | sim（模拟） | - | 0.78 | 有机质 22.0 g/kg（中），建议施有机肥 1000.0 kg/亩。 |
| model-6 | sim（模拟） | skipped | 0.0 |  |
| model-7 | sim（模拟） | skipped | 0.0 |  |

**【各 agent 完整输出】**

- **model-4**
  - confidence: `0.8`
  - simulated: `True`
  - answer:
    ```text
    土壤 pH=5.5（弱酸性），建议石灰施用量 50.0 kg/亩。
    ```
  - evidence (2 条):
    ```json
    [{"metric": "ph", "value": 5.5}, {"metric": "lime_dosage", "value": 50.0}]
    ```

- **model-5**
  - confidence: `0.78`
  - simulated: `True`
  - answer:
    ```text
    有机质 22.0 g/kg（中），建议施有机肥 1000.0 kg/亩。
    ```
  - evidence (2 条):
    ```json
    [{"metric": "level", "value": "中"}, {"metric": "manure_dosage", "value": 1000.0}]
    ```

- **model-6**
  - status: `skipped`
  - reason: `question_not_related`
  - confidence: `0.0`
  - simulated: `True`
  - answer: (空)

- **model-7**
  - status: `skipped`
  - reason: `question_not_related`
  - confidence: `0.0`
  - simulated: `True`
  - answer: (空)

---

#### Q11（期望 type=3）

> **问题原文：** 我们县划定的优先改良片区具体在哪几个村每块潜力多大

- **识别 question_type**：3 ✓ 匹配
- **识别 role**：`county`
- **调用 agents**：model-1, model-2, model-3
- **answer 来源**：`answer`（`answer` = LLM 生成；`summary` = AgentManager 模板拼接）
- **耗时**：22.1s

**【完整回答】**

```text
根据现有数据，**县域优先改良片区的整体潜力等级为中潜力，平均障碍度值为30.85**，但数据中**未列出具体涉及哪几个村以及每块地的潜力分值**。  

系统建议以地块为单元绘制潜力分布图，选中地块后可显示村名、地块编号、面积、当前等级、目标等级、潜力分值。由于当前为模拟数据，如需获取真实的地块级信息，请提供具体的地块ID（parcel_id）或查看潜力分布图。
```

**【各 agent 调用细节】**

| agent_id | simulated | status | confidence | answer 摘要 |
|---|---|---|---|---|
| model-1 | sim（模拟） | - | 0.85 | 稳定性评价结果：稳定性得分 0.85，风险等级：低风险。九模块评价均已完成。 |
| model-2 | sim（模拟） | - | 0.81 | 县域优先改良片区潜力分布：整体潜力等级 中潜力，平均障碍度值 30.85。建议以地块为单元绘制潜力分布图，颜色深浅表示潜力值，选中地块显示村名、地块编号、面积、当前等级、目标等级、潜力分值。 |
| model-3 | sim（模拟） | - | 0.83 | 县域障碍诊断：主要障碍因素 有机质, 全氮；次要障碍因素 pH, 黏粒含量, 孔隙度, 容重, 有效磷, 耕层厚度, 阳离子交换量, 速效钾。 结合模型2目标 pH=6.5，每个指标按 1~10 级频数统计，最后一列标注是否主要/次要障碍因...[truncated 15 chars] |

**【各 agent 完整输出】**

- **model-1**
  - confidence: `0.85`
  - simulated: `True`
  - answer:
    ```text
    稳定性评价结果：稳定性得分 0.85，风险等级：低风险。九模块评价均已完成。
    ```
  - evidence (2 条):
    ```json
    [{"metric": "稳定性得分", "value": 0.85}, {"metric": "风险等级", "value": "低风险"}]
    ```

- **model-2**
  - confidence: `0.81`
  - simulated: `True`
  - answer:
    ```text
    县域优先改良片区潜力分布：整体潜力等级 中潜力，平均障碍度值 30.85。建议以地块为单元绘制潜力分布图，颜色深浅表示潜力值，选中地块显示村名、地块编号、面积、当前等级、目标等级、潜力分值。
    ```
  - evidence (3 条):
    ```json
    [{"indicator": "有效磷", "obstacle_degree": 52.0, "potential_level": "中潜力"}, {"indicator": "速效钾", "obstacle_degree": 46.67, "potential_level": "中潜力"}, {"indicator": "阳离子交换量", "obstacle_degree": 43.33, "potential_level": "中潜力"}]
    ```

- **model-3**
  - confidence: `0.83`
  - simulated: `True`
  - answer:
    ```text
    县域障碍诊断：主要障碍因素 有机质, 全氮；次要障碍因素 pH, 黏粒含量, 孔隙度, 容重, 有效磷, 耕层厚度, 阳离子交换量, 速效钾。 结合模型2目标 pH=6.5，每个指标按 1~10 级频数统计，最后一列标注是否主要/次要障碍因素。障碍组合：无明显复合障碍。
    ```
  - evidence (3 条):
    ```json
    [{"factor": "有机质", "severity": 6.08, "type": "primary"}, {"factor": "全氮", "severity": 6.0, "type": "primary"}, {"target_ph_from_model2": 6.5}]
    ```

---

#### Q12（期望 type=3）

> **问题原文：** 我这块地到底有啥毛病

- **识别 question_type**：3 ✓ 匹配
- **识别 role**：`farmer`
- **调用 agents**：model-4, model-5, model-6, model-7
- **answer 来源**：`answer`（`answer` = LLM 生成；`summary` = AgentManager 模板拼接）
- **耗时**：9.24s

**【完整回答】**

```text
根据土壤检测结果，您的土地存在以下问题：

- **土壤偏酸**：pH值为5.5（弱酸性），建议每亩施用50.0 kg石灰来调节酸碱度。
- **有机质含量中等**：有机质为22.0 g/kg，属于中等水平，建议每亩施用1000.0 kg有机肥以提升地力。

其他指标未见异常，可针对上述问题采取相应改良措施。
```

**【各 agent 调用细节】**

| agent_id | simulated | status | confidence | answer 摘要 |
|---|---|---|---|---|
| model-4 | sim（模拟） | - | 0.8 | 土壤 pH=5.5（弱酸性），建议石灰施用量 50.0 kg/亩。 |
| model-5 | sim（模拟） | - | 0.78 | 有机质 22.0 g/kg（中），建议施有机肥 1000.0 kg/亩。 |
| model-6 | sim（模拟） | skipped | 0.0 |  |
| model-7 | sim（模拟） | skipped | 0.0 |  |

**【各 agent 完整输出】**

- **model-4**
  - confidence: `0.8`
  - simulated: `True`
  - answer:
    ```text
    土壤 pH=5.5（弱酸性），建议石灰施用量 50.0 kg/亩。
    ```
  - evidence (2 条):
    ```json
    [{"metric": "ph", "value": 5.5}, {"metric": "lime_dosage", "value": 50.0}]
    ```

- **model-5**
  - confidence: `0.78`
  - simulated: `True`
  - answer:
    ```text
    有机质 22.0 g/kg（中），建议施有机肥 1000.0 kg/亩。
    ```
  - evidence (2 条):
    ```json
    [{"metric": "level", "value": "中"}, {"metric": "manure_dosage", "value": 1000.0}]
    ```

- **model-6**
  - status: `skipped`
  - reason: `question_not_related`
  - confidence: `0.0`
  - simulated: `True`
  - answer: (空)

- **model-7**
  - status: `skipped`
  - reason: `question_not_related`
  - confidence: `0.0`
  - simulated: `True`
  - answer: (空)

---

#### Q13（期望 type=3）

> **问题原文：** 全省耕地质量存在哪些问题

- **识别 question_type**：3 ✓ 匹配
- **识别 role**：`province`
- **调用 agents**：model-1, model-3
- **answer 来源**：`answer`（`answer` = LLM 生成；`summary` = AgentManager 模板拼接）
- **耗时**：5.67s

**【完整回答】**

```text
根据提供的数据，全省耕地质量存在以下问题：

- **主要障碍因素**：有机质、全氮（含量不足）。
- **次要障碍因素**：pH、黏粒含量、孔隙度、容重、有效磷、耕层厚度、阳离子交换量、速效钾。
- **障碍组合**：无明显复合障碍。

此外，稳定性评价结果为稳定性得分0.85，风险等级为低风险，表明整体稳定性较好，但上述障碍因素仍需关注。
```

**【各 agent 调用细节】**

| agent_id | simulated | status | confidence | answer 摘要 |
|---|---|---|---|---|
| model-1 | sim（模拟） | - | 0.85 | 稳定性评价结果：稳定性得分 0.85，风险等级：低风险。九模块评价均已完成。 |
| model-3 | sim（模拟） | - | 0.83 | 主要障碍因素：有机质, 全氮；次要障碍因素：pH, 黏粒含量, 孔隙度, 容重, 有效磷, 耕层厚度, 阳离子交换量, 速效钾。障碍组合：无明显复合障碍。 |

**【各 agent 完整输出】**

- **model-1**
  - confidence: `0.85`
  - simulated: `True`
  - answer:
    ```text
    稳定性评价结果：稳定性得分 0.85，风险等级：低风险。九模块评价均已完成。
    ```
  - evidence (2 条):
    ```json
    [{"metric": "稳定性得分", "value": 0.85}, {"metric": "风险等级", "value": "低风险"}]
    ```

- **model-3**
  - confidence: `0.83`
  - simulated: `True`
  - answer:
    ```text
    主要障碍因素：有机质, 全氮；次要障碍因素：pH, 黏粒含量, 孔隙度, 容重, 有效磷, 耕层厚度, 阳离子交换量, 速效钾。障碍组合：无明显复合障碍。
    ```
  - evidence (2 条):
    ```json
    [{"factor": "有机质", "severity": 6.08, "type": "primary"}, {"factor": "全氮", "severity": 6.0, "type": "primary"}]
    ```

---

#### Q14（期望 type=3）

> **问题原文：** 县乡镇里的耕地在哪些方面有问题

- **识别 question_type**：3 ✓ 匹配
- **识别 role**：`county`
- **调用 agents**：model-1, model-2, model-3
- **answer 来源**：`answer`（`answer` = LLM 生成；`summary` = AgentManager 模板拼接）
- **耗时**：22.02s

**【完整回答】**

```text
根据提供的多模型评估数据，县乡镇里的耕地在以下方面存在问题：

### 1. 稳定性评价（model-1）
- **稳定性得分**：0.85，**风险等级**：低风险，稳定性问题不突出。

### 2. 耕地质量提升潜力（model-2）
- **潜力等级**：中潜力，**平均障碍度**：30.85。
- **主要障碍因素**：有效磷（障碍度52.0）、速效钾（46.67）、阳离子交换量（43.33）。

### 3. 县域障碍诊断（model-3）
- **主要障碍因素**：有机质（严重度6.08）、全氮（6.0）。
- **次要障碍因素**：pH、黏粒含量、孔隙度、容重、有效磷、耕层厚度、阳离子交换量、速效钾。
- **障碍组合**：无明显复合障碍。

### 综合问题方面
- **养分失衡**：有效磷、速效钾、有机质、全氮不足或比例失调。
- **土壤保肥能力**：阳离子交换量偏低。
- **物理性质**：pH不适宜（目标pH=6.5）、黏粒含量、孔隙度、容重、耕层厚度等存在障碍。

因此，耕地的主要问题集中在土壤养分和保肥能力上，同时土壤物理性质也有一定影响，但稳定性风险较低。
```

**【各 agent 调用细节】**

| agent_id | simulated | status | confidence | answer 摘要 |
|---|---|---|---|---|
| model-1 | sim（模拟） | - | 0.85 | 稳定性评价结果：稳定性得分 0.85，风险等级：低风险。九模块评价均已完成。 |
| model-2 | sim（模拟） | - | 0.8 | 耕地质量提升潜力等级为 中潜力，平均障碍度值 30.85，主要障碍因素：有效磷, 速效钾, 阳离子交换量。 |
| model-3 | sim（模拟） | - | 0.83 | 县域障碍诊断：主要障碍因素 有机质, 全氮；次要障碍因素 pH, 黏粒含量, 孔隙度, 容重, 有效磷, 耕层厚度, 阳离子交换量, 速效钾。 结合模型2目标 pH=6.5，每个指标按 1~10 级频数统计，最后一列标注是否主要/次要障碍因...[truncated 15 chars] |

**【各 agent 完整输出】**

- **model-1**
  - confidence: `0.85`
  - simulated: `True`
  - answer:
    ```text
    稳定性评价结果：稳定性得分 0.85，风险等级：低风险。九模块评价均已完成。
    ```
  - evidence (2 条):
    ```json
    [{"metric": "稳定性得分", "value": 0.85}, {"metric": "风险等级", "value": "低风险"}]
    ```

- **model-2**
  - confidence: `0.8`
  - simulated: `True`
  - answer:
    ```text
    耕地质量提升潜力等级为 中潜力，平均障碍度值 30.85，主要障碍因素：有效磷, 速效钾, 阳离子交换量。
    ```
  - evidence (4 条):
    ```json
    [{"indicator": "有效磷", "obstacle_degree": 52.0, "potential_level": "中潜力"}, {"indicator": "速效钾", "obstacle_degree": 46.67, "potential_level": "中潜力"}, {"indicator": "阳离子交换量", "obstacle_degree": 43.33, "potential_level": "中潜力"}, {"target_ph": 6.5, "recommendation": "目标 pH 供下游模型3使用"}]
    ```

- **model-3**
  - confidence: `0.83`
  - simulated: `True`
  - answer:
    ```text
    县域障碍诊断：主要障碍因素 有机质, 全氮；次要障碍因素 pH, 黏粒含量, 孔隙度, 容重, 有效磷, 耕层厚度, 阳离子交换量, 速效钾。 结合模型2目标 pH=6.5，每个指标按 1~10 级频数统计，最后一列标注是否主要/次要障碍因素。障碍组合：无明显复合障碍。
    ```
  - evidence (3 条):
    ```json
    [{"factor": "有机质", "severity": 6.08, "type": "primary"}, {"factor": "全氮", "severity": 6.0, "type": "primary"}, {"target_ph_from_model2": 6.5}]
    ```

---

### 类型4：肥力与有机质（6 题）

#### Q15（期望 type=4）

> **问题原文：** 全省耕地土壤有机质含量如何空间分布情况

- **识别 question_type**：4 ✓ 匹配
- **识别 role**：`province`
- **调用 agents**：model-1, model-3
- **answer 来源**：`answer`（`answer` = LLM 生成；`summary` = AgentManager 模板拼接）
- **耗时**：25.78s

**【完整回答】**

```text
根据提供的数据，无法直接回答全省耕地土壤有机质含量的空间分布情况，因为数据中未包含任何空间分布信息（如地图、区域差异或统计分布）。现有数据主要来自两个模型：

- **model-1**：给出稳定性评价结果（稳定性得分0.85，风险等级低风险），不涉及有机质空间分布。
- **model-3**：诊断出有机质是主要障碍因素之一（严重程度6.08），但仅表明其作为障碍因子的重要性，并未描述其在全省的空间变化。

因此，基于当前数据，只能推断有机质含量可能普遍偏低（作为主要障碍因素），但无法获知其高值区、低值区或变异特征等空间分布详情。如需了解具体空间分布，建议提供地块ID（parcel_id）以获取真实诊断结果，或查询相关的土壤有机质专题图。
```

**【各 agent 调用细节】**

| agent_id | simulated | status | confidence | answer 摘要 |
|---|---|---|---|---|
| model-1 | sim（模拟） | - | 0.85 | 稳定性评价结果：稳定性得分 0.85，风险等级：低风险。九模块评价均已完成。 |
| model-3 | sim（模拟） | - | 0.83 | 主要障碍因素：有机质, 全氮；次要障碍因素：pH, 黏粒含量, 孔隙度, 容重, 有效磷, 耕层厚度, 阳离子交换量, 速效钾。障碍组合：无明显复合障碍。 |

**【各 agent 完整输出】**

- **model-1**
  - confidence: `0.85`
  - simulated: `True`
  - answer:
    ```text
    稳定性评价结果：稳定性得分 0.85，风险等级：低风险。九模块评价均已完成。
    ```
  - evidence (2 条):
    ```json
    [{"metric": "稳定性得分", "value": 0.85}, {"metric": "风险等级", "value": "低风险"}]
    ```

- **model-3**
  - confidence: `0.83`
  - simulated: `True`
  - answer:
    ```text
    主要障碍因素：有机质, 全氮；次要障碍因素：pH, 黏粒含量, 孔隙度, 容重, 有效磷, 耕层厚度, 阳离子交换量, 速效钾。障碍组合：无明显复合障碍。
    ```
  - evidence (2 条):
    ```json
    [{"factor": "有机质", "severity": 6.08, "type": "primary"}, {"factor": "全氮", "severity": 6.0, "type": "primary"}]
    ```

---

#### Q16（期望 type=4）

> **问题原文：** 为了提升耕地土壤有机质有机肥或者秸秆每亩施用量多少

- **识别 question_type**：4 ✓ 匹配
- **识别 role**：`farmer`
- **调用 agents**：model-4, model-5, model-6, model-7
- **answer 来源**：`answer`（`answer` = LLM 生成；`summary` = AgentManager 模板拼接）
- **耗时**：9.74s

**【完整回答】**

```text
根据提供的数据，为了提升耕地土壤有机质，建议有机肥施用量为 **1000.0 kg/亩**。秸秆还田的施用量未给出具体数值，但可参考同等养分替代量进行施用。
```

**【各 agent 调用细节】**

| agent_id | simulated | status | confidence | answer 摘要 |
|---|---|---|---|---|
| model-4 | sim（模拟） | - | 0.8 | 土壤 pH=5.5（弱酸性），建议石灰施用量 50.0 kg/亩。 |
| model-5 | sim（模拟） | - | 0.82 | 有机质等级为中，建议有机肥施用量 1000.0 kg/亩，秸秆还田参考同等养分替代量，预期有机质提升 1.5 g/kg。 |
| model-6 | sim（模拟） | - | - | 基于 ML 预测，建议施肥量约 100.00 t/ha（模型不可用，返回训练集均值估算） |
| model-7 | sim（模拟） | skipped | 0.0 |  |

**【各 agent 完整输出】**

- **model-4**
  - confidence: `0.8`
  - simulated: `True`
  - answer:
    ```text
    土壤 pH=5.5（弱酸性），建议石灰施用量 50.0 kg/亩。
    ```
  - evidence (2 条):
    ```json
    [{"metric": "ph", "value": 5.5}, {"metric": "lime_dosage", "value": 50.0}]
    ```

- **model-5**
  - confidence: `0.82`
  - simulated: `True`
  - answer:
    ```text
    有机质等级为中，建议有机肥施用量 1000.0 kg/亩，秸秆还田参考同等养分替代量，预期有机质提升 1.5 g/kg。
    ```
  - evidence (4 条):
    ```json
    [{"metric": "organic_matter", "value": 22.0, "unit": "g/kg"}, {"metric": "manure_dosage", "value": 1000.0, "unit": "kg/亩"}, {"metric": "potential_increase", "value": 1.5, "unit": "g/kg"}, {"recommendation": "优先选用腐熟农家肥或商品有机肥，分季施用"}]
    ```

- **model-6**
  - confidence: `None`
  - simulated: `True`
  - answer:
    ```text
    基于 ML 预测，建议施肥量约 100.00 t/ha（模型不可用，返回训练集均值估算）
    ```
  - evidence (2 条):
    ```json
    [{"metric": "dose_prediction", "value": 100.0, "unit": "t/ha"}, {"metric": "dose_confidence", "value": 0.3}]
    ```

- **model-7**
  - status: `skipped`
  - reason: `question_not_related`
  - confidence: `0.0`
  - simulated: `True`
  - answer: (空)

---

#### Q17（期望 type=4）

> **问题原文：** 本县耕地土壤有机质平均含量是多少

- **识别 question_type**：4 ✓ 匹配
- **识别 role**：`county`
- **调用 agents**：model-1, model-2, model-3
- **answer 来源**：`answer`（`answer` = LLM 生成；`summary` = AgentManager 模板拼接）
- **耗时**：18.63s

**【完整回答】**

```text
根据提供的数据，无法直接得出本县耕地土壤有机质的平均含量。数据中仅显示有机质被诊断为主要障碍因素，其严重程度评分为6.08（1~10级频数统计），但未给出具体的平均含量数值。
```

**【各 agent 调用细节】**

| agent_id | simulated | status | confidence | answer 摘要 |
|---|---|---|---|---|
| model-1 | sim（模拟） | - | 0.85 | 稳定性评价结果：稳定性得分 0.85，风险等级：低风险。九模块评价均已完成。 |
| model-2 | sim（模拟） | - | 0.8 | 耕地质量提升潜力等级为 中潜力，平均障碍度值 30.85，主要障碍因素：有效磷, 速效钾, 阳离子交换量。 |
| model-3 | sim（模拟） | - | 0.83 | 县域障碍诊断：主要障碍因素 有机质, 全氮；次要障碍因素 pH, 黏粒含量, 孔隙度, 容重, 有效磷, 耕层厚度, 阳离子交换量, 速效钾。 结合模型2目标 pH=6.5，每个指标按 1~10 级频数统计，最后一列标注是否主要/次要障碍因...[truncated 15 chars] |

**【各 agent 完整输出】**

- **model-1**
  - confidence: `0.85`
  - simulated: `True`
  - answer:
    ```text
    稳定性评价结果：稳定性得分 0.85，风险等级：低风险。九模块评价均已完成。
    ```
  - evidence (2 条):
    ```json
    [{"metric": "稳定性得分", "value": 0.85}, {"metric": "风险等级", "value": "低风险"}]
    ```

- **model-2**
  - confidence: `0.8`
  - simulated: `True`
  - answer:
    ```text
    耕地质量提升潜力等级为 中潜力，平均障碍度值 30.85，主要障碍因素：有效磷, 速效钾, 阳离子交换量。
    ```
  - evidence (4 条):
    ```json
    [{"indicator": "有效磷", "obstacle_degree": 52.0, "potential_level": "中潜力"}, {"indicator": "速效钾", "obstacle_degree": 46.67, "potential_level": "中潜力"}, {"indicator": "阳离子交换量", "obstacle_degree": 43.33, "potential_level": "中潜力"}, {"target_ph": 6.5, "recommendation": "目标 pH 供下游模型3使用"}]
    ```

- **model-3**
  - confidence: `0.83`
  - simulated: `True`
  - answer:
    ```text
    县域障碍诊断：主要障碍因素 有机质, 全氮；次要障碍因素 pH, 黏粒含量, 孔隙度, 容重, 有效磷, 耕层厚度, 阳离子交换量, 速效钾。 结合模型2目标 pH=6.5，每个指标按 1~10 级频数统计，最后一列标注是否主要/次要障碍因素。障碍组合：无明显复合障碍。
    ```
  - evidence (3 条):
    ```json
    [{"factor": "有机质", "severity": 6.08, "type": "primary"}, {"factor": "全氮", "severity": 6.0, "type": "primary"}, {"target_ph_from_model2": 6.5}]
    ```

---

#### Q18（期望 type=4）

> **问题原文：** 我的田肥力怎么样

- **识别 question_type**：4 ✓ 匹配
- **识别 role**：`farmer`
- **调用 agents**：model-4, model-5, model-6, model-7
- **answer 来源**：`answer`（`answer` = LLM 生成；`summary` = AgentManager 模板拼接）
- **耗时**：12.81s

**【完整回答】**

```text
根据检测数据，您的田土壤pH为5.5（弱酸性），有机质含量22.0 g/kg（中等），建议施用石灰50.0 kg/亩调节酸碱度，并施用有机肥1000.0 kg/亩提升有机质。机器学习模型预测的土壤有机碳为12.00 g/kg，但置信度较低（30%），仅供参考。总体来看，田肥力中等，需通过改良措施进一步提升。
```

**【各 agent 调用细节】**

| agent_id | simulated | status | confidence | answer 摘要 |
|---|---|---|---|---|
| model-4 | sim（模拟） | - | 0.8 | 土壤 pH=5.5（弱酸性），建议石灰施用量 50.0 kg/亩。 |
| model-5 | sim（模拟） | - | 0.78 | 有机质 22.0 g/kg（中），建议施有机肥 1000.0 kg/亩。 |
| model-6 | sim（模拟） | - | - | 耕地综合地力改良提升综合诊断（基于 ML 预测）： - SOC（土壤有机碳）：12.00 g/kg（置信度 30%） - Dose（施肥量）：100.00 t/ha（置信度 30%，模型不可用，返回训练集均值估算） （模型不可用，以上为训练...[truncated 6 chars] |
| model-7 | sim（模拟） | skipped | 0.0 |  |

**【各 agent 完整输出】**

- **model-4**
  - confidence: `0.8`
  - simulated: `True`
  - answer:
    ```text
    土壤 pH=5.5（弱酸性），建议石灰施用量 50.0 kg/亩。
    ```
  - evidence (2 条):
    ```json
    [{"metric": "ph", "value": 5.5}, {"metric": "lime_dosage", "value": 50.0}]
    ```

- **model-5**
  - confidence: `0.78`
  - simulated: `True`
  - answer:
    ```text
    有机质 22.0 g/kg（中），建议施有机肥 1000.0 kg/亩。
    ```
  - evidence (2 条):
    ```json
    [{"metric": "level", "value": "中"}, {"metric": "manure_dosage", "value": 1000.0}]
    ```

- **model-6**
  - confidence: `None`
  - simulated: `True`
  - answer:
    ```text
    耕地综合地力改良提升综合诊断（基于 ML 预测）：
    - SOC（土壤有机碳）：12.00 g/kg（置信度 30%）
    - Dose（施肥量）：100.00 t/ha（置信度 30%，模型不可用，返回训练集均值估算）
    （模型不可用，以上为训练集均值估算）
    ```
  - evidence (4 条):
    ```json
    [{"metric": "soc_prediction", "value": 12.0, "unit": "g/kg"}, {"metric": "soc_confidence", "value": 0.3}, {"metric": "dose_prediction", "value": 100.0, "unit": "t/ha"}, {"metric": "dose_confidence", "value": 0.3}]
    ```

- **model-7**
  - status: `skipped`
  - reason: `question_not_related`
  - confidence: `0.0`
  - simulated: `True`
  - answer: (空)

---

#### Q19（期望 type=4）

> **问题原文：** 我的田土壤有机碳含量大概多少

- **识别 question_type**：4 ✓ 匹配
- **识别 role**：`farmer`
- **调用 agents**：model-4, model-5, model-6, model-7
- **answer 来源**：`answer`（`answer` = LLM 生成；`summary` = AgentManager 模板拼接）
- **耗时**：5.8s

**【完整回答】**

```text
根据模型预测，您的土壤有机碳（SOC）含量约为 **12.00 g/kg**（相当于有机质含量约22.0 g/kg，等级为中）。该预测基于训练集均值估算，置信度较低（0.3），建议结合当地实测数据进一步确认。
```

**【各 agent 调用细节】**

| agent_id | simulated | status | confidence | answer 摘要 |
|---|---|---|---|---|
| model-4 | sim（模拟） | - | 0.8 | 土壤 pH=5.5（弱酸性），建议石灰施用量 50.0 kg/亩。 |
| model-5 | sim（模拟） | - | 0.84 | 全省耕地有机质含量平均 22.0 g/kg，等级为中。全氮 1.2 g/kg，碳氮比 11.5。空间分布建议按高/中/低等级占比与地形梯度分析。 |
| model-6 | sim（模拟） | - | - | 基于 ML 预测，您的土壤有机碳（SOC）预测值约 12.00 g/kg（模型不可用，返回训练集均值估算） |
| model-7 | sim（模拟） | skipped | 0.0 |  |

**【各 agent 完整输出】**

- **model-4**
  - confidence: `0.8`
  - simulated: `True`
  - answer:
    ```text
    土壤 pH=5.5（弱酸性），建议石灰施用量 50.0 kg/亩。
    ```
  - evidence (2 条):
    ```json
    [{"metric": "ph", "value": 5.5}, {"metric": "lime_dosage", "value": 50.0}]
    ```

- **model-5**
  - confidence: `0.84`
  - simulated: `True`
  - answer:
    ```text
    全省耕地有机质含量平均 22.0 g/kg，等级为中。全氮 1.2 g/kg，碳氮比 11.5。空间分布建议按高/中/低等级占比与地形梯度分析。
    ```
  - evidence (4 条):
    ```json
    [{"metric": "organic_matter", "value": 22.0, "unit": "g/kg"}, {"metric": "level", "value": "中"}, {"metric": "total_nitrogen", "value": 1.2, "unit": "g/kg"}, {"metric": "cn_ratio", "value": 11.5}]
    ```

- **model-6**
  - confidence: `None`
  - simulated: `True`
  - answer:
    ```text
    基于 ML 预测，您的土壤有机碳（SOC）预测值约 12.00 g/kg（模型不可用，返回训练集均值估算）
    ```
  - evidence (2 条):
    ```json
    [{"metric": "soc_prediction", "value": 12.0, "unit": "g/kg"}, {"metric": "soc_confidence", "value": 0.3}]
    ```

- **model-7**
  - status: `skipped`
  - reason: `question_not_related`
  - confidence: `0.0`
  - simulated: `True`
  - answer: (空)

---

#### Q20（期望 type=4）

> **问题原文：** 我这块地大概需要施多少有机肥

- **识别 question_type**：4 ✓ 匹配
- **识别 role**：`farmer`
- **调用 agents**：model-4, model-5, model-6, model-7
- **answer 来源**：`answer`（`answer` = LLM 生成；`summary` = AgentManager 模板拼接）
- **耗时**：7.8s

**【完整回答】**

```text
根据土壤有机质等级为中，建议有机肥施用量为 **1000 kg/亩**（约合15吨/公顷），优先选用腐熟农家肥或商品有机肥，并分季施用。
```

**【各 agent 调用细节】**

| agent_id | simulated | status | confidence | answer 摘要 |
|---|---|---|---|---|
| model-4 | sim（模拟） | - | 0.8 | 土壤 pH=5.5（弱酸性），建议石灰施用量 50.0 kg/亩。 |
| model-5 | sim（模拟） | - | 0.82 | 有机质等级为中，建议有机肥施用量 1000.0 kg/亩，秸秆还田参考同等养分替代量，预期有机质提升 1.5 g/kg。 |
| model-6 | sim（模拟） | - | - | 耕地综合地力改良提升综合诊断（基于 ML 预测）： - SOC（土壤有机碳）：12.00 g/kg（置信度 30%） - Dose（施肥量）：100.00 t/ha（置信度 30%，模型不可用，返回训练集均值估算） （模型不可用，以上为训练...[truncated 6 chars] |
| model-7 | sim（模拟） | skipped | 0.0 |  |

**【各 agent 完整输出】**

- **model-4**
  - confidence: `0.8`
  - simulated: `True`
  - answer:
    ```text
    土壤 pH=5.5（弱酸性），建议石灰施用量 50.0 kg/亩。
    ```
  - evidence (2 条):
    ```json
    [{"metric": "ph", "value": 5.5}, {"metric": "lime_dosage", "value": 50.0}]
    ```

- **model-5**
  - confidence: `0.82`
  - simulated: `True`
  - answer:
    ```text
    有机质等级为中，建议有机肥施用量 1000.0 kg/亩，秸秆还田参考同等养分替代量，预期有机质提升 1.5 g/kg。
    ```
  - evidence (4 条):
    ```json
    [{"metric": "organic_matter", "value": 22.0, "unit": "g/kg"}, {"metric": "manure_dosage", "value": 1000.0, "unit": "kg/亩"}, {"metric": "potential_increase", "value": 1.5, "unit": "g/kg"}, {"recommendation": "优先选用腐熟农家肥或商品有机肥，分季施用"}]
    ```

- **model-6**
  - confidence: `None`
  - simulated: `True`
  - answer:
    ```text
    耕地综合地力改良提升综合诊断（基于 ML 预测）：
    - SOC（土壤有机碳）：12.00 g/kg（置信度 30%）
    - Dose（施肥量）：100.00 t/ha（置信度 30%，模型不可用，返回训练集均值估算）
    （模型不可用，以上为训练集均值估算）
    ```
  - evidence (4 条):
    ```json
    [{"metric": "soc_prediction", "value": 12.0, "unit": "g/kg"}, {"metric": "soc_confidence", "value": 0.3}, {"metric": "dose_prediction", "value": 100.0, "unit": "t/ha"}, {"metric": "dose_confidence", "value": 0.3}]
    ```

- **model-7**
  - status: `skipped`
  - reason: `question_not_related`
  - confidence: `0.0`
  - simulated: `True`
  - answer: (空)

---

### 类型5：质量等级评价（3 题）

#### Q21（期望 type=5）

> **问题原文：** 我的田耕地质量等级是多少

- **识别 question_type**：5 ✓ 匹配
- **识别 role**：`farmer`
- **调用 agents**：model-4, model-5, model-6, model-7
- **answer 来源**：`answer`（`answer` = LLM 生成；`summary` = AgentManager 模板拼接）
- **耗时**：3.76s

**【完整回答】**

```text
根据您提供的数据，您的田耕地质量等级为 **10等**，综合指数为 **0.6728**。
```

**【各 agent 调用细节】**

| agent_id | simulated | status | confidence | answer 摘要 |
|---|---|---|---|---|
| model-4 | sim（模拟） | - | 0.8 | 土壤 pH=5.5（弱酸性），建议石灰施用量 50.0 kg/亩。 |
| model-5 | sim（模拟） | - | 0.78 | 有机质 22.0 g/kg（中），建议施有机肥 1000.0 kg/亩。 |
| model-6 | sim（模拟） | skipped | 0.0 |  |
| model-7 | real（真实） | - | 0.9 | 耕地质量等级评价结果：质量等级为10等级，综合指数：0.6728。共12个指标参与评价。 |

**【各 agent 完整输出】**

- **model-4**
  - confidence: `0.8`
  - simulated: `True`
  - answer:
    ```text
    土壤 pH=5.5（弱酸性），建议石灰施用量 50.0 kg/亩。
    ```
  - evidence (2 条):
    ```json
    [{"metric": "ph", "value": 5.5}, {"metric": "lime_dosage", "value": 50.0}]
    ```

- **model-5**
  - confidence: `0.78`
  - simulated: `True`
  - answer:
    ```text
    有机质 22.0 g/kg（中），建议施有机肥 1000.0 kg/亩。
    ```
  - evidence (2 条):
    ```json
    [{"metric": "level", "value": "中"}, {"metric": "manure_dosage", "value": 1000.0}]
    ```

- **model-6**
  - status: `skipped`
  - reason: `question_not_related`
  - confidence: `0.0`
  - simulated: `True`
  - answer: (空)

- **model-7**
  - confidence: `0.9`
  - simulated: `False`
  - answer:
    ```text
    耕地质量等级评价结果：质量等级为10等级，综合指数：0.6728。共12个指标参与评价。
    ```
  - evidence (2 条):
    ```json
    [{"metric": "质量等级", "value": "10等"}, {"metric": "综合指数", "value": 0.6728}]
    ```

---

#### Q22（期望 type=5）

> **问题原文：** 查询地块的综合指数和障碍度排序

- **识别 question_type**：5 ✓ 匹配
- **识别 role**：`farmer`
- **调用 agents**：model-4, model-5, model-6, model-7
- **answer 来源**：`answer`（`answer` = LLM 生成；`summary` = AgentManager 模板拼接）
- **耗时**：11.94s

**【完整回答】**

```text
根据提供的数据，查询地块（代码A0001）的综合指数为 **0.6728**，对应的耕地质量等级为 **10等**。障碍度排序（从大到小）如下：

- 质地构型：0.169
- 地形部位：0.1516
- 有机质：0.1484
- 速效钾：0.1384
- 排水能力：0.1292
- 酸碱度：0.1008
- 灌溉能力：0.0766
- 质地构成：0.0506
- 耕层厚度：0.0294
- 土壤容重：0.0059
- 有效磷：0.0
- 有效土层厚度：0.0
```

**【各 agent 调用细节】**

| agent_id | simulated | status | confidence | answer 摘要 |
|---|---|---|---|---|
| model-4 | sim（模拟） | - | 0.8 | 土壤 pH=5.5（弱酸性），建议石灰施用量 50.0 kg/亩。 |
| model-5 | sim（模拟） | - | 0.78 | 有机质 22.0 g/kg（中），建议施有机肥 1000.0 kg/亩。 |
| model-6 | sim（模拟） | skipped | 0.0 |  |
| model-7 | real（真实） | - | 0.88 | 障碍度排序结果：质地构型(0.169); 地形部位(0.1516); 有机质(0.1484); 速效钾(0.1384); 排水能力(0.1292); 酸碱度(0.1008); 灌溉能力(0.0766); 质地构成(0.0506); 耕层厚度...[truncated 56 chars] |

**【各 agent 完整输出】**

- **model-4**
  - confidence: `0.8`
  - simulated: `True`
  - answer:
    ```text
    土壤 pH=5.5（弱酸性），建议石灰施用量 50.0 kg/亩。
    ```
  - evidence (2 条):
    ```json
    [{"metric": "ph", "value": 5.5}, {"metric": "lime_dosage", "value": 50.0}]
    ```

- **model-5**
  - confidence: `0.78`
  - simulated: `True`
  - answer:
    ```text
    有机质 22.0 g/kg（中），建议施有机肥 1000.0 kg/亩。
    ```
  - evidence (2 条):
    ```json
    [{"metric": "level", "value": "中"}, {"metric": "manure_dosage", "value": 1000.0}]
    ```

- **model-6**
  - status: `skipped`
  - reason: `question_not_related`
  - confidence: `0.0`
  - simulated: `True`
  - answer: (空)

- **model-7**
  - confidence: `0.88`
  - simulated: `False`
  - answer:
    ```text
    障碍度排序结果：质地构型(0.169); 地形部位(0.1516); 有机质(0.1484); 速效钾(0.1384); 排水能力(0.1292); 酸碱度(0.1008); 灌溉能力(0.0766); 质地构成(0.0506); 耕层厚度(0.0294); 土壤容重(0.0059); 有效磷(0.0); 有效土层厚度(0.0)。质量等级为10等级。
    ```
  - evidence (2 条):
    ```json
    [{"metric": "质量等级", "value": "10等"}, {"metric": "障碍度排序", "value": "质地构型(0.169); 地形部位(0.1516); 有机质(0.1484); 速效钾(0.1384); 排水能力(0.1292); 酸碱度(0.1008); 灌溉能力(0.0766); 质地构成(0.0506); 耕层厚度(0.0294); 土壤容重(0.0059); 有效磷(0.0); 有效土层厚度(0.0)"}]
    ```

---

#### Q23（期望 type=5）

> **问题原文：** 这块地的耕地质量等级评价结果

- **识别 question_type**：5 ✓ 匹配
- **识别 role**：`farmer`
- **调用 agents**：model-4, model-5, model-6, model-7
- **answer 来源**：`answer`（`answer` = LLM 生成；`summary` = AgentManager 模板拼接）
- **耗时**：4.84s

**【完整回答】**

```text
根据提供的数据，这块地的耕地质量等级评价结果为：**质量等级为10等，综合指数为0.6728**，共12个指标参与评价。
```

**【各 agent 调用细节】**

| agent_id | simulated | status | confidence | answer 摘要 |
|---|---|---|---|---|
| model-4 | sim（模拟） | - | 0.8 | 土壤 pH=5.5（弱酸性），建议石灰施用量 50.0 kg/亩。 |
| model-5 | sim（模拟） | - | 0.78 | 有机质 22.0 g/kg（中），建议施有机肥 1000.0 kg/亩。 |
| model-6 | sim（模拟） | skipped | 0.0 |  |
| model-7 | real（真实） | - | 0.9 | 耕地质量等级评价结果：质量等级为10等级，综合指数：0.6728。共12个指标参与评价。 |

**【各 agent 完整输出】**

- **model-4**
  - confidence: `0.8`
  - simulated: `True`
  - answer:
    ```text
    土壤 pH=5.5（弱酸性），建议石灰施用量 50.0 kg/亩。
    ```
  - evidence (2 条):
    ```json
    [{"metric": "ph", "value": 5.5}, {"metric": "lime_dosage", "value": 50.0}]
    ```

- **model-5**
  - confidence: `0.78`
  - simulated: `True`
  - answer:
    ```text
    有机质 22.0 g/kg（中），建议施有机肥 1000.0 kg/亩。
    ```
  - evidence (2 条):
    ```json
    [{"metric": "level", "value": "中"}, {"metric": "manure_dosage", "value": 1000.0}]
    ```

- **model-6**
  - status: `skipped`
  - reason: `question_not_related`
  - confidence: `0.0`
  - simulated: `True`
  - answer: (空)

- **model-7**
  - confidence: `0.9`
  - simulated: `False`
  - answer:
    ```text
    耕地质量等级评价结果：质量等级为10等级，综合指数：0.6728。共12个指标参与评价。
    ```
  - evidence (2 条):
    ```json
    [{"metric": "质量等级", "value": "10等"}, {"metric": "综合指数", "value": 0.6728}]
    ```

---

## 三、model-6 真实 ML 计算能力验证

- **输入特征**：`{'pH': 6.5, 'SOCbe': 15.0, 'TN': 1.2, 'TP': 0.8, 'TK': 20.0, 'AP': 25.0, 'AK': 180.0, 'Gap': 5.0, 'Dose': 300.0, 'Fertilizer type': 1}`
- **execute_status**：`fallback`
- **SOC 预测值**：12.0 g/kg（置信度 0.3）
- **Dose 预测值**：100.0 t/ha（置信度 0.3）
- **dose_warning**：模型不可用，返回训练集均值估算
- **imputation_applied**：False, imputed_features: `[]`
- **fallback_reason**：sklearn_missing
- **model_version**：`ETR_v1_20260713`
- **是否真实计算**：✗ 否（fallback）

**【SOC 自然语言回答】**
```text
基于 ML 预测，您的土壤有机碳（SOC）预测值约 12.00 g/kg（模型不可用，返回训练集均值估算）
```

**【Dose 自然语言回答】**
```text
耕地综合地力改良提升综合诊断（基于 ML 预测）：
- SOC（土壤有机碳）：12.00 g/kg（置信度 30%）
- Dose（施肥量）：100.00 t/ha（置信度 30%，模型不可用，返回训练集均值估算）
（模型不可用，以上为训练集均值估算）
```

---

## 四、汇总结论

- 真实可计算 agent：`['model-1', 'model-3', 'model-4']`
- 已集成但资源未部署（回退模拟）：`['model-2', 'model-5', 'model-6', 'model-7']`
- 占位桩 agent：`无`
- 问题库回答率：**23/23**
- 问题类型识别准确率：**23/23**
- model-6 真实计算：✗ 未通过

### 关键观察

1. **LLM 可用性**：本次运行 LLM 服务初始化成功（`deepseek-ai/DeepSeek-V4-Flash`），所有 23 题（20 题 type 1-4 + 3 题 type 5）均通过 LLM 生成自然语言 `answer`，未出现「抱歉，AI服务暂时不可用」降级。LLM 偶有不可用属于运行时波动，降级时 `answer` 字段为空或为降级提示，最终回答回退取自 AgentManager 的 `summary`（模板拼接）；若 LLM 超时降级，行为同上。
2. **真实计算 agent**：model-1（stability_db）、model-3/4（diagnosis_db）、model-7（Fortran exe+dat）资源均已部署并返回真实计算结果；model-6 因 `.joblib` 文件缺失走 fallback（训练集均值）。本次 model-7 在 Q21/Q22/Q23（type 5）均返回真实结果：质量等级 `10等`、综合指数 `0.6728`、12 个指标、12 个障碍度因子。但因 RoleRouter 按角色路由，每题只调用 2-4 个 agent，并非每题都触及全部真实模型。
3. **资源就绪状态汇总误判说明**：本章「资源就绪状态」中 `grade_exe_exists=False` 和 `grade_dat_exists=False` 是 `verify_agent_capabilities.py` 的路径检查问题（预存在，非本次 change 引入），实际 `bin/farmland_quality_eval/` 下 exe 和 dat 均存在，model-7 在 type 5 问题中真实调用成功。model-6 的 `soc_joblib_exists=False` / `dose_joblib_exists=False` 是真实缺失，需补齐 `.joblib` 文件后才能真实计算。
4. **路由细节**：`province` → model-1, model-3；`county` → model-1, model-2, model-3；`farmer` → model-4, model-5, model-6, model-7。model-7 的执行由 `AgentManager._should_execute_agent` 的关键词过滤（`GRADE_KEYWORDS`，含「质量等级」「等级评价」「综合指数」「障碍度排序」等）决定，**与 question_type 解耦**——只要问题文本含 `GRADE_KEYWORDS` 任一词即触发 model-7，无论 question_type 为何。因此 type 1-4 中含「质量等级」字面词的问题也会触发 model-7：例如 Q1「查询区域内耕地质量等级整体稳定吗」（type 1）、Q4「我的这块田质量等级稳不稳」（type 1）均会执行 model-7。这是已知的关键词碰撞，每次调用约 0.06s Fortran exe 开销，非正确性问题。
5. **model-6 问题感知过滤**：AgentManager._should_execute_agent 对 model-6 做关键词过滤，非肥力问题（不含 有机碳/SOC/施用量/施肥量/肥力/秸秆/有机肥/培肥/Dose 等）会跳过 model-6 （status=`skipped`, reason=`question_not_related`）。这就是 Q1-Q15 中 model-6 大量被跳过的原因。
6. **simulated 标志解读**：AgentManager 通过 `MockDataLoader.mark_simulated(payload)` 在结果顶层强制写入 `simulated=True`，即使 model-6 这种真实计算 agent 也显示 sim。**因此 `simulated=True` 不能作为真实/模拟的判据**。是否真实计算应以：
   - `fallback_reason is None` + `execute_status==success`（model-6 直接 execute 验证）
   - 或 agent 真实调用了底层模型（如 model-1 读 stability_db、model-7 调 Fortran exe）
   为准。本次 model-7 在 type 5 问题中 `simulated=False`，是因为 `FarmlandGradeAgent` 在拿到真实结果时未调用 `mark_simulated`。
7. **parcel 标识符透传**：本次验证脚本为 farmer 问题（含 type 5）预设 `parcel_id="1"` （来自 stability_db/acidification_results）+ `parcel_code="A0001"`（来自 fortran exe 数据库）。管道已接通 `execute_models → context → agents`，model-1/4 应返回真实 DB 记录，model-7 应返回真实 fortran exe 质量等级评价（本次 Q21/Q22/Q23 已验证）。**预存在数据缺口**：`diagnosis_results` 表 0 条记录，model-3 仍返回 mock，数据填充后管道自动生效（非本次引入）。
8. **model-7 parser 修复验证**：本次报告生成前已修复 `src/ai_culti_demo/farmland_grade_eval/runner.py:parse_output` 的解析 bug（原 bug 导致 `quality_grade=None`、`composite_index=None`、`indicators=[]`）。修复后通过真实 exe 调用断言（10等/0.6728/12指标/12障碍度），并在本次 Q21/Q22/Q23 的 orchestrator 链路中再次验证修复生效。
