# farmland-acidification-improvement-model Specification

## Purpose
TBD - created by archiving change add-stability-risk-and-grade-evaluation. Update Purpose after archive.
## Requirements
### Requirement: 模型3 酸化因子提取
系统 SHALL 从请求参数中提取过程酸化模型所需的三普输入数据（pHstart 对应 SJD、交换性氢对应 JHX、交换性铝对应 JLA），以及子模型选择参数（land_type、fertilizer_type），为后续过程计算提供基础数据。

#### Scenario: 提取三普输入与子模型参数
- **WHEN** 系统收到酸化改良请求，且包含 SJD（pH）、JHX（交换性氢）、JLA（交换性铝）字段
- **THEN** 系统 SHALL 提取 pHstart=SJD、Hex=JHX、Alex=JLA，并读取 land_type（默认 upland）和 fertilizer_type（默认 compound）用于子模型选择

#### Scenario: 缺少必填输入
- **WHEN** 系统收到酸化改良请求，但缺少 JHX（交换性氢）或 JLA（交换性铝）
- **THEN** 系统 SHALL 返回 status="rejected" 和缺少必填字段的错误提示

### Requirement: 模型3 酸化程度分区
系统 SHALL 根据 land_type（水田 paddy / 旱地 upland）和 fertilizer_type（尿素 urea / 复合肥 compound）的组合，从4个过程子模型中选择唯一一个执行酸化计算。子模型映射：paddy_urea、paddy_compound、upland_urea、upland_compound。

#### Scenario: 水田复合肥（默认）
- **WHEN** land_type="paddy" 且 fertilizer_type="compound"（或 fertilizer_type 未传，默认 compound）
- **THEN** 系统 SHALL 选择 paddy_compound 子模型执行计算

#### Scenario: 旱地尿素
- **WHEN** land_type="upland"（或未传，默认 upland）且 fertilizer_type="urea"
- **THEN** 系统 SHALL 选择 upland_urea 子模型执行计算

#### Scenario: 非法参数回退
- **WHEN** land_type 或 fertilizer_type 为非法值（非 upland/paddy 或非 urea/compound）
- **THEN** 系统 SHALL 回退到默认值（upland + compound）并在 warning 中追加参数非法提示

### Requirement: 模型3 改良方案生成
系统 SHALL 使用选定的过程子模型，基于 pHstart、Hex、Alex 和~15个默认参数（RPH/R/Y/S/元素含量/FertN/Ndep/pHtarget 等），计算改良剂需求量：亿土康 YTK（kg/ha）和木本泥炭 MBNT（kg/ha）。部分默认参数（RPH/R/Y/S/FertN/Ndep/pHtarget）SHALL 支持通过 API 可选参数覆盖。

#### Scenario: 默认参数计算
- **WHEN** 系统使用默认参数执行过程模型计算，且 pHstart/Hex/Alex 均在合理范围内
- **THEN** 系统 SHALL 返回 YTK（亿土康 kg/ha）和 MBNT（木本泥炭 kg/ha）的数值结果

#### Scenario: 自定义参数覆盖
- **WHEN** API 请求中包含可选参数（如 FertN=200、pHtarget=6.0）
- **THEN** 系统 SHALL 使用传入值覆盖默认参数执行计算，并在结果中标注哪些参数被自定义

#### Scenario: 输入值越界
- **WHEN** pHstart 超出 [3.0, 10.0] 范围，或 Hex/Alex 为负值
- **THEN** 系统 SHALL 返回 status="rejected" 和越界字段列表

### Requirement: 模型3 酸化改良在线查询
系统 SHALL 提供按需计算接口，API 请求参数直接触发过程模型计算并返回结果，不依赖 DB 预计算。若请求包含 parcel_id，系统 MAY 从 evaluation_results 表查询 SJD 值作为 pHstart 补充输入，但 JHX/JLA 必须由请求显式提供。

#### Scenario: 按需计算
- **WHEN** 调用方以 SJD/JHX/JLA 参数发起请求
- **THEN** 系统 SHALL 直接执行过程模型计算并返回 YTK/MBNT，无需 DB 查询

