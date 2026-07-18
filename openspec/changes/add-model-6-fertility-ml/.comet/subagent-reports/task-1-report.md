# Task 1 报告：数据资产迁移与依赖声明

**Change:** `add-model-6-fertility-ml`
**Task:** Task 1 - 数据资产迁移与依赖声明
**分支:** `feature/20260718/add-model-6-fertility-ml`
**提交 SHA:** `8b28aec1068fbe75ef29c03e477ea27aac4e1989`
**提交 subject:** `feat(fertility): 迁移训练数据资产并声明 scikit-learn/joblib 依赖`
**TDD 模式:** tdd（本任务为数据迁移 + 依赖声明，无业务逻辑代码，不强制 TDD）

---

## 实现了什么（按 Step 列出）

### Step 1: 创建数据目录并复制训练数据文件

- 创建目录 `data/fertility/models/`（已存在，Task 2 将填充模型产物）
- 从 `F:\BaiduNetdiskDownload\SOC（土壤有机碳）和Dose（施用量）预测模型\` 复制 3 个 xlsx 文件到 `data/fertility/`

**自检发现（重要）：** Plan 中 Step 1 写的源文件名 `ML-data-Dose-RF-Manual_splits.xlsx`（连字符 `RF-Manual`）与实际源文件名不符。实际源文件名为 `ML-data-Dose-RF_Manual_splits.xlsx`（下划线 `RF_Manual`，与 SOC 文件命名风格一致）。首次按 plan 字面复制失败，已用实际文件名重新复制成功。Plan 中存在命名拼写错误，但 Task 2 的训练脚本 `scripts/train_fertility_models.py` 应使用实际文件名 `ML-data-Dose-RF_Manual_splits.xlsx`。

### Step 2: 验证文件已复制且大小 <10MB

```
Name                               SizeMB
----                               ------
ML-data-Dose-RF_Manual_splits.xlsx   0.01
ML-data-SOC-RF_Manual_splits.xlsx    0.01
变量注释.xlsx                        0.01
```

3 个文件均存在，SizeMB 均 = 0.01 < 10 ✓

### Step 3: 更新 `.gitignore`

在 `.gitignore` 末尾追加（原文件以 `.vscode/` 结尾且无尾换行）：

```gitignore

