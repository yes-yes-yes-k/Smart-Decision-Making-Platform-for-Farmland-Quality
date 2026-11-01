# GraphRAG闭环、检索收益与领域约束技术栈核查 v1

日期：2026-10-30。依据当前代码、已有冻结试跑和官方资料整理；本轮未连接数据库、启动服务、调用模型或安装组件。服务器现状不以本机状态代替。用户随后已在Q13接受先复用Python/PostgreSQL验证真实链路与图关联价值，见[ADR-0004](adr/0004-domain-constraints-with-reusable-backends.md)；其他平台仍是候选，尚未部署。

## 三个直接结论

1. **能抽实体和关系候选，但当前上传到图谱检索的常驻闭环尚未证实完成。** 存在真实模型隔离试跑与候选持久化代码；仍有工作流部署、发布存储及查询接线断点。
2. **没有证明GraphRAG稳定优于向量，也不能说图完全没有贡献。** 外部小试跑实际使用了图并改变部分召回，但证据覆盖和可答完成没有稳定改善；产品新搜索又没有使用那套实验图。
3. **可以替换OpenSPG承担的领域建模/校验职责，但须分层替换。** 抽取器、领域规则、持久层和检索规划是不同职责。用户已接受先规则校验与有据关联、允许容器或独立服务；并未选定Neo4j、RDF或其他新平台。

## 当前上传到检索的实际链路

| 环节 | 已有实现与证据 | 尚缺的运行证明或实现 |
| --- | --- | --- |
| 上传、文献审核、解析分块 | `framework/api/routes/docs.py:306,481,840`；`framework/upload/ingestion_worker.py:89,92` | 上传先等待文献审核，不能声称上传即自动构图；当前新文件常驻全流程尚无证据 |
| 分块与向量入库 | `ingestion_worker.py:191,201,213`；M2完整112168块隔离Chroma/HNSW验证 | 向量分块数不是已抽取论文数或图谱事实数 |
| 入库完成与outbox | `ingestion_worker.py:254`与完成状态同事务；`framework/knowledge_graph/jobs.py:35,48`资格/幂等 | 最后M0/M2盘点未见主库KG表，不能把代码存在当作当前已持续入队 |
| outbox与抽取worker | `framework/knowledge_graph/worker.py:45,65,66,75,80` | 运行时/模型配置和后端准入门仍须满足；当前未部署常驻抽取worker |
| 实体、关系、Claim候选 | `framework/knowledge_graph/candidate_pipeline.py:309,350,437,665,710` | 真实抽取候选存在，但质量、来源支持和审核状态不能自动通过 |
| 审核与发布 | `review.py:81,151`；`release_platform.py:388` | 默认JSON无该增量发布路径所需写接口；AGE未部署，十篇发布/回滚未完成 |
| 图API、聊天与新搜索 | 图API按JSON/AGE配置；聊天另读文件图；新证据搜索走词法 | 切图API配置不会切换聊天；新搜索未接该图；同一活动版本尚未端到端对齐 |

部署现状依据[M0差距报告](knowledge-engineering-m0-runtime-gap-report.md)及[M2结果](knowledge-engineering-m2-results.md)，本轮不把旧快照当作新的实时数据库检查。

### 真实抽取成功的证据

[`live-shadow-paper-1171-v4.json`](../artifacts/knowledge_platform/live-shadow-paper-1171-v4.json)记录Microsoft GraphRAG 3.3.0通过真实模型处理1171号文献4块，产生5个实体候选、2个关系候选及2条证据记录，worker完成一个隔离任务。报告同时明确生产库和活动发布未修改、质量评估未完成。该报告使用旧模型配置，不能当作当前V4.1 Flash的全面质量成绩。

M1的两个产物则是独立`literature_record`中的pending研究记录，写入隔离研究库，不是上述KG候选/图发布链已经贯通的证据。参见[M1结果](knowledge-engineering-m1-results.md)及`framework/knowledge_graph/research_store.py`。

### 容易被忽略的发布和读取断点

- `release_platform.py:258`为approved Claim添加发布变更审计；`:452`的实际store应用仅调用release、entity、relation及activate接口，没有Claim图写入。必须检查研究断言在查询中是否真实可读，不能用审计记录替代持久化查询能力。
- 默认JSON store缺少该增量发布路径的写接口，会在`release_platform.py:455`返回`graph_store_read_only`。旧JSON小图可读不等于新增上传内容能自动加入它。
- `framework/rag/chain.py:24,379,402`使用Chroma混合检索及独立文件图检索器；图API另在`framework/api/app.py:149`创建JSON/AGE store。
- `framework/api/routes/literature_evidence.py:154`配置`corpus_search`；`research_service.py:85`直接走它，新`/search`因此跳过下面的可选`graph_lookup`。现状见`research_retrieval.py`。

## GraphRAG与向量检索的现有对照

