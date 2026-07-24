## 1. 配置与基础设施

- [x] 1.1 在 `framework/config.py` 增加 `MAX_DATA_IMPORT_SIZE = 200 * 1024 * 1024` 和 `DATA_IMPORT_TIMEOUT = 600` 配置项
- [x] 1.2 在 `framework/config.py` 增加数据类型到目标目录的映射配置：`DATA_IMPORT_TARGETS = {'csv': 'data/farmland_diagnosis', 'shapefile': 'data/farmland_stability', 'dat': 'bin/farmland_quality_eval'}`
- [x] 1.3 在 `framework/config.py` 增加 `BACKUP_RETENTION_COUNT = 3` 配置项
- [x] 1.4 创建 `framework/upload/__init__.py` 中导出数据导入相关模块（若需要）

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
- [x] 9.3 在 `start_http_server.py` 或 `framework/api/app.py` 启动时验证 `logs/` 目录存在（用于审计日志）

## 10. precompute.py 模块（src/ai_culti_demo/farmland_stability/precompute.py）

- [x] 10.1 创建 `src/ai_culti_demo/farmland_stability/precompute.py` 模块，填补 README 提及但缺失的 `python -m ...precompute` 入口
- [x] 10.2 实现 `g_to_records(G, id_col='ID', region='PJFQ', score='ZHQZ', grade='GDZLDJ') -> List[Dict]`：将 `run_all_models` 返回的 GeoDataFrame G 转换为 `StabilityStorage.save_results` 期望的 records 列表；用 `MODULE_FIELDS` 映射 module_1..9 字段，`RESULT_CN` 做中文 key，`all_results` 汇总所有模块
- [x] 10.3 实现 `main(shapefile_dir, manifest) -> dict`：调用 `run_all_models(current_file, history_files, years)` → `g_to_records(G)` → `StabilityStorage.save_results(records)` 写入 `data/farmland_stability/stability_results.db` → `save_final_results(G, shp_file, xlsx_file, years)` 输出 shapefile + xlsx；返回 `{status, processed, saved_to_db, output_files}`
- [x] 10.4 编写 `tests/test_precompute.py`：用 mock GeoDataFrame 测试 `g_to_records` 字段映射正确性；用 monkeypatch 测试 `main` 完整流程（mock run_all_models/StabilityStorage/save_final_results）
