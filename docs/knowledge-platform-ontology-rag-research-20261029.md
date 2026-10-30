# OpenSPG 替代路线调研：OntologyRAG

日期：2026-10-29。范围：根据用户确认，按“本体约束抽取与检索”技术路线研究，不限定某个同名仓库。本文为选型建议，未安装依赖、调用付费模型、修改生产配置或执行迁移。

## 结论

**可以把 OpenSPG 尚未接入的候选抽取位置，调整为轻量的 OntologyRAG 路线。建议复用本项目已有契约、Schema、证据和图存储接口，补充独立的本体约束抽取 adapter，先完成对照 POC。**

不建议为此次环境问题整体引入 TrustGraph 平台，也不建议直接把 IQVIA 的 ontologyRAG 原型作为文献抽取器。前者仍需平台部署；后者主要解决已有医学本体之间的编码映射。替换候选位置具有工程可行性；抽取质量、成本和生产资格尚无本次实测依据。

OntologyRAG 是一类架构方法，不是统一产品或接口。本体指导实体和关系识别、验证候选、组织图查询，再用来源证据支持回答。TrustGraph 的官方说明展示了这条流程，但其性能宣传不能代替本项目评测。[官方技术说明](https://docs.trustgraph.ai/guides/ontology-rag/)

## 项目现状与环境依据

- `docs/knowledge-platform-openspg-poc.md` 和 `artifacts/knowledge_platform/openspg-poc-environment-current.json` 记录 OpenSPG 环境阻断；后者生成于 2026-10-26。不能把历史探测时间写成今日。
- 今日只读检查：项目虚拟环境 Python 3.12.3；命令发现未找到 Docker、Cargo，找到了 `wsl.exe`。仅存在该命令不能证明 WSL 可用，本次没有重新安装或启动子系统。
- 当前虚拟环境可导入 `openai`、`pydantic`；未发现 `rdflib`、`pyshacl`、`pyoxigraph`。包存在不证明凭据有效或模型服务可用。
- `framework/knowledge_graph/adapters/` 当前有 GraphRAG 相关实现和 stub，未见 OpenSPG adapter；OpenSPG 主要存在于规划、治理候选和环境探测中。因此这次优先调整的是待实现候选，而非拆除已运行的生产后端。
- `schema.py` 已定义实体类别、关系类别及 source/target 类型约束；`contracts.py` 已定义 `ExtractionRequest`、`ExtractionResult` 与带页码、字符范围和哈希的 `EvidenceReference`。
- `two_stage_extraction.py`、`span_extraction.py` 已尝试 Schema 约束和证据定位。现有工程在方法上已经部分采用 OntologyRAG；新增 adapter 应提供明确差异，避免仅换名。
- `query.py` 提供受跳数、条数、超时和结果大小限制的图检索，并按过滤条件回取来源。现有存储路线保留 AGE / JsonGraphStore，不必为本体约束抽取新增数据库。

## 可选实现比较

| 路径 | 已核实特征 | 对当前项目的判断 |
| --- | --- | --- |
| 现有 Python 工程 + 本体约束 adapter | 复用领域 Schema、结构输出、证据定位和图接口；无需 OpenSPG Server | 首选 POC，部署增量最小；语义质量必须实测 |
| `ontorag/ontorag` | Python ≥3.12；文档→实例→RDF；可使用本地 RDFLib，也支持其他图后端；PyPI 标注 Apache 许可、Beta | 可作为隔离对照候选；需验证接口、证据粒度和依赖，不能直接接管现有发布链 |
| TrustGraph Ontology RAG | 支持 OWL 驱动的文献实体/关系抽取；官方流程要求先部署 TrustGraph，列出 Compose、Kubernetes 等部署方式 | 可借鉴方法；整体引入不符合本次降低环境负担的首要目标 |
| `iqvianlp/ontologyRAG` | README 标为原型，主要用已有本体图做医学编码映射；Python 3.11/3.12、Oxigraph 及指定模型客户端 | 任务不匹配，不是文献抽取器的直接替代品 |

依据：[OntoRAG 源码说明](https://github.com/ontorag/ontorag)、[包元数据](https://pypi.org/project/ontorag/)、[TrustGraph 部署](https://docs.trustgraph.ai/deployment/)、[IQVIA 原型](https://github.com/iqvianlp/ontologyRAG)、[论文](https://arxiv.org/abs/2502.18992)。以上为检索时文档状态，不等于已完成 Windows 安装和运行验证。

IQVIA 原型 README 还说明输入为已转换的本体图；它不会自动完成本项目的耕地文献构图。该仓库存在 GPL-3.0 LICENSE 和 CC BY-NC 声明，复用前需澄清具体工件的许可适用范围，本次不复制其代码或数据。[README](https://raw.githubusercontent.com/iqvianlp/ontologyRAG/main/README.md)

## 建议技术栈与接入边界

第一阶段只替代候选抽取能力：

```text
已有原文分块、页码、来源哈希
  → 版本化领域 Schema / 本体规则
  → 本体约束实体候选抽取
  → 候选实体间的有向关系判断
  → 本地证据定位、类型与语义约束检查
  → ExtractionResult
  → 现有审核、去重、发布流程
  → 已有图存储接口 + 向量来源检索
```

建议先使用现有 Python、OpenAI 兼容模型客户端、Pydantic 和确定性校验器；模型端是否完整支持所需结构输出必须通过 POC 验证。独立运行环境固定依赖版本，不升级主应用依赖。

本体的第一版以现有领域 Schema 为唯一类型来源，补充术语定义、关系方向、同义词来源、否定/条件/推测的处理规则。这里是应用层领域本体约束，不代表已经实现 OWL 推理。不能通过模型自动扩展类型来绕过未知类型校验。

如确有跨系统本体交换或 RDF 校验需求，再增加 RDFLib 与 SHACL。SHACL 用于检查 RDF 图的约束符合性，不证明抽取事实真实；OWL 的 domain/range 推断也不能替代证据与业务校验。[W3C SHACL](https://www.w3.org/TR/shacl/)

RDF / OWL / SPARQL 与 AGE 的属性图及现有查询接口不是同一套模型。若后续要求完整 SPARQL、RDF 命名图或 OWL 推理，应另行评估 RDF 存储及映射，不能宣称 AGE 可直接执行 SPARQL。POC 不引入第二套事实主库。

## 本体约束必须解决的实际问题

1. **证据完整性。** 保留文献/分块哈希、页码、原文摘录、字符范围；由程序核验摘录，不允许模型生成“解释性证据”补写事实。
2. **语义支持。** 结构合法不等于事实成立。区分否定、研究目的、推测、显著变化、联合措施和单项效果；同一模型多次一致也可能共同出错。
3. **实体归一。** 先保留来源提及和证据，再关联规范实体。别名词表应来自独立审核，不能从最终测试参考答案反推。
4. **复杂事实。** 土壤指标数值、单位、试验条件、时间和措施组合可能需要带属性的断言或事件；若现有二元关系不足，应单独版本化扩展契约，不能强行压成无条件三元组。
5. **信息不完整。** 本体约束只限定合法表达，不能恢复 OCR 丢失的表头、缺失上下文或没有明确陈述的关系。推导事实必须与原文明确事实区分并记录推导规则。

## POC 验证方案

当前最新 `docs/knowledge-graph-extraction-benchmark-v2-live-pilot-20261029.md` 记录参考流程、身份/近重复审计和预算仍有待完成事项；旧 94 条或历史 AI 银标不能直接充当此次最终验收标准。历史分数只作诊断，新路线使用同一冻结参考和同一来源输入比较。

建议步骤：

1. **离线适配。** 固定 adapter、Schema、提示词和依赖版本，接通统一契约。验证类型、方向、证据、空结果、失败状态和重复请求；开发数据与最终测试数据隔离。
2. **开发集小样本对照。** 使用既有曝光开发文献与控制题，覆盖论文、标准、无事实、否定、复杂单位和联合措施。对照现有 GraphRAG 路径，明确新增本体约束带来的区别；此阶段只作可行性诊断。
3. **冻结后公平评测。** 在参考准备完成后，固定相同输入、模型版本、预算和评分口径。记录实体及有向关系 P/R/F1、精确证据、空样本误报、失败率，以及实际 token、延迟和费用可得性。按关系类型分组，防止总分掩盖稀有类型退化。
4. **独立问答评测。** 单独测来源支持率、引用正确性、拒答和权限过滤；抽取指标通过不代表问答通过。
5. **影子运行及准入。** 仅输出候选，不自动发布事实；精确版本、真实评测和 conformance 通过后，再按现有治理流程决定是否启用。

本次没有启动上述模型实验，也没有扩大现有模型调用预算。开发对照、正式验收和生产启用的授权与预算沿用现有边界，调研本身不改变这些状态。

## 后续落地范围

- 优先新增本体约束 adapter 及运行配置，复用现有契约、审核、存储和证据回取。
- POC 通过后，再更新 `governance/knowledge-platform/adapter-policy-v1.json`、开源清单、OpenSpec 与 worker 候选选择；候选名称/版本要反映实际实现，新增时保持未获生产准入。
- OpenSPG 的历史环境证据和旧报告保留，当前状态可标为暂缓；不把历史结果改写成新 adapter 的结果。
- 工期和效果需经首轮 POC 估计；本次没有证据承诺准确率提升、成本降低比例或生产上线日期。

## 本次核验范围

完成项目源码/文档只读检查、Python 与模块可用性检查，以及上述官方文档和源码调研。仅新增本文；未运行后端功能测试，原因是未修改实现；未执行端到端 POC，因此“可替代”指方案与接口层面可行，不是运行验收通过。