# Fertility ML 训练数据与模型文件（入库，不忽略）
!data/fertility/
!data/fertility/**

# 忽略训练过程临时文件
*.pkl.bak
```

### Step 4: 修改 `pyproject.toml` 新增依赖

在 `[project.dependencies]` 的 `waitress = "^3.0.0"` 行后追加：

```toml
scikit-learn = "^1.3.0"
joblib = "^1.3.0"
```

### Step 5: 安装依赖并验证

**import 验证（通过）：**
```
sklearn 1.5.1
joblib 1.4.2
```
两个版本号均 >= 1.3.0，无 ImportError ✓

**`pip install -e .`（失败 - 预存在问题，见下方"顾虑"）：**
```
ValueError: invalid pyproject.toml config: `project.dependencies`.
configuration error: `project.dependencies` must be array
```

### Step 6: 提交

```
git add data/fertility/ .gitignore pyproject.toml
git commit -m "feat(fertility): 迁移训练数据资产并声明 scikit-learn/joblib 依赖"
```

提交结果：`8b28aec`，5 files changed, 10 insertions(+), 1 deletion(-)

---

## 测试了什么 + 测试结果

| 验证项 | 命令 | 结果 |
|---|---|---|
| 文件复制完整性 | `Get-Item data\fertility\*.xlsx` | 3 个文件均在 ✓ |
| 文件大小 <10MB | `Select-Object Name, @{N='SizeMB';...}` | 均 0.01MB ✓ |
| models 子目录存在 | `Test-Path data\fertility\models` | 存在 ✓ |
| sklearn 导入与版本 | `python -c "import sklearn; ..."` | 1.5.1 (>=1.3.0) ✓ |
| joblib 导入与版本 | `python -c "import joblib; ..."` | 1.4.2 (>=1.3.0) ✓ |
| `pip install -e .` | `pip install -e .` | **失败**（预存在问题，见顾虑）|

---

## 文件变更列表

| 操作 | 文件 |
|---|---|
| Create | `data/fertility/models/`（目录，git 不跟踪空目录，未入提交）|
| Create | `data/fertility/ML-data-SOC-RF_Manual_splits.xlsx` |
| Create | `data/fertility/ML-data-Dose-RF_Manual_splits.xlsx` |
| Create | `data/fertility/变量注释.xlsx` |
| Modify | `.gitignore`（追加 7 行 fertility 白名单 + pkl.bak 忽略）|
| Modify | `pyproject.toml`（追加 2 行 scikit-learn / joblib 依赖）|

提交统计：5 files changed, 10 insertions(+), 1 deletion(-)

---

## 自检发现

1. **Plan Step 1 文件名拼写错误**：Plan 写 `ML-data-Dose-RF-Manual_splits.xlsx`（连字符），实际源文件名为 `ML-data-Dose-RF_Manual_splits.xlsx`（下划线）。已按实际名称复制。**建议主会话在 Task 2 实现时核对训练脚本中引用的 Dose 文件名，应使用 `ML-data-Dose-RF_Manual_splits.xlsx`。**

2. **`pip install -e .` 失败（预存在问题）**：见下方"顾虑"。

3. **空目录 `data/fertility/models/` 未入 git**：git 不跟踪空目录，故该目录未出现在提交中。Task 2 将向其写入 `.joblib` 和 `.json` 产物后会自动入 git。目录在磁盘上已创建，不影响 Task 2 使用。

---

## 风险信号命中列表

逐条核对：

- 跨模块/跨子系统协调改动：**无**（仅数据资产 + 依赖声明）
- 安全敏感面（认证/授权/加解密/SQL/外部输入/密钥）：**无**
- 并发/锁/共享可变状态：**无**
- 数据或 schema 迁移：**命中（轻度）** - 复制训练数据 xlsx 文件到仓库，但这是静态数据资产迁移，不涉及数据库 schema 或运行时数据迁移
- 公共 API 契约或对外接口变更：**无**
- 单任务 diff 超过 200 行：**无**（5 files changed, 10 insertions, 1 deletion）
- 实现完成时存在顾虑：**命中** - 见下方"顾虑"

---

## 顾虑

### 顾虑 1：`pip install -e .` 失败（预存在问题，非本任务引入）

`pip install -e .` 报错：
```
ValueError: invalid pyproject.toml config: `project.dependencies`.
configuration error: `project.dependencies` must be array
```

**根因**：`pyproject.toml` 中 `[project.dependencies]` 表使用 `key = "version"` 语法（如 `Flask = "^3.0.0"`），这不符合 PEP 621 规范。PEP 621 要求 `[project]` 表下的 `dependencies` 字段为字符串数组（如 `dependencies = ["Flask>=3.0.0", ...]`）。

**预存在性验证**：通过 `git show HEAD:pyproject.toml` 确认，提交前的原 `pyproject.toml` 已使用相同的 `[project.dependencies]` + `key = "version"` 格式，所以 `pip install -e .` 在本任务之前就已经失败。本任务仅按 plan 要求在该表内追加 2 行同风格条目，**未引入新错误**。

**影响**：
- Step 5 的 `pip install -e .` 子步骤失败
- 但 Step 5 的实际验证目标（sklearn/joblib 可导入且版本 >= 1.3.0）已达成，因为环境中已预装 sklearn 1.5.1 和 joblib 1.4.2
- 不影响 Task 2/3 的运行时导入（依赖已就绪）

**建议**：
- 主会话决定是否在后续 Task 中（或单独的 fix Task）将 `[project.dependencies]` 改为 PEP 621 数组格式以修复 `pip install -e .`。该修复涉及改写所有现有依赖行，超出 Task 1 的 plan 范围（plan 仅授权追加 2 行），故本任务未自行修复。
- 或主会话确认项目实际不依赖 `pip install -e .`（可能使用 poetry 或手动 pip install），则可忽略此顾虑。

### 顾虑 2：Plan Step 1 的 Dose 文件名拼写错误

Plan 中 `ML-data-Dose-RF-Manual_splits.xlsx`（连字符）与实际 `ML-data-Dose-RF_Manual_splits.xlsx`（下划线）不符。Task 2 训练脚本需引用正确文件名。详见"自检发现 1"。
