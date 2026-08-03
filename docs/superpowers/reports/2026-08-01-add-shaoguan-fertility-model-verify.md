---
comet_change: add-shaoguan-fertility-model
role: verify-report
verify_mode: full
date: 2026-08-01
language: zh-CN
---

# 验证报告：add-shaoguan-fertility-model

## 摘要

| 维度 | 状态 |
|------|------|
| 完整性 (Completeness) | 30/30 任务完成；3 个 Requirement 全部实现 |
| 正确性 (Correctness) | 全部 spec 场景由测试覆盖；相关测试 101 passed / 0 failed |
| 一致性 (Coherence) | Design Doc D1-D5 决策均被遵循；1 个 SUGGESTION（非阻塞） |
| 回归 | 0 新增失败；79 个预存失败在 base-ref 上完全一致 |

**最终评估**：无 CRITICAL / IMPORTANT 问题。验证通过，可进入收尾与归档。

---

## 1. 完整性 (Completeness)

### 任务完成度
- `openspec status`：isComplete=true，4 产物（proposal/design/specs/tasks）均为 done
- `openspec instructions apply`：progress 30/30，state=all_done
- tasks.md 全部 `[x]`，无未勾选任务

### Spec 覆盖
delta spec (`specs/fertility-ml-prediction/spec.md`) 含 3 个 Requirement：
1. **Dose ML 预测能力**（MODIFIED）— 8 个 Scenario，全部实现
2. **训练脚本可重训模型**（MODIFIED）— 3 个 Scenario，全部实现
3. **训练数据资产可追溯**（MODIFIED）— 3 个 Scenario，全部实现
4. **韶关区域路由与 land_type 参数支持**（ADDED）— 4 个 Scenario，全部实现

无未实现的 Requirement。

---

## 2. 正确性 (Correctness)

### 测试证据（新鲜运行，2026-08-01）

使用主仓库 `.venv`（sklearn 1.9.0）运行本 change 涉及的 4 个测试文件：

```
tests/test_fertility_ml_prediction.py
tests/test_train_fertility_sg.py
tests/test_agent_classic_qa.py
tests/test_agent_specialized.py
→ 101 passed, 0 failed, 0 skipped
```

其中 SG 集成测试（真实模型，非 mock）全部通过：
- `TestModel6ShaoguanIntegration::test_real_sg_upland_dose_in_range` — Dose ∈ [0, 1000] 合理范围
- `TestModel6Integration::test_real_soc_prediction_in_range` / `test_real_dose_prediction_in_range`
- `test_real_non_shaoguan_unchanged` — 非韶关区域行为不变

### Spec 场景 → 测试映射

| Spec Scenario | 验证测试 | 结果 |
|---|---|---|
| 非韶关区域 Dose 预测（全局 ETR） | test_non_shaoguan_unchanged / test_real_non_shaoguan_unchanged | PASS |
| 韶关旱地 Dose（SG upland RF） | test_real_sg_upland_dose_in_range | PASS |
| 韶关水田 Dose（SG paddy RF） | test_shaoguan_paddy_routing | PASS |
| 韶关 SOC 回退全局 ETR | test_shaoguan_soc_uses_global_etr | PASS |
| SOMbe→SOCbe 映射 | TestNormalizeInput（3 用例） | PASS |
| 显式低置信度标注 | dose_warning 含模型类型 + R² | PASS |
| 部分特征缺失均值填充 | imputation 测试 | PASS |
| Dose 模型文件缺失降级 | test_sg_model_missing_fallback | PASS |
| land_type 未传默认旱地 + 提示 | test_shaoguan_land_type_not_specified_warning | PASS |
| 非韶关忽略 land_type | test_non_shaoguan_ignores_invalid_land_type | PASS |
| FertilityMLAgent 透传 | test_agent_passes_area_code_land_type | PASS |
| 训练脚本 --sg | test_train_fertility_sg.py | PASS |
| 韶关模型元数据可读 | metadata.json 字段核验（见下） | PASS |

### metadata.json 字段核验（spec 场景"韶关模型元数据可读"）

`sg_dose_upland_metadata.json`：
- model_type: "RandomForestRegressor" ✓
- trained_at: "2026-07-31T23:39:56"（ISO 8601）✓
- model_version: "SG_RF_v1_20260731" ✓
- hyperparameters: n_estimators=100, random_state=230 ✓
- metrics: cv_r2=0.9711, test_r2=0.9616, test_rmse=22.80 ✓
- feature_names: pH, SOCbe, TN, TP, TK, AP, AK, Gap, Fertilizer type（SOMbe 已重命名为 SOCbe）✓
- training_samples: 185 ✓（与 proposal "旱地 185 样本" 一致）

