## REMOVED Requirements

### Requirement: DAT Data Validation
**Reason**: 耕地质量等级评价已从 Fortran exe + 二进制 .dat 替换为纯 Python 实现 + CSV 数据文件，不再接受 .dat 文件上传。
**Migration**: 通过 `POST /api/v1/data/import` 上传 CSV 文件（data_type 标识为耕地质量评价数据），部署为 `bin/farmland_quality_eval/Farmland_quality_Level_Database.csv`。

## ADDED Requirements

### Requirement: 耕地质量评价 CSV 数据校验
系统 SHALL 校验上传的耕地质量评价 CSV 文件为非空可读文本文件，文件大小 > 0 且 ≤ 200MB，编码为 UTF-8（带或不带 BOM），且 SHALL 包含 20 个必需字段（SiteID、JD、WD、MJ、SJD、YJZ、YXL、SXJ、TRRZ、YXTCHD、GCHD、JHXLLZ、JHXQLZ、EJNYQcode、XQMCcode、GCZDcode、PSNLcode、GGNLcode、DXBWcode、ZDGXcode），字段名以 CSV 首行表头为准。

#### Scenario: CSV 文件为空
- **WHEN** 上传的耕地质量评价 CSV 文件大小为 0 字节
- **THEN** 系统 SHALL 返回 HTTP 400，响应体 `status: "error"`、`message: "CSV 文件为空"`

#### Scenario: CSV 文件可读且字段完整
- **WHEN** 上传的 CSV 文件大小 > 0 且 ≤ 200MB，含 20 个必需字段
- **THEN** 系统 SHALL 接受该文件并继续部署和触发流程

#### Scenario: CSV 字段缺失
- **WHEN** 上传的 CSV 文件缺少必需字段（如缺少 ejnyq 或 zdgx 列）
- **THEN** 系统 SHALL 返回 HTTP 400，`status: "error"`、`message` 包含缺失的字段名列表

## MODIFIED Requirements

### Requirement: Data Deployment with Backup
系统 SHALL 在部署新数据前，将目标目录下的现有文件移动到 `<target_dir>/backup/<YYYYMMDD-HHMMSS>/` 子目录；部署完成后 SHALL 扫描 `backup/` 下所有时间戳目录，按目录名倒序保留前 3 份，删除其余。诊断 CSV 部署到 `data/farmland_diagnosis/`、shapefile 部署到 `data/farmland_stability/`、耕地质量评价 CSV 部署到 `bin/farmland_quality_eval/`。

#### Scenario: 首次部署（目标目录无现有文件）
- **WHEN** 目标目录下不存在任何现有数据文件（仅有 README.md 或为空）
- **THEN** 系统 SHALL 跳过备份步骤，直接写入新文件，响应中 `backup_path` 为 `null`

#### Scenario: 覆盖部署（目标目录有现有文件）
- **WHEN** 目标目录下存在现有数据文件
- **THEN** 系统 SHALL 将现有数据文件（排除 README.md 和 `backup/` 子目录）移动到 `<target_dir>/backup/<YYYYMMDD-HHMMSS>/`，再写入新文件，响应中 `backup_path` 为该备份目录路径

#### Scenario: 诊断 CSV 部署时重命名为 test.csv
- **WHEN** 上传的诊断 CSV 文件原名为任意名称（如 `mydata.csv`），校验通过后部署到 `data/farmland_diagnosis/`
- **THEN** 系统 SHALL 将文件重命名为 `test.csv` 写入目标目录（与 README 约定和下游 `bulk_evaluate` 默认读取路径一致），原文件名记录在审计日志中

#### Scenario: 耕地质量评价 CSV 部署时重命名为固定文件名
- **WHEN** 上传的耕地质量评价 CSV 文件原名为任意名称，校验通过后部署到 `bin/farmland_quality_eval/`
- **THEN** 系统 SHALL 将文件重命名为 `Farmland_quality_Level_Database.csv` 写入目标目录（与 runner 默认读取路径一致），原文件名记录在审计日志中

#### Scenario: 备份目录超过 3 份
- **WHEN** 部署完成后 `backup/` 下存在超过 3 个时间戳子目录
- **THEN** 系统 SHALL 按目录名倒序保留最新 3 份，删除其余旧备份目录及其内容

### Requirement: Offline Computation Trigger
系统 SHALL 在部署成功后同步触发对应数据类型的离线计算：诊断 CSV 触发 `bulk_evaluate(input_csv, output_db_path)`、shapefile 触发 `precompute.main(shapefile_dir, manifest)`（封装 `run_all_models` → `StabilityStorage.save_results` → `save_final_results` 完整流程）、耕地质量评价 CSV 触发 `FarmlandGradeRunner.check_deployment()`。触发超时为 600 秒（配置项 `DATA_IMPORT_TIMEOUT`）。

#### Scenario: 诊断 CSV 触发 bulk_evaluate 成功
- **WHEN** 诊断 CSV 部署成功后调用 `bulk_evaluate` 返回 `status: "ok"`
- **THEN** 系统 SHALL 返回 HTTP 200，`trigger_result` 包含 `processed` 行数和 `errors` 列表（可能为空）

#### Scenario: 诊断 CSV 触发 bulk_evaluate 返回错误
- **WHEN** 诊断 CSV 部署成功后调用 `bulk_evaluate` 返回 `status: "error"`（例如未知区域名称）
- **THEN** 系统 SHALL 从最近一次 `backup/` 恢复文件，返回 HTTP 500，`status: "error"`、`message: "触发失败已回滚"`、`trigger_error` 包含 bulk_evaluate 返回的错误信息

#### Scenario: shapefile 触发 precompute 成功
- **WHEN** shapefile 部署成功后调用 `precompute.main(shapefile_dir, manifest)` 完整执行 `run_all_models` → `StabilityStorage.save_results` → `save_final_results` 流程并返回 `status: "ok"`
- **THEN** 系统 SHALL 返回 HTTP 200，`trigger_result` 包含 `processed`（处理的地块数）、`saved_to_db`（写入 DB 的记录数）、`output_files`（输出的 shapefile 和 xlsx 文件路径列表）

#### Scenario: 触发抛出未捕获异常
- **WHEN** 触发函数抛出未捕获异常（非返回错误字典）
- **THEN** 系统 SHALL 从最近一次 `backup/` 恢复文件，返回 HTTP 500，`status: "error"`、`message: "触发异常已回滚"`、`detail` 包含异常信息

#### Scenario: 触发超时
- **WHEN** 触发函数执行时间超过 600 秒
- **THEN** 系统 SHALL 终止触发操作，从最近一次 `backup/` 恢复文件，返回 HTTP 504，`status: "error"`、`message: "触发超时已回滚"`

#### Scenario: 耕地质量评价 CSV 部署后自动生效
- **WHEN** 耕地质量评价 CSV 部署成功后调用 `check_deployment` 返回通过
- **THEN** 系统 SHALL 返回 HTTP 200，`trigger_result` 包含 `deployment_ok: true`，后续查询时按需从 CSV 加载数据
