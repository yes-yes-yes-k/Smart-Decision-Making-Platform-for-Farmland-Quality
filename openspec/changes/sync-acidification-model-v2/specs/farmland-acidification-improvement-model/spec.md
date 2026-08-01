## ADDED Requirements

### Requirement: 模型3 v2 版本标识
系统 SHALL 将酸化过程模型的 `model_version` 标识更新为 `process_v2_20260801`，反映与模型作者 2026-08-01 发布的 v2 源码（`模型5_酸化模型_v2_20260801`）同步。所有计算结果（单次 API 调用、批量 CSV 计算）SHALL 返回该版本标识。4 个子模型的核心数学公式、默认参数、系数与 v2 源码逐行一致，无公式变更。

#### Scenario: 单次计算返回 v2 版本
- **WHEN** 系统通过 `calculate_acidification_amendment` 执行单次酸化模型计算
- **THEN** 结果中的 `model_version` 字段 SHALL 为 `process_v2_20260801`

#### Scenario: 批量计算返回 v2 版本
- **WHEN** 系统通过 `run_csv` 执行批量 CSV 计算
- **THEN** 输出的每行结果 SHALL 包含 `model_version = process_v2_20260801`（通过 CLI 脚本元数据或单独版本文件体现，CSV 行内可选）

#### Scenario: model_4_execution 入口透传 v2 版本
- **WHEN** 调用 `model_4_execution` 入口（含 fallback 场景 model_unavailable）
- **THEN** 返回的 `model_version` 字段 SHALL 为 `process_v2_20260801`

### Requirement: 模型3 批量 CSV 计算工具
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

### Requirement: 模型3 v2 回归测试验证
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