`sg_dose_paddy_metadata.json`：同结构，training_samples=1974, test_r2=0.9931。

两个模型 test_r2（0.96 / 0.99）均显著高于全局 Dose ETR（0.47），达成 proposal 提升本地 Dose 预测质量的目标。

---

## 3. 一致性 (Coherence)

### Design Doc 决策遵循

Design Doc (`docs/superpowers/specs/2026-07-31-add-shaoguan-fertility-model-design.md`) 决策 D1-D5：

| 决策 | 实现遵循 | 证据 |
|---|---|---|
| D1 签名设计（area_code 从 input_data，land_type 显式参数） | ✓（轻微漂移见下） | model_6.py model_6_execution 签名 |
| D2 区域路由（SHAOGUAN_AREA_CODES={"lechang"}, .lower()） | ✓ | model_6.py SHAOGUAN_AREA_CODES + is_shaoguan |
| D3 SG RF 惰性加载（double-checked locking） | ✓ | _ensure_sg_model_loaded 复用 _LOAD_LOCK |
| D4 SOMbe→SOCbe 输入层映射 | ✓ | _normalize_input |
| D5 训练脚本扩展（--sg/--all） | ✓ | train_fertility_models.py |

### design.md（OpenSpec）高层决策遵循

design.md D1-D5 与 Design Doc 一致，实现均遵循。Risks 节"SG 水田样本 <30 标注低置信度"逻辑已实现（`if training_samples < 30: dose_warning += ...`）；实际水田 1974、旱地 185 样本均 >30，未触发。

### Issues

**SUGGESTION（非阻塞）**：Design Doc D1 签名行写作 `land_type: str = "upland"`，实际实现为 `land_type: Optional[str] = None`（为区分"显式传 upland"与"未传"，以触发 spec L82-83 的"未指定 land_type"提示）。Design Doc 第 6 节测试策略表（行 143）已记录"未传 land_type | 默认 upland + warning 提示"，与 spec 一致。此为设计文档内部签名细节滞后，非 delta spec 与 design doc 矛盾。建议归档时同步更新 D1 签名描述，或标记为 superseded-by-main-spec。

无 CRITICAL / WARNING 问题。

---

## 4. 回归核验

### 全量测试套件（排除 4 个预存 collection-error 模块）

HEAD（本 change）：79 failed, 317 passed, 2 skipped

### 预存失败确认（base-ref 对比）

在 base-ref `cee7265d` 创建临时 worktree 运行同样 8 个失败测试文件：
- **base-ref：79 failed, 42 passed**
- **HEAD：79 failed**（全量 317 passed）

失败数完全一致（79=79），失败文件清单相同：
- tests/test_agent_integration.py
- tests/test_execute_models_pipeline.py
- tests/test_import_lechang_data.py
- tests/test_knowledge_question.py
- tests/test_model_specs_sync.py
- tests/test_multi_agent.py
- tests/test_question_type_keywords.py
- tests/test_stability_and_grade_integration.py

这些文件均不在本 change 的 diff 中。失败原因均为预存问题：
- `QUESTION_TYPE_4/5_KEYWORDS` 从未在 nodes.py 定义（type 4/5 关键词路由未实现，预存缺口）
- `framework.models.data_file` 模块缺失（预存）
- langchain `Tool` 导入版本问题（预存）
- `fake.shp` 测试数据缺失（预存环境问题）

**结论：本 change 零回归。**

### 本 change diff 涉及的测试文件

`test_fertility_ml_prediction.py` / `test_train_fertility_sg.py` / `test_agent_classic_qa.py` / `test_agent_specialized.py` → 101 passed, 0 failed

---

## 5. 安全检查

- 无硬编码密钥
- 无新增 unsafe 操作
- 模型文件为二进制 .joblib（scikit-learn 标准持久化格式），无安全风险

---

## 6. 构建检查

Python 项目无 package.json；guard `Build passes` 项通过（COMET_SKIP_BUILD=1，Python 项目无编译步骤）。测试即构建验证，已通过。

---

## 最终评估

- **CRITICAL**：0
- **IMPORTANT**：0
- **WARNING**：0
- **SUGGESTION**：1（Design Doc D1 签名细节滞后，非阻塞）

验证通过。全部测试（本 change 相关）通过，无回归，spec 场景全覆盖，Design Doc 决策被遵循。可进入分支收尾与归档。
