# Task 2 Report — 训练脚本与模型生成

> **BASE commit**：`d75217d`
> **Task 2 implementer**：subagent (TDD skill 已加载，但训练脚本为工具脚本无单元测试可写，按 brief 约定不强制 TDD Red-Green-Refactor)
> **工作目录**：`d:\17417\Documents\agent_culti_demo`（Windows / PowerShell）
> **分支**：`feature/20260718/add-model-6-fertility-ml`

## 1. Status

**DONE**

所有 5 个步骤（创建脚本 / 运行训练 / 验证产物 / 验证 schema / 提交）全部完成；训练脚本一次运行成功，4 个产物文件全部生成且 schema 完整；test_r2 与预期一致（SOC=0.9096 接近 0.91，Dose=0.4683 接近 0.47）。

## 2. Commits

- **`45628c2`** — `feat(fertility): 训练 SOC/Dose ETR 模型并生成 joblib 与 metadata 产物`
  - 5 files changed, 245 insertions(+)
  - 新增 `scripts/train_fertility_models.py`（155 行）
  - 新增 `data/fertility/models/soc_etr_model.joblib`（224,289 bytes / ~219 KB，binary）
  - 新增 `data/fertility/models/soc_metadata.json`（46 行）
  - 新增 `data/fertility/models/dose_etr_model.joblib`（458,673 bytes / ~448 KB，binary）
  - 新增 `data/fertility/models/dose_metadata.json`（44 行）
  - 父提交：`d75217d`（BASE，未偏移）

## 3. 测试摘要

### 训练脚本运行输出（exit code 0）

```
=== 训练 SOC 模型 ===
训练集: 52 样本, 10 特征
测试集: 13 样本
特征名: ['pH', 'SOCbe', 'TN ', 'TP ', 'TK ', 'AP', 'AK', 'Gap', 'Dose', 'Fertilizer type']
5CV R²: 0.8916, 5CV RMSE: 2.1028
Test R²: 0.9096, Test RMSE: 2.2352
超参数: {'n_estimators': 30, 'max_depth': 10, 'min_samples_split': 2, 'min_samples_leaf': 1, 'max_features': None, 'criterion': 'squared_error', 'random_state': 0, 'n_jobs': -1}
模型已保存: data\fertility\models\soc_etr_model.joblib
元数据已保存: data\fertility\models\soc_metadata.json

=== 训练 Dose 模型 ===
训练集: 45 样本, 9 特征
测试集: 12 样本
特征名: ['pH', 'SOCbe', 'TN ', 'TP ', 'TK ', 'AP', 'AK', 'Gap', 'Fertilizer type']
5CV R²: 0.4344, 5CV RMSE: 245.3736
Test R²: 0.4683, Test RMSE: 320.5223
超参数: {'n_estimators': 290, 'max_depth': 10, 'min_samples_split': 10, 'min_samples_leaf': 1, 'max_features': 0.7, 'criterion': 'friedman_mse', 'random_state': 86, 'n_jobs': -1}
模型已保存: data\fertility\models\dose_etr_model.joblib
元数据已保存: data\fertility\models\dose_metadata.json

=== 训练完成 ===
SOC test_r2: 0.9096
Dose test_r2: 0.4683
```

### 4 个产物文件清单（PowerShell `Get-Item` 验证）

| 文件 | SizeKB |
|---|---|
| `data/fertility/models/soc_etr_model.joblib` | 219.0 |
| `data/fertility/models/soc_metadata.json` | 1.0 |
| `data/fertility/models/dose_etr_model.joblib` | 447.9 |
| `data/fertility/models/dose_metadata.json` | 0.9 |

### .joblib 加载验证

```
SOC model: ExtraTreesRegressor n_estimators= 30
Dose model: ExtraTreesRegressor n_estimators= 290
```

两个 `.joblib` 文件均能通过 `joblib.load()` 正常加载为 `ExtraTreesRegressor` 实例，n_estimators 与超参数一致。

### metadata.json schema 验证（brief Interfaces 要求的 7 个关键字段）

| 字段 | SOC | Dose |
|---|---|---|
| `model_type` | `"ExtraTreesRegressor"` ✓ | `"ExtraTreesRegressor"` ✓ |
| `model_version` | `"ETR_v1_20260713"` ✓ | `"ETR_v1_20260713"` ✓ |
| `trained_at` | `"2026-07-18T15:35:06"` ✓ | `"2026-07-18T15:35:08"` ✓ |
| `hyperparameters` | 7 keys（n_jobs 已剔除）✓ | 7 keys（n_jobs 已剔除）✓ |
| `metrics.test_r2` | `0.9096` ✓（接近预期 0.91） | `0.4683` ✓（接近预期 0.47） |
| `metrics.cv_r2` | `0.8916` | `0.4344` |
| `metrics.cv_rmse` | `2.1028` | `245.3736` |
| `metrics.test_rmse` | `2.2352` | `320.5223` |
| `feature_names` | 10 项，含 `"TN "`、`"TP "`（保留尾空格）✓ | 9 项（无 Dose 列，因 Dose 是目标），含 `"TN "`、`"TP "` ✓ |
| `feature_means` | 10 项 dict[str, float] ✓ | 9 项 dict[str, float] ✓ |
| `training_samples` | `52` ✓ | `45` ✓ |
| `test_samples` | `13` ✓ | `12` ✓ |

