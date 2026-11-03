# 任务抽取契约 v2

状态：R2.2冻结；首期用于原十篇任务相关研究候选。机器契约为[task-evidence-extraction-v2.json](../governance/knowledge-platform/task-evidence-extraction-v2.json)，编译入口为[research_contract_v2.py](../framework/knowledge_graph/research_contract_v2.py)。未改变v1记录、现有生产图本体或发布门禁；尚未连接真实模型请求和PG持久写入，分别留给R2.3—R2.6。

## 来源与位置

可信调用方提供`document_id`、原文件`document_sha256`、`parse_version`、`chunk_set_version`以及本次可读`chunks`。模型不得替换这四项来源身份。相同文件重新解析也产生独立解析/分块版本，不能仅按文件hash和旧块号复用证据。

每次选择必须包含`chunk_index`、`start`、`end`及`quote`，位置为块内从0开始的Unicode码点区间`[start,end)`。编译器核对整数类型、页码、边界和原文切片相等，生成绑定四项来源身份的span ID与引文SHA256。重复片段通过明确位置区分，不再要求模型为消歧扩大或改写名称。规范化原文中每个字符的PDF坐标另由解析产物保存；规范化跨度不能假装原PDF字符偏移。

旧分块映射只在新页文本中整体唯一精确出现时提供偏移。其余仅给同页候选块，状态为`same_page_only_no_span_transfer`；不得据模糊匹配转移旧标签、已审身份或研究结论。

## 阶段一：研究归属与实体枚举

输入仅为可信来源文本、位置约定和冻结手册，不提供旧答案、旧模型选择或其他样本输出。输出为`studies`和`entities`：

| 对象 | 必需内容 | 约束 |
| --- | --- | --- |
| study | 本地ID、kind、原文context、attribution或null | kind为原始试验、综述引用研究、观察、建模或未知；context至少一处原文。综述引用研究必须保留原文归属，不冒充本文新试验。 |
| entity | 本地ID、study_id、entity_type、mention | 类型为measure/indicator/soil/crop/condition/location；mention是原文跨度，不接受模型自由生成canonical_name。 |

同文献可有多个研究、地点、处理和季别；相同表面形式不自动合并。规范实体归并与原文提及分开；当前编译输出的`normalization`为unresolved，canonical ID/name为null。后续受控归并须记录依据与版本，不能改写原文提及。

## 阶段二：关系及结果判定

输入为同一来源版本、已校验的study/entity列表及原文。模型仅引用阶段一ID，不重新命名端点。输出`relations`，当前任务关系限定为`reports_effect`，方向为measure→indicator；它表示来源报告，不能自动映射成“科学因果成立”或现有图谱的`improves_indicator`。

每条关系包括study_id、source_id、target_id、result原文跨度、direction以及全部qualifier槽位。direction为increase/decrease/no_significant_change/mixed/uncertain/not_reported；数值大小不自动等于改善程度，`no_significant_change`不等于效应严格为零。

qualifier分别保存soil_type、conditions、dose、duration、effect_size、unit、negation、uncertainty、comparator。原文未明确则null，编译后为`status=unknown,evidence=null`；不能补猜剂量/单位、把否定未知当无否定，或把条件未知当条件吻合。量值与单位、季别、对照、实测与预测均须结合原文复核，不直接跨条件汇总。

## 编译和审核边界

- 编译器拒绝错源位置、错块/越界/改写引文、重复ID、相同实体提及重复计数、端点类型/方向错误、不同study ID的端点及缺失综述归属。输入输出规模有界：40个study、200实体、200关系。
- 相同study ID只能证明协议一致；模型仍可能误判两个试验属于同一study。原文语义支持、研究归属是否正确、direction及数值/单位是否恰当需要单独核实。
- 输出固定`review_status=pending`、`semantic_support=unreviewed`、`published_claims_added=0`。规则校验通过不提升为已确认知识。
- 后续候选可辅助内部召回，来源/权限/解析版本失效后停止参与；不得靠本契约绕过文献审核和断言发布审核。
- 当前v1的EvidenceReference/SourceChunk/研究存储接口保持兼容。v2候选不能直接写入只识别文件hash的旧存储；R2.6必须补齐版本绑定和实际读取，再讨论切换。

## 必要故障检查

测试覆盖重复文字的明确位置、错误跨度、规范名自由生成、跨试验关联、关系端点反向、综述缺归属、重复事实及来源解析版本改变后的身份变化。契约和编译器SHA256登记在[冻结记录](../artifacts/knowledge_platform/retrieval-quality-r1/r1-r2-20261030-v1/contract-freeze.json)。模型调用、语义核实、抽取覆盖或专家认证不由这些测试代替。
