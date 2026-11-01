## MODIFIED Requirements

### Requirement: 酸化 RF 非 HTTP、非离线批处理边界

系统 SHALL 通过当前系统自身的 HTTP API 与内部 callable/domain 入口提供酸化 RF 能力。对外 HTTP 接口 SHALL 由本项目实现并复用本地模型资产与已验证的在线语义；MUST NOT 转发、代理或依赖旧系统 HTTP 服务，此即本要求中"非 HTTP"边界的含义。该能力 SHALL NOT 迁移或执行 `calculate_soil_acidification_with_model.py` 的 CSV 批处理、CSV 结果生成或历史离线结果导入。

#### Scenario: 内部调用 RF

- **WHEN** 当前系统内部调用方请求已核验的酸化 RF 能力
- **THEN** 系统 SHALL 在本地调用适配器、模型加载器和 RF 模型完成预测
- **AND** 运行时 MUST NOT 发起旧系统 HTTP 请求

#### Scenario: 通过本项目 HTTP 接口调用

- **WHEN** 已认证调用方请求本项目酸化 RF HTTP 端点
- **THEN** 系统 SHALL 在本地完成模型加载与预测
- **AND** 请求处理 MUST NOT 转发至旧系统 `/predict`

#### Scenario: 尝试使用离线批处理作为在线实现

- **WHEN** 实现或调用路径试图依赖离线脚本的 CSV 处理或其生成结果完成 RF 在线预测
- **THEN** 系统 SHALL 拒绝该路径或将其视为不支持
- **AND** 系统 MUST NOT 把离线脚本文件路径当作 Web 模型身份或模型文件证据

### Requirement: 酸化 RF 输入适配与缺失值处理

系统 SHALL 在 RF 预测前执行经在线路由和真实模型 metadata 核验的输入字段适配、类型转换和特征顺序构造。特征集与列序 MUST 按模型编号分别维护，并以各模型训练时记录的 `feature_names_in_` 为准；MUST NOT 以 `data_type` 作为特征集划分依据，也不得假定同一类型的不同模型共享字段集。若在线语义确认为对当前请求批次执行 `SimpleImputer(strategy=mean).fit_transform`，实现 SHALL 保留该语义并记录填充字段；在该语义尚未核验时，系统 MUST 显式降级而不得擅自改用零值或臆造训练集均值。规范字段和旧别名值冲突时 SHALL 拒绝请求。

#### Scenario: 核验后的部分缺失输入

- **WHEN** 请求包含已确认模型的部分缺失特征，且在线核验确认请求批次均值填充适用
- **THEN** 系统 SHALL 按核验策略完成填充并返回被填充字段及 imputation 元数据
- **AND** 预测结果 SHALL 标记实际使用的填充策略

#### Scenario: 缺失值语义尚未核验

- **WHEN** 请求存在缺失特征，但在线路由或模型 metadata 尚不能确认填充策略
- **THEN** 系统 SHALL 返回可解释的 degraded/need_verification 结果
- **AND** 系统 MUST NOT 静默以 0 或未经证实的固定均值执行 RF

#### Scenario: 输入无法形成有效批次

- **WHEN** 请求批次为空、某特征全列缺失、字段无法转为模型要求的数值类型或规范字段与别名冲突
- **THEN** 系统 SHALL 返回 rejected/degraded 结果及机器可读原因
- **AND** 系统 MUST NOT 调用 RF 模型

#### Scenario: 同一数据类型的不同模型特征集不同

- **WHEN** 两个模型的 `data_type` 相同但训练特征集不同（例如水田与旱地 reflux）
- **THEN** 系统 SHALL 各自按其 `feature_names_in_` 构造输入
- **AND** 请求只提供另一模型字段集时 SHALL 返回缺列信息，MUST NOT 按当前模型字段错序执行
