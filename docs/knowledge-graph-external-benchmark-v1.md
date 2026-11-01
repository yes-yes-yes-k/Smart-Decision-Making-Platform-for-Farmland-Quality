# 外部评测运行与问答评分

## 当前范围

抽取使用真实GraphRAG3.3.0、V4.1 Flash和原生给定实体关系任务。12篇开发试跑与499篇有效校准分别保存，官方dev原有500篇中的1篇因与最终集高度重复而停用，处理依据在来源隔离报告中。此任务不能证明端到端NER或土壤本体抽取质量。

外部预算按用户2026-10-29新授权从零计，独立上限2000万token/5000次尝试、并发2，旧内部账本保留。所有尝试先预留，未知用量保守计费；语义错误与截断不重试，瞬时网络/限流最多重试一次，402停止。

## 完整校准预算

权威计划：`artifacts/knowledge_platform/external-benchmark-v1/reports/calibration-budget-v1.json`。

- 文档499篇，全部进入固定评分分母；提示、原生96类关系和8192输出上限沿用开发试跑。
- 按实际GraphRAG消息与JSON Schema逐篇构造请求，首轮预留10,148,547 token；预算预检没有模型调用。
- 起跑余额19,952,075 token。首轮可覆盖；若所有请求均按完整预留再重试一次，需要20,297,094 token，超过起跑余额345,019。
- 12篇实耗外推499篇约1,992,881 token，只是成本估计。重试仍逐次检查全局硬上限，极端情况下保存未完成检查点，不自动增加总额。
- 运行目录：`runs/redocred-calibration-v1/`。`run-config.json`绑定源代码、输入、原生标签及请求哈希，`jobs.jsonl`包含全部499篇实际请求；文件变动会阻止续接。

纯本地重算当前校准分数：

```powershell
python scripts/score_kg_external_calibration.py
```

运行中报告的分母仍为499篇，尚未处理的文档计漏报，因此中途召回率不能作为全量质量结论。以`execution_state`、`pending_documents`和`scores_provisional`判断是否已结束。最终数值门槛尚待确认，不自动运行最终集。

批次终态后使用`python scripts/finalize_kg_external_calibration.py`保存错误分解、结果与依赖快照。发现`calibration-result-manifest-v1.json`后，评分/冻结命令只核验并读取原结果，不再覆盖；后续分析或后端修订须另建版本。

## 问答预测协议

评分脚本支持QASPER和MultiHop-RAG，输入为JSON数组或JSONL，每条预测包含：

```json
{
  "question_id": "数据输入清单中的原始规范化ID",
  "predicted_answer": "回答，或Unanswerable / Insufficient information",
  "predicted_evidence": ["逐字证据引文"],
  "retrieved": [
    {"document_id": "语料ID", "block_id": "块ID"}
  ]
}
```

QASPER语料采用`normalized/qasper-v2/`，保留所有章节标题、正文和图表说明；MultiHop使用`normalized/multihop-v2/`，正文块ID为`body`。检索顺序就是排名，错源、伪造文本和重复条目占用原排名，不允许将后续证据向前补位。

正式后端预测的同目录须有`run-config.json`，包含`prediction_mode: live_backend_predictions`、`model`、`backend`、`corpus_sha256`、`retrieval_budget`和`generation_parameters`。参考答案不得进入生成、检索或建图输入。评分器可独立消费真实向量基线或GraphRAG预测；评分代码接通不等于这两个问答后端均已运行。

```powershell
python scripts/score_kg_external_qa.py --dataset qasper --partition calibration --predictions <预测文件> --mode live_backend_predictions --output <报告文件>
python scripts/score_kg_external_qa.py --dataset multihop_rag --partition calibration --predictions <预测文件> --mode live_backend_predictions --output <报告文件>
```

开发/校准可评分，`final`在数值门槛确认工作流完成前直接阻断。`reference_replay`及`integration_fixture`模式只验证评分流程，报告保留该身份，不能作为后端成绩。

## 原生与补充指标

QASPER直接调用经SHA256核验的官方Answer F1和Evidence F1，保留多答案及图表证据，不开启`text_evidence_only`。官方分类型均值不包含缺失预测的实现局限单列，补充指标保留各类型完整完成率分母。

MultiHop官方答案函数只需任意一个空白分词重合就算成功，不能称为严格准确率；另报严格匹配和token F1。原生检索函数保留其检查11个排名及非标准MAP公式的行为并明确提示。`null_query`仅按官方规则不进入检索指标，仍进入回答、完成率及拒答统计。

补充指标包含证据Recall@5、可答完成率、正确拒答率、字面引用定位率以及按论文/相连支持文档组重采样的区间。QASPER定位不到的60条原生证据不被模糊修复、不据此排除问题。缺失或无效预测留在完整分母；重复预测保留第一条，错源不增加分数。`No`等否定答案不作为拒答，混合可答性参考单列。

## 独立语义支持复核

字面引用能定位不能证明引用支持回答。语义复核器为每道有真实预测的问题分别准备“参考证据支持”与“回答/引用支持”请求；输出`supported/unsupported/insufficient`，缺上下文或检索未找到只判证据不足，不据此断言事实为假。

```powershell
python scripts/judge_kg_external_qa.py --dataset qasper --partition calibration --predictions <预测文件> --out-dir <复核目录>
```

默认只准备请求和预算，不调用模型。显式增加`--execute`后使用现有硅基流动模型，每次尝试记入同一个外部预算。其他批次在途时阻止执行；参考回放和测试预测禁止调用语义模型。两个独立请求的ID及预测文件哈希与合并结果绑定，同模型裁判偏差始终声明。

```powershell
python scripts/score_kg_external_qa.py --dataset qasper --partition calibration --predictions <预测文件> --mode live_backend_predictions --semantic-judgments <复核目录>/judgments.jsonl --output <报告文件>
```

没有独立复核记录时，语义支持项为`inconclusive`，不将字面定位率冒称有据率。不完整复核按全部问题给支持率下界，同时报告覆盖数。

## 离线测试

用户已明确允许新增并运行离线测试：

```powershell
python -m unittest discover -s tests -p test_external_qa_scoring.py -v
```

11项测试使用QASPER校准1005题及MultiHop自定义校准132题，覆盖参考回放、缺失、重复、错源、伪造检索文本、排名保留、否定与拒答、最终评分拦截、复核请求独立性及禁止参考回放调用模型。测试不发模型请求，不构成真实问答质量测量。


## 2026-10-30 真实问答已完成

来源修正版的真实对照、104次独立语义复核、25项离线验证和冻结均已交付。上述章节中的接入说明仍适用，实际结果、来源遗漏修复、条件/全题分母、同模型不稳定性及最终预算缺口，见 [来源修正版报告](knowledge-graph-external-qa-pilot-v2.md)。当前仍为非最终试跑，门槛及最终范围待用户确认。
