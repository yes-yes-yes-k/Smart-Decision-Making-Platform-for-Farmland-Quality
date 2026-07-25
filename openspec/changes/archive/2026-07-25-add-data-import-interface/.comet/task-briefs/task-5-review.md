# Task 5 审查报告：数据部署器

## 审查对象
- 提交：`703233c feat: add data deployer with backup and rollback`
- 文件：`framework/upload/data_deployer.py`（144 行，新建）、`tests/test_data_deployer.py`（152 行，新建）
- diff stat：2 files changed, 296 insertions(+)

## 审查结论

| 维度 | 结论 |
| --- | --- |
| Spec 合规性 | **PASS** |
| 代码质量与安全 | **PASS** |
| 测试覆盖 | **PASS** |

**总结：无需修复，可放行。** 实现忠实复刻 brief Step 3 参考实现，6 个公共函数签名/语义/返回值全部符合契约；9 个测试按 brief 原文编写，RED/GREEN 证据可追溯；zip slip 防护有效；所有发现均为 MINOR，多数为 brief 显式约定的设计取舍。

---

## A. Spec 合规性（PASS）

逐函数核验（对照 brief 全局约束与 Interfaces 节）：

| 函数 | 契约要点 | 实现 | 结论 |
| --- | --- | --- | --- |
| `backup_existing` | 排除 `README.md` 和 `backup/`；无文件返回 None；移动到 `<target>/backup/YYYYMMDD-HHMMSS/` | `BACKUP_EXCLUDES = {'README.md', 'backup'}`；`os.path.isfile` 过滤；`shutil.move`；`exist_ok=True` | OK |
| `deploy_csv` | 重命名为 `test.csv`；返回部署路径 | `shutil.copy2` 到 `target_dir/test.csv` | OK |
| `deploy_dat` | 重命名为 `Farmlands_Quality_Level_Database.dat` | `shutil.copy2` 到固定名 | OK |
| `deploy_shapefile` | `os.path.basename` 扁平化解压；返回文件名列表 | `info.is_dir()` 跳过目录；`os.path.basename` 提取；`zf.open` + `open(dst,'wb')` 写入 | OK |
| `cleanup_backups` | 按目录名倒序保留前 `keep` 份；默认 `Config.BACKUP_RETENTION_COUNT` | `sorted(..., reverse=True)`；`subdirs[keep:]` 删除；`keep is None` 回退 Config | OK |
| `restore_from_backup` | 从最近备份恢复；恢复后删除空备份目录；无备份返回 False | `subdirs[0]` 取最新；`shutil.move` 还原；`os.rmdir` 删空目录；前置 `os.path.exists` 与空列表双重守卫 | OK |

Config 依赖核验：`framework/config.py:59` 确认 `BACKUP_RETENTION_COUNT = 3`，与 brief 前置依赖声明一致。`framework/upload/__init__.py` 存在，模块可导入。

---

## B. 代码质量与安全（PASS）

