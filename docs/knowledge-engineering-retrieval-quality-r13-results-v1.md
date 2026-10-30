# R1.3来源类型、权限、有效版本与条件过滤实施结果

日期：2026-10-30。完成R1.3的离线实现与单元验证；未部署服务、未迁移正式库、未新增模型调用，也未执行真实接口基线（属R1.4）。语义支持仍为未评估，本批不宣称支持前5通过。

## 实现

`framework/knowledge_graph/research_retrieval.py`新增`PublishedCorpusSearch`，把来源范围、权限、有效版本和条件过滤放在同一条检索路径上：

- **来源类型**：`SOURCE_SCOPES`固定五类范围——`papers`（学术论文）、`standards`（标准）、`guidelines`（方法指南）、`policies`（政策）、`all_qualified`（四类并集）。默认`papers`，其他类型必须显式指定，检索侧同时以`document_kind`过滤，避免只靠调用方声明。
- **权限与发布身份**：先按`visibility_scope=public`过滤候选，再用`current_sources.lookup_many`对每个`document_id`做当前来源复核；撤回、私有、未完成、复核未通过的来源在文献列表和片段列表中都不返回。返回的`publication`字段记录的是**当前有效版本**（`content_sha256`、`version`、`review_status`、`source_bytes_valid`），不是检索时的历史快照。
- **条件过滤**：`measure`、`indicator`、`soil_type`、`conditions`四个字段独立求值。`evaluate_conditions`只做**显式原文表面匹配**，返回三值结果：`matched`或`unknown`；单块文本无法判定"不符"，因此`mismatch_detection`明确为`not_derivable_from_single_chunk_text`，不把"没提到"当成"不满足"。`require_condition_match=true`时必须至少声明一个条件字段，未命中的块被排除；默认保留并标注`unknown`。
- **支持与条件分离**：`_support`固定返回`support_verified:false`、`semantic_support:"unreviewed"`，并显式声明`condition_surface_match_is_support:false`。原文里出现"红壤"只说明条件词出现，不构成结论支持。
- **输入边界**：查询长度、`limit`上限30、检索预算`min(90, limit*3)`、`document_ids`上限1000、条件值长度300、请求字段白名单均校验；非法输入返回`ResearchError`，不透传底层异常。

`framework/vector_store/retrieval_policy.py`提供版本化概念词表（`soil-concepts-context-v3`）与独立文献排序`rank_documents`：同一文献的重复分块不重复投票，文献列表不随最终片段窗口截断而消失，来源撤回后文献与片段同时消失。

产品接线：`framework/api/routes/literature_evidence.py`在`configure_evidence_service`中把`PublishedCorpusSearch`注入`ResearchService`，检索、对照、来源目录与原文块读取共用同一套来源/权限校验。

## 验证

```powershell
py -3.12 -m pytest tests/test_retrieval_quality_r13.py -q
py -3.12 -m pytest tests/test_retrieval_quality_policy.py -q
```

结果：`14 passed`（7 subtests）、`6 passed`，合计20项通过。覆盖范围：

| 用例组 | 覆盖行为 |
| --- | --- |
| 条件求值 | 缺词即`unknown`且不当匹配；空白容忍的码点定位；未请求条件时返回`not_requested`；多字段独立上报 |
| 范围与版本 | 范围声明来源类型且策略显式；发布身份携带复核后的版本；支持永不被断言、表面匹配不等于支持；撤回/私有/过期来源在文献与片段中都不出现；改类型不能冒充请求类型 |
| 条件过滤 | 未知条件默认保留并标注；严格模式要求显式过滤且排除未知；文档同时上报发布身份、条件与"未评估的支持"；拒绝非字符串/超长值；条件过滤不改变发布身份、不允许额外字段 |

连同证据闭环、图谱任务与版本化结果测试，`tests/test_research_evidence.py tests/test_knowledge_graph_jobs.py tests/test_versioned_model_results.py`共41项通过，未见回归。

## 限制

1. **未跑真实接口**：本批只有单元级验证，没有在真实语料上执行五类问题基线；支持前5、条件覆盖率与实际拒答率仍属R1.4。
2. **条件判定是词面级**：仅识别显式出现的条件词，不做同义归并、否定识别与跨块推理。"红壤"与"酸性红壤"是否等价、条件是否真正支配结论，仍需语义核实。
3. **来源范围未做真实样本验收**：标准/指南/政策三类范围的过滤只有单测样例，库内实际分布未统计。
4. **未接到聊天主链**：`PublishedCorpusSearch`仅服务文献证据接口，日常聊天仍走原RAG链路。
5. **无新产物目录**：本批不产生运行证据，故未在`artifacts/knowledge_platform/retrieval-quality-r1/`下新建run目录。

## 下一步

R1.4在真实接口上跑U1—U5及冻结变体，逐子问题报告召回、排序、来源命中与支持前5，R1.3的过滤行为在该轮一并接受真实数据检验；R2.3（选择协议：先定实体片段与位置，再判关系）不依赖模型预算，可并行推进。
