# Task 4 Review

> 审查对象：commit `dd784ad` `feat: add data validators for CSV/shapefile/dat`
> 审查范围：`framework/upload/data_validator.py` (137 行) + `tests/test_data_validator.py` (173 行)
> 审查依据：`task-4-brief.md`（唯一需求来源）

## Spec 合规性: PASS

逐项核对：

| 项 | brief 要求 | 实现位置 | 结论 |
|---|---|---|---|
| 3 个校验函数签名 | `validate_csv -> Tuple[bool, str]`、`validate_shapefile_zip -> Tuple[bool, str, dict]`、`validate_dat -> Tuple[bool, str]` | data_validator.py:35, 55, 69 | PASS |
| CSV_REQUIRED_COLUMNS 14 列 | 一级农业区/二级农业区/pH/有机质/有效磷/速效钾/容重/耕层质地/灌溉能力/排水能力/地形部位/质地构型/有效土层/耕层厚度 | data_validator.py:18-22（14 列、顺序、名称完全一致） | PASS |
| CSV 编码回退 UTF-8 → GBK | UTF-8 失败回退 GBK | data_validator.py:42-45（`except UnicodeDecodeError` 触发 GBK 读取） | PASS |
| zip 校验顺序 | 文件数 → 总大小 → 路径穿越 → manifest → 5 组件 | data_validator.py:84-130（注释 1-5 顺序与 brief 一致） | PASS |
| manifest 必需 5 字段 | current_year/history_years/years/current_filename/history_filenames | data_validator.py:25 | PASS |
| 返回格式 | csv/dat 返回 (bool, str)；zip 返回 (bool, str, dict)，失败时 dict={} | data_validator.py 全部分支 | PASS |
| 全局约束 200MB / 30 文件 | Config.MAX_DATA_IMPORT_SIZE、ZIP_MAX_FILE_COUNT=30 | data_validator.py:31-32；Config.py:52 确认 `MAX_DATA_IMPORT_SIZE = 200*1024*1024` | PASS |
| shapefile 字段校验延迟 | 本任务不做 | data_validator.py 未做字段校验 | PASS |

实现与 brief Step 3 代码逐字一致，无自行扩张或缩减。

## 代码质量与安全: PASS（带 IMPORTANT 发现，均为 brief 设计限制而非实现偏差）

### 安全校验健壮性分析

