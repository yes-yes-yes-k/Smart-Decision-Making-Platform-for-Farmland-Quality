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

