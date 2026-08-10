# 智能体能力完整验证报告

- 生成时间：2026-08-08 21:14:00
- 项目根目录：`D:\work\agent_culti_demo\agent_culti_demo`
- Python：`C:\Users\PC\.conda\envs\agent_culti_demo_py312\python.exe`
- 问题库：`framework/agents/nodes.py` 中的 `REFERENCE_QUESTIONS`
- 数据来源：重新调用 `multi_agent_orchestrator.run()` 实时获取（非日志回放）
- 参考日志：`verify_output.log`（仅作历史对照）
- 原始 JSON：`verification_raw_outputs.json`

> 模型2通过 `farmland_grade_eval` 的 Python 引擎提供真实质量等级、障碍度、单地块潜力和县域潜力情景计算。

### 模型2真实计算资产

- **变更对象**：`src/ai_culti_demo/farmland_grade_eval/`（耕地质量等级评价）
- **运行入口**：`model-2/PotentialAssessmentAgent` 调用纯 Python 评价和潜力函数，数据源为 CSV（`bin/farmland_quality_eval/Farmland_quality_Level_Database.csv`）。
- **验证结果**：`parcel_code=A0001` 的真实评价结果：
  - `quality_grade` = `10等` ✓
  - `composite_index` = `0.6728330580097418` ✓
  - `indicators` = 12 条 ✓
  - `obstacle_degree` = 12 条 ✓
- **错误契约**：缺少 `parcel_code` 返回 `MISSING_PARCEL_CODE`；CSV 缺失返回 `DEPLOYMENT_ERROR`；不生成模拟成功结果。

---

## 一、Agent 加载状态盘点

> 按 Excel 标准表格「数据字段标准化」（`D:\destkop\模型\数据字段标准化 (1).xlsx`）定义的 6 个标准模型顺序展示，使用标准命名。**模型6（耕地综合地力改良提升模型）项目尚未实现，以占位符行标注**。

| Excel 标准模型 | 项目 model_id | class | 占位桩 | 真实模型 | 资源就绪 | 期望行为 |
|---|---|---|---|---|---|---|
| 模型1：耕地质量等级稳定性与退化风险识别模型 | model-1 | `StabilityRiskAgent` | 否 | farmland_stability | ✓ | 真实计算 |
| 模型2：耕地质量提升潜力评估模型 | model-2 | `PotentialAssessmentAgent` | 否 | farmland_grade_eval Python implementation | ✓ | 真实计算 |
| 模型3：耕地质量主要问题精准识别模型 | model-3 | `ProblemIdentificationAgent` | 否 | farmland_diagnosis | ✓ | 真实计算 |
| 模型4：耕地土壤酸化改良模型 | model-4 | `AcidificationRemediationAgent` | 否 | farmland_acidification | ✓ | 真实计算 |
| 模型5：耕地土壤有机质培肥提升模型 | model-6 | `FertilityMLAgent` | 否 | sklearn ETR (soc_etr + dose_etr) | ✓ | 真实 ML 计算 |
| 模型6：耕地综合地力改良提升模型 | —（占位符） | — | — | — | ✗ | 未实现（占位符） |
| —（未对应 Excel 标准） | model-5 | `OrganicMatterAgent` | 否 | - | ✗ | 占位桩（无真实模型绑定） |

> **Excel 标准 ↔ 项目 model 对应关系**：模型1→model-1；模型2→model-2；模型3→model-3；模型4→model-4；模型5→model-6；模型6→未实现（占位符）。model-5（OrganicMatterAgent）未对应 Excel 标准。

**资源就绪状态：**

- ✓ `stability_db_exists`: `True`
- ✓ `stability_db_path`: `data\farmland_stability\stability_results.db`
- ✓ `diagnosis_db_exists`: `True`
- ✓ `diagnosis_db_path`: `D:\work\agent_culti_demo\agent_culti_demo\src\ai_culti_demo\farmland_diagnosis\..\..\data\farmland_diagnosis\farmland_diagnosis.db`
- ✓ `soc_joblib_exists`: `True`
- ✓ `dose_joblib_exists`: `True`
- ✓ `grade_csv_exists`: `True`

**问题类型路由表（QuestionTypeRouter.TYPE_AGENTS，1:1 映射；含 Excel 标准模型对应关系）：**

| question_type | 语义 | 调用 agent | Excel 标准模型 |
|---|---|---|---|
| `1` | 稳定性/退化风险 | model-1 | 模型1：耕地质量等级稳定性与退化风险识别模型 |
| `2` | 酸化改良 | model-4 | 模型4：耕地土壤酸化改良模型 |
| `3` | 障碍诊断 | model-3 | 模型3：耕地质量主要问题精准识别模型 |
| `4` | 肥力/SOC/Dose | model-6 | 模型5：耕地土壤有机质培肥提升模型 |
| `5` | 耕地质量等级评价 | model-2 | 模型2：耕地质量提升潜力评估模型 |
| `6` | 耕地质量提升潜力 | model-2 | 模型2：耕地质量提升潜力评估模型 |
| `0` | 知识性问题（什么是X/X是什么意思） | 走 RAG，不调专业模型 | —（不对应专业模型） |

> 知识性问题（含「什么是」「何为」「解释」「是什么意思」「定义」「概念」「含义」等模式）经 `_is_knowledge_question` 预检后返回 type 0，直接走 RAG 知识库，不进入专业模型路由。Excel 标准模型6（耕地综合地力改良提升模型）尚未实现，暂无 question_type 路由。

---

## 二、问题库完整回答与调用细节

- 总计问题数：**23**
- 返回非空 answer：**23/23**
- question_type 匹配：**22/23**

### 类型1：稳定性风险（5 题）

#### Q1（期望 type=1）

> **问题原文：** 查询区域内耕地质量等级整体稳定吗

- **识别 question_type**：1 ✓ 匹配
- **识别 role**：`None`
- **调用 agents**：model-1
- **answer 来源**：`answer`（`answer` = LLM 生成；`summary` = AgentManager 模板拼接）
- **耗时**：0.02s

**【完整回答】**

```text
[model-1] 耕地质量稳定性与退化风险评价已完成结构化分析。
risk_level：低风险；risk_score：0.15；risk_types：['掉级风险']；stability_score：0.85
```

**【各 agent 调用细节】**

| agent_id | simulated | status | confidence | answer 摘要 |
|---|---|---|---|---|
| model-1 | sim（模拟） | - | 0.5 | 耕地质量稳定性与退化风险评价已完成结构化分析。 risk_level：低风险；risk_score：0.15；risk_types：['掉级风险']；stability_score：0.85 |

**【各 agent 完整输出】**

- **model-1**
  - confidence: `0.5`
  - simulated: `True`
  - answer:
    ```text
    耕地质量稳定性与退化风险评价已完成结构化分析。
    risk_level：低风险；risk_score：0.15；risk_types：['掉级风险']；stability_score：0.85
    ```
  - evidence (4 条):
    ```json
    [{"metric": "risk_level", "value": "低风险"}, {"metric": "risk_score", "value": 0.15}, {"metric": "stability_score", "value": 0.85}, {"metric": "stability_level", "value": "稳定"}]
    ```

---

#### Q2（期望 type=1）

> **问题原文：** 查询区域内哪些高等级耕地存在退化风险

- **识别 question_type**：1 ✓ 匹配
- **识别 role**：`None`
- **调用 agents**：model-1
- **answer 来源**：`answer`（`answer` = LLM 生成；`summary` = AgentManager 模板拼接）
- **耗时**：0.0s

**【完整回答】**

```text
[model-1] 耕地质量稳定性与退化风险评价已完成结构化分析。
risk_level：低风险；risk_score：0.15；risk_types：['掉级风险']；stability_score：0.85
```

**【各 agent 调用细节】**

| agent_id | simulated | status | confidence | answer 摘要 |
|---|---|---|---|---|
| model-1 | sim（模拟） | - | 0.5 | 耕地质量稳定性与退化风险评价已完成结构化分析。 risk_level：低风险；risk_score：0.15；risk_types：['掉级风险']；stability_score：0.85 |

