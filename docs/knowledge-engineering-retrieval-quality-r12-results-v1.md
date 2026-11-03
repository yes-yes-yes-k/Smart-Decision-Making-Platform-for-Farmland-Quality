# R1.2候选召回、融合与文献排序实施结果

日期：2026-10-30。R1.2a—R1.2c完成首批有界实现与隔离真实接口验证，R1.2完成本批交付；R1.3、R1.4及支持前5验收未完成。未部署常驻服务、迁移正式数据库或新增模型调用。

## 实现与结果

`retrieval_policy.py`提供版本化土壤概念词表，不含来源ID、论文题名或参考答案。措施、指标和已识别时长/酸性/作物概念分别保留，同义别名用OR连接。多指标在概念路联合匹配，原词法/向量路仍保留仅涉及部分指标的候选；词法命中不认证条件适用或结论支持。原问题继续使用其原始查询向量，不把修改后的文本套用旧向量。

词法配额60平分为原词法30和概念词法30，交错去重后不超过60；向量仍为60，融合仍保留60，片段仍返回20。分块RRF保持k=60、两路同权，没有用扩窗或指定论文提升排名。既有聊天检索不默认开启这项扩展。

`PublishedCorpusSearch`在两次当前来源/版本/原件校验后，新增独立`documents`文献列表。每篇以两路文献首次出现顺序计算文献级RRF，同文献重复分块不重复投票；所有合格证据定位继续保留。`sources`仍是分块排序原文，文献候选不会随最终20片段窗口消失。所有文献明确`support_verified:false`。

| 主问题/目标 | 原两路前60最佳位置（向量/词法） | 新词法最佳位置 | 新文献排名 | 新返回片段最佳位置 |
| --- | --- | --- | --- | --- |
| U1 / 449 | 未入 / 未入 | 2 | 6 | 18 |
| U2 / 1149 | 未入 / 未入 | 2 | 10 | 16 |
| U3 / 104 | 15 / 未入 | 2 | 2 | 1 |
| U4 / 1141 | 未入 / 未入 | 2 | 9 | 11 |
| U5 / 1032 | 1 / 1 | 1 | 1 | 1 |

原9条问题基线的最终20块顺序全部复现。五类主要问题的已知相关目标全部进入前10不同文献；四个既有变体的目标文献新排名为1、3、1、1。U2.PREMISE从文献第1降到第3、首个目标片段从第1降到第3，保留该退化，不将有限样本通过外推为全库质量改善。带题名变体只作定位回归，不证明错误前提、条件匹配或拒答能力。

## 融合对照与未通过版本

同一原查询、原两路候选、来源快照和最大预算下，对每条问题比较原同权RRF、向量权重1.5/2、向量60+词法30及向量30+词法60，共45组。配额缩小组实际候选更少，不能解释为严格等量候选的因果实验。每组完整融合、截断、两次当前来源校验及返回均保留。

U3仅改权重后的最佳分块是第22，两个配额组为第31/29，仍未返回；原策略为第35。没有因此选定新权重。最终策略通过补足概念候选和独立文献排序改善U3，不能声称单独调融合权重已解决所有类似问题。

各轮产物均保留：v1因沙箱禁止本机PG连接在查询前失败；v2不保留查询限定，U1/U2文献第11/13；v3补时长/酸性/作物，但将不同指标合并为OR，U2仍第11；v4分别保留指标概念后达到本批文献门槛。这些是同一有限用例上的迭代开发结果，未另建盲测或宣称泛化认证。

## 验证与复核

最终证据目录：[retrieval-policy-20261030-v4](../artifacts/knowledge_platform/retrieval-quality-r1/retrieval-policy-20261030-v4/manifest.json)。其中：

- [candidate-recall-results.json](../artifacts/knowledge_platform/retrieval-quality-r1/retrieval-policy-20261030-v4/candidate-recall-results.json)：18组HTTP实测、两路/完整融合、实际响应、目标后置核对、换入换出及耗时。
- [fusion-ranking-results.json](../artifacts/knowledge_platform/retrieval-quality-r1/retrieval-policy-20261030-v4/fusion-ranking-results.json)：45组融合/配额对照及来源复核。
- [document-evidence-ranking-results.json](../artifacts/knowledge_platform/retrieval-quality-r1/retrieval-policy-20261030-v4/document-evidence-ranking-results.json)：独立文献列表、保留定位与片段列表。
- [validation.json](../artifacts/knowledge_platform/retrieval-quality-r1/retrieval-policy-20261030-v4/validation.json)：独立重建RRF、验证候选预算、列表去重、定位/融合身份、代码哈希和74个旧冻结文件；结构检查与五类文献前10通过，语义支持明确未评。
- `frozen-code/`和`manifest.json`：实际执行代码、词表、版本及产物哈希；新运行ID禁止覆盖。

实际运行：

```powershell
.\.venv\Scripts\python.exe scripts/run_retrieval_quality_policy_pilot.py --run-id retrieval-policy-20261030-v4
.\.venv\Scripts\python.exe scripts/validate_retrieval_quality_policy_pilot.py --run-id retrieval-policy-20261030-v4
.\.venv\Scripts\python.exe -m unittest tests.test_retrieval_quality_policy tests.test_research_corpus_m2 tests.test_retrieval_candidate_diagnostics tests.test_lexical_operations_m2 tests.test_chroma_lexical_m2 tests.test_research_evidence tests.test_research_admission_m2 tests.test_research_contract_v2
```

最终86项测试通过，覆盖真实隔离Chroma/FTS、单查询向量、扩展失败降级、权限/撤回/版本、文献独立截断、跨文献与多片段保留、持久化和恢复。中间一次组合测试出现Chroma的HNSW reader `Nothing found on disk`，未改实现后独立13项及后续完整86项两次通过；保留为测试环境偶发问题，不计作新排序修复。未运行会初始化正式应用的根pytest套件。语法、UTF-8和改动范围空白检查通过。

执行只复用精确匹配原问题的9条真实缓存向量，并共享每条查询实际ANN候选以隔离词法策略变量。调用0、新向量0、历史预算账本未改；每条原查询与变体用独立输出保留。PG适配器强制`default_transaction_read_only=on`并校验读取事务；研究表只在内存SQLite显式准备。已有可变隔离Chroma运行副本被复用，未切换生产索引；该实测延迟不能代替线上SLO或新模型实时调用验收。

## 剩余工作与回退

R1.4仍需按12个子问题核实真正支持的前5段落、原文定位、否定/不显著/条件及无证据情形。U1/U2/U4目标片段尚不在前5，文献前10通过不能代替段落支持门槛；也不能据来源ID推断已返回片段必然支持问题。R1.3的结构化条件与知识身份过滤继续独立实施。

本轮不开展新抽取、嵌入或重排调用。若后续需要这些请求，须先列明具体输入、独立批次、预留及尝试上限；既有27次调用额度已耗尽，不转用历史预算。

词法回退：Flask配置`LITERATURE_EVIDENCE_DOMAIN_EXPANSION=False`，或构建`PublishedCorpusSearch(..., enhance_recall=False)`。回退关闭概念路，新增文献列表仍保留；分块融合公式与原向量路径不变。本轮无需数据库迁移或索引重建。
