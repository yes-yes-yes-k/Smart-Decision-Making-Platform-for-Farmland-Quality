# Comet Design Handoff

- Change: add-data-import-interface
- Phase: design
- Mode: compact
- Context hash: af514c0322d04e414c9d977562da783b64d98b35fd3ea8e0500d575ed0fde479

Generated-by: comet-handoff.sh

OpenSpec remains the canonical capability spec. This handoff is a deterministic, source-traceable context pack, not an agent-authored summary.

## openspec/changes/add-data-import-interface/proposal.md

- Source: openspec/changes/add-data-import-interface/proposal.md
- Lines: 1-37
- SHA256: 6bb78c6465bb9681af66af7035068effd040b79185af44d92b759af81cd5ee7e

```md
## Why

当前三类专题模型数据（模型 3 耕地诊断 CSV、模型 1 耕地稳定性 shapefile、耕地质量等级评价 .dat）的部署完全依赖手工操作：管理员需要登录服务器，从外部数据源复制文件到 `data/farmland_diagnosis/`、`data/farmland_stability/`、`bin/farmland_quality_eval/` 目录，再手动运行 `bulk_evaluate` 或 `precompute` 脚本触发重新评价/预计算。这一流程无审计、易出错、且无法远程执行，是上一轮 `add-stability-risk-and-grade-evaluation` 归档时在 design doc 第 7 节明确规划的后续 P2 任务。

现有 `file-upload-management` 能力面向 RAG 文档（txt/md/pdf/docx/xlsx），不做专题模型数据的字段校验和触发；现有 `soil-data-ingestion` 能力面向脚本批量导入 Excel 到数据库表，与本次 HTTP API 上传部署到文件系统的需求正交。本次变更填补"通过 HTTP API 远程部署专题模型数据并触发离线计算"这一空白。

## What Changes

- 新增 `POST /api/v1/data/import` 端点，支持三种数据类型上传：`csv`（模型 3 耕地诊断）、`shapefile`（模型 1 耕地稳定性）、`dat`（耕地质量等级评价数据库）
- 新增文件类型校验：CSV 必须含 14 项必需列；shapefile 必须为完整多文件组（.shp + .cpg/.dbf/.prj/.shx）且字段含 `LSD1`~`LSD12`、`QZ1`~`QZ12`、`ZHQZ`、`GDZLDJ`、`ID`、`PJFQ`；.dat 仅做二进制可读校验
- 新增部署逻辑：CSV 部署到 `data/farmland_diagnosis/`、shapefile 部署到 `data/farmland_stability/`、.dat 部署到 `bin/farmland_quality_eval/`，部署前对现有文件做备份（带时间戳）
- 新增触发逻辑：CSV 导入后同步调用 `bulk_evaluate`；shapefile 导入后同步调用 `run_all_models` 并持久化预计算结果；.dat 导入后调用 `FarmlandGradeRunner.check_deployment()` 校验自动生效
- 新增权限控制：仅 `admin` 角色可调用（复用 `User.is_admin()`），非 admin 返回 403
- 新增 `framework/api/routes/data_import.py` Blueprint，注册到 `framework/api/app.py` 的 `/api/v1/data` 前缀

## Capabilities

### New Capabilities
- `thematic-data-import`: 通过 HTTP API 上传、校验、部署三类专题模型数据（CSV / shapefile / .dat）并触发离线评价/预计算的能力。覆盖文件类型校验、字段校验、部署前备份、触发离线计算、admin 权限控制。

### Modified Capabilities
<!-- 不修改 file-upload-management（RAG 文档上传，职责不同）和 soil-data-ingestion（脚本批量导入 Excel，职责不同）。本次为独立新能力。 -->

## Impact

- **新增代码**：
  - `framework/api/routes/data_import.py`（新 Blueprint）
  - `framework/upload/data_deploy.py`（数据部署 + 备份工具）
  - `framework/upload/data_validator.py`（按数据类型的字段校验器）
- **修改代码**：
  - `framework/api/app.py`：注册 `data_import_bp` 到 `/api/v1/data` 前缀
- **依赖**：复用 `pandas`（CSV 读取）、`geopandas`（shapefile 读取，已在 pyproject.toml）、`werkzeug.security`/`flask_jwt_extended`（鉴权）
- **触发函数**：调用 `src.ai_culti_demo.farmland_diagnosis.evaluation.bulk_evaluate`、`src.ai_culti_demo.farmland_stability.model.run_all_models`、`src.ai_culti_demo.farmland_grade_eval.runner.FarmlandGradeRunner`
- **文件系统**：写入 `data/farmland_diagnosis/`、`data/farmland_stability/`、`bin/farmland_quality_eval/`，并生成带时间戳的备份目录
- **数据库**：`bulk_evaluate` 写入 `instance/farmland_diagnosis.db`，`run_all_models` 预计算结果写入 `instance/farmland_stability.db`
- **配置**：在 `framework/config.py` 增加数据导入相关配置（最大文件大小、允许的数据类型清单）
- **测试**：新增 `tests/test_data_import.py` 覆盖各数据类型的成功/失败/权限/触发场景

```

