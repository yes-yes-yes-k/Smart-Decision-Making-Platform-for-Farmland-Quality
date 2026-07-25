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

**备选**：异步任务 + `GET /api/v1/data/import/status/{task_id}` 轮询。放弃：v1 过度设计，留待后续若出现超时再引入。

### D4：admin 角色鉴权（vs 新增 province 角色）

**选择**：复用 `User.is_admin()`（`role == 'admin'`），非 admin 返回 403。

**理由**：
- 现有 `init_db.py` 仅种子 `admin` 和 `user` 两种角色，无 `province`
- 数据导入是高风险管理操作（覆盖文件 + 触发离线计算），admin 限制合理
- 不引入新角色，避免改动 `init_db.py` 和角色管理逻辑

**备选**：新增 `province` 角色。放弃：无现成需求，本次不扩展角色体系。

### D5：时间戳备份目录 + 保留最近 3 份

**选择**：部署前将目标目录现有文件移动到 `<target_dir>/backup/<YYYYMMDD-HHMMSS>/` 子目录；部署完成后扫描 `backup/` 下所有时间戳目录，按时间倒序保留前 3 份，其余删除。

**理由**：
- 覆盖语义下保留回滚能力（新数据有问题可手动恢复）
- 限制 3 份避免磁盘膨胀（3 期 shapefile ≈ 108MB × 3 = 324MB/备份）
- 时间戳目录比文件级 `.bak` 后缀更清晰

**备选**：无备份直接覆盖。放弃：误操作无法回滚，对管理操作风险过高。

### D6：文件大小限制 200MB（全局）

**选择**：`Config.MAX_DATA_IMPORT_SIZE = 200 * 1024 * 1024`（200MB），在 Flask `app.config['MAX_CONTENT_LENGTH']` 之外额外做应用层校验。

**理由**：
- shapefile zip 最大（3 期 × 36MB ≈ 108MB），200MB 留余量
- .dat 仅 199KB，CSV ~1.7MB，均远小于上限
- Flask `MAX_CONTENT_LENGTH` 超限返回 413，应用层校验可返回更友好的 JSON 错误

### D7：部署与触发为单一事务（失败回滚到备份）

**选择**：部署 + 触发在同一请求内顺序执行；若触发阶段抛异常，自动从最近一次 `backup/` 恢复文件，返回 500 + 错误详情；若恢复失败，返回 500 + "需手动恢复"警告。

**理由**：
- 部署新数据但触发失败时，系统处于"新数据 + 旧预计算结果"的不一致状态，必须回滚
- 备份目录已存在，恢复成本低

**权衡**：恢复本身可能失败（磁盘错误等），此时需人工介入；属可接受风险。

## Risks / Trade-offs

- **[同步触发超时]** 大数据量 CSV（>10MB）或复杂 shapefile 可能使 `bulk_evaluate` / `run_all_models` 超过 600 秒 → v1 文档明确"建议数据量上限"，超大数据仍走手工部署；后续按需引入异步
- **[zip bomb / 恶意 zip]** 攻击者上传高压缩比 zip 导致磁盘耗尽 → 解压前校验总大小、文件数、路径穿越；admin-only 也降低风险
- **[备份目录膨胀]** 高频导入累积备份 → 保留 3 份策略 + 文档提示
- **[shapefile 字段命名漂移]** 不同年份 shapefile 字段名可能不一致（如 `LSD1` vs `lsd1`）→ 校验时做大小写不敏感匹配；不一致时返回详细错误
- **[部署期间服务可用性]** 部署 + 触发期间相关模型查询返回旧数据或临时不可用 → 接受短暂不一致（管理操作窗口期）；不实现读锁
- **[SQLite 写入并发]** `bulk_evaluate` 写入期间若并发查询 `farmland_diagnosis.db` 可能锁冲突 → SQLite WAL 模式已开启（项目约定），管理操作低频可接受
- **[exe 与 .dat 版本不匹配]** 上传新 .dat 后 exe 行为变化 → `check_deployment` 仅校验存在性和可读性，不校验语义版本；文档提示"exe 与 .dat 应配套升级"
