# kb-retrieval-evaluation Specification

## Purpose
提供检索质量评估能力，用可量化指标（如检索命中率）衡量知识库检索效果，支持迭代优化。

## Requirements

### Requirement: Retrieval quality evaluation

系统 SHALL 提供检索质量评估脚本，基于标注查询集计算检索命中率（hit rate）等指标。

#### Scenario: Compute retrieval hit rate
- **WHEN** 运行评估脚本并指定标注查询集
- **THEN** 系统 SHALL 输出每个查询的召回结果命中情况与整体命中率指标