## openspec/changes/add-data-import-interface/design.md

- Source: openspec/changes/add-data-import-interface/design.md
- Lines: 1-133
- SHA256: 124e6b65af37f219dd48acc1c651be12dd6715c23f37bc299d2d8318a549d77d

[TRUNCATED]

```md
## Context

当前系统已实现三类专题模型的离线计算：
- **模型 3 耕地诊断**：`src/ai_culti_demo/farmland_diagnosis/evaluation.py:bulk_evaluate(input_csv, output_db_path)` 读取 CSV，按 14 项指标计算隶属度并写入 `data/farmland_diagnosis/farmland_diagnosis.db`
- **模型 1 耕地稳定性**：`src/ai_culti_demo/farmland_stability/model.py:run_all_models(current_file, history_files, years, ...)` 读取 3 期 shapefile，运行九模块评价；持久化由新建的 `precompute.py` 封装（`StabilityStorage.save_results` 写入 `data/farmland_stability/stability_results.db`，`save_final_results` 输出 shapefile + xlsx）
- **耕地质量等级评价**：`src/ai_culti_demo/farmland_grade_eval/runner.py:FarmlandGradeRunner` 通过 `subprocess.Popen` 启动 `Farmland_quality_evaluation.exe`，运行时从同目录 `Farmlands_Quality_Level_Database.dat` 读取指标数据库

三类数据当前部署方式（见各目录 README.md）：管理员登录服务器，从外部数据源 `F:\BaiduNetdiskDownload\...` 手动 `Copy-Item` 到 `data/farmland_diagnosis/`、`data/farmland_stability/`、`bin/farmland_quality_eval/`，再手动运行 `python -m ...precompute` 触发预计算。该流程无 HTTP 入口、无字段校验、无审计日志、易出错。

现有 HTTP 上传能力 `framework/upload/file_upload.py` + `framework/api/routes/docs.py` 仅支持 RAG 文档（txt/md/pdf/docx/xlsx，UUID 文件名、SHA-256 去重、向量库索引），与专题模型数据"原文件名部署到固定目录 + 触发离线计算"的需求正交，不能直接复用。

约束：
- 必须保留原文件名部署（下游 `bulk_evaluate`、`run_all_models`、exe 均按固定文件名读取）
- 必须复用 `framework/core_engine/adapter.py` 访问 `src/ai_culti_demo`（项目硬约束）
- 数据库为 SQLite（开发环境 `instance/development.db`、生产 `instance/production.db`）
- API 鉴权统一使用 JWT（`Authorization: Bearer <token>`）

## Goals / Non-Goals

**Goals:**
- 提供 `POST /api/v1/data/import` 单一端点，支持 `csv` / `shapefile` / `dat` 三种数据类型上传
- 上传时按数据类型做字段/完整性校验，校验失败返回结构化错误（缺失字段、不完整 shapefile、无法识别的编码等）
- 部署到目标目录前对现有文件做时间戳备份，保留最近 3 份
- 部署成功后同步触发对应离线计算（`bulk_evaluate` / `run_all_models` / `check_deployment`），返回触发结果摘要
- 仅 `admin` 角色可调用，复用 `User.is_admin()`
- 全程记录审计日志（操作人、时间、数据类型、文件名、触发结果）

**Non-Goals:**
- 不修改现有 `file-upload-management`（RAG 文档上传）能力
- 不修改现有 `soil-data-ingestion`（脚本批量导入 Excel）能力
- 不实现异步任务队列 / 任务 ID 轮询（v1 采用同步触发 + 扩展超时；异步留待后续按需扩展）
- 不实现文件内容级幂等去重（数据部署是覆盖语义，非文档去重语义）
- 不实现 .exe 上传（exe 是可执行程序，不属于"数据"，仍由运维部署；本次仅支持 .dat 数据库）
- 不实现 Web UI（仅 HTTP API；前端可后续基于此 API 构建）
- 不实现断点续传 / 分片上传（单次 multipart 上传即可，200MB 内）

## Decisions

### D1：单一端点 + `data_type` 字段（vs 三个独立端点）

**选择**：`POST /api/v1/data/import` 单一端点，通过 multipart form 的 `data_type` 字段（`csv` / `shapefile` / `dat`）区分处理分支。

**理由**：
- 三种类型共享鉴权、备份、审计、错误响应骨架，单一端点减少 Blueprint 样板
- 校验/部署/触发逻辑按 `data_type` 自然分支，与三独立端点的代码复杂度相当
- 客户端只需记一个 URL

**备选**：三独立端点 `/api/v1/data/import/{csv,shapefile,dat}`。放弃：路由多、共享逻辑要么抽到 helper 要么重复，收益不抵成本。

### D2：shapefile 采用 zip 包 + manifest.json（vs 多文件 multipart）

**选择**：shapefile 类型上传一个 zip 压缩包，内含 3 期 shapefile 的完整组件（.shp/.cpg/.dbf/.prj/.shx）加一个 `manifest.json`：

```json
{
  "current_year": 2024,
  "history_years": [2018, 2021],
  "years": [2018, 2021, 2024],
  "current_filename": "2024_测试数据.shp",
  "history_filenames": ["2018_测试数据.shp", "2021_测试数据.shp"]
}
```

**理由**：
- shapefile 本质是多文件格式（.shp 单独无法读取），zip 是标准传输形态
- `run_all_models` 需要 1 个 current + N 个 history + 年份列表，manifest 显式声明避免端点猜测
- zip 整体校验 + 原子部署，避免"上传一半失败留下脏数据"
- 防 zip bomb：解压前校验总大小 ≤ 200MB、文件数 ≤ 30、路径无 `..` 穿越

**备选**：multipart 多文件上传（5 文件 × 3 期 = 15 文件）。放弃：客户端组装复杂、无法表达 current/history 语义、校验顺序难协调。

### D3：同步触发 + 扩展超时（vs 异步任务队列）

**选择**：部署成功后在同一请求内同步调用 `bulk_evaluate` / `run_all_models` / `check_deployment`，HTTP 超时设为 600 秒（配置项 `DATA_IMPORT_TIMEOUT`）。

**理由**：
- 数据导入是低频管理操作（每次部署后导入一次），非高并发场景
- 同步返回触发结果摘要（处理行数、错误列表），客户端立即知晓成败
- 避免引入 Celery/Redis 等异步基础设施
- `bulk_evaluate` 处理 ~1.7MB CSV 通常 < 60 秒；`run_all_models` 处理 3 期 shapefile 通常 < 120 秒；600 秒留足余量

```

