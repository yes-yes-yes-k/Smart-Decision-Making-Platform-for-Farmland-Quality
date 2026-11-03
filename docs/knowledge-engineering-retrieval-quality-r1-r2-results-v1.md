# R1.1、R2.1、R2.2实施结果 v1

日期：2026-10-30。范围：真实混合检索基线、已确认解析问题的版本修复、两阶段抽取契约。三项实施交付完成；相关论文与支持片段质量尚未通过验收，常驻本机服务尚未部署。

## 交付与证据

| 任务 | 本次行为 | 验证与边界 |
| --- | --- | --- |
| R1.1 | 证据接口改接真实向量+持久词法索引，RRF融合；跨集合复用一次查询向量，保留两路状态、排名与融合分；默认合格论文，可显式选择其他合格来源 | 新隔离Chroma副本含112168块；9条固定查询通过同一产品蓝图完成认证HTTP调用，9/9返回200且两路实际参与；当前PG及原件hash两次核验。尚未完成文献去重、条件判定及支持质量验收。 |
| R2.1 | 增加显式`pdf-layout-v2`，修复已确认双栏、页外旧稿、重复字形与反向文本问题；保存字符坐标、新分块与旧块映射 | 五篇共69页、666新块；原文件与旧产物保留。新版仅在独立产物中，未索引或替换当前生产数据。表格语义、图片文字和原生CAJ仍有明确限制。 |
| R2.2 | 冻结[任务抽取契约v2](knowledge-engineering-extraction-contract-v2.md)，实现研究归属/实体枚举→关系判定的源文跨度编译 | 规则拒收、版本身份、未知字段及待审边界已测试；尚未运行新抽取模型请求，也未连接新的PG候选存储。 |

机器产物位于[本轮目录](../artifacts/knowledge_platform/retrieval-quality-r1/r1-r2-20261030-v1/)，主要包括[真实基线结果](../artifacts/knowledge_platform/retrieval-quality-r1/r1-r2-20261030-v1/baseline-results.json)、[解析及契约校验](../artifacts/knowledge_platform/retrieval-quality-r1/r1-r2-20261030-v1/artifact-validation-v2.json)、[测试结果](../artifacts/knowledge_platform/retrieval-quality-r1/r1-r2-20261030-v1/test-results-final.json)和[契约冻结记录](../artifacts/knowledge_platform/retrieval-quality-r1/r1-r2-20261030-v1/contract-freeze.json)。

## 真实检索结果与仍存在的问题

本轮使用新生成的BAAI/bge-m3查询向量，在当前索引的隔离副本运行实际Chroma/HNSW与FTS5。缓存只复用这9条完全相同查询的新向量，没有用文献向量代替查询向量。配置为RRF k=60、候选预算60、返回20个分块，不做重排或回答生成；图谱未参与本基线。

HTTP使用轻量产品蓝图、隔离内存研究库及本轮临时JWT，actor由当前PG只读核实。它不是已部署的常驻服务器，也不证明生产JWT配置或其他API运行。原件复核累计300次文件哈希读取，18次元数据查询；每题返回前再次核实来源。首次词法索引构建约154.43秒，9次HTTP查询约2.01—4.34秒，查询计时不包含此前生成向量的网络时间。这些数值不是冻结SLO或容量结论。

基线暴露了实际质量缺口：

| 主要问题 | 返回20块覆盖不同论文数 | 已知来源线索 | 该来源首个返回分块位置 |
| --- | ---: | ---: | --- |
| U1 生物炭与SOC | 5 | 449 | 未进入该窗口 |
| U2 石灰、稻米Cd与产量 | 10 | 1149 | 未进入该窗口 |
| U3 粪肥与物理性质 | 13 | 104 | 未进入该窗口 |
| U4 紫云英/稻草/石灰与Cd | 10 | 1141 | 未进入该窗口 |
| U5 珠三角Cd与分区管理 | 4 | 1032 | 第1块 |

来源ID只在结果保存后用于诊断，没有注入检索请求。分块位置不是文献排名，这5篇也不是全库相关文献的完整分母；不能据此给出全库召回率。多块集中在少量论文是直接观测，跨语言、同义表达、候选预算和融合的各自影响仍需R1.2定位。原文真正支持每个子问题尚未在R1.4验收，HTTP成功不代表有据率或正确拒答通过。

当前降级会明确标记，不能把词法回退记为混合成功；全部检索不可用返回503。来源范围在索引和权威元数据分别核实，当前权限、审核、来源类型或文件版本失效的结果会被过滤。条件参数仍未结构化判定，接口明确`conditions_structurally_evaluated=false`，故R1.3保持未完成。

## 解析修复与版本映射

