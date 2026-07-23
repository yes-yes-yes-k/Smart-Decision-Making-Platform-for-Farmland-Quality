# Task 1 Brief：数据资产迁移与依赖声明

> 从 Plan `docs/superpowers/plans/2026-07-18-add-model-6-fertility-ml.md` Task 1 提取。

## Files
- Create: `data/fertility/`（目录）
- Create: `data/fertility/models/`（目录）
- Copy: `data/fertility/ML-data-SOC-RF_Manual_splits.xlsx`（从源路径）
- Copy: `data/fertility/ML-data-Dose-RF_Manual_splits.xlsx`（从源路径，注意：实际文件名是下划线 `RF_Manual`，非连字符 `RF-Manual`）
- Copy: `data/fertility/变量注释.xlsx`（从源路径）
- Modify: `.gitignore`
- Modify: `pyproject.toml`

## Interfaces
- Consumes: 无
- Produces: `data/fertility/` 目录含 3 个 xlsx 训练数据文件；`pyproject.toml` 新增 `scikit-learn` 与 `joblib` 依赖。Task 2 训练脚本读取这些 xlsx 文件，Task 3 model_6.py 加载 `data/fertility/models/` 下的产物。

## Steps

### Step 1: 创建数据目录并复制训练数据文件
- 创建 `data/fertility/models/` 目录
- 从源路径复制 3 个 xlsx 到 `data/fertility/`

### Step 2: 验证文件已复制且大小 <10MB
- 3 个文件均列出，SizeMB 均 < 10

### Step 3: 更新 `.gitignore` 确保 `data/fertility/` 不被忽略
追加到 `.gitignore` 末尾：
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
- 运行 `pip install -e .`
- 验证 `python -c "import sklearn; import joblib; print(sklearn.__version__, joblib.__version__)"` 输出两个版本号均 >= 1.3.0

### Step 6: 提交
- `git add data/fertility/ .gitignore pyproject.toml`
- `git commit -m "feat(fertility): 迁移训练数据资产并声明 scikit-learn/joblib 依赖"`

## Global Constraints（来自 Plan）

- 模型版本号统一为 `"ETR_v1_20260713"`
- SOC 模型 confidence = 0.91；Dose 模型 confidence = 0.47
- Fallback 时 confidence 降为 0.3
- 模型文件路径用 `Path(__file__).resolve().parents[3] / "data" / "fertility" / "models"` 计算
- 特征名保留原始含空格形式（`"TN "`、`"TP "`），用户输入层做 `strip()` 规范化
- 范围校验合法范围：pH(3-11)、SOCbe(0-100)、TN(0-10)、TP(0-10)、TK(0-100)、AP(0-200)、AK(0-500)、Gap(-10~50)、Dose(0-1000)、Fertilizer type(1-2)
- 任一特征越界即整体拒绝 `status: "rejected"`
- 任一模型文件缺失即整体降级 `status: "fallback"`
- Dose 单位统一为 t/ha
- 模型加载用 double-checked locking + `threading.Lock`；加载失败后不重试
- `model_6_execution` 函数签名与 `__init__.py` 导出名保持不变
- 测试运行命令：`python -m pytest tests/ -v`
- `pyproject.toml` 使用 Poetry 风格版本号 `^1.3.0`（与现有 `pandas = "^2.2.0"` 一致）
- 训练数据来源：`F:\BaiduNetdiskDownload\SOC（土壤有机碳）和Dose（施用量）预测模型\`

## 注意事项

- Plan Step 1 中 Dose 文件名写为 `ML-data-Dose-RF-Manual_splits.xlsx`（连字符），实际源文件名是 `ML-data-Dose-RF_Manual_splits.xlsx`（下划线）。implementer 已按实际文件名复制。
- `pip install -e .` 失败是预存在问题（pyproject.toml `[project.dependencies]` 表使用 Poetry 风格 `key = "version"` 而非 PEP 621 数组格式）。本任务按 plan 在该表追加同风格条目，未引入新错误。
