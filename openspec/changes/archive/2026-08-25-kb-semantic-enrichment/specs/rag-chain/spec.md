# rag-chain Specification (Delta)

## ADDED Requirements

### Requirement: Query Synonym Preprocessing

系统 SHALL 在查询进入检索前，依据耕地领域同义词/专业词表对查询做同义词替换，用规范化术语改写查询后再向量化与检索。

#### Scenario: Synonym replacement applies to query
- **WHEN** 查询包含词表中已登记的同义词（如"可交换氢"）
- **THEN** 系统 SHALL 将其替换为规范术语（如"交换性氢"）后进入检索

#### Scenario: Unmatched terms pass through
- **WHEN** 查询不包含词表中的任何词条
- **THEN** 系统 SHALL 保持查询原样，不做改写