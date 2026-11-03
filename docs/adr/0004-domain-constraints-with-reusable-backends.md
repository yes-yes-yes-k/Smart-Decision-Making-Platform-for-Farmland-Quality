# 优先复用Python/PostgreSQL建立可替换的领域约束层

状态：已接受。2026-10-30，用户对Q13明确确认：“先验证真实链路和图关联价值，再决定新增平台。”首期复用Python/PostgreSQL，允许容器或独立服务作为后续选择；具体新平台、迁移和模型批次尚未启用。

决定将实体/关系/研究断言/证据的领域契约与抽取器、图存储分开，先复用现有Python规则层与PostgreSQL持久化/关联查询验证原十篇的小闭环。Microsoft GraphRAG可保留为候选抽取器；OpenSPG、Neo4j或RDF/SHACL在明确的能力缺口及图关联收益得到验证后，再决定是否经适配边界引入。

选择依据是当前主要断点还包括原文定位、同研究条件、Claim发布读取和多条检索路径未接通，换图数据库本身不能解决这些问题。该路线减少新增服务运维，但需自行明确并验证领域规则、有界路径查询及发布一致性；复杂多跳的性能和本体互操作能力未认证，后续可能需要专用服务。

独立OpenSPG/KAG可提供较完整的构图/逻辑检索栈，Neo4j可提供专用属性图查询，RDF/SHACL可提供标准图约束表达；各自仍需领域与证据映射、部署、版本及运维核实。允许这些选项，不等于现在必须同时引入它们。技术能力与现有断点依据见[核查报告](../knowledge-engineering-graphrag-stack-assessment-v1.md)。

该决策保持[ADR-0001](0001-separate-candidate-recall-from-published-claims.md)及[ADR-0003](0003-separate-evidence-support-conditions-and-publication.md)的信任边界。规则校验不能替代原文语义支持，图关联不能自动提升为已发布事实；图谱相对同预算强混合检索的收益须另行追踪。
