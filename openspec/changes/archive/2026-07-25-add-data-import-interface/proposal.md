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
