## ADDED Requirements

### Requirement: Data Import Endpoint
系统 SHALL 提供 `POST /api/v1/data/import` 端点，接受 multipart/form-data 请求，通过 form 字段 `data_type`（取值 `csv` / `shapefile` / `dat`）区分数据类型，按类型执行校验、部署、触发离线计算。

#### Scenario: 成功上传 CSV 数据
- **WHEN** admin 用户上传 `data_type=csv` 的 multipart 请求，包含一个 `.csv` 文件，文件大小 ≤ 200MB，且 CSV 首行包含全部 14 项必需列
- **THEN** 系统 SHALL 返回 HTTP 200，响应体包含 `status: "ok"`、`data_type: "csv"`、`deployed_path`（部署后的绝对路径）、`backup_path`（备份目录路径）、`trigger_result`（`bulk_evaluate` 返回的字典，含 `processed` 行数和 `errors` 列表）

#### Scenario: 成功上传 shapefile zip
- **WHEN** admin 用户上传 `data_type=shapefile` 的 multipart 请求，包含一个 `.zip` 文件，zip 内含 3 期完整 shapefile（每期含 .shp/.cpg/.dbf/.prj/.shx）和 `manifest.json`
- **THEN** 系统 SHALL 返回 HTTP 200，响应体包含 `status: "ok"`、`data_type: "shapefile"`、`deployed_files`（部署的文件名列表）、`backup_path`、`trigger_result`（`run_all_models` 返回的结果摘要）

#### Scenario: 成功上传 .dat 数据库
- **WHEN** admin 用户上传 `data_type=dat` 的 multipart 请求，包含一个 `.dat` 文件，文件大小 ≤ 200MB
- **THEN** 系统 SHALL 返回 HTTP 200，响应体包含 `status: "ok"`、`data_type: "dat"`、`deployed_path`、`backup_path`、`trigger_result`（`check_deployment` 返回的校验结果）

#### Scenario: 缺少 data_type 字段
- **WHEN** 请求未包含 `data_type` form 字段，或 `data_type` 取值不在 `csv` / `shapefile` / `dat` 范围内
- **THEN** 系统 SHALL 返回 HTTP 400，响应体 `status: "error"`、`message: "无效的 data_type，必须为 csv/shapefile/dat"`

#### Scenario: 缺少文件
- **WHEN** 请求未包含 `file` 字段，或 `file` 字段为空
- **THEN** 系统 SHALL 返回 HTTP 400，响应体 `status: "error"`、`message: "未选择文件"`

### Requirement: CSV Data Validation
系统 SHALL 校验 CSV 文件首行包含全部 14 项必需列：`一级农业区`、`二级农业区`、`pH`、`有机质`、`有效磷`、`速效钾`、`容重`、`耕层质地`、`灌溉能力`、`排水能力`、`地形部位`、`质地构型`、`有效土层`、`耕层厚度`。校验时 SHALL 尝试 UTF-8 解码，失败时回退到 GBK 解码。

#### Scenario: CSV 缺少必需列
- **WHEN** 上传的 CSV 首行缺少任一必需列（例如缺 `有效磷`）
- **THEN** 系统 SHALL 返回 HTTP 400，响应体 `status: "error"`、`message` 包含缺失的列名列表，不执行部署和触发

#### Scenario: CSV 编码为 GBK
- **WHEN** 上传的 CSV 文件用 UTF-8 解码失败但用 GBK 解码成功，且包含全部必需列
- **THEN** 系统 SHALL 接受该文件并继续部署和触发流程

#### Scenario: CSV 文件无法解析
- **WHEN** 上传的 CSV 文件既无法用 UTF-8 也无法用 GBK 解码，或 `pandas.read_csv` 抛出其他异常
- **THEN** 系统 SHALL 返回 HTTP 400，响应体 `status: "error"`、`message: "CSV 文件解析失败"`、`detail` 包含异常信息

### Requirement: Shapefile Zip Validation
系统 SHALL 校验 shapefile zip 包的完整性：解压前校验总大小 ≤ 200MB、文件数 ≤ 30、无路径穿越（文件名不含 `..` 或绝对路径）；解压后校验存在 `manifest.json` 且字段完整，每期 shapefile 必须包含 `.shp` + `.cpg` + `.dbf` + `.prj` + `.shx` 五个组件。