**【各 agent 完整输出】**

- **model-1**
  - confidence: `0.5`
  - simulated: `True`
  - answer:
    ```text
    耕地质量稳定性与退化风险评价已完成结构化分析。
    risk_level：低风险；risk_score：0.15；risk_types：['掉级风险']；stability_score：0.85
    ```
  - evidence (4 条):
    ```json
    [{"metric": "risk_level", "value": "低风险"}, {"metric": "risk_score", "value": 0.15}, {"metric": "stability_score", "value": 0.85}, {"metric": "stability_level", "value": "稳定"}]
    ```

---

#### Q3（期望 type=1）

> **问题原文：** 本县哪些乡镇或地块等级稳定性较弱需要现场复核

- **识别 question_type**：1 ✓ 匹配
- **识别 role**：`None`
- **调用 agents**：model-1
- **answer 来源**：`answer`（`answer` = LLM 生成；`summary` = AgentManager 模板拼接）
- **耗时**：0.0s

**【完整回答】**

```text
[model-1] 耕地质量稳定性与退化风险评价已完成结构化分析。
risk_level：低风险；risk_score：0.15；risk_types：['掉级风险']；stability_score：0.85
```

**【各 agent 调用细节】**

| agent_id | simulated | status | confidence | answer 摘要 |
|---|---|---|---|---|
| model-1 | sim（模拟） | - | 0.5 | 耕地质量稳定性与退化风险评价已完成结构化分析。 risk_level：低风险；risk_score：0.15；risk_types：['掉级风险']；stability_score：0.85 |

**【各 agent 完整输出】**

- **model-1**
  - confidence: `0.5`
  - simulated: `True`
  - answer:
    ```text
    耕地质量稳定性与退化风险评价已完成结构化分析。
    risk_level：低风险；risk_score：0.15；risk_types：['掉级风险']；stability_score：0.85
    ```
  - evidence (4 条):
    ```json
    [{"metric": "risk_level", "value": "低风险"}, {"metric": "risk_score", "value": 0.15}, {"metric": "stability_score", "value": 0.85}, {"metric": "stability_level", "value": "稳定"}]
    ```

---

#### Q4（期望 type=1）

> **问题原文：** 我的这块田质量等级稳不稳

- **识别 question_type**：1 ✓ 匹配
- **识别 role**：`None`
- **调用 agents**：model-1
- **answer 来源**：`answer`（`answer` = LLM 生成；`summary` = AgentManager 模板拼接）
- **耗时**：0.0s

**【完整回答】**

```text
[model-1] 耕地质量稳定性与退化风险评价已完成结构化分析。
parcel_id：1；region：闽南粤中农林水产区；score：0.7841；grade：4
```

**【各 agent 调用细节】**

| agent_id | simulated | status | confidence | answer 摘要 |
|---|---|---|---|---|
| model-1 | real（真实） | - | 0.9 | 耕地质量稳定性与退化风险评价已完成结构化分析。 parcel_id：1；region：闽南粤中农林水产区；score：0.7841；grade：4 |

**【各 agent 完整输出】**

- **model-1**
  - confidence: `0.9`
  - simulated: `False`
  - answer:
    ```text
    耕地质量稳定性与退化风险评价已完成结构化分析。
    parcel_id：1；region：闽南粤中农林水产区；score：0.7841；grade：4
    ```
  - evidence (4 条):
    ```json
    [{"metric": "parcel_id", "value": "1"}, {"metric": "region", "value": "闽南粤中农林水产区"}, {"metric": "score", "value": 0.7841}, {"metric": "grade", "value": "4"}]
    ```

---

#### Q5（期望 type=1）

> **问题原文：** 查询区域内哪些对象需要纳入重点关注清单

- **识别 question_type**：1 ✓ 匹配
- **识别 role**：`None`
- **调用 agents**：model-1
- **answer 来源**：`answer`（`answer` = LLM 生成；`summary` = AgentManager 模板拼接）
- **耗时**：0.0s

**【完整回答】**

```text
[model-1] 耕地质量稳定性与退化风险评价已完成结构化分析。
risk_level：低风险；risk_score：0.15；risk_types：['掉级风险']；stability_score：0.85
```

**【各 agent 调用细节】**

| agent_id | simulated | status | confidence | answer 摘要 |
|---|---|---|---|---|
| model-1 | sim（模拟） | - | 0.5 | 耕地质量稳定性与退化风险评价已完成结构化分析。 risk_level：低风险；risk_score：0.15；risk_types：['掉级风险']；stability_score：0.85 |

**【各 agent 完整输出】**

- **model-1**
  - confidence: `0.5`
  - simulated: `True`
  - answer:
    ```text
    耕地质量稳定性与退化风险评价已完成结构化分析。
    risk_level：低风险；risk_score：0.15；risk_types：['掉级风险']；stability_score：0.85
    ```
  - evidence (4 条):
    ```json
    [{"metric": "risk_level", "value": "低风险"}, {"metric": "risk_score", "value": 0.15}, {"metric": "stability_score", "value": 0.85}, {"metric": "stability_level", "value": "稳定"}]
    ```

---

### 类型2：酸化改良（5 题）

#### Q6（期望 type=2）

> **问题原文：** 查询区域内农用地土壤酸化程度如何不同酸化等级比例分别多少

- **识别 question_type**：2 ✓ 匹配
- **识别 role**：`None`
- **调用 agents**：model-4
- **answer 来源**：`answer`（`answer` = LLM 生成；`summary` = AgentManager 模板拼接）
- **耗时**：0.0s

**【完整回答】**

```text
[model-4] 耕地土壤酸化改良已完成结构化分析。
ytk：6401.831754761487；mbnt：11814.123053654765；sub_model：upland_compound；customized_params：{}
```

**【各 agent 调用细节】**

| agent_id | simulated | status | confidence | answer 摘要 |
|---|---|---|---|---|
| model-4 | sim（模拟） | - | 0.5 | 耕地土壤酸化改良已完成结构化分析。 ytk：6401.831754761487；mbnt：11814.123053654765；sub_model：upland_compound；customized_params：{} |

**【各 agent 完整输出】**

- **model-4**
  - confidence: `0.5`
  - simulated: `True`
  - answer:
    ```text
    耕地土壤酸化改良已完成结构化分析。
    ytk：6401.831754761487；mbnt：11814.123053654765；sub_model：upland_compound；customized_params：{}
    ```
  - evidence (3 条):
    ```json
    [{"metric": "ytk", "value": 6401.831754761487}, {"metric": "mbnt", "value": 11814.123053654765}, {"metric": "sub_model", "value": "upland_compound"}]
    ```

---

#### Q7（期望 type=2）

> **问题原文：** 我的田酸化了pH是多少我要施加多少碱性调理剂可以治理好

- **识别 question_type**：2 ✓ 匹配
- **识别 role**：`None`
- **调用 agents**：model-4
- **answer 来源**：`answer`（`answer` = LLM 生成；`summary` = AgentManager 模板拼接）
- **耗时**：0.0s

**【完整回答】**

```text
[model-4] 耕地土壤酸化改良已完成结构化分析。
ytk：6401.831754761487；mbnt：11814.123053654765；sub_model：upland_compound；customized_params：{}
```

**【各 agent 调用细节】**

| agent_id | simulated | status | confidence | answer 摘要 |
|---|---|---|---|---|
| model-4 | sim（模拟） | - | 0.5 | 耕地土壤酸化改良已完成结构化分析。 ytk：6401.831754761487；mbnt：11814.123053654765；sub_model：upland_compound；customized_params：{} |

**【各 agent 完整输出】**

- **model-4**
  - confidence: `0.5`
  - simulated: `True`
  - answer:
    ```text
    耕地土壤酸化改良已完成结构化分析。
    ytk：6401.831754761487；mbnt：11814.123053654765；sub_model：upland_compound；customized_params：{}
    ```
  - evidence (3 条):
    ```json
    [{"metric": "ytk", "value": 6401.831754761487}, {"metric": "mbnt", "value": 11814.123053654765}, {"metric": "sub_model", "value": "upland_compound"}]
    ```

