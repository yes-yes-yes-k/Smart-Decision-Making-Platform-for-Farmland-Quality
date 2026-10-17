## ADDED Requirements

### Requirement: 独立酸化 RF 在线预测能力

系统 SHALL 提供独立于 model-4 过程模型的酸化 RF 预测能力。该能力 SHALL 按经核验的旧 Web 在线路由选择模型、适配输入并返回 RF 预测结果；不得把 model-4 过程计算作为 RF 的隐式实现、回退或自动组合。模型选择所需的 `ModelID`、`Data_type`、`Land_type`、`ModelFilePath` 和模型 metadata MUST 来自已核验的旧系统数据库/模型资产证据，不能仅依据离线脚本路径推断。

#### Scenario: 使用已核验模型执行独立 RF 预测

- **WHEN** 调用方通过当前系统内部 callable 入口提交满足已核验模型特征契约的酸化 RF 请求
- **THEN** 系统 SHALL 按核验的模型 ID、土地类型和特征顺序加载对应模型并返回 RF 原始预测、实际模型元数据和独立的 RF 来源标识
- **AND** 系统 MUST NOT 调用旧 HTTP `/predict` 或自动执行 model-4 过程模型

#### Scenario: 模型身份或资产未核验

- **WHEN** `ModelID`、`Data_type`、`Land_type`、`ModelFilePath` 或模型 metadata 无法从可靠证据确认
- **THEN** 系统 SHALL 返回明确的未核验/不可用降级结果
- **AND** 系统 MUST NOT 通过离线脚本路径猜测模型身份或伪造 RF 成功结果

### Requirement: 酸化 RF 输入适配与缺失值处理

系统 SHALL 在 RF 预测前执行经在线路由和真实模型 metadata 核验的输入字段适配、类型转换和特征顺序构造。若在线语义确认为对当前请求批次执行 `SimpleImputer(strategy=mean).fit_transform`，实现 SHALL 保留该语义并记录填充字段；在该语义尚未核验时，系统 MUST 显式降级而不得擅自改用零值或臆造训练集均值。规范字段和旧别名值冲突时 SHALL 拒绝请求。

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

### Requirement: 酸化 RF reduce 与 reflux 输出语义

系统 SHALL 将 RF 原始 prediction 与业务转换结果分层保存。对于 `reduce`，只有在在线路由和真实模型 metadata 核验转换单位、系数、精度和负值语义后，才应用 `predict_to_Q`、`Q_to_t_ha`、`t_ha_to_t_mu` 链；对于水田 `reflux`，只有核验确认旧在线语义后才应用绝对值处理。未核验时 SHALL 保留原始预测并返回转换未核验的降级信息，不得猜测单位或符号规则。

#### Scenario: 已核验 reduce 结果

- **WHEN** RF 模型输出类型为已核验的 reduce，且三段转换的单位与参数已确认
- **THEN** 系统 SHALL 返回原始 prediction 和按核验链转换的业务结果
- **AND** 结果 SHALL 标记转换版本、单位及来源元数据

#### Scenario: 水田 reflux 绝对值

- **WHEN** 已核验在线语义确认当前水田 RF 输出使用 reflux 且需要绝对值处理
- **THEN** 系统 SHALL 对 reflux 结果应用绝对值并保留原始有符号 prediction
- **AND** 非水田或未确认适用范围时 MUST NOT 擅自应用该规则

#### Scenario: 转换语义未核验

- **WHEN** reduce/reflux 的输出单位、系数或适用土地类型无法由在线路由和真实 metadata 确认
- **THEN** 系统 SHALL 返回原始预测及转换未核验状态
- **AND** 系统 MUST NOT 将推测的转换结果作为确定性施用量输出

### Requirement: 酸化 RF 非 HTTP、非离线批处理边界

系统 SHALL 通过当前系统内部 callable/domain 入口提供酸化 RF 能力，不依赖旧系统 HTTP 服务。该能力 SHALL NOT 迁移或执行 `calculate_soil_acidification_with_model.py` 的 CSV 批处理、CSV 结果生成或历史离线结果导入；是否增加外部 HTTP API MUST 由后续独立 change 决定。

#### Scenario: 内部调用 RF

- **WHEN** 当前系统内部调用方请求已核验的酸化 RF 能力
- **THEN** 系统 SHALL 在本地调用适配器、模型加载器和 RF 模型完成预测
- **AND** 运行时 MUST NOT 发起旧系统 HTTP 请求

#### Scenario: 尝试使用离线批处理作为在线实现

- **WHEN** 实现或调用路径试图依赖离线脚本的 CSV 处理或其生成结果完成 RF 在线预测
- **THEN** 系统 SHALL 拒绝该路径或将其视为不支持
- **AND** 系统 MUST NOT 把离线脚本文件路径当作 Web 模型身份或模型文件证据