**brief Step 4 Expected 输出对照**：
> `ExtraTreesRegressor ETR_v1_20260713 0.9096 10 ['pH', 'SOCbe', 'TN ', 'TP ', 'TK ', 'AP', 'AK', 'Gap', 'Dose', 'Fertilizer type']`

实际输出（model_type, model_version, test_r2, n_features, feature_names）与此完全一致。

## 4. Concerns

无功能性顾虑。少量观察记录如下，均不影响 Task 3 消费：

1. **Dose 模型 test_r2 = 0.4683**：略低于设计文档 2.3 中标注的 `0.47`（round 2 位小数为 0.47），但实际精确值为 0.4683，与 brief Expected 范围一致。Task 3 在使用 `metadata.metrics.test_r2` 计算 confidence 时应使用 round 2 位小数（`round(0.4683, 2) = 0.47`），与设计文档 2.3 SOC=0.91 / Dose=0.47 一致。
2. **CV 警告**：sklearn 在 5-fold CV 时未输出任何警告（已观察运行日志无 warning），训练样本数（SOC=52, Dose=45）足够 5-fold 划分。
3. **CRLF 提示**：git add 时出现 `LF will be replaced by CRLF` 警告，这是 Windows + git autocrlf 的正常行为，不影响代码功能。
4. **训练耗时**：本地训练总耗时约 2 秒（含两次 5-fold CV，每次 CV 训练 5 个模型 + 1 个全量模型），无性能瓶颈。
5. **task-2-brief.md 未提交**：该文件是 brief 规格本身（comet 派发文件，非实现），按惯例不在 Task 2 提交范围内，保持 untracked。

## 5. 风险信号自报

按 brief 报告契约要求的 7 个风险信号逐项核对：

| 风险信号 | 是否命中 | 说明 |
|---|---|---|
| 跨模块协调 | 否 | 仅创建新文件 `scripts/train_fertility_models.py` + 4 个产物文件；未修改 framework/、tests/、pyproject.toml、.gitignore 任何既有文件。Task 3 将消费本任务的 4 个产物，但接口契约（joblib.load + json.load + metadata schema）已在 brief 中明确，无未对齐风险。 |
| 安全敏感 | 否 | 训练脚本只读本地 xlsx + 写本地 joblib/json，无网络、无认证、无敏感数据；feature_means 是数值统计非敏感信息。 |
| 并发 | 否 | 单进程单线程训练（n_jobs=-1 仅 sklearn 内部并行），无共享状态、无锁、无并发问题。 |
| 数据迁移 | 否 | 仅新增文件，未修改/删除任何既有数据；data/fertility/ 下原 xlsx 训练数据未触碰。 |
| API 变更 | 否 | 无 API 改动；脚本通过 argparse 接受 `--data-dir`/`--output-dir`，是工具脚本非服务接口。 |
| DONE_WITH_CONCERNS | 否 | 全部 5 个步骤通过，无功能性问题，少量观察已在 Concerns 中记录但均不影响交付。 |
| diff > 200 行代码 | 否 | 训练脚本本身 155 行（< 200）。提交总 insertions=245，但其中 binary `.joblib` 文件按二进制 diff 计数不计入代码行数，两个 `metadata.json` 是产物非代码。按 brief 风险信号说明「不算 >200 行代码改动」，本信号未命中。 |

**综合结论**：7 个风险信号均未命中，本任务为低风险交付。

## 6. 文件清单（绝对路径）

- 训练脚本：`d:\17417\Documents\agent_culti_demo\scripts\train_fertility_models.py`
- SOC 模型：`d:\17417\Documents\agent_culti_demo\data\fertility\models\soc_etr_model.joblib`
- SOC 元数据：`d:\17417\Documents\agent_culti_demo\data\fertility\models\soc_metadata.json`
- Dose 模型：`d:\17417\Documents\agent_culti_demo\data\fertility\models\dose_etr_model.joblib`
- Dose 元数据：`d:\17417\Documents\agent_culti_demo\data\fertility\models\dose_metadata.json`

## 7. 给 Task 3 的接口提示

Task 3 `model_6.py` 应通过以下方式消费本任务产物：

```python
import joblib, json
from pathlib import Path

model_dir = Path("data/fertility/models")
soc_model = joblib.load(model_dir / "soc_etr_model.joblib")
soc_meta = json.load(open(model_dir / "soc_metadata.json", encoding="utf-8"))
# soc_meta["feature_names"] 保留 "TN " / "TP " 含尾空格，用户输入层需 strip() 规范化
# soc_meta["feature_means"] 用于缺失特征填均值
# soc_meta["metrics"]["test_r2"] 用于 confidence（round 2 位小数 → 0.91）
# soc_meta["model_version"] = "ETR_v1_20260713"
```

Dose 同理（feature_names 9 项，无 `Dose` 列，因 Dose 是预测目标；test_r2 round 2 位 → 0.47）。