#### Scenario: zip 包含完整 manifest 和 3 期 shapefile
- **WHEN** 上传的 zip 包含 `manifest.json`（含 `current_year`、`history_years`、`years`、`current_filename`、`history_filenames` 字段）且 manifest 中声明的每个 shapefile 都有完整 5 组件
- **THEN** 系统 SHALL 接受该 zip 并继续部署和触发流程

#### Scenario: zip 缺少 manifest.json
- **WHEN** 上传的 zip 不包含 `manifest.json`
- **THEN** 系统 SHALL 返回 HTTP 400，响应体 `status: "error"`、`message: "zip 包缺少 manifest.json"`

#### Scenario: shapefile 组件不完整
- **WHEN** manifest 声明的某个 shapefile 缺少任一组件（例如有 .shp 但缺 .dbf）
- **THEN** 系统 SHALL 返回 HTTP 400，响应体 `status: "error"`、`message` 列出缺失的组件文件名

#### Scenario: zip 总大小超限
- **WHEN** 解压前预估 zip 解压后总大小 > 200MB，或文件数 > 30
- **THEN** 系统 SHALL 返回 HTTP 400，响应体 `status: "error"`、`message: "zip 包大小或文件数超限"`

#### Scenario: zip 包含路径穿越
- **WHEN** zip 内任一文件名包含 `..` 或以 `/` 开头（绝对路径）
- **THEN** 系统 SHALL 返回 HTTP 400，响应体 `status: "error"`、`message: "zip 包含非法路径"`

#### Scenario: 字段校验延迟到触发阶段
- **WHEN** shapefile zip 通过上传阶段校验（manifest 完整、5 组件齐全），但 shapefile 字段缺少 `LSD1`~`LSD12`、`QZ1`~`QZ12`、`ZHQZ`、`GDZLDJ`、`ID`、`PJFQ` 中的任一项
- **THEN** 系统 SHALL 在触发阶段由 `run_all_models` 内置的 `require_columns` 抛出 `ValueError`，触发器捕获后从备份回滚，返回 HTTP 400，`status: "error"`、`message` 包含缺失的字段名列表

### Requirement: DAT Data Validation
系统 SHALL 校验 `.dat` 文件为非空可读二进制文件，文件大小 > 0 且 ≤ 200MB。

#### Scenario: .dat 文件为空
- **WHEN** 上传的 .dat 文件大小为 0 字节
- **THEN** 系统 SHALL 返回 HTTP 400，响应体 `status: "error"`、`message: ".dat 文件为空"`

#### Scenario: .dat 文件可读
- **WHEN** 上传的 .dat 文件大小 > 0 且 ≤ 200MB
- **THEN** 系统 SHALL 接受该文件并继续部署和触发流程

### Requirement: Data Deployment with Backup
系统 SHALL 在部署新数据前，将目标目录下的现有文件移动到 `<target_dir>/backup/<YYYYMMDD-HHMMSS>/` 子目录；部署完成后 SHALL 扫描 `backup/` 下所有时间戳目录，按目录名倒序保留前 3 份，删除其余。CSV 部署到 `data/farmland_diagnosis/`、shapefile 部署到 `data/farmland_stability/`、.dat 部署到 `bin/farmland_quality_eval/`。

#### Scenario: 首次部署（目标目录无现有文件）
- **WHEN** 目标目录下不存在任何现有数据文件（仅有 README.md 或为空）
- **THEN** 系统 SHALL 跳过备份步骤，直接写入新文件，响应中 `backup_path` 为 `null`

#### Scenario: 覆盖部署（目标目录有现有文件）
- **WHEN** 目标目录下存在现有数据文件
- **THEN** 系统 SHALL 将现有数据文件（排除 README.md 和 `backup/` 子目录）移动到 `<target_dir>/backup/<YYYYMMDD-HHMMSS>/`，再写入新文件，响应中 `backup_path` 为该备份目录路径

#### Scenario: CSV 部署时重命名为 test.csv
- **WHEN** 上传的 CSV 文件原名为任意名称（如 `mydata.csv`），校验通过后部署到 `data/farmland_diagnosis/`
- **THEN** 系统 SHALL 将文件重命名为 `test.csv` 写入目标目录（与 README 约定和下游 `bulk_evaluate` 默认读取路径一致），原文件名记录在审计日志中

