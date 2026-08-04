# 验证报告：refresh-sg-dose-model-v2

**变更**：重训韶关 Dose RF 模型 v2 并修正版本号返回
**工作流**：tweak（spec-driven）
**验证模式**：full（8 任务 > 3 阈值 + 1 delta spec capability）
**验证日期**：2026-08-04
**验证基线**：base_ref `6d65be3` → HEAD `2834523`

## Summary

| 维度 | 状态 |
|------|------|
| Completeness | 8/8 任务完成；1 MODIFIED Requirement（9 场景）全部实现 |
| Correctness | 9/9 场景已实现并验证（单元 + E2E）；1 SUGGESTION |
| Coherence | design.md A-E 节全部遵循；指标与预测一致；无独立 Design Doc（tweak 预期） |

## 验证证据（本会话新鲜执行）

| 检查项 | 命令 | 结果 |
|--------|------|------|
| 单元 + 集成测试 | `.venv\Scripts\python.exe -m pytest tests/test_fertility_ml_prediction.py -q` | **52 passed**, 3 warnings（sklearn FutureWarning，良性） |
| 韶关旱地版本号 | `model_6_execution(..., area_code='lechang', land_type='upland')` | `model_version=SG_RF_v2_20260804` ✓ |
| 韶关水田版本号 | `model_6_execution(..., area_code='lechang', land_type='paddy')` | `model_version=SG_RF_v2_20260804` ✓ |
| 非韶关版本号 | `model_6_execution(..., area_code='other')` | `model_version=ETR_v1_20260713` ✓（不变） |
| OpenSpec 状态 | `openspec status --change refresh-sg-dose-model-v2 --json` | `isComplete: true`, 4 产物 done, 8/8 任务 |

## Completeness

### 任务完成
- 8/8 任务标记 `[x]`（openspec instructions apply 确认 `progress.complete=8, remaining=0`）

### Spec 覆盖
- delta spec（`specs/fertility-ml-prediction/spec.md`）：1 个 MODIFIED Requirement，9 个 Scenario
- 全部场景在 `model_6.py` 中有对应实现分支

## Correctness

### 需求实现映射

| 需求 | 实现位置 | 验证 |
|------|---------|------|
| 升版本常量 SG_RF_v2_20260804 | [train_fertility_models.py:38](file:///d:/17417/Documents/agent_culti_demo/scripts/train_fertility_models.py#L38) | ✓ 代码确认 |
| 重训模型 + metadata | `data/fertility/models/sg_dose_{upland,paddy}_*` | ✓ metadata version=v2, trained_at 更新 |
| 韶关 dose 返回 sg_meta 版本号 | [model_6.py:350](file:///d:/17417/Documents/agent_culti_demo/framework/domain/other_models/model_6.py#L350) | ✓ E2E 验证 |
| 非韶关 dose 返回 _MODEL_VERSION | [model_6.py:359](file:///d:/17417/Documents/agent_culti_demo/framework/domain/other_models/model_6.py#L359) | ✓ E2E 验证 |
| fallback/rejected 返回 _MODEL_VERSION | [model_6.py:248,325](file:///d:/17417/Documents/agent_culti_demo/framework/domain/other_models/model_6.py#L248) | ✓ 代码确认（未改动） |
| 测试 mock 同步 v2 | [test_fertility_ml_prediction.py:354,368](file:///d:/17417/Documents/agent_culti_demo/tests/test_fertility_ml_prediction.py#L354) | ✓ 代码确认 |

### 场景覆盖

| Scenario | 实现 | 测试 | E2E |
|----------|------|------|-----|
| 非韶关完整特征 Dose | ✓ | ✓ test_non_shaoguan_uses_global_etr | ✓ |
| 韶关旱地 Dose | ✓ | ✓ test_shaoguan_upland_uses_sg_rf | ✓ |
| 韶关水田 Dose | ✓ | ✓ test_shaoguan_paddy_uses_sg_rf | ✓ |
| 韶关 SOC 回退全局 ETR | ✓ | ✓ test_shaoguan_soc_always_global_etr | ✓ |
| SOMbe→SOCbe 映射 | ✓ | ✓ _normalize_input | — |
| 低置信度显式标注 | ✓ | ✓ dose_warning 断言 | ✓ |
| 部分特征缺失填充 | ✓ | ✓ test_success_partial_features_imputation | — |
| 模型缺失降级回退 | ✓ | ✓ test_shaoguan_model_missing_fallback | — |
| 韶关 dose 返回 SG 版本号（新增） | ✓ | mock 数据正确 | ✓ E2E 验证 |

## Coherence

### Design 遵循（design.md A-E 节）

| 节 | 决策 | 实现一致性 |
|----|------|-----------|
| A | SG_MODEL_VERSION → SG_RF_v2_20260804，SG_RF_PARAMS 不变 | ✓ |
| B | venv 重训，feature_means/sample 不变，指标轻微漂移 | ✓ 实际：旱地 test_r2=0.9622(预测~0.9611)、水田 test_r2=0.9930(预测~0.9930)；samples 185/47、1974/220 一致 |
| C | 韶关 dose 返回 sg_meta["model_version"]，边界不变 | ✓ |
| D | mock 版本字符串同步，测试断言不破坏 | ✓ 52 passed |
| E | 历史 plan/report 不篡改 | ✓ 未触碰 |

### Design Doc
- `.comet.yaml design_doc: null`——tweak 预设不创建独立 Superpowers Design Doc，design.md 即设计产物。检查项 3/6/7（Design Doc 相关）N/A。

## Issues

### CRITICAL
（无）

### WARNING
（无）

### SUGGESTION
1. **SG 路由单元测试未显式断言 `model_version` 字段**
   - 现状：`test_shaoguan_upland_uses_sg_rf` / `test_shaoguan_paddy_uses_sg_rf` 断言了 dose_prediction/confidence/warning，但未断言 `model_version`。非韶关路径（L77）有断言。
   - 影响：新增场景"韶关 Dose 响应返回 SG 模型版本号"的回归保护依赖 E2E + mock 数据正确性，缺少显式单测断言。
   - 已验证：E2E 真实模型确认 SG upland/paddy 均返回 `SG_RF_v2_20260804`，mock 数据已同步 v2。
   - 建议：后续可在 SG 路由单测中追加 `assert result["model_version"] == "SG_RF_v2_20260804"`。

## Final Assessment

无 CRITICAL 或 WARNING 问题。1 项 SUGGESTION（测试覆盖增强，行为已通过 E2E 验证）。**验证通过，可进入归档。**

- 全部测试通过（52 passed）
- 无硬编码密钥或安全问题（本次仅升版本常量、重训模型、修正版本号返回逻辑、同步 mock）
- 改动文件与 tasks.md 描述一致（7 文件 + OpenSpec change 目录，已提交 `2834523`）