| 文献 | 页数 | 旧块数 | 新块数 | 具体发现与修复 |
| --- | ---: | ---: | ---: | --- |
| 449 | 11 | 106 | 106 | SOC等正文按整栏读取，摘要与Significance保持独立文本块，避免逐行穿插 |
| 1149 | 10 | 89 | 91 | 左右栏正文及结论分离；保留材料、Cd指标和产量限定，不由解析器补结论 |
| 1141 | 13 | 80 | 76 | 页外FOR PEER REVIEW旧稿和重复字形不再纳入；第4页65.2%及第5页Blue and red文字恢复可读 |
| 104 | 14 | 141 | 147 | 结果、讨论与结论按栏读取，避免不同作物/土类句子逐行交错 |
| 308 | 21 | 225 | 246 | 反向表格页的文字可正向读取；保留rotated_text_requires_review，未认证表格行列关系 |

前3篇见`parsing/`，后2篇见`parsing-additional/`。每个规范化字符保留PDF矩形，额外换行对应null；NFKC展开字符共享原字形位置。没有自动去断词、补空白单词或科学数值修正。布局只在有足够双栏证据时按几何分栏，否则保留原生文本块顺序并保留未推断警告。

原文件SHA256、解析版本及分块版本分别记录。旧块仅在新页文本中唯一精确匹配时提供偏移，其余状态为`same_page_only_no_span_transfer`，不能模糊迁移旧跨度或审核身份。即使文字一致，新版证据仍须绑定新版身份。

派生产物状态为`unpublished_candidate_parse`，与文献审核状态分开；没有将已审来源改成待审。当前PG并不登记本轮新解析/分块版本，切换须等待R2.6/R2.8的版本绑定及持久化验证。原生CAJ页映射、图像页/OCR和表格语义不由本次数字文本修复认证；未对正常来源或全库重新解析。

## 抽取契约与知识身份

新契约将文件、解析、分块版本共同绑定到每个原文跨度。阶段一选择研究归属和实体表面形式；阶段二只能引用已校验ID，关系暂限measure→indicator的`reports_effect`，不直接映射为“改善”或科学因果成立。规范实体归并单独保留unresolved；未知剂量、单位、条件、否定和不确定性不补猜。

同文献多个试验、季别、土类及处理须区分；综述引用研究必须有归属原文。编译器校验跨度、重复、方向和study ID一致性，语义支持与研究归属是否正确仍须独立核实。输出固定待审、语义未审核、发布新增0。已有v1契约及冻结标签保留，没有把新bundle直接写入只识别文件hash的旧KG存储。

## 调用预算与网络限制

初次在受限沙箱执行的18次尝试全部因ProxyError失败，按保守预留计入11628 token。随后只读网络预检在完整网络权限下成功：本机PG可读取，硅基流动HTTPS可达。R0的连接失败不能据此解释为宿主数据库未运行。

用户明确将本轮尝试上限由18调整为27，token总上限仍20000；账本以授权修订追加，保留原18次失败。追加9次成功，无重试，服务报告334 token。最终累计27次、按预算计11962 token、inflight=0；token余量8038，**尝试额度已用完，不继续调用**。

新执行器遇代理配置错误会停止排队任务，不按瞬时网络错误重复重试；相关故障测试通过。没有向模型发送论文正文，没有新抽取或语义裁判调用，历史M1及外部评测账本未转用或重置。

## 验证与交接

必要回归109项通过：68项unittest、18项解析兼容测试、23项既有索引/混合检索兼容测试；最后接口标记调整另定向复验9项，不重复计入109。测试使用隔离目录，未加载根conftest。失败测试记录保留，最终结果以`test-results-final.json`为准。

主要可复现入口：

```text
.venv/Scripts/python.exe scripts/validate_retrieval_quality_r1_r2.py
.venv/Scripts/python.exe -m unittest tests.test_pdf_layout_v2 tests.test_research_contract_v2 tests.test_research_corpus_m2 tests.test_chroma_lexical_m2 tests.test_retrieval_embedding_budget tests.test_research_evidence tests.test_research_admission_m2
.venv/Scripts/python.exe -m pytest --noconftest -q tests/test_document_parser_caj.py tests/test_document_parser_pdf.py tests/test_document_parser_pdf_fidelity.py tests/test_document_parser_clean.py
.venv/Scripts/python.exe scripts/validate_knowledge_m2_compatibility.py
openspec validate enable-literature-evidence-comparison --strict
```

重建解析必须另选新输出目录，不能覆盖本轮版本。模型执行脚本保留预算硬限和完成记录，不作为可重复调用的验收命令。

2459个历史冻结文件引用及35个R0目录内冻结资产再次校验一致。正式数据库与原向量库未写入；本轮只有新隔离副本及内存测试库发生写入。没有启动常驻worker、修改前端、发布新断言或安装专用图平台。

下一步优先R1.2论文去重与跨语言/同义召回，针对已经暴露的窗口漏失定位原因；R1.3补条件与支持身份，R1.4再按子问题检查真实支持。抽取进入R2.3时使用v2契约和新版原文，不立即重跑大批量或把结构校验当语义质量通过。