### zip slip 防护（重点核验）
`deploy_shapefile` 第 86 行 `filename = os.path.basename(info.filename)`：
- 对 `../etc/passwd` → basename 返回 `passwd`，落入 target_dir 内，**有效防御**。
- 对 `subdir/file.shp` → basename 返回 `file.shp`，扁平化生效。
- 跨平台：Python 的 `os.path.basename` 在 Windows 上由 `ntpath` 提供，同时识别 `/` 和 `\`；在 POSIX 上由 `posixpath` 提供，仅识别 `/`。zip 规范要求 `/` 分隔，故跨平台均能正确提取末段。**防护有效**。
- 残留风险：未校验 Windows 保留设备名（CON/PRN/NUL/AUX/COM*/LPT*）与非法字符。数据源为内部受信任管道，且 brief 参考实现亦未处理，归为 MINOR。

### 文件操作健壮性
- `deploy_shapefile` 使用 `with ZipFile(...)` + `with zf.open(...) as src, open(dst, 'wb') as dst_f`，上下文管理器正确，无资源泄漏。
- `shutil.move/copy2/rmtree` 均为标准库稳定 API，无泄漏面。
- `restore_from_backup`：`shutil.move` 失败时 `os.rmdir` 会在非空目录上抛异常，被 `except Exception` 捕获返回 False。可能留下部分还原状态，但 brief 参考实现如此，且备份目录仅含文件（backup_existing 仅移动文件），实践中 `os.rmdir` 可达。

### 异常处理
- `restore_from_backup` 的 `except Exception: return False` 静默吞异常。`Exception` 不捕获 `KeyboardInterrupt`/`SystemExit`（BaseException 子类），语义正确。无日志输出确属诊断弱点，但与 brief Step 3 参考实现一字不差，属约定行为。
- `cleanup_backups` 的 `shutil.rmtree(old_path, ignore_errors=True)` 静默忽略删除失败（如 Windows 文件占用）。可能导致旧备份残留，但不影响新备份流程。

### 并发安全
- 无锁。多进程同时备份同一 target_dir 时，秒级时间戳可能命中同一目录（实现者顾虑 1）。brief 全局约束明确"不加并发锁，文档提示"，符合契约；上层编排器（Task 6）应串行调用。

### 命名与 YAGNI
- 命名清晰（`backup_existing`/`deploy_csv`/`cleanup_backups` 等动词+宾语），常量 `BACKUP_EXCLUDES` 集合语义明确。
- 无过度设计，无未使用的辅助类/函数。`manifest` 参数未消费（见发现列表 MINOR-2），但为 brief 显式签名要求。

---

## C. 测试覆盖（PASS）

### TDD 证据核验
- **RED**：报告显示 `ModuleNotFoundError: No module named 'framework.upload.data_deployer'`，collection 阶段 1 error。符合 brief Step 2 预期（功能缺失，非拼写错误）。可追溯。
- **GREEN**：报告显示 `9 passed in 0.26s`，9 个测试名与 brief Step 1 原文逐一对应，输出纯净无 warning。可追溯。

### 场景覆盖矩阵

| Brief 要求场景 | 对应测试 | 覆盖 |
| --- | --- | --- |
| 无文件备份返回 None | `test_backup_existing_no_files` | OK |
| 有文件备份移动到时间戳目录 | `test_backup_existing_with_files` | OK |
| 排除 README.md 和 backup/ | `test_backup_existing_excludes_readme_and_backup_dir` | OK |
| CSV 重命名为 test.csv | `test_deploy_csv_renames_to_test_csv` | OK |
| .dat 重命名为固定名 | `test_deploy_dat_renames_to_fixed_name` | OK |
| zip 解压扁平化 | `test_deploy_shapefile_extracts_zip` | OK |
| 清理保留最近 3 份 | `test_cleanup_backups_keeps_latest_3` | OK |
| 回滚成功 | `test_restore_from_backup_success` | OK |
| 无备份回滚返回 False | `test_restore_from_backup_no_backup` | OK |

9/9 必备场景全覆盖。测试代码与 brief Step 1 原文逐字一致（已 diff 比对）。

### 覆盖盲区（非 brief 强制，记录备查）
- 未测试 zip slip 负向用例（zip 含 `../` 条目）。安全敏感面建议补一个负向测试，但 brief 测试清单未要求。
- 未测试 `restore_from_backup` 失败路径（如备份目录不可读）。可移植性差，brief 未要求。
- 未测试 `cleanup_backups` 在备份数 < keep 时的边界（应全部保留）。逻辑显然正确，但缺直接断言。
- 未测试 `deploy_*` 到不存在 target_dir 的自动创建。隐式覆盖（测试中 target_dir 不存在，部署后断言文件存在）。

---

## 发现列表

### CRITICAL
无。

### IMPORTANT
无。

### MINOR
1. **`restore_from_backup` 静默吞异常**（data_deployer.py:143-144）。`except Exception: return False` 无日志，调用方无法区分"无备份"与"I/O 错误"。建议加 `logging.warning(...)` 或上抛自定义异常。brief 参考实现如此，**不阻塞放行**。
2. **`deploy_shapefile` 的 `manifest` 参数未消费**（data_deployer.py:72,82）。签名要求 `manifest: dict` 但函数体未引用。若 Task 6 编排器需按 manifest 过滤/重命名，需回头扩展。实现者已在顾虑 4 中自报，brief 参考实现如此，**不阻塞放行**。
3. **`cleanup_backups` 类型注解不严格**（data_deployer.py:96）。`keep: int = None` 应为 `Optional[int] = None`。功能无影响，纯属类型标注严谨性。
4. **`cleanup_backups` 静默忽略删除失败**（data_deployer.py:115）。`shutil.rmtree(old_path, ignore_errors=True)` 在 Windows 文件占用时会静默残留旧备份。建议至少 `logging.warning`。brief 参考实现如此，**不阻塞放行**。
5. **缺少 zip slip 负向测试**（tests/test_data_deployer.py）。`deploy_shapefile` 是安全敏感面，建议补一个含 `../` 条目的 zip 测试以锁死防护行为。brief 测试清单未要求，**不阻塞放行**。
6. **`backup_existing` 秒级时间戳冲突风险**（data_deployer.py:46）。1 秒内两次备份会命中同一目录，`exist_ok=True` 不报错，两批文件混入。实现者顾虑 1 已自报，brief 参考实现如此，**不阻塞放行**。
7. **`deploy_shapefile` 同名文件覆盖**（data_deployer.py:89-91）。zip 内多个条目 basename 相同（如 `a/file.shp` 和 `b/file.shp`）时后者静默覆盖前者。brief 未要求处理，**不阻塞放行**。
8. **测试文件未使用的 import**（tests/test_data_deployer.py:5-8）。`json`、`shutil`、`datetime` 未在测试中使用。无功能影响。

---

## 总结

**是否需要修复：否。**

实现严格遵循 brief Step 3 参考实现（逐字对照一致），6 个函数语义、签名、返回值全部合规；测试严格遵循 brief Step 1 原文（9 个测试逐字一致），RED/GREEN 证据可追溯且符合预期；zip slip 防护经跨平台分析有效；安全敏感面（文件系统操作）的异常处理与并发约定均与 brief 契约一致。

8 项 MINOR 发现中，6 项为 brief 显式约定的设计取舍（实现者已在报告中自报），2 项为可选改进（类型标注、负向测试）。无 CRITICAL/IMPORTANT 级别问题。建议在 Task 6 编排器集成时回访 MINOR-2（manifest 消费）与 MINOR-1（restore 日志），但不在本任务范围内强制修复。

**审查通过，可继续 Task 6。**
