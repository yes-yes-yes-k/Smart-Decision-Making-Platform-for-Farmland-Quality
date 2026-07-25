# Task 5 报告：数据部署器

## Status
完成（9/9 测试通过，已提交）

## 实现摘要
按 brief 原文实现 `framework/upload/data_deployer.py`（6 个公共函数），并按 brief 原文编写 `tests/test_data_deployer.py`（9 个测试）。严格遵循 TDD Red-Green 循环。

公共 API：
- `backup_existing(target_dir) -> Optional[str]`：将现有数据文件移动到 `<target_dir>/backup/YYYYMMDD-HHMMSS/`，排除 `README.md` 与 `backup/`，无文件返回 None。
- `deploy_csv(src_path, target_dir) -> str`：复制并重命名为 `test.csv`。
- `deploy_dat(src_path, target_dir) -> str`：复制并重命名为 `Farmlands_Quality_Level_Database.dat`。
- `deploy_shapefile(zip_path, target_dir, manifest) -> List[str]`：解压 zip，扁平化文件名（`os.path.basename`），返回部署文件名列表。
- `cleanup_backups(target_dir, keep=None) -> None`：按目录名倒序保留前 `keep` 份（默认 `Config.BACKUP_RETENTION_COUNT=3`），删除更旧目录。
- `restore_from_backup(target_dir) -> bool`：从最近备份恢复，恢复后删除空备份目录；无备份返回 False。

依赖：仅标准库（os/shutil/zipfile/datetime/typing）+ `framework.config.Config`。未引入 geopandas。

## TDD 证据

### RED 证据
命令：
```
d:\miniconda3\python.exe -m pytest tests/test_data_deployer.py -v
```
结果摘要：
```
collected 0 items / 1 error
ERROR collecting tests/test_data_deployer.py
E   ModuleNotFoundError: No module named 'framework.upload.data_deployer'
!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
1 error in 0.87s
```
失败原因：模块尚未实现（功能缺失，非拼写错误），符合预期。

### GREEN 证据
命令：
```
d:\miniconda3\python.exe -m pytest tests/test_data_deployer.py -v
```
结果摘要：
```
collected 9 items
tests/test_data_deployer.py::test_backup_existing_no_files PASSED        [ 11%]
tests/test_data_deployer.py::test_backup_existing_with_files PASSED      [ 22%]
tests/test_data_deployer.py::test_backup_existing_excludes_readme_and_backup_dir PASSED [ 33%]
tests/test_data_deployer.py::test_deploy_csv_renames_to_test_csv PASSED  [ 44%]
tests/test_data_deployer.py::test_deploy_dat_renames_to_fixed_name PASSED [ 55%]
tests/test_data_deployer.py::test_deploy_shapefile_extracts_zip PASSED   [ 66%]
tests/test_data_deployer.py::test_cleanup_backups_keeps_latest_3 PASSED  [ 77%]
tests/test_data_deployer.py::test_restore_from_backup_success PASSED     [ 88%]
tests/test_data_deployer.py::test_restore_from_backup_no_backup PASSED   [100%]
9 passed in 0.26s
```
输出纯净（无 warning/error），9 个测试全部 PASS。

## 自检（逐条对照任务 brief）
- [x] `backup_existing` 排除 `README.md` 与 `backup/`，无文件返回 None（test_backup_existing_no_files / test_backup_existing_excludes_readme_and_backup_dir 验证）
- [x] `deploy_csv` 重命名为 `test.csv`（test_deploy_csv_renames_to_test_csv 验证）
- [x] `deploy_dat` 重命名为 `Farmlands_Quality_Level_Database.dat`（test_deploy_dat_renames_to_fixed_name 验证）
- [x] `deploy_shapefile` 用 `os.path.basename` 扁平化解压（test_deploy_shapefile_extracts_zip 验证）
- [x] `cleanup_backups` 按目录名倒序保留前 keep 份（test_cleanup_backups_keeps_latest_3 验证：4 份保留最新 3 份，最旧被删）
- [x] `restore_from_backup` 从最近备份恢复，恢复后删除空备份目录（test_restore_from_backup_success / test_restore_from_backup_no_backup 验证）
- [x] 9 个测试全部 PASS

## 变更文件
- `framework/upload/data_deployer.py`（新建，144 行）
- `tests/test_data_deployer.py`（新建，152 行）

## 提交哈希
`703233cc5a26d6af966f971e16a3fa95d63094ee`

提交信息：`feat: add data deployer with backup and rollback`

## 风险信号自报
| 信号 | 触发 | 说明 |
| --- | --- | --- |
| 跨模块协调 | 是 | 消费 Task 1 的 `Config.BACKUP_RETENTION_COUNT`（已确认=3，运行时验证通过）；本任务的 6 个函数为后续 Task 6（编排器）调用的接口，需在 Task 6 集成时对齐调用约定 |
| 安全敏感面 | 是 | 文件系统操作密集：`shutil.move`（备份/回滚）、`shutil.copy2`（部署）、`shutil.rmtree`（清理旧备份）、`os.rmdir`（删除空备份目录）。zip 解压采用 `os.path.basename` 扁平化，已天然防御 zip slip（路径穿越），但未显式校验文件名合法性；`restore_from_backup` 用 `try/except Exception` 静默吞错返回 False，生产环境若需精细诊断需增强日志 |
| 并发锁 | 否 | 无并发锁；多进程同时备份/部署同一 target_dir 时存在竞态（时间戳目录可能冲突或文件移动竞争）。当前任务未要求并发安全，留待上层编排器串行调用 |
| schema 迁移 | 否 | 无数据库 schema 变更 |
| 公共 API 变更 | 否 | 仅新增 6 个函数，未修改/删除现有 API；不破坏向后兼容 |
| diff > 200 行 | 是 | 单次提交 296 行（144 实现 + 152 测试），全部为新增文件，无对既有代码的修改 |

## 顾虑
1. **时间戳冲突**：`backup_existing` 使用 `%Y%m%d-%H%M%S`（秒级粒度）。若 1 秒内连续两次备份，第二次会 `os.makedirs(exist_ok=True)` 命中同一目录，可能将两批文件混入同一备份目录。brief 原文如此实现，未改动。如需更稳健可加微秒或序号后缀，但超出 brief 范围。
2. **`restore_from_backup` 异常静默**：捕获 `Exception` 后直接返回 False，无日志或异常上抛，调用方难以区分“无备份”与“恢复过程 I/O 错误”。按 brief 原文实现，未改动。
3. **`cleanup_backups` 目录名假设**：按目录名倒序字符串排序，依赖命名约定 `YYYYMMDD-HHMMSS`。若上游写入了非时间戳命名的子目录，排序结果可能与“按时间最新”不符。brief 已规定命名格式，符合契约。
4. **manifest 参数未使用**：`deploy_shapefile(zip_path, target_dir, manifest)` 的 `manifest` 参数在当前实现中未消费（仅按 zip 内容解压）。brief Step 3 实现原文如此，测试也未检查 manifest 行为；若 Task 6 需根据 manifest 过滤/重命名，需回头扩展。
