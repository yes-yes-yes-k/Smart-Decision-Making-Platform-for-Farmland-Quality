# Task 4 报告：数据校验器

## Status

DONE_WITH_CONCERNS

## 实现内容摘要

严格按 brief Step 1 与 Step 3 原文实现，未改动校验逻辑、返回格式或错误信息。

- 新建 `framework/upload/data_validator.py`：实现 `validate_csv` / `validate_dat` / `validate_shapefile_zip` 三个校验器
  - `CSV_REQUIRED_COLUMNS` 14 列与 brief 完全一致
  - `validate_csv`：UTF-8 失败回退 GBK
  - `validate_shapefile_zip` 校验顺序：文件数 → 总大小 → 路径穿越 → manifest → 5 组件（与 brief 一致）
  - 路径穿越校验：检查 `..`、绝对路径 `/`、`\` 三种
  - `MANIFEST_REQUIRED_FIELDS` 5 字段：current_year / history_years / years / current_filename / history_filenames
  - `SHP_COMPONENTS` 5 组件：.shp / .cpg / .dbf / .prj / .shx
- 新建 `tests/test_data_validator.py`：与 brief Step 1 完整代码一致

## TDD 证据

### RED 证据

命令：
```
d:\miniconda3\python.exe -m pytest tests/test_data_validator.py -v
```

失败摘要：
```
collected 0 items / 1 error
ERROR collecting tests/test_data_validator.py
E   ModuleNotFoundError: No module named 'framework.upload.data_validator'
1 error in 0.62s
```
失败原因与 brief Step 2 预期完全一致（ModuleNotFoundError）。

### GREEN 证据

命令：
```
d:\miniconda3\python.exe -m pytest tests/test_data_validator.py -v
```

通过摘要：
```
collected 11 items
tests/test_data_validator.py::test_validate_csv_success_utf8 PASSED
tests/test_data_validator.py::test_validate_csv_success_gbk PASSED
tests/test_data_validator.py::test_validate_csv_missing_column PASSED
tests/test_data_validator.py::test_validate_csv_unparseable PASSED
tests/test_data_validator.py::test_validate_dat_success PASSED
tests/test_data_validator.py::test_validate_dat_empty PASSED
tests/test_data_validator.py::test_validate_shapefile_zip_success PASSED
tests/test_data_validator.py::test_validate_shapefile_zip_missing_manifest PASSED
tests/test_data_validator.py::test_validate_shapefile_zip_incomplete_components PASSED
tests/test_data_validator.py::test_validate_shapefile_zip_path_traversal PASSED
tests/test_data_validator.py::test_validate_shapefile_zip_manifest_missing_field PASSED
11 passed in 1.93s
```
全部通过。

## 变更文件列表

- `framework/upload/data_validator.py`（新建，137 行）
- `tests/test_data_validator.py`（新建，173 行）

未修改其他任何文件。

## 提交哈希

`dd784adee736aee9a9457f6b71782b095044f49b`

提交信息：`feat: add data validators for CSV/shapefile/dat`

## 风险信号自报

- **跨模块/跨子系统协调改动**：未命中。仅新建 framework/upload/ 与 tests/ 下两个文件，未触碰其他模块。
- **安全敏感面（外部输入处理）**：命中。本任务直接处理外部上传文件，含 zip 路径穿越校验（`..` / 绝对路径 `/` `\`）、zip bomb 防护（解压后总大小 ≤ 200MB、文件数 ≤ 30）、CSV 编码异常处理。属"外部输入处理"安全面。校验逻辑已按 brief 原文实现，未自行扩张或缩减。
- **并发、锁、共享可变状态**：未命中。校验器无状态，无共享可变状态，无锁。
- **数据或 schema 迁移**：未命中。仅校验，不写入任何持久化数据。
- **公共 API 契约或对外接口变更**：部分命中。新增三个公共函数（validate_csv / validate_shapefile_zip / validate_dat），属新增公共接口，未修改已有契约。与本 change 名 `add-data-import-interface` 一致。
- **单任务 diff 超过 200 行**：命中。本任务 diff 共 310 行（validator 137 + test 173），超过 200 行阈值。原因是 brief 要求测试与实现一一对应、且 9 个（实际 11 个）测试覆盖 CSV/shapefile/.dat 三类校验的全部失败路径，难以压缩。

## 顾虑

1. **brief 测试数量与实际不符**：brief 多处叙述（任务概要、Step 2 预期、Step 4 预期、报告契约）均称"9 个测试"，但 brief Step 1 完整代码实际定义了 11 个测试函数（CSV 4 + dat 2 + shapefile zip 5 = 11）。按指令"按 brief 原文执行，不要自行改动"，我严格逐字照搬了 brief Step 1 代码，因此实际为 11 个测试，全部 PASS。该差异为 brief 文本与 brief 代码的不一致，并非实现偏差。如需对齐到 9 个，需 brief owner 确认要保留哪 9 个。
2. 其余无顾虑，校验逻辑、返回格式、错误信息均与 brief 原文一致。
