## ADDED Requirements

### Requirement: Bounded Lexical Index Maintenance

面向规模运行的关键词索引 SHALL 避免启动累计全库原文、单文献更新触发全库重新分词及每次查询对全库文本重新分词。实现 SHALL 记录索引版本、维护成本、检索候选预算及失败恢复，不以分页最终全量累计宣称有界。

#### Scenario: A document is incrementally updated
- **WHEN** 单文献内容版本变化
- **THEN** 维护 SHALL 作用于相应文献/索引增量，不依赖重新读取和分词所有来源正文

#### Scenario: A large collection is queried
- **WHEN** 查询在声明规模的集合执行
- **THEN** 系统 SHALL 使用索引召回与有界候选处理，不逐次加载或重分词全库原文，且仍执行来源权限过滤