#### Scenario: 备份目录超过 3 份
- **WHEN** 部署完成后 `backup/` 下存在超过 3 个时间戳子目录
- **THEN** 系统 SHALL 按目录名倒序保留最新 3 份，删除其余旧备份目录及其内容

### Requirement: Offline Computation Trigger
系统 SHALL 在部署成功后同步触发对应数据类型的离线计算：CSV 触发 `bulk_evaluate(input_csv, output_db_path)`、shapefile 触发 `precompute.main(shapefile_dir, manifest)`（封装 `run_all_models` → `StabilityStorage.save_results` → `save_final_results` 完整流程）、.dat 触发 `FarmlandGradeRunner.check_deployment()`。触发超时为 600 秒（配置项 `DATA_IMPORT_TIMEOUT`）。

#### Scenario: CSV 触发 bulk_evaluate 成功
- **WHEN** CSV 部署成功后调用 `bulk_evaluate` 返回 `status: "ok"`
- **THEN** 系统 SHALL 返回 HTTP 200，`trigger_result` 包含 `processed` 行数和 `errors` 列表（可能为空）

#### Scenario: CSV 触发 bulk_evaluate 返回错误
- **WHEN** CSV 部署成功后调用 `bulk_evaluate` 返回 `status: "error"`（例如未知区域名称）
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

#### Scenario: .dat 部署后自动生效
- **WHEN** .dat 部署成功后调用 `check_deployment` 返回通过
- **THEN** 系统 SHALL 返回 HTTP 200，`trigger_result` 包含 `deployment_ok: true`，不调用 exe（exe 在后续查询时按需启动）

### Requirement: Admin Permission Control
系统 SHALL 仅允许 `role == 'admin'` 的用户调用数据导入端点；非 admin 用户 SHALL 返回 HTTP 403。

#### Scenario: admin 用户调用
- **WHEN** 携带有效 JWT 且 `role == 'admin'` 的用户调用 `POST /api/v1/data/import`
- **THEN** 系统 SHALL 正常处理请求

#### Scenario: 非 admin 用户调用
- **WHEN** 携带有效 JWT 但 `role != 'admin'` 的用户调用 `POST /api/v1/data/import`
- **THEN** 系统 SHALL 返回 HTTP 403，响应体 `status: "error"`、`message: "需要 admin 权限"`

#### Scenario: 未携带 JWT
- **WHEN** 请求未携带 `Authorization: Bearer <token>` 头
- **THEN** 系统 SHALL 返回 HTTP 401（由 `@jwt_required()` 装饰器处理）

### Requirement: Audit Logging
系统 SHALL 为每次数据导入操作记录审计日志，包含操作人用户名、时间戳、数据类型、上传文件名、部署路径、触发结果摘要、是否成功。

#### Scenario: 成功导入审计
- **WHEN** 一次数据导入操作成功完成（部署 + 触发均成功）
- **THEN** 系统 SHALL 写入一条审计日志，字段 `success: true`，包含上述全部信息

#### Scenario: 失败导入审计
- **WHEN** 一次数据导入操作失败（校验失败、部署失败、触发失败、回滚等）
- **THEN** 系统 SHALL 写入一条审计日志，字段 `success: false`，包含失败原因和已执行的步骤

#### Scenario: 回滚后审计
- **WHEN** 触发失败导致回滚
- **THEN** 系统 SHALL 写入一条审计日志，`success: false`，`message` 包含 "触发失败已回滚"，`restored_from_backup: true`

### Requirement: File Size Limit
系统 SHALL 限制单次上传文件大小不超过 200MB（配置项 `MAX_DATA_IMPORT_SIZE`）；超限时 SHALL 返回 HTTP 413。

#### Scenario: 文件大小在限制内
- **WHEN** 上传的文件大小 ≤ 200MB
- **THEN** 系统 SHALL 正常处理

#### Scenario: 文件大小超限
- **WHEN** 上传的文件大小 > 200MB
- **THEN** 系统 SHALL 返回 HTTP 413，响应体 `status: "error"`、`message: "文件大小超过 200MB 限制"`
