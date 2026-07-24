# professional-model-agents Specification

## Purpose
TBD - created by archiving change multi-agent-model-framework. Update Purpose after archive.
## Requirements
### Requirement: StabilityRiskAgent 智能体
系统 SHALL 实现 `StabilityRiskAgent` 智能体，对应模型1「耕地质量等级稳定性与退化风险识别模型」，通过调用模型1 的在线查询接口（`get_parcel_result`）获取预计算结果，返回基于真实九模块分析的稳定性评价和退化风险识别，不再使用模拟数据。

#### Scenario: 等级稳定性评价
- **WHEN** 用户询问"全省耕地质量整体稳定吗？"，且模型1 预计算结果已就绪
- **THEN** 智能体 SHALL 调用模型1 在线查询接口获取历史变化趋势模块（module=5）结果，返回基于真实数据的稳定性评价，包括持续改善/基本稳定/波动退化/持续退化的分类统计

#### Scenario: 退化风险识别
- **WHEN** 用户询问"哪些县区高等级耕地存在退化风险？"，且模型1 预计算结果已就绪
- **THEN** 智能体 SHALL 调用模型1 在线查询接口获取掉级风险（module=6）和关键因子退化风险（module=7）模块结果，返回真实的退化风险分布和关键退化因子

#### Scenario: 重点关注清单
- **WHEN** 用户询问"哪些对象需要纳入重点关注清单？"，且模型1 预计算结果已就绪
- **THEN** 智能体 SHALL 调用模型1 在线查询接口获取持续低质风险（module=9）模块结果，输出需要关注的地块清单、低质年份数和风险类型

#### Scenario: 预计算数据未就绪
- **WHEN** 用户询问稳定性或退化风险相关问题，但模型1 离线预计算结果未就绪
- **THEN** 智能体 SHALL 返回"模型1 数据未就绪，请先执行离线预计算"的提示，`confidence` 字段降低，不返回模拟数据冒充真实结果

### Requirement: PotentialAssessmentAgent 智能体
系统 SHALL 实现 `PotentialAssessmentAgent` 智能体，对应模型2「耕地质量提升潜力评估模型」，负责评估耕地质量提升潜力和计算障碍度值。

**模型输入**（来源：xlsx 总览表）：
- 地块唯一编码、地块经纬度、pH值、有机质、有效磷、速效钾、土壤容重、有效土层厚度、耕层质地、质地构型、灌溉能力、排水能力、地形部位、耕地质量等级、pH增加值（模型4传参）、有机质增加值（模型5传参）

**模型输出**（来源：xlsx 总览表）：
- 潜在pH值、潜在有机质、潜在有效磷、潜在速效钾、潜在土壤容重、潜在有效土层厚度、潜在耕层质地、潜在灌溉能力、潜在地形部位、潜在排水能力、潜在耕地质量等级、11 个评价指标的潜在障碍度值

#### Scenario: 提升潜力评估
- **WHEN** 用户询问"辖区耕地质量提升的总体潜力有多大？可增产多少粮食？"
- **THEN** 智能体 SHALL 回答耕地质量平均可从 xx 等提升至 xx 等，可改善面积 xx 万亩，粮食增产潜力约 xx 万吨

#### Scenario: 目标 pH 计算
- **WHEN** 智能体接收到当前 pH 值和质量目标
- **THEN** 智能体 SHALL 计算目标 pH 或 pH 增加值，供模型1和模型3使用

#### Scenario: 县域潜力分布
- **WHEN** 县域执行端用户询问"我们县划定的优先改良片区具体在哪几个村？每块潜力多大？"
- **THEN** 智能体 SHALL 输出一幅大比例尺地图，以地块为单元用颜色深浅表示潜力值，选中任一地块弹出信息窗显示村名、地块编号、面积、当前质量等级、目标等级、潜力分值

#### Scenario: 农户地块诊断
- **WHEN** 农户询问"我这块地到底有啥毛病？"
- **THEN** 智能体 SHALL 给出地块耕地质量等级和诊断结论，重点标出地块的主要障碍因子，同时配上示意图

### Requirement: ProblemIdentificationAgent 智能体
系统 SHALL 实现 `ProblemIdentificationAgent` 智能体，对应模型3「耕地质量主要问题精准识别模型」，负责识别主要/次要障碍因素和障碍组合。

