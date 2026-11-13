## ADDED Requirements

### Requirement: Cd capability availability
系统 SHALL 声明 Cd 统计、参数查询与计算能力的指标、数据类别、操作、地理层级、时间支持、输入契约、单位状态和就绪原因，并登记八类输入输出通量。

#### Scenario: Flux service is pending
- **WHEN** 用户请求尚未就绪的某类 Cd 通量计算
- **THEN** 系统 SHALL 返回具体能力缺项及原因，并保留已经可用的查询入口

#### Scenario: Existing capabilities are available
- **WHEN** 用户请求已核验的土壤统计、作物或有效态 Cd 结果、参数契约或纯参数预测
- **THEN** 系统 SHALL 通过现有工具执行链调用相应服务并返回实际结果

### Requirement: Resolve analysis scope and data category
系统 SHALL 验证地区对象、指标与数据类别，支持省、市、县、乡镇及地块的目标查询范围，并依据实际服务和数据覆盖决定可回答范围。

#### Scenario: Ambiguous cadmium query
- **WHEN** 上下文无法确定用户所问镉含量的指标、实测或预测类别、或同名地区
- **THEN** 系统 SHALL 追问歧义项并在对象验证后执行相应服务

#### Scenario: Partial spatial coverage
- **WHEN** 请求区域仅有局部地块或记录覆盖
- **THEN** 系统 SHALL 显示实际覆盖范围与数量对象，将统计结果限定于已覆盖数据

### Requirement: Preserve statistical and source semantics
系统 SHALL 对土壤区域结果保留面积加权均值、有效地块数与有效面积，对预测结果使用记录数、算术均值、中位数及服务支持的统计项，并默认分别展示不同来源。

#### Scenario: Regional soil statistics
- **WHEN** 用户查询某县土壤总镉统计
- **THEN** 系统 SHALL 展示服务返回的面积加权口径、有效地块数和面积及可用极值

#### Scenario: Prediction statistics with multiple sources
- **WHEN** 自有和移植来源均有 Cd 预测记录
- **THEN** 系统 SHALL 分别查询展示来源、记录数、分布统计和单位核验状态，保留现有服务的分位数和标准差算法

### Requirement: Temporal truthfulness
系统 SHALL 区分统计年度、实际测量年份、插补信息与查询时间。指定年份请求 SHALL 仅使用满足时间条件的数据。

#### Scenario: Annual soil snapshot
- **WHEN** 查询具有年度快照的土壤指标
- **THEN** 系统 SHALL 返回实际使用年度及测量年份和插补信息，未指定年份时明确所选数据时期

#### Scenario: Prediction has no temporal filter
- **WHEN** 用户指定年份而预测服务无法按该年份筛选
- **THEN** 系统 SHALL 说明限制并询问是否查看时期未知数据

### Requirement: Parameter lookup and validated computation
系统 SHALL 提供参数定义、单位、适用条件及地区已有值来源，自动补入条件匹配的值，集中追问剩余必需参数。经验默认值 SHALL 经用户接受后使用，计算 SHALL 调用后端公式或模型。

#### Scenario: Incomplete inputs
- **WHEN** 用户仅提供部分必需参数
- **THEN** 系统 SHALL 查询匹配的已有参数并列出剩余缺项，参数验证通过后执行计算

#### Scenario: Unverified units
- **WHEN** 结果或参数单位尚未核验
- **THEN** 系统 SHALL 保留原始值与核验状态，并将依赖该单位的换算、通量计算及超标判断标记为待核验

### Requirement: Multi-message parameter continuity
系统 SHALL 在用户及会话隔离的草稿中记录参数、单位、来源、适用范围、地区、时期及版本，支持跨消息补参和修改。

#### Scenario: Change one parameter
- **WHEN** 用户要求修改上一组参数中的一个值并重新计算
- **THEN** 系统 SHALL 更新指定项、校验受影响条件，并展示实际输入摘要与新结果

#### Scenario: Change region or year
- **WHEN** 用户切换地区或年份
- **THEN** 系统 SHALL 重新查询受影响的地区参数，并对单位或适用性歧义追问

#### Scenario: Stale response
- **WHEN** 旧草稿版本的工具响应在新版本之后返回
- **THEN** 系统 SHALL 将结果关联到原版本并保护当前草稿与结果的一致性

### Requirement: Explicit and idempotent trial persistence
系统 SHALL 在用户明确要求保存时创建独立试算记录，包含完整输入、来源、地区、时期、计算版本和输出，并通过事务及唯一约束保证同一用户同一结果的保存幂等性。

#### Scenario: Save and retry
- **WHEN** 用户重复保存同一结果或保存请求并发重试
- **THEN** 系统 SHALL 返回同一记录，失败后允许安全重试

#### Scenario: Save changed calculation
- **WHEN** 用户修改参数、重新计算并要求保存
- **THEN** 系统 SHALL 创建关联新结果的记录并保留先前试算

#### Scenario: Record ownership
- **WHEN** 请求涉及其他用户的会话草稿或试算记录
- **THEN** 系统 SHALL 执行归属校验并拒绝越权访问

### Requirement: Bounded flux summaries
系统 SHALL 在通量服务就绪后按一致的单位、时期和空间覆盖汇总，单位面积通量 SHALL 结合适用面积换算区域总量，输入、输出及净收支 SHALL 披露分项覆盖。

#### Scenario: Missing components
- **WHEN** 请求总通量但部分分项缺失
- **THEN** 系统 SHALL 仅返回口径可比的已覆盖小计及缺项说明

### Requirement: Consistent conversational presentation
系统 SHALL 在普通及流式聊天中返回简短结论、结果表格、统计口径和来源，计算附实际输入摘要，并区分无数据、缺参数、能力不可用、单位未核验与服务异常。

#### Scenario: Empty result versus failure
- **WHEN** 服务返回空数据或执行失败
- **THEN** 系统 SHALL 展示对应真实状态，保留用户已确定的查询条件供后续操作