#### Scenario: parcel_id 补充 SJD
- **WHEN** 调用方提供 parcel_id 但未提供 SJD，且 evaluation_results 表中存在该地块的 SJD 值
- **THEN** 系统 SHALL 从 DB 查询 SJD 作为 pHstart，与请求中的 JHX/JLA 一起执行计算

#### Scenario: parcel_id 查无数据
- **WHEN** 调用方提供 parcel_id 但 evaluation_results 表中无该地块，且请求未提供 SJD
- **THEN** 系统 SHALL 返回 status="rejected" 和"无法获取 pH 值，请提供 SJD 参数"的提示

### Requirement: 模型3 改良方案输出格式
系统 SHALL 以标准化格式输出改良方案，包含改良剂需求量（YTK/MBNT）、子模型标识和参数信息。不暴露中间产酸量分解（Adep/Acrop/ANcy/Aagri/Aback）。

#### Scenario: 标准化输出
- **WHEN** 系统成功完成过程模型计算
- **THEN** 输出 SHALL 包含：status（success/rejected）、ytk（亿土康 kg/ha）、mbnt（木本泥炭 kg/ha）、land_type、fertilizer_type、model_version、warning（可选）

#### Scenario: 错误输出
- **WHEN** 系统因输入缺失或越界无法完成计算
- **THEN** 输出 SHALL 包含：status="rejected"、reason（missing_input / input_out_of_range / invalid_parameter）、缺失或越界字段列表

### Requirement: 模型4 v2 版本标识
系统 SHALL 将酸化过程模型的 `model_version` 标识更新为 `process_v2_20260801`，反映与模型作者 2026-08-01 发布的 v2 源码（`模型5_酸化模型_v2_20260801`）同步。所有计算结果（单次 API 调用、批量 CSV 计算）SHALL 返回该版本标识。4 个子模型的核心数学公式、默认参数、系数与 v2 源码逐行一致，无公式变更。

#### Scenario: 单次计算返回 v2 版本
- **WHEN** 系统通过 `calculate_acidification_amendment` 执行单次酸化模型计算
- **THEN** 结果中的 `model_version` 字段 SHALL 为 `process_v2_20260801`

#### Scenario: 批量计算返回 v2 版本
- **WHEN** 系统通过 `run_csv` 执行批量 CSV 计算
- **THEN** 系统 SHALL 通过 `MODEL_VERSION` 常量与单次 API 返回暴露版本号 `process_v2_20260801`；批量 CSV 输出不强制包含 `model_version` 列（run_csv 输出列仅为输入列 + 中间变量列 + 结果列）

#### Scenario: model_4_execution 入口透传 v2 版本
- **WHEN** 调用 `model_4_execution` 入口（含 fallback 场景 model_unavailable）
- **THEN** 返回的 `model_version` 字段 SHALL 为 `process_v2_20260801`

### Requirement: 模型4 批量 CSV 计算工具
系统 SHALL 提供批量 CSV 计算能力，包含内部函数 `run_csv` 和 CLI 脚本 `scripts/run_acidification_batch.py`，支持从 CSV 文件读取多个地块数据，批量执行酸化模型计算，输出包含中间变量和结果变量的 CSV 文件。该能力 SHALL NOT 通过 HTTP API 暴露，仅用于离线批量分析场景。

#### Scenario: run_csv 函数批量计算成功
- **WHEN** 调用 `run_csv(input_file, output_file, land_type, fertilizer_type)`，输入 CSV 包含 `SJD`（或 `pH`）、`Hex`、`Alex` 列，`land_type` 为 `paddy` 或 `upland`，`fertilizer_type` 为 `urea` 或 `compound`
- **THEN** 系统 SHALL 读取输入 CSV，对每行数据执行对应的 4 个子模型之一（paddy_urea/paddy_compound/upland_urea/upland_compound），输出 CSV 包含输入列 + 中间变量列（`Adep`/`Acrop`/`ANcy`/`Aagri`/`Aback`）+ 结果列（`YTK`/`MBNT`），返回填充后的 DataFrame

