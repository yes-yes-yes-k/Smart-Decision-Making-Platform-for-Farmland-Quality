# GraphRAG 抽取评测集 v2 使用说明

此版本重建来源、分区及AI银标参考，替代旧小规模金标的正式验收用途。参考建设完成、软件测试通过与GraphRAG后端质量通过是三件不同的事。当前实际状态以审核页及各冻结清单为准，不以本文推定运行完成。

**当前存在语义质量拦截。** 12条原文抽查确认6条错误、3条需裁决；抽查不代表总体错误率。100条校准参考仍保留冻结原件，但暂限开发诊断，最终400条不得冻结为验收参考。详见`semantic-quality-audit-v1/review.html`及`docs/knowledge-graph-extraction-benchmark-v2-semantic-quality-stop.md`；不要直接运行原批次续接或补裁决。先验证新的片段/证据检查方案，不以重新调用同一模型或扩大排除范围替代质量修复。

## 文件入口

产物根目录为 `artifacts/knowledge_platform/extraction-benchmark-v2/`。

| 路径 | 用途 |
|---|---|
| `execution/review.html` | 当前阶段与预算的生成时快照 |
| `dataset-v1/review.html` | 500条来源、分区、原文、原始失败和参考状态 |
| `dataset-v1/manifest.json` | 冻结采样清单及原始输入依赖哈希 |
| `calibration-silver-v1/manifest.json` | 已冻结的100条校准参考及全部构建证据 |
| `test-silver-v1/manifest.json` | 仅在最终400条参考全部完成后才生成的冻结清单 |
| `reference-release-v1/coverage-report.json` | 两轨分别统计、全部关系类型的事实/文档组支持数及缺口 |
| `reference-construction-audit-v1/report.json` | 初标协议完成、同模型共同偏差与构建来源检查 |
| `execution/budget-and-integrity-v2.json` | 历史文件、协议本体、冻结输入/参考及共享预算检查 |

没有最终参考清单时，`test-silver-v1/`下的导出文件仅为中间进度，不得当作已冻结版本。`references-v1/`及`reference-release-v1/`保留原始响应、结构编译和必要证据门禁的历史视图；已冻结的校准参考优先于首轮校准门禁统计，不能把旧问题计作仍未解决，也不能覆盖原失败记录。

## 来源与适用总体

指定目录是 `D:\17417\Documents\知识库文献`，实际包含论文、标准及其他文件，并非全部都是论文。951个不同PDF字节哈希与数据库匹配；数据库中未匹配指定目录的来源单列，不静默纳入总体。可抽样池为510份文档、509个隔离组，42份身份或重复关系未决来源被隔离。来源语言、类型及解析质量的窗口审查保留未知值，不代表全文认证。

固定种子抽出500块、200个文档隔离组：代表性轨300块（校准60、最终240）；挑战轨200块（校准40、最终160），文档组在轨道和分区间互斥。代表性轨每组最多3块，短文档保留。挑战轨使用词面关系提示及困难负例/随机对照，不使用被测后端表现筛选。

两轨分别报告，正文和题名分别计分。题名可作身份上下文，不能代替正文断言。代表性轨的概率/权重针对文档组抽样设计，不是所有分块的等概率总体权重。不得把挑战轨与代表性轨合并宣传总体质量，也不得只保留正例或可解析项。

## 参考构建及可靠性边界

初标A/B仅接收原文、未改写的冻结数据库题名及冻结手册；角色请求互不读取答案，采用同一模型、相同提示及temperature=0。第三次请求检查去除投票信息的候选并集，并可补充共同漏项。独立请求不等于独立错误，可能共同漏标或共同作出错误判断。

原始失败、无效方向、超界跨度和截断不会重分类为初标成功。结构编译只合并同位置同类型的字面重复并保留适用条件；必要证据门禁拦截题名作正文断言，不自动删关系来形成负例。未决案件单独回到原文裁决；安全的截断续接只请求从未完整输出的关系索引，已完成判断保持不变。不能可靠续接的字段仍为未决，不能补写缺失JSON或推定空数组。

最终银标可用于内部比较，但不是专家认证，不能声称训练数据层面的盲测。完整参考不意味着全部初标响应成功。共同偏差是相对AI参考的观察，不能直接解释为专家准确率。

## 安全续接与离线检查

以下命令在仓库根目录使用 `.venv/Scripts/python.exe`：

```powershell
.venv/Scripts/python.exe scripts/verify_kg_benchmark_budget_v2.py
.venv/Scripts/python.exe scripts/verify_kg_benchmark_membership.py
.venv/Scripts/python.exe scripts/gate_kg_benchmark_references.py
.venv/Scripts/python.exe scripts/report_kg_benchmark_reference_coverage.py
.venv/Scripts/python.exe scripts/audit_kg_benchmark_reference_construction.py
.venv/Scripts/python.exe scripts/render_kg_benchmark_dataset_review.py
.venv/Scripts/python.exe scripts/report_kg_benchmark_progress.py
```

这些命令不发模型请求。旧 `rebuild_kg_extraction_benchmark.py --verify`保留原1000万预算规则，不能用于解释新的2000万授权；使用v2校验器，不修改旧冻结代码。

有限批次只有在确认旧进程停止且共享账本没有活动请求后，才可显式运行 `resume_kg_benchmark_final_references.py`。它验证冻结请求哈希并跳过缓存；不启动定时任务或自动后台续跑。有未结算预留时先确认请求所属进程已经终止，保守按完整预留计入并留痕，不能清零账本。仅瞬时网络或限流等错误可重试一次，每次尝试都计入预算。

全项目硬上限为用户明确批准的2000万token或5000次尝试，以先到者为准；并发2。旧授权、阶段调整及历史消耗保留。未知用量按完整预留记账，不视为零成本；不能自动扩容总上限或扩大样本规模。

## 投入验收前的门禁

完整参考、隔离及来源检查通过后，先用冻结的可复现GraphRAG后端运行校准，不调参。被测流程只接收来源，不能注入参考实体/关系；候选错误与输出格式/适配错误分别报告。

分别报告实体精确率/召回率、关系精确率/召回率、证据支持、有效完成率和排除率，并按文档组给出区间。缺失或无效预测计漏报，不能靠候选自行排除难题。稀有类型不足30事实/10文档组时明确列缺口，不替换冻结样本或补造正例。

数值阈值必须在试测后由用户确认、再冻结，才能运行正式最终验收。阈值未确认、关键类型覆盖不足、预算耗尽或后端不可用时只能报告未完成/证据不足；不能宣称通过。冻结标签不得原地修改，后续修订另建版本并保留差异。

本基准针对抽取后端，不能替代GraphRAG问答验收。检索命中、回答有据、引用支持和正确拒答须另用独立问题集与相同预算的向量基线验证；图谱缺少某关系本身不能证明事实不存在。