已有[外部QA来源修正版报告](knowledge-graph-external-qa-pilot-v2.md)使用相同回答模型和最多5块/20000 UTF-8字节的证据预算；QASPER为5篇/10题，MultiHop为57篇新闻/16题。GraphRAG抽取输出组成NetworkX实验图，不是生产AGE图，也不是Microsoft默认全局社区搜索。当前结论为`inconclusive`。

| 指标 | 向量 | 实验GraphRAG | 能说明什么 |
| --- | ---: | ---: | --- |
| QASPER Answer F1 | 0.1633 | 0.1699 | 小幅变化，不是稳定优势 |
| QASPER精确证据Recall@5 | 47.62% | 44.05% | 图参与并没有保证更多正确片段 |
| QASPER可答完成 | 5/9 | 5/9 | 没有改善这一小样本的完成数 |
| MultiHop支持文档Recall@5 | 93.06% | 93.06% | 文献命中相同，不代表正文证据充分 |
| MultiHop正文事实片段Recall@5 | 67.36% | 67.36% | 图没有改善这一版本的正文事实覆盖 |
| MultiHop可答完成 | 4/12 | 4/12 | 仍存在明显回答/证据链缺口 |

QASPER F1差值约+0.0066，文档组95%区间[-0.0069,0.0307]。MultiHop的0.4375→0.5是“任意分词重合率”，不是严格回答准确率，不能据此宣称GraphRAG提高了6.25个百分点的正确率。独立文档组和样本很少，AI复核也不构成专家认证。

图实际参与26/26题，改变QASPER的7/10题及MultiHop的6/16题检索。因此，实验没有稳定收益不能简单归因为“没走图”；产品路径未接实验图是另一项问题。原始证据见[`real-QA-pilot-v2.json`](../artifacts/knowledge_platform/external-benchmark-v1/reports/real-QA-pilot-v2.json)及[`QA-evidence-granularity-v2.json`](../artifacts/knowledge_platform/external-benchmark-v1/reports/QA-evidence-granularity-v2.json)。

## 差距原因：事实与待验证解释

| 可观察事实 | 对收益的限制 | 还需验证的解释 |
| --- | --- | --- |
| 产品搜索、聊天、图API读取不同路径 | 实验收益不能自动进入产品 | 统一来源/活动版本后是否改善实际查询 |
| 试点仅80/1306块、2条研究记录通过定位，原件还可有双栏交织 | 条件化研究记录覆盖不足，准确引用困难 | 修复原文和定位后可增加多少有用关联 |
| 实验文档召回高而正文事实覆盖不足 | 找到论文/新闻不等于取得支持每个子问题的证据 | 图扩展带回的段落是否支持、是否挤占关键段落 |
| 图参与改变结果但部分证据指标不升 | 关联扩展不是天然高质量排序 | 同名合并、关系不足、候选排序和上下文截断各自影响尚未做归因消融 |
| Claim图写入和读取契约仍有断点 | 措施、条件、结果不能仅靠二元边稳定保留 | 哪些条件可由当前研究读模型复用，哪些需扩展关联查询契约 |

这些是具体阻碍与诊断方向，不是已经证明的单一根因。实体更多、关系更多或图遍历发生，不自动代表找到更多支持证据。

### 实验实现中已定位的限制

`framework/knowledge_graph/external_qa_retrieval.py`及对应冻结代码揭示了更具体的机制：

1. 图从向量前2块和问题中的实体名称字面命中选种子，再做2跳扩展（`:117–137`）。不是独立验证过的语义实体链接，向量漏召回可能限制图入口。
2. 实体全局身份仅以`strip().upper()`后的名称合并（`:73,79`）。同名可能跨研究误合并，异名不自动对齐；具体发生多少有害碰撞尚需trace核对。
3. 这轮GraphExtractor采用通用类型/提示，图边保存description和unit，但遍历不读关系描述、研究条件或关系方向的科学含义，入边出边均走。它未测到用户要求的同研究、同条件关联能力。
4. 图boost优先于向量分数，并把命中unit所有块提升，然后截到5块/20KB（`:130–146`）。图会替换候选，并非只追加证据；粗粒度扩展可能挤掉正确正文，但逐题因果尚需验证。
5. 元数据修复版允许题名、作者等独立块公平进入两组。MultiHop共80个召回槽，向量33个、图34个是metadata，16/16题均出现；它们对来源型问题可能有用，不能一概删除，但必须另看正文事实覆盖。

原始实验向量基线为纯bge-m3余弦；产品的`vector_results`却可能已包含BM25/向量RRF与重排，参见`framework/vector_store/chroma_store.py:320–325`、`framework/rag/chain.py:379`。因此，现有“对向量”的成绩不能代替产品相对强混合基线的增益。

实验图为空即报错，报告两组错误0，没有证据表明这次26题靠无图静默回退完成。产品聊天会在图失败时保留基线，成功回答不能证明图有贡献。两种行为必须分开记录。

## OpenSPG环境：需要纠正的前提