**模型输入**（来源：xlsx 总览表）：
- 一级农业区、二级农业区、土壤pH、有机质、pH、有效磷、速效钾、容重、耕层质地、灌溉能力、排水能力、地形部位、质地构型、有效土层、地块唯一编码、地块经纬度、地块边界、行政区划边界、农田类型（水田/旱地）

**模型输出**（来源：xlsx 总览表）：
- 主要障碍因素、次要障碍因素、pH障碍等级、有机质障碍等级、有效磷障碍等级、速效钾障碍等级、容重障碍等级、耕层质地障碍等级、灌溉能力障碍等级、排水能力障碍等级、地形部位障碍等级、质地构型障碍等级、有效土层障碍等级、障碍因素组合

#### Scenario: 障碍因素识别
- **WHEN** 用户询问"全省耕地质量存在哪些问题？"
- **THEN** 智能体 SHALL 返回全省/市范围内的主要障碍因素、次要障碍因素和障碍组合统计

#### Scenario: 指标障碍等级统计
- **WHEN** 智能体接收到地块指标数据
- **THEN** 智能体 SHALL 输出每个指标的障碍等级（1~10级频数统计），最后一列为该指标是否主要、次要障碍因素

#### Scenario: 县域障碍诊断
- **WHEN** 县域执行端用户询问"县/乡镇里的耕地在哪些方面有问题"
- **THEN** 智能体 SHALL 统计全区域内的信息，每个指标为一行，列为每个指标1~10等级的频数统计，最后一列为是否主要、次要障碍因素

#### Scenario: 农户地块问题
- **WHEN** 农户询问"我这块地有没有问题？"
- **THEN** 智能体 SHALL 用简单语言说明耕地质量等级、列举低等级的指标

### Requirement: AcidificationRemediationAgent 智能体
系统 SHALL 实现 `AcidificationRemediationAgent` 智能体，对应模型4「耕地土壤酸化改良模型」，负责判定酸化程度并计算调理剂施用量。

**模型输入**（来源：xlsx 总览表）：
- 土壤pH、有机质、阳离子交换量、土壤黏粒、总氮、游离铁、总铁、交换性氢离子、交换性铝离子、全氮、全磷、全钾、游离氧化铁、年降雨量、年降雨pH年均值、施肥类型及施肥量、作物类型及产量、农田类型（水田/旱地）、目标pH（或pH增加值）

**模型输出**（来源：xlsx 总览表）：
- 土壤酸化程度级别、土壤本底酸量、农业活动产酸量、碱性调理剂施用量、木本泥炭施用量

#### Scenario: 酸化程度判定
- **WHEN** 用户询问"查询区域内农用地土壤酸化程度如何，不同酸化等级比例分别多少？"
- **THEN** 智能体 SHALL 按 GB/T 42817-2023 标准（酸性 5.5≤pH<6.5、强酸性 4.5≤pH<5.5、极强酸性 pH<4.5）输出酸化等级和比例

#### Scenario: 调理剂施用量计算
- **WHEN** 农户询问"我的田酸化了，pH是XX，我要施加多少碱性调理剂可以治理好？"
- **THEN** 智能体 SHALL 输出使土壤pH从当前值提升到6.5目标值的碱性调理剂建议施用量，结合 GB/T 42817-2023 和 NY/T 443-2019 标准

#### Scenario: 不同土地利用类型酸化
- **WHEN** 用户询问"查询区域内不同土地利用类型的酸化程度"
- **THEN** 智能体 SHALL 输出旱地、水田、园地、林地等不同土地利用类型土壤的酸化等级及比例

#### Scenario: 农户酸化判断
- **WHEN** 农户询问"我的这块田酸化严重吗？"
- **THEN** 智能体 SHALL 输出该地块土壤酸化等级

### Requirement: OrganicMatterAgent 智能体
系统 SHALL 实现 `OrganicMatterAgent` 智能体，对应模型5「耕地土壤有机质培肥提升模型」，负责有机质提升评估和有机肥施用量计算。

**模型输入**（来源：xlsx 总览表）：
- 土壤pH、有机质、有效磷、速效钾、总氮、阳离子交换量、土壤黏粒、交换性氢离子、交换性铝离子、游离铁、总铁、全氮、全磷、全钾、游离氧化铁、土壤容重、年降雨量、年降雨pH年均值、施肥类型及施肥量、作物类型及产量、农田类型（水田/旱地）、目标土壤有机质