**路径穿越校验**（data_validator.py:96）：
```python
if '..' in name or name.startswith('/') or name.startswith('\\'):
```
- `..` 子串检查：覆盖 `../evil`、`foo/..\\bar`、`foo\\..\\bar` 等所有相对穿越 ✅
- `name.startswith('/')`：Unix 绝对路径 ✅
- `name.startswith('\\')`：Windows 单反斜杠绝对路径，可拦截 `\\server\share`（UNC，首字符为 `\`）✅
- **缺口**：Windows 盘符绝对路径 `C:\foo` 或 `C:/foo` 不以 `/` 或 `\` 开头，不会被拦截。但本任务仅做校验不解压，下游若用 Python `zipfile.extract` 在 Windows 上 `C:` 会被作为 drive-relative 处理（写到当前目录的 `C:` 子目录），不构成绝对路径写入。属 brief 设计限制。
- `..` 检查偏严：会误报 `foo..bar.txt` 这类合法文件名，但安全角度属"过严非漏洞"。

**zip bomb 防护**（data_validator.py:89-91）：
- `total_size = sum(i.file_size for i in infos)`：使用 unzip 后大小 ✅
- 文件数 ≤ 30 ✅
- **缺口**：`file_size` 取自 zip central directory，攻击者可伪造该字段绕过预检。但本任务不解压，且 brief 设计如此，属 brief 限制。

**异常处理**：
- `BadZipFile` 单独捕获 ✅（data_validator.py:134）
- `JSONDecodeError` 单独捕获 ✅（data_validator.py:107）
- 通用 `Exception` 兜底 ✅（data_validator.py:136, 46）
- **缺口**：`validate_dat` 未捕获 `FileNotFoundError`（data_validator.py:61 `os.path.getsize` 可能抛出）。brief 未要求，且本任务假设上游已确认文件存在。

**资源管理**：
- `with zipfile.ZipFile(...)` ✅
- `with zf.open(manifest_names[0])` ✅
- 无泄漏。

**代码风格与 YAGNI**：
- 命名清晰、注释与 brief 一致 ✅
- data_validator.py:115-120 的 `all_basenames` 集合被计算但未使用（死代码），但属 brief 原文，非实现偏差。MINOR。
- 无 YAGNI 违规。

## 测试覆盖: PASS

### RED 证据核验
- 命令：`d:\miniconda3\python.exe -m pytest tests/test_data_validator.py -v`
- 失败：`ModuleNotFoundError: No module named 'framework.upload.data_validator'`
- 与 brief Step 2 预期完全一致 ✅

### GREEN 证据核验
- 11 个测试全部 PASS（CSV 4 + dat 2 + shapefile zip 5）
- brief 文本多处称"9 个测试"，但 brief Step 1 代码实际定义 11 个测试函数。实现者严格遵循 brief Step 1 代码，11 PASS。该差异为 brief 文本与代码不一致，非实现偏差。✅

### 测试场景覆盖核验

| 场景 | 测试函数 | 位置 | 结论 |
|---|---|---|---|
| CSV 成功 UTF-8 | test_validate_csv_success_utf8 | test:28 | ✅ |
| CSV 成功 GBK | test_validate_csv_success_gbk | test:38 | ✅ |
| CSV 缺列 | test_validate_csv_missing_column | test:47 | ✅ |
| CSV 不可解析 | test_validate_csv_unparseable | test:59 | ✅ |
| dat 成功 | test_validate_dat_success | test:70 | ✅ |
| dat 空 | test_validate_dat_empty | test:79 | ✅ |
| zip 成功 | test_validate_shapefile_zip_success | test:112 | ✅ |
| zip 缺 manifest | test_validate_shapefile_zip_missing_manifest | test:124 | ✅ |
| zip 组件不完整 | test_validate_shapefile_zip_incomplete_components | test:136 | ✅ |
| zip 路径穿越 | test_validate_shapefile_zip_path_traversal | test:149 | ✅ 真实构造 `../evil.shp` |
| zip 缺字段 | test_validate_shapefile_zip_manifest_missing_field | test:163 | ✅ |

brief Step 1 要求的所有场景全部覆盖。

## 发现列表

### [IMPORTANT] 路径穿越未覆盖 Windows 盘符绝对路径
- 位置: framework/upload/data_validator.py:96
- 描述: 路径穿越校验 `name.startswith('/') or name.startswith('\\')` 无法识别 `C:\foo` 或 `C:/foo` 这类 Windows 盘符绝对路径。本任务仅校验不解压，影响有限（下游 Python zipfile 会作为 drive-relative 处理），但若下游换用其他解压库或路径拼接逻辑，存在潜在风险。同时 `..` 子串检查会误报 `foo..bar.txt` 等合法文件名。
- 建议: 由 brief owner 评估是否强化为 `os.path.isabs(name)` 或追加 `len(name) >= 2 and name[1] == ':'` 检查。属 brief 设计限制，**本任务实现者无需修复**。

### [IMPORTANT] validate_dat 未处理文件不存在异常
- 位置: framework/upload/data_validator.py:61
- 描述: `os.path.getsize(file_path)` 在文件不存在时抛 `FileNotFoundError`，未被 try/except 包裹。`validate_csv` 和 `validate_shapefile_zip` 均有 `Exception` 兜底，`validate_dat` 缺失。
- 建议: 由 brief owner 评估是否补充 try/except。属 brief 设计限制，**本任务实现者无需修复**（严格遵循 brief 原文）。

### [MINOR] all_basenames 死代码
- 位置: framework/upload/data_validator.py:115-120
- 描述: `all_basenames` 集合被构建但未在任何后续逻辑中使用，第 122-130 行改用 `any(n.endswith(expected) for n in all_names)` 重新查找。
- 建议: 可移除该死代码块。属 brief 原文，非实现偏差。

### [MINOR] 测试缺少部分安全边界场景
- 位置: tests/test_data_validator.py
- 描述: 未覆盖 zip bomb（>200MB 总大小）、文件数 >30、BadZipFile、JSONDecodeError、dat 文件过大、Windows 盘符路径穿越等场景。brief Step 1 未要求这些测试。
- 建议: 由 brief owner 评估是否在后续任务中补充。本任务测试覆盖与 brief Step 1 完全一致。

## 总结
- Spec: **PASS**（6 项全部符合 brief，逐字照搬 brief Step 3 代码）
- Quality: **PASS**（实现者严格遵循 brief，未引入实现偏差；所有 IMPORTANT 发现均为 brief 本身的设计限制）
- 测试覆盖: **PASS**（11 个测试全部 PASS，覆盖 brief Step 1 全部场景，RED/GREEN 证据与 brief 预期一致）
- 是否需要修复: **否**
  - 无 CRITICAL 发现
  - 2 个 IMPORTANT 发现均为 brief 设计限制（路径穿越未覆盖盘符绝对路径、validate_dat 未处理文件不存在），非实现偏差，应由 brief owner 在后续任务或 change 收尾时统一评估，不应阻塞本任务
  - 2 个 MINOR 发现（死代码、测试场景缺口）同样源自 brief，非实现偏差
  - 实现者报告的 brief 文本/代码不一致（9 vs 11 测试）属实，已正确遵循 brief 代码（唯一需求来源），不构成偏差