#### Scenario: CLI 脚本批量计算成功
- **WHEN** 用户执行 `python scripts/run_acidification_batch.py --input <input.csv> --output <output.csv> --land <paddy|upland> --fertilizer <urea|compound>`
- **THEN** 系统 SHALL 执行批量计算并写入输出 CSV，退出码 0 表示成功，控制台输出处理行数

#### Scenario: 输入 CSV 缺少必填列
- **WHEN** 输入 CSV 不包含 `SJD`（或 `pH`）、`Hex`、`Alex` 中的任一列
- **THEN** 系统 SHALL 抛出 `ValueError` 提示缺失的列名（"CSV必须包含pH或SJD、Hex、Alex列"），不执行计算

#### Scenario: 非法 land_type 或 fertilizer_type
- **WHEN** `run_csv` 接收 `land_type` 非 `paddy`/`upland`，或 `fertilizer_type` 非 `urea`/`compound`
- **THEN** 系统 SHALL 抛出 `ValueError`（"土地类型只能为水田或旱地，肥料类型只能为尿素或复合肥"）

#### Scenario: 含 NaN 行的处理
- **WHEN** 输入 CSV 某行的 `SJD`/`Hex`/`Alex` 任一值为 NaN
- **THEN** 系统 SHALL 在输出 CSV 对应行的 7 个计算列（`Adep`/`Acrop`/`ANcy`/`Aagri`/`Aback`/`YTK`/`MBNT`）填入 None，不抛异常，继续处理其他行

#### Scenario: 批量计算不通过 API 暴露
- **WHEN** 调用方尝试通过 HTTP API 触发批量 CSV 计算
- **THEN** 系统 SHALL NOT 提供批量计算端点（`run_csv` 仅作为内部函数和 CLI 工具存在，`chat.py` 路由层无改动）

### Requirement: 模型4 v2 回归测试验证
系统 SHALL 通过 v2 源码提供的 393 个地块测试数据验证项目实现的正确性，确保在大数据集（含极端值如 `Alex=8.95`、`SJD=4.19`）上与 v2 源码输出偏差 < 0.01。测试数据 SHALL 自包含在 `tests/data/acidification_v2/` 目录下，不依赖外部路径。

#### Scenario: 393 地块回归测试通过
- **WHEN** 运行 `test_acidification_v2_regression` 测试，使用 `tests/data/acidification_v2/03_Data.csv`（393 地块输入）和 `tests/data/acidification_v2/04_upland_compound_expected.csv`（期望输出，旱地+复合肥场景）
- **THEN** 所有 393 个地块的 `YTK`/`MBNT` 计算结果 SHALL 与期望值偏差 < 0.01

#### Scenario: 极端值正常处理
- **WHEN** 输入数据包含极端值（如 `Alex=8.95`、`SJD=4.19`、`Hex=1.62`）
- **THEN** 系统 SHALL 正常计算（不抛异常），结果与 v2 源码输出一致

#### Scenario: 中间变量一致性
- **WHEN** 运行回归测试并对比 `Adep`/`Acrop`/`ANcy`/`Aagri`/`Aback` 中间变量
- **THEN** 所有 393 个地块的中间变量 SHALL 与 v2 源码输出偏差 < 0.01（可选验证，回归测试默认验证 YTK/MBNT）

### Requirement: 实现产酸平衡模型计算

系统 SHALL 根据 land_type（旱地/水田）和 fertilizer_type（尿素/复合肥）选择对应的产酸平衡函数，计算石灰施用量（YTK）和有机肥施用量（MBNT）。输入参数为 SJD（pH）、Hex（交换性氢）、Alex（交换性铝）。

#### Scenario: 旱地复合肥计算
- **WHEN** land_type=upland 且 fertilizer_type=compound 且 soil_indicators 有 soil_ph、exchangeable_hydrogen、exchangeable_aluminum
- **THEN** 返回 YTK（石灰施用量）和 MBNT（有机肥施用量），持久化到 acidification_remediation_result 表