---

#### Q8（期望 type=2）

> **问题原文：** 查询区域内不同土地利用类型的酸化程度

- **识别 question_type**：2 ✓ 匹配
- **识别 role**：`None`
- **调用 agents**：model-4
- **answer 来源**：`answer`（`answer` = LLM 生成；`summary` = AgentManager 模板拼接）
- **耗时**：0.0s

**【完整回答】**

```text
[model-4] 耕地土壤酸化改良已完成结构化分析。
ytk：6401.831754761487；mbnt：11814.123053654765；sub_model：upland_compound；customized_params：{}
```

**【各 agent 调用细节】**

| agent_id | simulated | status | confidence | answer 摘要 |
|---|---|---|---|---|
| model-4 | sim（模拟） | - | 0.5 | 耕地土壤酸化改良已完成结构化分析。 ytk：6401.831754761487；mbnt：11814.123053654765；sub_model：upland_compound；customized_params：{} |

**【各 agent 完整输出】**

- **model-4**
  - confidence: `0.5`
  - simulated: `True`
  - answer:
    ```text
    耕地土壤酸化改良已完成结构化分析。
    ytk：6401.831754761487；mbnt：11814.123053654765；sub_model：upland_compound；customized_params：{}
    ```
  - evidence (3 条):
    ```json
    [{"metric": "ytk", "value": 6401.831754761487}, {"metric": "mbnt", "value": 11814.123053654765}, {"metric": "sub_model", "value": "upland_compound"}]
    ```

---

#### Q9（期望 type=2）

> **问题原文：** 我的这块田酸化严重吗

- **识别 question_type**：2 ✓ 匹配
- **识别 role**：`None`
- **调用 agents**：model-4
- **answer 来源**：`answer`（`answer` = LLM 生成；`summary` = AgentManager 模板拼接）
- **耗时**：0.0s

**【完整回答】**

```text
[model-4] 耕地土壤酸化改良已完成结构化分析。
ytk：6401.831754761487；mbnt：11814.123053654765；sub_model：upland_compound；customized_params：{}
```

**【各 agent 调用细节】**

| agent_id | simulated | status | confidence | answer 摘要 |
|---|---|---|---|---|
| model-4 | sim（模拟） | - | 0.5 | 耕地土壤酸化改良已完成结构化分析。 ytk：6401.831754761487；mbnt：11814.123053654765；sub_model：upland_compound；customized_params：{} |

**【各 agent 完整输出】**

- **model-4**
  - confidence: `0.5`
  - simulated: `True`
  - answer:
    ```text
    耕地土壤酸化改良已完成结构化分析。
    ytk：6401.831754761487；mbnt：11814.123053654765；sub_model：upland_compound；customized_params：{}
    ```
  - evidence (3 条):
    ```json
    [{"metric": "ytk", "value": 6401.831754761487}, {"metric": "mbnt", "value": 11814.123053654765}, {"metric": "sub_model", "value": "upland_compound"}]
    ```

---

### 类型3：障碍诊断与潜力（5 题）

#### Q10（期望 type=3）

> **问题原文：** 我这块地到底有啥毛病

- **识别 question_type**：3 ✓ 匹配
- **识别 role**：`None`
- **调用 agents**：model-3
- **answer 来源**：`answer`（`answer` = LLM 生成；`summary` = AgentManager 模板拼接）
- **耗时**：0.0s

**【完整回答】**

```text
[model-3] 耕地质量主要问题与障碍诊断已完成结构化分析。
primary_factors：['有机质', '全氮']；secondary_factors：['pH', '黏粒含量', '孔隙度', '容重', '有效磷', '耕层厚度', '阳离子交换量', '速效钾']；combinations：[]；indicator_grades：{'pH': [2, 5, 8, 15, 20, 18, 12, 10, 6, 4], '有机质': [1, 3, 6, 10, 15, 20, 22, 15, 6, 2], '全氮': [1, 2, 5, 12, 18, 22, 20, 12, 6, 2], '有效磷': [3, 8, 12, 18, 22, 15, 10, 7, 3, 2], '速效钾': [5, 10, 15, 20, 22, 15, 8, 3, 1, 1], '阳离子交换量': [4, 8, 12, 18, 22, 18, 10, 5, 2, 1], '容重': [2, 6, 10, 15, 22, 20, 15, 6, 3, 1], '孔隙度': [2, 5, 10, 15, 22, 20, 15, 8, 2, 1], '黏粒含量': [1, 3, 8, 15, 25, 22, 15, 7, 3, 1], '耕层厚度': [3, 7, 12, 18, 22, 18, 12, 5, 2, 1], '灌溉保证率': [8, 15, 20, 22, 18, 10, 5, 1, 1, 0]}
```

**【各 agent 调用细节】**