**模型输出**（来源：xlsx 总览表）：
- 有机肥/秸秆、有机肥施用量、秸秆施用量

#### Scenario: 有机质含量评估
- **WHEN** 用户询问"全省耕地土壤有机质含量如何，空间分布情况？"
- **THEN** 智能体 SHALL 返回总体水平（平均含量及高、中、低等级占比）和空间分布（哪些区域较高、较低，是否呈现地形梯度）

#### Scenario: 有机肥施用量计算
- **WHEN** 农户询问"为了提升耕地土壤有机质，有机肥或者秸秆每亩施用量多少？"
- **THEN** 智能体 SHALL 分别输出有机肥和秸秆还田的每亩施用量

#### Scenario: 有机质低值区域识别
- **WHEN** 县域执行端用户询问"本县耕地土壤有机质平均含量是多少？"
- **THEN** 智能体 SHALL 说明本县耕地土壤有机质平均含量及高、中、低等级占比，识别出土壤有机质低的区域并给出明确数值

#### Scenario: 有机质低值原因
- **WHEN** 用户询问"耕地有机质含量低的原因是什么？"
- **THEN** 智能体 SHALL 从土壤类型、气候、地形、耕作制度、秸秆还田和施肥管理等方面解释差异，指出低有机质区域及后续培肥重点

### Requirement: FertilityMLAgent 智能体
系统 SHALL 实现 `FertilityMLAgent` 智能体，对应模型6「耕地综合地力改良提升模型」，负责综合多个模型结果形成分区分类的综合提升建议。该智能体内部使用预训练的 ExtraTreesRegressor 模型对 SOC 和 Dose 进行 ML 预测作为综合地力评估的计算单元，并通过 `framework/agents/manager.py` 注册为 `model-6`。

**模型输入**（来源：xlsx 总览表，xlsx 未填写，保留现有实现）：
- 综合上述模型1-5的输入指标，包括土壤理化指标、农田类型、目标有机质等

**模型输出**（来源：xlsx 总览表，xlsx 未填写，保留现有实现）：
- 综合提升建议（基于 SOC 预测和 Dose 预测的综合地力评估）

#### Scenario: 农户综合诊断
- **WHEN** 农户询问"我的田肥力怎么样？"
- **THEN** 智能体 SHALL 同时返回 SOC 和 Dose 两个预测值，并提供综合诊断说明（如"SOC 预测 X g/kg，建议施肥量约 Y kg/亩"）

#### Scenario: 农户 SOC 预测查询
- **WHEN** 农户询问"我的田土壤有机碳含量大概多少？"
- **THEN** 智能体 SHALL 调用 `model_6_execution` 返回 `soc_prediction`（g/kg）、`soc_confidence`（0.91）等结构化结果

#### Scenario: 农户 Dose 施用量预测查询
- **WHEN** 农户询问"我这块地大概需要施多少有机肥？"
- **THEN** 智能体 SHALL 调用 `model_6_execution` 返回 `dose_prediction`（kg/亩）、`dose_confidence`（0.47）、`dose_warning` 字段，并在回答中标注"预测结果仅供参考"

#### Scenario: 模型降级时的回退响应
- **WHEN** `model_6_execution` 返回 `status: "fallback"`（模型文件缺失或 sklearn 未安装）
- **THEN** 智能体 SHALL 在回答中标注"基于训练集均值的估算"而非"基于 ML 模型预测"，confidence 降为 0.3

#### Scenario: Agent 独立执行无依赖
- **WHEN** `AgentManager.process` 调用 farmer 角色对应的智能体集合
- **THEN** `model-6`（FertilityMLAgent）的 `dependencies` SHALL 为空列表 `[]`，可与其他模型并行执行

#### Scenario: 非肥力相关问题跳过 model-6
- **WHEN** 农户角色提出的问题不包含肥力相关关键词（如"我的田 pH 如何"），且 `AgentManager` 路由到 model-6
- **THEN** `AgentManager._should_execute_agent` SHALL 返回 False，model-6 不被执行

#### Scenario: 输入越界时返回拒绝响应
- **WHEN** `FertilityMLAgent.execute` 收到包含越界特征值的输入，`model_6_execution` 返回 `status: "rejected"`
- **THEN** Agent SHALL 在回答中明文标注越界特征和合法范围，不返回预测值