#### Scenario: 水田尿素计算
- **WHEN** land_type=paddy 且 fertilizer_type=urea
- **THEN** 使用 paddy_urea 函数计算，YTK 系数为 0.6

### Requirement: 替代外部 .exe 模型依赖

系统 SHALL 使用纯 Python 实现产酸平衡计算，不再依赖外部 .exe 模型。当 soil_indicators 缺少 exchangeable_hydrogen 或 exchangeable_aluminum 时降级。

#### Scenario: 外部模型不可用时正常计算
- **WHEN** 外部 .exe 模型不存在但 DB 有完整的酸化指标
- **THEN** 系统使用 Python 实现计算，status=ok，不返回 model_unavailable

#### Scenario: 交换性铝缺失降级
- **WHEN** soil_indicators 缺少 exchangeable_aluminum
- **THEN** 返回 status=degraded、reason=missing_input

### Requirement: 旧酸化 SQLite 结果表停止作为活动数据源

系统 MUST 废弃旧 SQLite `acidification_results` 表及其 `expected_effect` 内容。新数据库禁止创建该表，运行时代码禁止向该表写入、从该表读取或把其中任何字段转换为当前酸化模型结果。`evaluation_results` 和 `diagnosis_results` 等仍被正式流程使用的表不受此废弃影响。

#### Scenario: 初始化新的诊断 SQLite

- **WHEN** `DiagnosisStorage` 初始化新的 SQLite 数据库
- **THEN** 系统 MUST NOT 创建 `acidification_results` 表
- **AND** 其他仍在使用的评价和障碍诊断表 SHALL 正常创建

#### Scenario: 兼容调用旧保存或读取方法

- **WHEN** 旧调用方调用 `save_acidification()` 或 `get_acidification()`
- **THEN** 系统 SHALL 返回或抛出明确的 deprecated/unavailable 结果
- **AND** 系统 MUST NOT 访问旧 `acidification_results` 表
- **AND** 系统 MUST NOT 返回 `expected_effect`

#### Scenario: 当前酸化按需计算

- **WHEN** 当前酸化入口基于地块或显式指标执行计算
- **THEN** 系统 SHALL 使用正式 Python 过程模型和可验证输入生成结果
- **AND** 系统 MUST NOT 回退读取旧 SQLite 酸化结果表

### Requirement: 生产旧酸化结果可备份废弃

系统 MUST 提供生产迁移能力，对明确配置的旧 SQLite 数据库进行 dry-run 盘点，在可校验备份完成后归档并删除 `acidification_results` 表。历史 `expected_effect` 只能存在于受限迁移备份中，不得继续作为应用数据源。

#### Scenario: dry-run 发现旧结果表

- **WHEN** 运维人员对指定 SQLite 执行迁移 dry-run，且数据库包含 `acidification_results`
- **THEN** 工具 SHALL 报告表结构、记录数量、非空 `expected_effect` 数量和计划备份位置
- **AND** 工具 MUST NOT 修改数据库

#### Scenario: apply 归档并删除旧结果表

- **WHEN** 运维人员显式使用 `--apply` 且备份创建与 SHA-256 校验成功
- **THEN** 工具 SHALL 在受控事务中从活动 SQLite 删除 `acidification_results` 表
- **AND** SHALL 生成包含数据库标识、处理数量、备份校验值、时间和结果状态的 JSON 审计摘要
- **AND** 其他业务表和记录 MUST 保持不变

#### Scenario: 备份或 Schema 校验失败

- **WHEN** 备份失败、SQLite Schema 不符合预期或目标路径不在显式配置范围内
- **THEN** 迁移 MUST 中止且不得删除任何表或记录
- **AND** 工具 SHALL 返回机器可读错误和人工处理建议

#### Scenario: 迁移后运行验证

- **WHEN** 生产迁移完成
- **THEN** 活动数据库 MUST 不再包含 `acidification_results` 表
- **AND** 当前酸化计算与障碍诊断流程 SHALL 继续通过验证
- **AND** API、报告和内部查询 MUST 不再出现 `expected_effect`

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