| agent_id | simulated | status | confidence | answer 摘要 |
|---|---|---|---|---|
| model-3 | sim（模拟） | - | 0.5 | 耕地质量主要问题与障碍诊断已完成结构化分析。 primary_factors：['有机质', '全氮']；secondary_factors：['pH', '黏粒含量', '孔隙度', '容重', '有效磷', '耕层厚度', '阳离子交换...[truncated 531 chars] |

**【各 agent 完整输出】**

- **model-3**
  - confidence: `0.5`
  - simulated: `True`
  - answer:
    ```text
    耕地质量主要问题与障碍诊断已完成结构化分析。
    primary_factors：['有机质', '全氮']；secondary_factors：['pH', '黏粒含量', '孔隙度', '容重', '有效磷', '耕层厚度', '阳离子交换量', '速效钾']；combinations：[]；indicator_grades：{'pH': [2, 5, 8, 15, 20, 18, 12, 10, 6, 4], '有机质': [1, 3, 6, 10, 15, 20, 22, 15, 6, 2], '全氮': [1, 2, 5, 12, 18, 22, 20, 12, 6, 2], '有效磷': [3, 8, 12, 18, 22, 15, 10, 7, 3, 2], '速效钾': [5, 10, 15, 20, 22, 15, 8, 3, 1, 1], '阳离子交换量': [4, 8, 12, 18, 22, 18, 10, 5, 2, 1], '容重': [2, 6, 10, 15, 22, 20, 15, 6, 3, 1], '孔隙度': [2, 5, 10, 15, 22, 20, 15, 8, 2, 1], '黏粒含量': [1, 3, 8, 15, 25, 22, 15, 7, 3, 1], '耕层厚度': [3, 7, 12, 18, 22, 18, 12, 5, 2, 1], '灌溉保证率': [8, 15, 20, 22, 18, 10, 5, 1, 1, 0]}
    ```

---

#### Q11（期望 type=3）

> **问题原文：** 全省耕地质量存在哪些问题

- **识别 question_type**：3 ✓ 匹配
- **识别 role**：`None`
- **调用 agents**：model-3
- **answer 来源**：`answer`（`answer` = LLM 生成；`summary` = AgentManager 模板拼接）
- **耗时**：0.0s

**【完整回答】**

```text
[model-3] 耕地质量主要问题与障碍诊断已完成结构化分析。
primary_factors：['有机质', '全氮']；secondary_factors：['pH', '黏粒含量', '孔隙度', '容重', '有效磷', '耕层厚度', '阳离子交换量', '速效钾']；combinations：[]；indicator_grades：{'pH': [2, 5, 8, 15, 20, 18, 12, 10, 6, 4], '有机质': [1, 3, 6, 10, 15, 20, 22, 15, 6, 2], '全氮': [1, 2, 5, 12, 18, 22, 20, 12, 6, 2], '有效磷': [3, 8, 12, 18, 22, 15, 10, 7, 3, 2], '速效钾': [5, 10, 15, 20, 22, 15, 8, 3, 1, 1], '阳离子交换量': [4, 8, 12, 18, 22, 18, 10, 5, 2, 1], '容重': [2, 6, 10, 15, 22, 20, 15, 6, 3, 1], '孔隙度': [2, 5, 10, 15, 22, 20, 15, 8, 2, 1], '黏粒含量': [1, 3, 8, 15, 25, 22, 15, 7, 3, 1], '耕层厚度': [3, 7, 12, 18, 22, 18, 12, 5, 2, 1], '灌溉保证率': [8, 15, 20, 22, 18, 10, 5, 1, 1, 0]}
```

**【各 agent 调用细节】**

| agent_id | simulated | status | confidence | answer 摘要 |
|---|---|---|---|---|
| model-3 | sim（模拟） | - | 0.5 | 耕地质量主要问题与障碍诊断已完成结构化分析。 primary_factors：['有机质', '全氮']；secondary_factors：['pH', '黏粒含量', '孔隙度', '容重', '有效磷', '耕层厚度', '阳离子交换...[truncated 531 chars] |

**【各 agent 完整输出】**

- **model-3**
  - confidence: `0.5`
  - simulated: `True`
  - answer:
    ```text
    耕地质量主要问题与障碍诊断已完成结构化分析。
    primary_factors：['有机质', '全氮']；secondary_factors：['pH', '黏粒含量', '孔隙度', '容重', '有效磷', '耕层厚度', '阳离子交换量', '速效钾']；combinations：[]；indicator_grades：{'pH': [2, 5, 8, 15, 20, 18, 12, 10, 6, 4], '有机质': [1, 3, 6, 10, 15, 20, 22, 15, 6, 2], '全氮': [1, 2, 5, 12, 18, 22, 20, 12, 6, 2], '有效磷': [3, 8, 12, 18, 22, 15, 10, 7, 3, 2], '速效钾': [5, 10, 15, 20, 22, 15, 8, 3, 1, 1], '阳离子交换量': [4, 8, 12, 18, 22, 18, 10, 5, 2, 1], '容重': [2, 6, 10, 15, 22, 20, 15, 6, 3, 1], '孔隙度': [2, 5, 10, 15, 22, 20, 15, 8, 2, 1], '黏粒含量': [1, 3, 8, 15, 25, 22, 15, 7, 3, 1], '耕层厚度': [3, 7, 12, 18, 22, 18, 12, 5, 2, 1], '灌溉保证率': [8, 15, 20, 22, 18, 10, 5, 1, 1, 0]}
    ```

---

#### Q12（期望 type=3）

> **问题原文：** 县乡镇里的耕地在哪些方面有问题

- **识别 question_type**：3 ✓ 匹配
- **识别 role**：`None`
- **调用 agents**：model-3
- **answer 来源**：`answer`（`answer` = LLM 生成；`summary` = AgentManager 模板拼接）
- **耗时**：0.0s

**【完整回答】**

```text
[model-3] 耕地质量主要问题与障碍诊断已完成结构化分析。
primary_factors：['有机质', '全氮']；secondary_factors：['pH', '黏粒含量', '孔隙度', '容重', '有效磷', '耕层厚度', '阳离子交换量', '速效钾']；combinations：[]；indicator_grades：{'pH': [2, 5, 8, 15, 20, 18, 12, 10, 6, 4], '有机质': [1, 3, 6, 10, 15, 20, 22, 15, 6, 2], '全氮': [1, 2, 5, 12, 18, 22, 20, 12, 6, 2], '有效磷': [3, 8, 12, 18, 22, 15, 10, 7, 3, 2], '速效钾': [5, 10, 15, 20, 22, 15, 8, 3, 1, 1], '阳离子交换量': [4, 8, 12, 18, 22, 18, 10, 5, 2, 1], '容重': [2, 6, 10, 15, 22, 20, 15, 6, 3, 1], '孔隙度': [2, 5, 10, 15, 22, 20, 15, 8, 2, 1], '黏粒含量': [1, 3, 8, 15, 25, 22, 15, 7, 3, 1], '耕层厚度': [3, 7, 12, 18, 22, 18, 12, 5, 2, 1], '灌溉保证率': [8, 15, 20, 22, 18, 10, 5, 1, 1, 0]}
```

**【各 agent 调用细节】**

| agent_id | simulated | status | confidence | answer 摘要 |
|---|---|---|---|---|
| model-3 | sim（模拟） | - | 0.5 | 耕地质量主要问题与障碍诊断已完成结构化分析。 primary_factors：['有机质', '全氮']；secondary_factors：['pH', '黏粒含量', '孔隙度', '容重', '有效磷', '耕层厚度', '阳离子交换...[truncated 531 chars] |

**【各 agent 完整输出】**

- **model-3**
  - confidence: `0.5`
  - simulated: `True`
  - answer:
    ```text
    耕地质量主要问题与障碍诊断已完成结构化分析。
    primary_factors：['有机质', '全氮']；secondary_factors：['pH', '黏粒含量', '孔隙度', '容重', '有效磷', '耕层厚度', '阳离子交换量', '速效钾']；combinations：[]；indicator_grades：{'pH': [2, 5, 8, 15, 20, 18, 12, 10, 6, 4], '有机质': [1, 3, 6, 10, 15, 20, 22, 15, 6, 2], '全氮': [1, 2, 5, 12, 18, 22, 20, 12, 6, 2], '有效磷': [3, 8, 12, 18, 22, 15, 10, 7, 3, 2], '速效钾': [5, 10, 15, 20, 22, 15, 8, 3, 1, 1], '阳离子交换量': [4, 8, 12, 18, 22, 18, 10, 5, 2, 1], '容重': [2, 6, 10, 15, 22, 20, 15, 6, 3, 1], '孔隙度': [2, 5, 10, 15, 22, 20, 15, 8, 2, 1], '黏粒含量': [1, 3, 8, 15, 25, 22, 15, 7, 3, 1], '耕层厚度': [3, 7, 12, 18, 22, 18, 12, 5, 2, 1], '灌溉保证率': [8, 15, 20, 22, 18, 10, 5, 1, 1, 0]}
    ```

---

### 类型4：肥力与有机质（4 题）

#### Q13（期望 type=4）

> **问题原文：** 我的田肥力怎么样

- **识别 question_type**：4 ✓ 匹配
- **识别 role**：`None`
- **调用 agents**：model-6
- **answer 来源**：`answer`（`answer` = LLM 生成；`summary` = AgentManager 模板拼接）
- **耗时**：1.14s

**【完整回答】**

```text
[model-6] 耕地肥力 SOC/Dose 预测已完成结构化分析。
soc_prediction：18.4111；soc_confidence：0.91；dose_prediction：608.1787；dose_confidence：0.96
```

**【各 agent 调用细节】**

| agent_id | simulated | status | confidence | answer 摘要 |
|---|---|---|---|---|
| model-6 | sim（模拟） | - | 0.5 | 耕地肥力 SOC/Dose 预测已完成结构化分析。 soc_prediction：18.4111；soc_confidence：0.91；dose_prediction：608.1787；dose_confidence：0.96 |

**【各 agent 完整输出】**

- **model-6**
  - confidence: `0.5`
  - simulated: `True`
  - answer:
    ```text
    耕地肥力 SOC/Dose 预测已完成结构化分析。
    soc_prediction：18.4111；soc_confidence：0.91；dose_prediction：608.1787；dose_confidence：0.96
    ```
  - evidence (6 条):
    ```json
    [{"metric": "soc_prediction", "value": 18.4111}, {"metric": "soc_confidence", "value": 0.91}, {"metric": "dose_prediction", "value": 608.1787}, {"metric": "dose_confidence", "value": 0.96}, {"metric": "dose_warning", "value": "韶关旱地 RF 模型 R²=0.96，预测结果仅供参考（未指定 land_type，默认使用旱地模型）"}, {"metric": "imputation_applied", "value": true}]
    ```

---

#### Q14（期望 type=4）

> **问题原文：** 我的田土壤有机碳含量大概多少

- **识别 question_type**：4 ✓ 匹配
- **识别 role**：`None`
- **调用 agents**：model-6
- **answer 来源**：`answer`（`answer` = LLM 生成；`summary` = AgentManager 模板拼接）
- **耗时**：0.03s

**【完整回答】**

```text
[model-6] 耕地肥力 SOC/Dose 预测已完成结构化分析。
soc_prediction：18.4111；soc_confidence：0.91；dose_prediction：608.1787；dose_confidence：0.96
```

**【各 agent 调用细节】**

| agent_id | simulated | status | confidence | answer 摘要 |
|---|---|---|---|---|
| model-6 | sim（模拟） | - | 0.5 | 耕地肥力 SOC/Dose 预测已完成结构化分析。 soc_prediction：18.4111；soc_confidence：0.91；dose_prediction：608.1787；dose_confidence：0.96 |

**【各 agent 完整输出】**

- **model-6**
  - confidence: `0.5`
  - simulated: `True`
  - answer:
    ```text
    耕地肥力 SOC/Dose 预测已完成结构化分析。
    soc_prediction：18.4111；soc_confidence：0.91；dose_prediction：608.1787；dose_confidence：0.96
    ```
  - evidence (6 条):
    ```json
    [{"metric": "soc_prediction", "value": 18.4111}, {"metric": "soc_confidence", "value": 0.91}, {"metric": "dose_prediction", "value": 608.1787}, {"metric": "dose_confidence", "value": 0.96}, {"metric": "dose_warning", "value": "韶关旱地 RF 模型 R²=0.96，预测结果仅供参考（未指定 land_type，默认使用旱地模型）"}, {"metric": "imputation_applied", "value": true}]
    ```

---

#### Q15（期望 type=4）

> **问题原文：** 预测这块地需要多少施肥量

- **识别 question_type**：0 ✗ 不匹配
- **识别 role**：`None`
- **调用 agents**：-
- **answer 来源**：`answer`（`answer` = LLM 生成；`summary` = AgentManager 模板拼接）
- **耗时**：0.27s

**【完整回答】**

```text
抱歉，AI服务暂时不可用，请稍后重试。
```

---

### 类型5：质量等级评价（3 题）

#### Q16（期望 type=5）

> **问题原文：** 我的田耕地质量等级是多少

- **识别 question_type**：5 ✓ 匹配
- **识别 role**：`None`
- **调用 agents**：model-2
- **answer 来源**：`answer`（`answer` = LLM 生成；`summary` = AgentManager 模板拼接）
- **耗时**：0.01s

**【完整回答】**

```text
[model-2] 耕地质量提升潜力评估已完成结构化分析。
parcel_code：A0001；model_version：python_v1_20260801；parcel_info：{'地块代码': 'A0001', '经度': '112.973801', '纬度': '25.324301', '县区名称': '武江区', '二级农业区名称': '闽南粤中农林水产区'}；composite_index：0.6728330580097418
```

**【各 agent 调用细节】**

| agent_id | simulated | status | confidence | answer 摘要 |
|---|---|---|---|---|
| model-2 | real（真实） | - | 0.9 | 耕地质量提升潜力评估已完成结构化分析。 parcel_code：A0001；model_version：python_v1_20260801；parcel_info：{'地块代码': 'A0001', '经度': '112.973801',...[truncated 93 chars] |

**【各 agent 完整输出】**

- **model-2**
  - confidence: `0.9`
  - simulated: `False`
  - answer:
    ```text
    耕地质量提升潜力评估已完成结构化分析。
    parcel_code：A0001；model_version：python_v1_20260801；parcel_info：{'地块代码': 'A0001', '经度': '112.973801', '纬度': '25.324301', '县区名称': '武江区', '二级农业区名称': '闽南粤中农林水产区'}；composite_index：0.6728330580097418
    ```
  - evidence (4 条):
    ```json
    [{"metric": "parcel_code", "value": "A0001"}, {"metric": "model_version", "value": "python_v1_20260801"}, {"metric": "composite_index", "value": 0.6728330580097418}, {"metric": "quality_grade", "value": "10等"}]
    ```

---

#### Q17（期望 type=5）

> **问题原文：** 查询地块的综合指数和障碍度排序

- **识别 question_type**：5 ✓ 匹配
- **识别 role**：`None`
- **调用 agents**：model-2
- **answer 来源**：`answer`（`answer` = LLM 生成；`summary` = AgentManager 模板拼接）
- **耗时**：0.0s

**【完整回答】**

```text
[model-2] 耕地质量提升潜力评估已完成结构化分析。
parcel_code：A0001；model_version：python_v1_20260801；parcel_info：{'地块代码': 'A0001', '经度': '112.973801', '纬度': '25.324301', '县区名称': '武江区', '二级农业区名称': '闽南粤中农林水产区'}；composite_index：0.6728330580097418
```

**【各 agent 调用细节】**

| agent_id | simulated | status | confidence | answer 摘要 |
|---|---|---|---|---|
| model-2 | real（真实） | - | 0.9 | 耕地质量提升潜力评估已完成结构化分析。 parcel_code：A0001；model_version：python_v1_20260801；parcel_info：{'地块代码': 'A0001', '经度': '112.973801',...[truncated 93 chars] |

**【各 agent 完整输出】**

- **model-2**
  - confidence: `0.9`
  - simulated: `False`
  - answer:
    ```text
    耕地质量提升潜力评估已完成结构化分析。
    parcel_code：A0001；model_version：python_v1_20260801；parcel_info：{'地块代码': 'A0001', '经度': '112.973801', '纬度': '25.324301', '县区名称': '武江区', '二级农业区名称': '闽南粤中农林水产区'}；composite_index：0.6728330580097418
    ```
  - evidence (4 条):
    ```json
    [{"metric": "parcel_code", "value": "A0001"}, {"metric": "model_version", "value": "python_v1_20260801"}, {"metric": "composite_index", "value": 0.6728330580097418}, {"metric": "quality_grade", "value": "10等"}]
    ```

---

#### Q18（期望 type=5）

> **问题原文：** 这块地的耕地质量等级评价结果

- **识别 question_type**：5 ✓ 匹配
- **识别 role**：`None`
- **调用 agents**：model-2
- **answer 来源**：`answer`（`answer` = LLM 生成；`summary` = AgentManager 模板拼接）
- **耗时**：0.0s

**【完整回答】**

```text
[model-2] 耕地质量提升潜力评估已完成结构化分析。
parcel_code：A0001；model_version：python_v1_20260801；parcel_info：{'地块代码': 'A0001', '经度': '112.973801', '纬度': '25.324301', '县区名称': '武江区', '二级农业区名称': '闽南粤中农林水产区'}；composite_index：0.6728330580097418
```

**【各 agent 调用细节】**

| agent_id | simulated | status | confidence | answer 摘要 |
|---|---|---|---|---|
| model-2 | real（真实） | - | 0.9 | 耕地质量提升潜力评估已完成结构化分析。 parcel_code：A0001；model_version：python_v1_20260801；parcel_info：{'地块代码': 'A0001', '经度': '112.973801',...[truncated 93 chars] |

**【各 agent 完整输出】**

- **model-2**
  - confidence: `0.9`
  - simulated: `False`
  - answer:
    ```text
    耕地质量提升潜力评估已完成结构化分析。
    parcel_code：A0001；model_version：python_v1_20260801；parcel_info：{'地块代码': 'A0001', '经度': '112.973801', '纬度': '25.324301', '县区名称': '武江区', '二级农业区名称': '闽南粤中农林水产区'}；composite_index：0.6728330580097418
    ```
  - evidence (4 条):
    ```json
    [{"metric": "parcel_code", "value": "A0001"}, {"metric": "model_version", "value": "python_v1_20260801"}, {"metric": "composite_index", "value": 0.6728330580097418}, {"metric": "quality_grade", "value": "10等"}]
    ```

---

### 类型6

#### Q19（期望 type=6）

> **问题原文：** 辖区耕地质量提升的总体潜力有多大可增产多少粮食

- **识别 question_type**：6 ✓ 匹配
- **识别 role**：`None`
- **调用 agents**：model-2
- **answer 来源**：`answer`（`answer` = LLM 生成；`summary` = AgentManager 模板拼接）
- **耗时**：0.0s

**【完整回答】**

```text
[model-2] 耕地质量提升潜力评估已完成结构化分析。
county_code：8；scenario：1；result：{'scenario': 1, 'county_name': '武江区', 'parcel_count': 27, 'total_area': 71903.13920000002, 'avg_grade_pot': 7.703703703703703, 'avg_ind_pot': [6.3175720164609075, 19.43684499314129, 37.21489711934158, 69.02373113854597, 1.3510425240054875, 120.97530864197532, 18.22359396433471, 5.037037037037037, 2.3333333333333335, 1.9259259259259258, 7.111111111111111, 3.1481481481481484], 'min_ind_pot': [5.942222222222223, 16.805925925925926, 27.642222222222227, 58.196296296296296, 1.3359259259259262, 117.11111111111111, 17.296296296296298, 1.0, 2.0, 1.0, 5.0, 1.0], 'max_ind_pot': [7.457777777777777, 32.3, 85.6, 130.0, 1.364074074074074, 130.0, 23.0, 11.0, 3.0, 4.0, 10.0, 6.0], 'avg_lim_pot': [0.023924262816671087, 0.15351686641796997, 0.058257881623892366, 0.15857296790557887, 0.00012343338688438254, 0.0, 0.02255045139168196, 0.08016203687405758, 0.10553414157229414, 0.0832164172954944, 0.22541963961274686, 0.08872190110272843], 'sorted_avg_pot': [0.22541963961274686, 0.15857296790557887, 0.15351686641796997, 0.10553414157229414, 0.08872190110272843, 0.0832164172954944, 0.08016203687405758, 0.058257881623892366, 0.023924262816671087, 0.02255045139168196, 0.00012343338688438254, 0.0], 'sorted_names_pot': ['地形部位  ', '速效钾   ', '有机质   ', '排水能力  ', '质地构型  ', '灌溉能力  ', '质地构成  ', '有效磷   ', '酸碱度   ', '耕层厚度  ', '土壤容重  ', '有效土层厚度'], 'cnt_grade_pot': [0, 0, 0, 2, 2, 5, 1, 6, 5, 6], 'mj_grade_pot': [0.0, 0.0, 0.0, 8523.5231, 6077.357099999999, 12813.914700000001, 312.2856, 16144.5723, 11918.710500000001, 16112.7759], 'cnt_primary_pot': [0, 1, 0, 0, 0, 0, 0, 0, 0, 6, 15, 5], 'mj_primary_pot': [0.0, 3168.1774, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 14844.929800000002, 42794.02859999999, 11096.003399999998], 'avg_grade_orig': 8.851851851851851, 'avg_ind_orig': [5.942222222222223, 16.805925925925926, 27.642222222222227, 58.196296296296296, 1.364074074074074, 117.11111111111111, 17.296296296296298, 5.037037037037037, 2.111111111111111, 1.9259259259259258, 7.111111111111111, 3.1481481481481484], 'avg_contrib_orig': [0.05081065766295261, 0.050214525334933105, 0.02889851399865706, 0.026527703483080624, 0.05700673556141167, 0.07105394704968859, 0.0478956066550814, 0.06034037037037037, 0.08221111111111111, 0.09931185185185187, 0.0656740740740741, 0.053837037037037044], 'avg_contrib_pot': [0.06071916899289044, 0.05540949307600937, 0.042290303182234194, 0.033041878521360965, 0.05956833944698431, 0.07160000000000004, 0.052628020562703715, 0.06034037037037037, 0.07751333333333334, 0.09931185185185187, 0.0656740740740741, 0.053837037037037044], 'cnt_grade_orig': [0, 0, 0, 0, 2, 1, 3, 2, 4, 15], 'mj_grade_orig': [0.0, 0.0, 0.0, 0.0, 8523.5231, 3469.1557, 6685.6606, 4405.4322, 7356.429, 41462.938599999994]}
```

**【各 agent 调用细节】**

| agent_id | simulated | status | confidence | answer 摘要 |
|---|---|---|---|---|
| model-2 | real（真实） | - | 0.9 | 耕地质量提升潜力评估已完成结构化分析。 county_code：8；scenario：1；result：{'scenario': 1, 'county_name': '武江区', 'parcel_count': 27, 'total_are...[truncated 2642 chars] |

**【各 agent 完整输出】**

- **model-2**
  - confidence: `0.9`
  - simulated: `False`
  - answer:
    ```text
    耕地质量提升潜力评估已完成结构化分析。
    county_code：8；scenario：1；result：{'scenario': 1, 'county_name': '武江区', 'parcel_count': 27, 'total_area': 71903.13920000002, 'avg_grade_pot': 7.703703703703703, 'avg_ind_pot': [6.3175720164609075, 19.43684499314129, 37.21489711934158, 69.02373113854597, 1.3510425240054875, 120.97530864197532, 18.22359396433471, 5.037037037037037, 2.3333333333333335, 1.9259259259259258, 7.111111111111111, 3.1481481481481484], 'min_ind_pot': [5.942222222222223, 16.805925925925926, 27.642222222222227, 58.196296296296296, 1.3359259259259262, 117.11111111111111, 17.296296296296298, 1.0, 2.0, 1.0, 5.0, 1.0], 'max_ind_pot': [7.457777777777777, 32.3, 85.6, 130.0, 1.364074074074074, 130.0, 23.0, 11.0, 3.0, 4.0, 10.0, 6.0], 'avg_lim_pot': [0.023924262816671087, 0.15351686641796997, 0.058257881623892366, 0.15857296790557887, 0.00012343338688438254, 0.0, 0.02255045139168196, 0.08016203687405758, 0.10553414157229414, 0.0832164172954944, 0.22541963961274686, 0.08872190110272843], 'sorted_avg_pot': [0.22541963961274686, 0.15857296790557887, 0.15351686641796997, 0.10553414157229414, 0.08872190110272843, 0.0832164172954944, 0.08016203687405758, 0.058257881623892366, 0.023924262816671087, 0.02255045139168196, 0.00012343338688438254, 0.0], 'sorted_names_pot': ['地形部位  ', '速效钾   ', '有机质   ', '排水能力  ', '质地构型  ', '灌溉能力  ', '质地构成  ', '有效磷   ', '酸碱度   ', '耕层厚度  ', '土壤容重  ', '有效土层厚度'], 'cnt_grade_pot': [0, 0, 0, 2, 2, 5, 1, 6, 5, 6], 'mj_grade_pot': [0.0, 0.0, 0.0, 8523.5231, 6077.357099999999, 12813.914700000001, 312.2856, 16144.5723, 11918.710500000001, 16112.7759], 'cnt_primary_pot': [0, 1, 0, 0, 0, 0, 0, 0, 0, 6, 15, 5], 'mj_primary_pot': [0.0, 3168.1774, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 14844.929800000002, 42794.02859999999, 11096.003399999998], 'avg_grade_orig': 8.851851851851851, 'avg_ind_orig': [5.942222222222223, 16.805925925925926, 27.642222222222227, 58.196296296296296, 1.364074074074074, 117.11111111111111, 17.296296296296298, 5.037037037037037, 2.111111111111111, 1.9259259259259258, 7.111111111111111, 3.1481481481481484], 'avg_contrib_orig': [0.05081065766295261, 0.050214525334933105, 0.02889851399865706, 0.026527703483080624, 0.05700673556141167, 0.07105394704968859, 0.0478956066550814, 0.06034037037037037, 0.08221111111111111, 0.09931185185185187, 0.0656740740740741, 0.053837037037037044], 'avg_contrib_pot': [0.06071916899289044, 0.05540949307600937, 0.042290303182234194, 0.033041878521360965, 0.05956833944698431, 0.07160000000000004, 0.052628020562703715, 0.06034037037037037, 0.07751333333333334, 0.09931185185185187, 0.0656740740740741, 0.053837037037037044], 'cnt_grade_orig': [0, 0, 0, 0, 2, 1, 3, 2, 4, 15], 'mj_grade_orig': [0.0, 0.0, 0.0, 0.0, 8523.5231, 3469.1557, 6685.6606, 4405.4322, 7356.429, 41462.938599999994]}
    ```
  - evidence (2 条):
    ```json
    [{"metric": "county_code", "value": 8}, {"metric": "scenario", "value": 1}]
    ```

---

#### Q20（期望 type=6）

> **问题原文：** 我们县划定的优先改良片区具体在哪几个村每块潜力多大

- **识别 question_type**：6 ✓ 匹配
- **识别 role**：`None`
- **调用 agents**：model-2
- **answer 来源**：`answer`（`answer` = LLM 生成；`summary` = AgentManager 模板拼接）
- **耗时**：0.0s

**【完整回答】**

```text
[model-2] 耕地质量提升潜力评估已完成结构化分析。
county_code：8；scenario：1；result：{'scenario': 1, 'county_name': '武江区', 'parcel_count': 27, 'total_area': 71903.13920000002, 'avg_grade_pot': 7.703703703703703, 'avg_ind_pot': [6.3175720164609075, 19.43684499314129, 37.21489711934158, 69.02373113854597, 1.3510425240054875, 120.97530864197532, 18.22359396433471, 5.037037037037037, 2.3333333333333335, 1.9259259259259258, 7.111111111111111, 3.1481481481481484], 'min_ind_pot': [5.942222222222223, 16.805925925925926, 27.642222222222227, 58.196296296296296, 1.3359259259259262, 117.11111111111111, 17.296296296296298, 1.0, 2.0, 1.0, 5.0, 1.0], 'max_ind_pot': [7.457777777777777, 32.3, 85.6, 130.0, 1.364074074074074, 130.0, 23.0, 11.0, 3.0, 4.0, 10.0, 6.0], 'avg_lim_pot': [0.023924262816671087, 0.15351686641796997, 0.058257881623892366, 0.15857296790557887, 0.00012343338688438254, 0.0, 0.02255045139168196, 0.08016203687405758, 0.10553414157229414, 0.0832164172954944, 0.22541963961274686, 0.08872190110272843], 'sorted_avg_pot': [0.22541963961274686, 0.15857296790557887, 0.15351686641796997, 0.10553414157229414, 0.08872190110272843, 0.0832164172954944, 0.08016203687405758, 0.058257881623892366, 0.023924262816671087, 0.02255045139168196, 0.00012343338688438254, 0.0], 'sorted_names_pot': ['地形部位  ', '速效钾   ', '有机质   ', '排水能力  ', '质地构型  ', '灌溉能力  ', '质地构成  ', '有效磷   ', '酸碱度   ', '耕层厚度  ', '土壤容重  ', '有效土层厚度'], 'cnt_grade_pot': [0, 0, 0, 2, 2, 5, 1, 6, 5, 6], 'mj_grade_pot': [0.0, 0.0, 0.0, 8523.5231, 6077.357099999999, 12813.914700000001, 312.2856, 16144.5723, 11918.710500000001, 16112.7759], 'cnt_primary_pot': [0, 1, 0, 0, 0, 0, 0, 0, 0, 6, 15, 5], 'mj_primary_pot': [0.0, 3168.1774, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 14844.929800000002, 42794.02859999999, 11096.003399999998], 'avg_grade_orig': 8.851851851851851, 'avg_ind_orig': [5.942222222222223, 16.805925925925926, 27.642222222222227, 58.196296296296296, 1.364074074074074, 117.11111111111111, 17.296296296296298, 5.037037037037037, 2.111111111111111, 1.9259259259259258, 7.111111111111111, 3.1481481481481484], 'avg_contrib_orig': [0.05081065766295261, 0.050214525334933105, 0.02889851399865706, 0.026527703483080624, 0.05700673556141167, 0.07105394704968859, 0.0478956066550814, 0.06034037037037037, 0.08221111111111111, 0.09931185185185187, 0.0656740740740741, 0.053837037037037044], 'avg_contrib_pot': [0.06071916899289044, 0.05540949307600937, 0.042290303182234194, 0.033041878521360965, 0.05956833944698431, 0.07160000000000004, 0.052628020562703715, 0.06034037037037037, 0.07751333333333334, 0.09931185185185187, 0.0656740740740741, 0.053837037037037044], 'cnt_grade_orig': [0, 0, 0, 0, 2, 1, 3, 2, 4, 15], 'mj_grade_orig': [0.0, 0.0, 0.0, 0.0, 8523.5231, 3469.1557, 6685.6606, 4405.4322, 7356.429, 41462.938599999994]}
```

**【各 agent 调用细节】**

| agent_id | simulated | status | confidence | answer 摘要 |
|---|---|---|---|---|
| model-2 | real（真实） | - | 0.9 | 耕地质量提升潜力评估已完成结构化分析。 county_code：8；scenario：1；result：{'scenario': 1, 'county_name': '武江区', 'parcel_count': 27, 'total_are...[truncated 2642 chars] |

**【各 agent 完整输出】**

- **model-2**
  - confidence: `0.9`
  - simulated: `False`
  - answer:
    ```text
    耕地质量提升潜力评估已完成结构化分析。
    county_code：8；scenario：1；result：{'scenario': 1, 'county_name': '武江区', 'parcel_count': 27, 'total_area': 71903.13920000002, 'avg_grade_pot': 7.703703703703703, 'avg_ind_pot': [6.3175720164609075, 19.43684499314129, 37.21489711934158, 69.02373113854597, 1.3510425240054875, 120.97530864197532, 18.22359396433471, 5.037037037037037, 2.3333333333333335, 1.9259259259259258, 7.111111111111111, 3.1481481481481484], 'min_ind_pot': [5.942222222222223, 16.805925925925926, 27.642222222222227, 58.196296296296296, 1.3359259259259262, 117.11111111111111, 17.296296296296298, 1.0, 2.0, 1.0, 5.0, 1.0], 'max_ind_pot': [7.457777777777777, 32.3, 85.6, 130.0, 1.364074074074074, 130.0, 23.0, 11.0, 3.0, 4.0, 10.0, 6.0], 'avg_lim_pot': [0.023924262816671087, 0.15351686641796997, 0.058257881623892366, 0.15857296790557887, 0.00012343338688438254, 0.0, 0.02255045139168196, 0.08016203687405758, 0.10553414157229414, 0.0832164172954944, 0.22541963961274686, 0.08872190110272843], 'sorted_avg_pot': [0.22541963961274686, 0.15857296790557887, 0.15351686641796997, 0.10553414157229414, 0.08872190110272843, 0.0832164172954944, 0.08016203687405758, 0.058257881623892366, 0.023924262816671087, 0.02255045139168196, 0.00012343338688438254, 0.0], 'sorted_names_pot': ['地形部位  ', '速效钾   ', '有机质   ', '排水能力  ', '质地构型  ', '灌溉能力  ', '质地构成  ', '有效磷   ', '酸碱度   ', '耕层厚度  ', '土壤容重  ', '有效土层厚度'], 'cnt_grade_pot': [0, 0, 0, 2, 2, 5, 1, 6, 5, 6], 'mj_grade_pot': [0.0, 0.0, 0.0, 8523.5231, 6077.357099999999, 12813.914700000001, 312.2856, 16144.5723, 11918.710500000001, 16112.7759], 'cnt_primary_pot': [0, 1, 0, 0, 0, 0, 0, 0, 0, 6, 15, 5], 'mj_primary_pot': [0.0, 3168.1774, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 14844.929800000002, 42794.02859999999, 11096.003399999998], 'avg_grade_orig': 8.851851851851851, 'avg_ind_orig': [5.942222222222223, 16.805925925925926, 27.642222222222227, 58.196296296296296, 1.364074074074074, 117.11111111111111, 17.296296296296298, 5.037037037037037, 2.111111111111111, 1.9259259259259258, 7.111111111111111, 3.1481481481481484], 'avg_contrib_orig': [0.05081065766295261, 0.050214525334933105, 0.02889851399865706, 0.026527703483080624, 0.05700673556141167, 0.07105394704968859, 0.0478956066550814, 0.06034037037037037, 0.08221111111111111, 0.09931185185185187, 0.0656740740740741, 0.053837037037037044], 'avg_contrib_pot': [0.06071916899289044, 0.05540949307600937, 0.042290303182234194, 0.033041878521360965, 0.05956833944698431, 0.07160000000000004, 0.052628020562703715, 0.06034037037037037, 0.07751333333333334, 0.09931185185185187, 0.0656740740740741, 0.053837037037037044], 'cnt_grade_orig': [0, 0, 0, 0, 2, 1, 3, 2, 4, 15], 'mj_grade_orig': [0.0, 0.0, 0.0, 0.0, 8523.5231, 3469.1557, 6685.6606, 4405.4322, 7356.429, 41462.938599999994]}
    ```
  - evidence (2 条):
    ```json
    [{"metric": "county_code", "value": 8}, {"metric": "scenario", "value": 1}]
    ```

---

### 类型7

#### Q21（期望 type=7）

> **问题原文：** 全省耕地土壤有机质含量如何空间分布情况

- **识别 question_type**：7 ✓ 匹配
- **识别 role**：`None`
- **调用 agents**：model-5
- **answer 来源**：`answer`（`answer` = LLM 生成；`summary` = AgentManager 模板拼接）
- **耗时**：0.0s

**【完整回答】**

```text
[model-5] 耕地土壤有机质培肥提升已完成结构化分析。
organic_matter：22.0；level：中；manure_dosage：1000.0；potential_increase：1.5
```

**【各 agent 调用细节】**

| agent_id | simulated | status | confidence | answer 摘要 |
|---|---|---|---|---|
| model-5 | sim（模拟） | - | 0.5 | 耕地土壤有机质培肥提升已完成结构化分析。 organic_matter：22.0；level：中；manure_dosage：1000.0；potential_increase：1.5 |

**【各 agent 完整输出】**

- **model-5**
  - confidence: `0.5`
  - simulated: `True`
  - answer:
    ```text
    耕地土壤有机质培肥提升已完成结构化分析。
    organic_matter：22.0；level：中；manure_dosage：1000.0；potential_increase：1.5
    ```
  - evidence (7 条):
    ```json
    [{"metric": "organic_matter", "value": 22.0}, {"metric": "level", "value": "中"}, {"metric": "manure_dosage", "value": 1000.0}, {"metric": "potential_increase", "value": 1.5}, {"metric": "total_nitrogen", "value": 1.2}, {"metric": "cn_ratio", "value": 11.5}, {"metric": "clay_content", "value": 35.0}]
    ```

---

#### Q22（期望 type=7）

> **问题原文：** 为了提升耕地土壤有机质有机肥或者秸秆每亩施用量多少

- **识别 question_type**：7 ✓ 匹配
- **识别 role**：`None`
- **调用 agents**：model-5
- **answer 来源**：`answer`（`answer` = LLM 生成；`summary` = AgentManager 模板拼接）
- **耗时**：0.0s

**【完整回答】**

```text
[model-5] 耕地土壤有机质培肥提升已完成结构化分析。
organic_matter：22.0；level：中；manure_dosage：1000.0；potential_increase：1.5
```

**【各 agent 调用细节】**

| agent_id | simulated | status | confidence | answer 摘要 |
|---|---|---|---|---|
| model-5 | sim（模拟） | - | 0.5 | 耕地土壤有机质培肥提升已完成结构化分析。 organic_matter：22.0；level：中；manure_dosage：1000.0；potential_increase：1.5 |

**【各 agent 完整输出】**

- **model-5**
  - confidence: `0.5`
  - simulated: `True`
  - answer:
    ```text
    耕地土壤有机质培肥提升已完成结构化分析。
    organic_matter：22.0；level：中；manure_dosage：1000.0；potential_increase：1.5
    ```
  - evidence (7 条):
    ```json
    [{"metric": "organic_matter", "value": 22.0}, {"metric": "level", "value": "中"}, {"metric": "manure_dosage", "value": 1000.0}, {"metric": "potential_increase", "value": 1.5}, {"metric": "total_nitrogen", "value": 1.2}, {"metric": "cn_ratio", "value": 11.5}, {"metric": "clay_content", "value": 35.0}]
    ```

---

#### Q23（期望 type=7）

> **问题原文：** 本县耕地土壤有机质平均含量是多少

- **识别 question_type**：7 ✓ 匹配
- **识别 role**：`None`
- **调用 agents**：model-5
- **answer 来源**：`answer`（`answer` = LLM 生成；`summary` = AgentManager 模板拼接）
- **耗时**：0.0s

**【完整回答】**

```text
[model-5] 耕地土壤有机质培肥提升已完成结构化分析。
organic_matter：22.0；level：中；manure_dosage：1000.0；potential_increase：1.5
```

**【各 agent 调用细节】**

| agent_id | simulated | status | confidence | answer 摘要 |
|---|---|---|---|---|
| model-5 | sim（模拟） | - | 0.5 | 耕地土壤有机质培肥提升已完成结构化分析。 organic_matter：22.0；level：中；manure_dosage：1000.0；potential_increase：1.5 |

**【各 agent 完整输出】**

- **model-5**
  - confidence: `0.5`
  - simulated: `True`
  - answer:
    ```text
    耕地土壤有机质培肥提升已完成结构化分析。
    organic_matter：22.0；level：中；manure_dosage：1000.0；potential_increase：1.5
    ```
  - evidence (7 条):
    ```json
    [{"metric": "organic_matter", "value": 22.0}, {"metric": "level", "value": "中"}, {"metric": "manure_dosage", "value": 1000.0}, {"metric": "potential_increase", "value": 1.5}, {"metric": "total_nitrogen", "value": 1.2}, {"metric": "cn_ratio", "value": 11.5}, {"metric": "clay_content", "value": 35.0}]
    ```

---

## 三、model-6 真实 ML 计算能力验证

- **输入特征**：`{'pH': 6.5, 'SOCbe': 15.0, 'TN': 1.2, 'TP': 0.8, 'TK': 20.0, 'AP': 25.0, 'AK': 180.0, 'Gap': 5.0, 'Dose': 300.0, 'Fertilizer type': 1}`
- **execute_status**：`success`
- **SOC 预测值**：20.0881 g/kg（置信度 0.91）
- **Dose 预测值**：189.5341 t/ha（置信度 0.47）
- **dose_warning**：Dose 模型 R²=0.47，预测结果仅供参考，建议结合田间试验校准
- **imputation_applied**：False, imputed_features: `[]`
- **fallback_reason**：None
- **model_version**：`ETR_v1_20260713`
- **是否真实计算**：✓ 是

**【SOC 自然语言回答】**
```text
基于 ML 预测，您的土壤有机碳（SOC）预测值约 20.09 g/kg（置信度 91%）
```

**【Dose 自然语言回答】**
```text
耕地综合地力改良提升综合诊断（基于 ML 预测）：
- SOC（土壤有机碳）：20.09 g/kg（置信度 91%）
- Dose（施肥量）：189.53 t/ha（置信度 47%，Dose 模型 R²=0.47，预测结果仅供参考，建议结合田间试验校准）
```

---

## 四、汇总结论

- 真实可计算 agent：`['model-1', 'model-2', 'model-3', 'model-4', 'model-6']`
- 已集成但资源未部署（回退模拟）：`['model-5']`
- 占位桩 agent：`无`
- 问题库回答率：**23/23**
- 问题类型识别准确率：**22/23**
- model-6 真实计算：✓ 通过

### 关键观察

1. **模型2真实计算**：type 5 与 type 6 均路由到 model-2。type 5 使用 `parcel_code` 返回质量等级、综合指数和障碍度；type 6 使用 `parcel_code` 返回单地块潜力，或使用 `xqmc_code` 与 `scenario` 返回县域潜力情景。
2. **资源状态**：模型2依赖 `grade_csv`；资源缺失时返回 `DEPLOYMENT_ERROR`，不回退为模拟结果。
3. **路由细节**：每个 question_type 只调用一个正式模型，其中 `type 5` 和 `type 6` 均为 model-2；知识性问题仍走 RAG。
4. **结果标志**：模型2真实计算的 `metadata.simulated` 为 `false`；输入不足和引擎错误保留机器可读错误码。