OpenSPG/KAG并非简单“只支持Linux”：当前官方快速开始列出Windows，但Windows路径需要WSL2/Hyper-V及Docker/Compose。仓库历史POC记录缺这些运行条件和OpenSPG服务，因此未跑通；它本来是规划中的可选后端，不是当前上传和搜索的必需运行组件。[官方KAG快速开始](https://github.com/OpenSPG/KAG)支持这一环境区分。

`governance/knowledge-platform/adapter-policy-v1.json:18`将其列为`approved=false`的候选；当前`adapters/`未见可运行OpenSPG适配器。更换选型主要是调整尚未落实的路线，并非拆除已在生产运行的OpenSPG服务。

用户已明确允许容器或独立服务，故可以评估独立引擎；尚不能断言目标服务器绝对不适配。其具体OS版本、资源、网络和运维条件仍未知，不能用本机Windows 11/PostgreSQL17.4代替服务器事实。

还须一并审视AGE：本仓库[AGE手册](../deploy/apache-age.md)固定PG16、Linux容器/主机，本机则是PG17.4。只替换OpenSPG并不能消除这项现有持久层部署差异；当前没有认证这套AGE方案在目标服务器可用。

## 可替代职责与候选路线

领域约束至少包含实体/关系合法性、同研究归属、条件/单位/否定及证据范围；结构规则通过不证明科学结论真实。用户首期选择规则校验及有据关联，不要求自动生成原文未报告的新结论。

| 路线 | 可以承担的职责 | 代价和局限 | 当前建议 |
| --- | --- | --- | --- |
| Python规则层＋现有PostgreSQL关系化图读模型 | 实体/关系/研究断言/证据持久化，类型与身份约束，条件关联和有界多跳 | 需要补齐发布/读取契约；SQL约束不能判定语义支持，复杂路径性能待测 | 优先评估的低新增运维方案，不声称现有代码已实现 |
| RDFLib/pySHACL规则层 | 用可版本化shapes校验RDF图中的类型、基数及关系约束 | 需要映射现有模型；不是抽取器、完整查询服务或科学事实认证器 | 如确需标准本体互操作，可作为局部验证层 |
| Neo4j＋领域规则/证据层 | 持久属性图与路径查询；官方有Windows及独立服务安装路径 | 新服务、备份、驱动及版本/许可能力需核实；仍需抽取、领域约束和证据判断 | 有实际路径查询需要时评估，不作为抽取质量修复的捷径 |
| 独立OpenSPG/KAG服务 | 集成领域schema、构图及逻辑检索能力 | 多服务运维与模型/契约适配，尚缺本项目可运行及增益证明 | 允许保留候选，不设为本轮先决条件 |

技术能力依据：[PostgreSQL17约束](https://www.postgresql.org/docs/17/ddl-constraints.html)、[递归查询](https://www.postgresql.org/docs/17/queries-with.html)、[Pydantic验证器](https://docs.pydantic.dev/latest/concepts/validators/)、[W3C SHACL](https://www.w3.org/TR/shacl/)、[pySHACL官方项目](https://github.com/RDFLib/pySHACL)、[Neo4j Windows安装](https://neo4j.com/docs/operations-manual/current/installation/windows/)。Neo4j具体服务器/JDK兼容性仍须按其[系统要求](https://neo4j.com/docs/operations-manual/current/installation/requirements/)核对。上述功能不等于本项目集成或容量已验收。

关系化保存实体、关系、条件化断言及来源仍可表达知识图谱；是否使用专用图数据库是存储选择。需要明确关联身份、方向、条件和证据，不能把任意几张业务表直接称为已完成领域图谱。Microsoft GraphRAG可继续作为候选抽取适配器，领域约束层无需与它或某个图数据库绑定。

## 已确认的推进顺序

1. 先为原十篇列出一次有来源身份的上传/入库任务到候选、持久化、实际检索的追踪清单，明确文献审核与候选发布两道门。失败状态与未部署环节逐项列出，不以向量入库成功代替构图完成。
2. 领域规则单独版本化并保留失败原因；先处理实际原文与定位问题、同研究字段绑定，再决定保留哪些抽取适配器。研究记录与KG候选/Claim需有明确映射，不靠名字相近视为同一管线。
3. 在五类已确认问题上复用同一来源快照和预算，检查强词法/向量混合基线、带相同领域过滤的基线、再加图关联三种结果。条件过滤本身的收益不能全算成图遍历收益。
4. 记录每题图带来的新增文献/片段、其支持性、被替换证据及延迟/调用成本，保留图无贡献或变差的情形。小范围诊断即可，不再扩建评测集。
5. 先复用Python/PostgreSQL完成上述验证，确定尚缺的图查询和发布能力后，再决定是否新增Neo4j、独立OpenSPG等平台。通过可替换的抽取/规则/存储边界集成，保留清晰的领域与证据契约。

现有26题的缓存与trace还可用于离线检查图换入/换出片段、metadata预算和同名实体碰撞，不需要重新构建评测集或调用模型。它们只能诊断已有实验机制，不能替代原十篇的领域任务与实际上传闭环验收。
