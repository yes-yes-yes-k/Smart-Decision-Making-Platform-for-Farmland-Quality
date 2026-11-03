## ADDED Requirements

### Requirement: Source Retrieval with Optional Graph Assistance

RAG原文来源检索 SHALL 可在图后端不可用或无相关关系时独立工作。图谱辅助 SHALL 通过可追溯适配边界保留后端、版本、状态及贡献；所有返回证据 SHALL 满足当前权限和来源版本约束。

#### Scenario: Graph backend is unavailable
- **WHEN** 图后端未部署、不可用或没有相关关系
- **THEN** 系统 SHALL 继续执行可用原文检索，明确图路径状态，不将回退当成图谱收益或事实否定

#### Scenario: A graph hit refers to withdrawn evidence
- **WHEN** 图命中来源已撤回或用户无权读取
- **THEN** 系统 SHALL 过滤该证据，不经图命中绕过原文权限及版本检查

### Requirement: Observable Hybrid Corpus Baseline

证据检索 SHALL 支持真实查询向量与持久词法索引融合，保留两路状态、来源排名及融合配置。查询向量 SHALL 在同次全库检索的集合间复用。默认来源范围 SHALL 为当前合格论文，显式来源范围 SHALL 在索引及当前权威元数据中分别核实。

#### Scenario: Vector retrieval fails while lexical results remain
- **WHEN** 查询向量或向量检索失败，但词法路径仍可用
- **THEN** 接口 SHALL 标记降级及实际路径，不将词法结果冒称混合成功；全部检索不可用时 SHALL NOT 作为资料不存在返回

#### Scenario: A candidate source changes before response
- **WHEN** 候选的文件hash、资格、权限或来源类型在返回前已变化
- **THEN** 系统 SHALL 重新核实并过滤失效项，返回原文不得依赖过时索引身份