### Requirement: FarmlandGradeObstacleAgent 智能体
系统 SHALL 实现 `FarmlandGradeObstacleAgent` 智能体，对应耕地质量等级和障碍度评价模型（Fortran exe），通过 subprocess 调用 `Farmland_quality_evaluation.exe` 获取地块评价结果，返回基于 GB/T 33469-2016 标准的真实质量等级和障碍度诊断。

#### Scenario: 质量等级查询
- **WHEN** 用户询问某地块的耕地质量等级，且提供了合法的地块统一代码
- **THEN** 智能体 SHALL 通过 subprocess 调用 exe，返回质量等级（1-10等）、综合指数和 12 项指标的隶属度

#### Scenario: 障碍度诊断
- **WHEN** 用户询问某地块的主要障碍因素，且提供了合法的地块统一代码
- **THEN** 智能体 SHALL 通过 subprocess 调用 exe，返回障碍度因子排序表（从大到小），识别主要限制因子

#### Scenario: exe 调用失败
- **WHEN** exe 调用失败（超时、数据库缺失、exe 未部署、地块代码无效）
- **THEN** 智能体 SHALL 返回明确的错误信息（如"评价服务超时"、"数据库文件缺失"、"未找到地块代码"），`confidence` 字段降低，不返回模拟数据

### Requirement: ObstacleDiagnosisAgent 智能体
系统 SHALL 实现 `ObstacleDiagnosisAgent` 智能体，对应模型3「耕地质量主要问题精准识别模型」，通过调用模型3 的在线查询接口获取障碍诊断结果，返回真实的障碍类型、主要/次要障碍因素和障碍组合类型。

#### Scenario: 障碍诊断查询
- **WHEN** 用户询问某地块的障碍诊断结果，且模型3 批量评价和诊断结果已就绪
- **THEN** 智能体 SHALL 调用模型3 在线查询接口，返回障碍类型（单一障碍/多障碍）、主要障碍因素、次要障碍因素和障碍度排序

#### Scenario: 障碍组合类型识别
- **WHEN** 用户询问某地块的障碍组合类型，且该地块存在多个中度以上障碍因素
- **THEN** 智能体 SHALL 返回障碍组合类型描述（如"酸化+有机质不足"、"养分失衡+耕层条件偏弱"）

#### Scenario: 诊断数据未就绪
- **WHEN** 用户询问障碍诊断相关问题，但模型3 批量评价和诊断结果未就绪
- **THEN** 智能体 SHALL 返回"模型3 数据未就绪，请先执行批量评价"的提示，不返回模拟数据

### Requirement: AcidificationImprovementAgent 智能体
系统 SHALL 实现 `AcidificationImprovementAgent` 智能体，对应模型3「耕地土壤酸化改良模型」，通过调用模型3 的在线查询接口获取酸化程度分区和改良方案，返回真实的酸化程度、调理剂施用量建议和改良措施。

#### Scenario: 酸化程度查询
- **WHEN** 用户询问某地块的酸化程度，且模型3 批量评价和诊断结果已就绪
- **THEN** 智能体 SHALL 返回酸化程度（无明显酸化/轻度/中度/重度）、酸化方向（酸化/碱化）和 pH 值

#### Scenario: 改良方案查询
- **WHEN** 用户询问某地块的酸化改良方案，且该地块被判定为中度或重度酸化
- **THEN** 智能体 SHALL 返回调理剂施用量建议（如石灰施用量 kg/亩）和改良措施（如施肥方式、轮作制度调整）

#### Scenario: 轻度或无酸化
- **WHEN** 用户询问某地块的酸化改良方案，但该地块为轻度酸化或无明显酸化
- **THEN** 智能体 SHALL 返回"无需特殊改良"的提示，建议常规监测和维护

### Requirement: 模型3 与模型1 整合诊断
系统 SHALL 在 agent 层实现模型3（障碍诊断）与模型1（退化风险）的整合，当用户请求综合诊断时，同时调用两个模型并整合结果。

#### Scenario: 综合诊断查询
- **WHEN** 用户询问某地块的综合诊断结果（同时涉及稳定性和障碍诊断），且两个模型的数据均已就绪
- **THEN** 系统 SHALL 同时调用 StabilityRiskAgent 和 ObstacleDiagnosisAgent，整合退化风险和障碍诊断结果，返回综合诊断报告

