# vector-store Specification (Delta)

## ADDED Requirements

### Requirement: Hybrid Search

系统 SHALL 支持混合检索：对查询同时执行向量相似度召回与 BM25 关键词召回，并用 RRF（Reciprocal Rank Fusion）融合两路结果后返回排序结果。

#### Scenario: Hybrid search combines vector and keyword paths
- **WHEN** 提交检索查询
- **THEN** 系统 SHALL 并行执行向量召回与 BM25 关键词召回
- **AND** 系统 SHALL 用 RRF 融合两路结果并返回排序后的文档

#### Scenario: BM25 keyword index maintained
- **WHEN** 文档被加入向量库或按 source 删除
- **THEN** 系统 SHALL 同步更新对应的 BM25 关键词索引

#### Scenario: Keyword recall catches terminology
- **WHEN** 查询包含高区分度专业术语（如"交换性氢"、"有效钾"）
- **THEN** 系统 SHALL 通过 BM25 关键词召回命中包含该术语的文档