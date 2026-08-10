## MODIFIED Requirements

### Requirement: Six Professional Models Support

系统 SHALL 支持并且只支持 6 个正式专题模型。工作流 SHALL 将耕地质量等级评价和提升潜力评估统一交由 `model-2` 执行；`model-7` SHALL NOT 被注册、调度或计入模型数量。

#### Scenario: Execute acidification assessment
- **WHEN** an acidification assessment request is submitted
- **THEN** the system SHALL execute the acidification model

#### Scenario: Execute lime demand calculation
- **WHEN** a lime demand calculation request is submitted
- **THEN** the system SHALL execute the lime calculator model

#### Scenario: Execute other assessment models
- **WHEN** requests for other models are submitted
- **THEN** the system SHALL route to the appropriate model

#### Scenario: 执行模型2真实评价
- **WHEN** 多智能体工作流收到质量等级或提升潜力问题以及有效 `parcel_code`
- **THEN** 工作流 SHALL 调用 `model-2` 返回真实 Python 计算结果
- **AND** `agents_invoked` SHALL 仅包含 `model-2` 作为该问题的专题执行者

#### Scenario: 执行其他专题模型
- **WHEN** 多智能体工作流收到稳定性、障碍诊断、酸化改良、有机质培肥或肥力预测问题
- **THEN** 工作流 SHALL 将请求路由到相应的 `model-1`、`model-3`、`model-4`、`model-5` 或 `model-6`
- **AND** SHALL NOT 注册或调用 `model-7`

### Requirement: 地块标识符上下文透传

系统 SHALL 将请求中的 `parcel_id`、`parcel_code`、`xqmc_code`、`scenario` 和可选 `csv_path` 原样写入 Agent 上下文。`parcel_id` SHALL 继续供依赖数据库记录的专题模型使用；`parcel_code` SHALL 供 `model-2` 进行真实质量等级和单地块潜力计算；`xqmc_code` 与 `scenario` SHALL 供县域潜力情景计算使用。

#### Scenario: 传递 parcel_id 触发 DB 真实查询
- **WHEN** request 包含 `parcel_id: "1"` 且问题路由到 model-1（StabilityRiskAgent）
- **THEN** `execute_models` SHALL 将 `parcel_id` 透传到 context
- **AND** model-1 SHALL 用 `parcel_id="1"` 查询 stability_db 返回真实稳定性记录（非 mock pH=5.5）

#### Scenario: 传递 parcel_code 触发模型2真实计算
- **WHEN** 请求包含 `parcel_code: "A0001"` 且问题被路由到 `model-2`
- **THEN** 工作流 SHALL 将 `parcel_code` 传入 `model-2`
- **AND** `model-2` SHALL 返回真实 Python 质量等级或潜力计算结果，且 `simulated` 为 `false`

#### Scenario: 传递 parcel_code 触发模型2真实计算
- **WHEN** request 包含 `parcel_code: "A0001"` 且问题路由到质量等级或提升潜力能力
- **THEN** `execute_models` SHALL 将 `parcel_code` 透传到 `model-2`
- **AND** `model-2` SHALL 使用项目内纯 Python 评价引擎返回真实结果，不再要求或调用 Fortran exe

#### Scenario: 双 ID 并存
- **WHEN** request 同时包含 `parcel_id: "1"` 和 `parcel_code: "A0001"`
- **THEN** context SHALL 同时携带两个字段
- **AND** model-1/3/4 SHALL 读 `parcel_id` 查 DB，model-2 SHALL 读 `parcel_code` 进行 Python 评价，互不干扰

#### Scenario: 未传地块标识符时保留错误契约
- **WHEN** type 5 或单地块 type 6 请求未提供 `parcel_code`，或县域 type 6 请求缺少 `xqmc_code`/`scenario`
- **THEN** 工作流 SHALL 返回 `status: "error"` 和对应的机器可读错误码（`MISSING_PARCEL_CODE` 或 `MISSING_SCENARIO`）
- **AND** 结果 SHALL 明确说明缺少真实计算输入，不得伪造地块级或县域真实计算结果
