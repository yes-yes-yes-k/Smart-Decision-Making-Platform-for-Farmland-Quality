## MODIFIED Requirements

### Requirement: ProblemIdentificationAgent 智能体
系统 SHALL 实现 `ObstacleDiagnosisAgent` 智能体，对应模型3「耕地质量主要问题精准识别模型」，负责识别主要/次要障碍因素和障碍组合。`execute()` 方法 SHALL 在 `FARMland_DIAGNOSIS_AVAILABLE=True` 且提供 `parcel_id` 时调用 `_get_real_diagnosis()` 复用已有方法获取真实诊断结果；模型不可用或缺少 `parcel_id` 时 SHALL 返回统一降级响应（`status: "degraded"`, `degraded: True`, `reason`, `message`），不得返回硬编码 mock 数据。

**模型输入**（来源：xlsx 总览表）：
- 一级农业区、二级农业区、土壤pH、有机质、pH、有效磷、速效钾、容重、耕层质地、灌溉能力、排水能力、地形部位、质地构型、有效土层、地块唯一编码、地块经纬度、地块边界、行政区划边界、农田类型（水田/旱地）

**模型输出**（来源：xlsx 总览表）：
- 主要障碍因素、次要障碍因素、pH障碍等级、有机质障碍等级、有效磷障碍等级、速效钾障碍等级、容重障碍等级、耕层质地障碍等级、灌溉能力障碍等级、排水能力障碍等级、地形部位障碍等级、质地构型障碍等级、障碍因素组合

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

#### Scenario: 真实诊断执行
- **WHEN** `execute()` 被调用且 `FARMland_DIAGNOSIS_AVAILABLE=True` 且 `parcel_id` 已提供
- **THEN** 智能体 SHALL 调用 `_get_real_diagnosis()` 复用已有方法获取真实诊断结果
- **AND** 返回结果中 `simulated` SHALL 为 `False` 或不设置

#### Scenario: 统一降级响应
- **WHEN** `execute()` 被调用但 `FARMland_DIAGNOSIS_AVAILABLE=False` 或未提供 `parcel_id`
- **THEN** 智能体 SHALL 返回统一降级响应：`status: "degraded"`, `degraded: True`, `reason: "model_unavailable" | "missing_input"`, `message: <说明>`
- **AND** SHALL NOT 返回硬编码 mock 数据

### Requirement: AcidificationRemediationAgent 智能体
系统 SHALL 实现 `AcidificationRemediationAgent` 智能体，对应模型4「耕地土壤酸化改良模型」，负责判定酸化程度并计算调理剂施用量。`execute()` 方法 SHALL 调用 `model_4_execution()` 进行真实计算，且 SHALL NOT 在顶层添加误导性的 `simulated: True` 标记。

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

#### Scenario: 真实计算标记
- **WHEN** `execute()` 调用 `model_4_execution()` 成功返回
- **THEN** 返回结果中 `simulated` SHALL 为 `False`
- **AND** SHALL NOT 使用 `MockDataLoader.mark_simulated()` 包装真实计算结果

### Requirement: StabilityRiskAgent 智能体
系统 SHALL 实现 `StabilityRiskAgent` 智能体，对应模型1「耕地质量稳定性与退化风险评价模型」，基于预计算结果识别稳定性、历史变化和退化风险。当 `STABILITY_MODEL_AVAILABLE=True` 且提供 `parcel_id` 时 SHALL 调用 `StabilityStorage` 获取真实结果；不可用时 SHALL 返回统一降级响应（`status: "degraded"`, `degraded: True`, `reason`, `message`），不得返回硬编码 mock 数据。

#### Scenario: 稳定性评价查询
- **WHEN** 用户询问某地块的稳定性评价结果，且预计算数据已就绪
- **THEN** 智能体 SHALL 返回九模块综合评价结果，包括等级边界安全度、指标支撑均衡度等

#### Scenario: 退化风险评估
- **WHEN** 用户询问某地块的退化风险
- **THEN** 智能体 SHALL 返回掉级风险、关键因子退化风险等评估结果

#### Scenario: 预计算数据未就绪
- **WHEN** 用户询问稳定性相关问题，但预计算数据未就绪
- **THEN** 智能体 SHALL 返回"数据未就绪"提示，不返回模拟数据

#### Scenario: 统一降级响应
- **WHEN** `execute()` 被调用但 `STABILITY_MODEL_AVAILABLE=False` 或未提供 `parcel_id`
- **THEN** 智能体 SHALL 返回统一降级响应：`status: "degraded"`, `degraded: True`, `reason: "model_unavailable" | "missing_input"`, `message: <说明>`
- **AND** SHALL NOT 返回硬编码 mock 数据

### Requirement: FarmlandGradeObstacleAgent 智能体
系统 SHALL 实现 `FarmlandGradeObstacleAgent` 智能体，对应模型2「耕地质量等级评价模型」（纯 Python 实现），通过调用 `run_grade_evaluation` 获取地块评价结果，返回基于 GB/T 33469-2016 标准的真实质量等级和障碍度诊断。模型不可用或缺少 `parcel_code` 时 SHALL 返回统一降级响应（`status: "degraded"`, `degraded: True`, `reason`, `message`），不得返回硬编码 mock 数据。

#### Scenario: 质量等级查询
- **WHEN** 用户询问某地块的耕地质量等级，且提供了合法的地块统一代码
- **THEN** 智能体 SHALL 调用 `run_grade_evaluation`（Python 实现），返回质量等级（1-10等）、综合指数和 12 项指标的原始值

#### Scenario: 障碍度诊断
- **WHEN** 用户询问某地块的主要障碍因素，且提供了合法的地块统一代码
- **THEN** 智能体 SHALL 调用 `run_grade_evaluation`（Python 实现），返回障碍度因子排序表（从大到小），识别主要限制因子

#### Scenario: 评价调用失败
- **WHEN** Python 评价调用失败（CSV 数据缺失、地块代码无效、编码字段越界）
- **THEN** 智能体 SHALL 返回明确的错误信息（如"CSV 数据文件缺失"、"未找到地块代码"），`confidence` 字段降低，不返回模拟数据

#### Scenario: 统一降级响应
- **WHEN** `execute()` 被调用但 `GRADE_EVAL_AVAILABLE=False` 或未提供 `parcel_code`
- **THEN** 智能体 SHALL 返回统一降级响应：`status: "degraded"`, `degraded: True`, `reason: "model_unavailable" | "missing_input"`, `message: <说明>`
- **AND** SHALL NOT 返回硬编码 mock 数据