Full source: openspec/changes/add-data-import-interface/design.md

## openspec/changes/add-data-import-interface/tasks.md

- Source: openspec/changes/add-data-import-interface/tasks.md
- Lines: 1-85
- SHA256: 9e9758cf7f3059df6835faea27c10faab8d28d97078db46589e1813602b49c58

[TRUNCATED]

```md
## 1. 配置与基础设施

- [ ] 1.1 在 `framework/config.py` 增加 `MAX_DATA_IMPORT_SIZE = 200 * 1024 * 1024` 和 `DATA_IMPORT_TIMEOUT = 600` 配置项
- [ ] 1.2 在 `framework/config.py` 增加数据类型到目标目录的映射配置：`DATA_IMPORT_TARGETS = {'csv': 'data/farmland_diagnosis', 'shapefile': 'data/farmland_stability', 'dat': 'bin/farmland_quality_eval'}`
- [ ] 1.3 在 `framework/config.py` 增加 `BACKUP_RETENTION_COUNT = 3` 配置项
- [ ] 1.4 创建 `framework/upload/__init__.py` 中导出数据导入相关模块（若需要）

## 2. 数据校验器（framework/upload/data_validator.py）

- [ ] 2.1 创建 `framework/upload/data_validator.py` 模块
- [ ] 2.2 实现 `validate_csv(file_path) -> Tuple[bool, str]`：用 pandas 读取 CSV（UTF-8 失败回退 GBK），校验 14 项必需列（`一级农业区`/`二级农业区`/`pH`/`有机质`/`有效磷`/`速效钾`/`容重`/`耕层质地`/`灌溉能力`/`排水能力`/`地形部位`/`质地构型`/`有效土层`/`耕层厚度`），返回 (ok, error_msg)
- [ ] 2.3 实现 `validate_shapefile_zip(zip_path) -> Tuple[bool, str, dict]`：解压前校验总大小 ≤ 200MB、文件数 ≤ 30、路径无穿越；解压后校验 `manifest.json` 字段完整（current_year/history_years/years/current_filename/history_filenames）；校验每期 shapefile 5 组件齐全（.shp/.cpg/.dbf/.prj/.shx）；返回 (ok, error_msg, manifest)
- [ ] 2.4 实现 `validate_dat(file_path) -> Tuple[bool, str]`：校验文件大小 > 0 且 ≤ 200MB
- [ ] 2.5 编写 `tests/test_data_validator.py` 覆盖各校验器的成功和失败场景（缺列、GBK 编码、zip 缺 manifest、组件不完整、路径穿越、空 .dat 等）

## 3. 数据部署器（framework/upload/data_deployer.py）

- [ ] 3.1 创建 `framework/upload/data_deployer.py` 模块
- [ ] 3.2 实现 `backup_existing(target_dir) -> Optional[str]`：将 target_dir 下现有数据文件（排除 README.md 和 backup/ 子目录）移动到 `target_dir/backup/YYYYMMDD-HHMMSS/`；无文件时返回 None
- [ ] 3.3 实现 `deploy_csv(src_path, target_dir) -> str`：备份后写入 `target_dir/test.csv`（固定文件名，下游 bulk_evaluate 依赖），返回部署路径
- [ ] 3.4 实现 `deploy_shapefile(zip_path, target_dir, manifest) -> List[str]`：备份后解压 zip 内容到 target_dir，返回部署的文件名列表
- [ ] 3.5 实现 `deploy_dat(src_path, target_dir) -> str`：备份后写入 `target_dir/Farmlands_Quality_Level_Database.dat`（固定文件名），返回部署路径
- [ ] 3.6 实现 `cleanup_backups(target_dir, keep=3)`：扫描 `target_dir/backup/` 下时间戳目录，按目录名倒序保留前 keep 份，删除其余
- [ ] 3.7 实现 `restore_from_backup(target_dir) -> bool`：将最近一次 `backup/` 子目录内容移动回 target_dir，返回是否成功
- [ ] 3.8 编写 `tests/test_data_deployer.py` 覆盖备份、部署、清理、回滚场景

## 4. 触发器封装（framework/upload/data_trigger.py）

- [ ] 4.1 创建 `framework/upload/data_trigger.py` 模块
- [ ] 4.2 实现 `trigger_csv_evaluate(csv_path) -> dict`：通过 `framework/core_engine/adapter.py` 调用 `src.ai_culti_demo.farmland_diagnosis.evaluation.bulk_evaluate(csv_path)`，返回结果字典
- [ ] 4.3 实现 `trigger_shapefile_precompute(target_dir, manifest) -> dict`：通过 adapter 调用 `src.ai_culti_demo.farmland_stability.precompute.main(shapefile_dir, manifest)`（封装 run_all_models + 持久化），返回结果摘要（含 processed 地块数、saved_to_db、output_files）
- [ ] 4.4 实现 `trigger_dat_check(target_dir) -> dict`：通过 adapter 调用 `src.ai_culti_demo.farmland_grade_eval.runner.FarmlandGradeRunner.check_deployment()`，返回 `{'deployment_ok': True/False, 'detail': ...}`
- [ ] 4.5 实现超时控制：用 `concurrent.futures.ThreadPoolExecutor` + `future.result(timeout=DATA_IMPORT_TIMEOUT)` 包裹触发调用，超时抛 `TimeoutError`
- [ ] 4.6 编写 `tests/test_data_trigger.py` 用 monkeypatch 模拟 adapter 调用，覆盖成功、返回错误字典、抛异常、超时场景

## 5. 审计日志（framework/upload/audit_logger.py）

- [ ] 5.1 创建 `framework/upload/audit_logger.py` 模块
- [ ] 5.2 实现 `log_data_import(username, data_type, filename, deployed_path, trigger_result, success, message='')`：写入结构化日志到 `logs/data_import.log`（或 SQLite 表 `data_import_audit`，二选一，建议先用日志文件）
- [ ] 5.3 日志字段：timestamp、username、data_type、filename、deployed_path、trigger_result_summary、success、message、restored_from_backup
- [ ] 5.4 编写 `tests/test_audit_logger.py` 验证日志写入和字段完整性

## 6. API 路由（framework/api/routes/data_import.py）

- [ ] 6.1 创建 `framework/api/routes/data_import.py` Blueprint：`data_import_bp = Blueprint('data_import', __name__)`
- [ ] 6.2 实现 `POST /import` 路由：`@jwt_required()` + admin 角色校验（`User.is_admin()`，非 admin 返回 403）
- [ ] 6.3 解析 multipart form：`data_type` 字段 + `file` 字段；缺失返回 400
- [ ] 6.4 文件大小校验：`Content-Length` 或读取后大小 > `MAX_DATA_IMPORT_SIZE` 返回 413
- [ ] 6.5 临时保存上传文件到 `tempfile`，按 data_type 调用对应校验器；校验失败返回 400 + 错误信息
- [ ] 6.6 校验通过后调用部署器：`backup_existing` → `deploy_*` → `cleanup_backups`
- [ ] 6.7 部署成功后调用触发器：`trigger_*`，捕获超时（返回 504）、异常（尝试回滚后返回 500）、错误字典（尝试回滚后返回 500）
- [ ] 6.8 触发失败时调用 `restore_from_backup` 回滚；回滚失败时记录警告并返回 500
- [ ] 6.9 全程调用审计日志记录器写入审计条目
- [ ] 6.10 成功路径返回 200 + 完整响应体（status/data_type/deployed_path/backup_path/trigger_result）
- [ ] 6.11 在 `framework/api/app.py` 注册 `data_import_bp` 到 `/api/v1/data` 前缀
- [ ] 6.12 编写 `tests/test_data_import_route.py` 覆盖：admin 成功上传三种类型、非 admin 403、未携带 JWT 401、缺 data_type 400、缺文件 400、文件超限 413、校验失败 400、触发失败回滚 500/504

## 7. 集成测试

- [ ] 7.1 编写 `tests/test_data_import_integration.py`：使用真实临时目录和 mock adapter，端到端测试 CSV 上传 → 部署 → 触发 → 审计日志写入
- [ ] 7.2 端到端测试 shapefile zip 上传 → 解压 → 部署 → 触发 → 审计日志写入
- [ ] 7.3 端到端测试 .dat 上传 → 部署 → check_deployment → 审计日志写入
- [ ] 7.4 端到端测试触发失败 → 回滚 → 审计日志记录回滚
- [ ] 7.5 端到端测试备份保留策略：连续导入 4 次，验证 backup/ 下仅保留最近 3 份

## 8. 文档更新

- [ ] 8.1 更新 `data/farmland_diagnosis/README.md`：增加"通过 HTTP API 部署"小节，说明 `POST /api/v1/data/import` 用法和示例
- [ ] 8.2 更新 `data/farmland_stability/README.md`：增加 shapefile zip + manifest.json 的打包说明和 API 调用示例
- [ ] 8.3 更新 `bin/farmland_quality_eval/README.md`：增加 .dat 通过 API 部署的说明
- [ ] 8.4 创建 `docs/api/data_import.md`（或在已有 API 文档中补充）：完整 API 契约、请求/响应示例、错误码表、manifest.json 格式说明
- [ ] 8.5 更新项目根 README.md（若列有 API 端点清单）：补充 `/api/v1/data/import`

## 9. 依赖与启动校验

- [ ] 9.1 确认 `geopandas`、`pandas` 已在 `pyproject.toml` 中（上一轮已添加，本次仅需确认）
- [ ] 9.2 确认 `framework/core_engine/adapter.py` 已暴露 `bulk_evaluate_csv`、`precompute_stability`、`check_grade_eval_deployment` 三个新方法；若未暴露，补充 adapter 方法（含 `_ensure_data_import_imports` 延迟导入）
- [ ] 9.3 在 `start_http_server.py` 或 `framework/api/app.py` 启动时验证 `logs/` 目录存在（用于审计日志）

## 10. precompute.py 模块（src/ai_culti_demo/farmland_stability/precompute.py）

```

Full source: openspec/changes/add-data-import-interface/tasks.md

## openspec/changes/add-data-import-interface/specs/thematic-data-import/spec.md

- Source: openspec/changes/add-data-import-interface/specs/thematic-data-import/spec.md
- Lines: 1-164
- SHA256: 5936941652f3e94e97d7eee64461cb2bba6c3094bc4ffa864834910b78766899

[TRUNCATED]

```md
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

```

Full source: openspec/changes/add-data-import-interface/specs/thematic-data-import/spec.md
