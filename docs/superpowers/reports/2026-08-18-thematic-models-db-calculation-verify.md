# 专题模型数据库计算流程验证报告

**日期**: 2026-08-18
**验证目标**: 检验 5 个专题模型（Model-1~Model-5）从 PostgreSQL 数据库读取地块数据、执行计算、持久化结果的全流程
**数据库**: PostgreSQL 16 + PostGIS 3.4
**验证脚本**: [scripts/verify_thematic_models_db.py](file:///d:/17417/Documents/agent_culti_demo/scripts/verify_thematic_models_db.py)

## 1. 测试地块数据

向 `parcel_info` 表插入 3 个代表性地块，覆盖不同土壤条件：

| parcel_id | land_type | soil_ph | organic_matter | available_p | available_k | terrain_position | 特征 |
|-----------|-----------|---------|----------------|-------------|-------------|------------------|------|
| P-VERIFY-001 | upland | 4.8 | 15.0 | 8.0 | 60.0 | lower | 酸性旱地，低有机质 |
| P-VERIFY-002 | paddy | 5.8 | 28.0 | 15.0 | 120.0 | middle | 中性水田，高有机质 |
| P-VERIFY-003 | upland | 5.2 | 8.0 | 5.0 | 40.0 | upper | 弱酸性旱地，极低有机质 |

同时向 `thematic_model_registry` 表注册了 6 个模型条目（model-1~model-6），满足 `model_execution_log` 的 FK 约束。

## 2. 各模型计算结果

### Model-1 稳定性风险评价（model-1）

| parcel_id | status | data_source | simulated | persisted | 说明 |
|-----------|--------|-------------|-----------|-----------|------|
| P-VERIFY-001 | degraded | unknown | N/A | N/A | LLM/ChromaDB 初始化失败 |
| P-VERIFY-002 | degraded | unknown | N/A | N/A | LLM/ChromaDB 初始化失败 |
| P-VERIFY-003 | degraded | unknown | N/A | N/A | LLM/ChromaDB 初始化失败 |

**问题**: Model-1 的 `StabilityRiskAgent` 依赖 LLM 路由和 ChromaDB 向量检索。验证环境中 embedding API 返回 400 错误，ChromaDB 重建集合后仍降级。Agent 未从 `parcel_info` 读取数据（data_source=unknown），结果未持久化。

### Model-2 耕地质量等级评价（model-2）

| parcel_id | status | data_source | simulated | persisted | quality_grade | composite_index |
|-----------|--------|-------------|-----------|-----------|---------------|-----------------|
| P-VERIFY-001 | ok | db | False | True | 0 | 0.0 |
| P-VERIFY-002 | ok | db | False | True | 0 | 0.0 |
| P-VERIFY-003 | ok | db | False | True | 0 | 0.0 |

**结果**: DB 优先读取成功（data_source=db），计算结果非模拟（simulated=False），成功持久化到 `quality_grade_result` 表。

**注意**: `quality_grade=0` 和 `composite_index=0.0` 表明该 Agent 的实际评价逻辑未充分实现——仅读取了 DB 指标但未执行真正的等级计算。indicators 中 `soil_bulk_density`、`topsoil_texture`、`irrigation_capacity`、`drainage_capacity` 均为 None，这些字段在 `soil_indicators` JSON 中使用的键名（`bulk_density`、`soil_texture`）与 Agent 期望的键名不匹配。

### Model-3 障碍诊断（model-3）

| parcel_id | status | data_source | simulated | persisted | obstacle_type |
|-----------|--------|-------------|-----------|-----------|---------------|
| P-VERIFY-001 | ok | db | False | True | 未知 |
| P-VERIFY-002 | ok | db | False | True | 未知 |
| P-VERIFY-003 | ok | db | False | True | 未知 |

**结果**: DB 优先读取成功，结果持久化到 `obstacle_diagnosis_result` 表。

**注意**: `obstacle_type=未知`、`diagnosis.ZALX=待诊断`、所有 membership/obstacle_degree/obstacle_grade 字段为 None。说明 Agent 的障碍诊断隶属度计算逻辑未充分实现，仅完成了数据读取和持久化框架。

### Model-4 酸化改良（model-4）

| parcel_id | status | data_source | simulated | persisted | reason |
|-----------|--------|-------------|-----------|-----------|--------|
| P-VERIFY-001 | rejected | db | False | True | model_unavailable |
| P-VERIFY-002 | rejected | db | False | True | model_unavailable |
| P-VERIFY-003 | rejected | db | False | True | model_unavailable |

**结果**: DB 优先读取成功（SJD=soil_ph, JHX=exchangeable_hydrogen），结果持久化到 `acidification_remediation_result` 表。

**注意**: `status=rejected`，外部酸化模型（`.exe`）不可用（model_unavailable）。`soil_conditioner_dosage=0.0`、`woody_peat_dosage=0.0`，说明 DB 数据已正确传递到模型输入，但外部计算引擎缺失。输入参数中 `SJD`（pH=4.8/5.8/5.2）和 `JHX`（交换性氢=5.0/2.0/4.0）均从 DB 正确读取。

### Model-5 有机质培肥（model-5）

| parcel_id | status | data_source | simulated | persisted | level | manure_dosage | potential_increase |
|-----------|--------|-------------|-----------|-----------|-------|---------------|-------------------|
| P-VERIFY-001 | ok | db | False | True | 低 | 1500.0 | 2.25 |
| P-VERIFY-002 | ok | db | False | True | 中 | 1000.0 | 1.5 |
| P-VERIFY-003 | ok | db | False | True | 极低 | 2000.0 | 3.0 |

**结果**: DB 优先读取成功（pH/SOMbe/AK/AP/TN 均从 soil_indicators 映射），规则计算正确，结果持久化到 `organic_matter_result` 表。

**验证逻辑**:
- P-VERIFY-001: organic_matter=15.0 → level=低 → manure_dosage=1500.0 (符合 10≤v<20→低→1500 规则)
- P-VERIFY-002: organic_matter=28.0 → level=中 → manure_dosage=1000.0 (符合 20≤v<30→中→1000 规则)
- P-VERIFY-003: organic_matter=8.0 → level=极低 → manure_dosage=2000.0 (符合 v<10→极低→2000 规则)

## 3. 持久化验证

### model_execution_log

| agent_id | 记录数 | 状态 |
|----------|--------|------|
| model-2 | 3 | ok |
| model-3 | 3 | ok |
| model-4 | 3 | ok（Agent 返回 rejected，但持久化 status=ok） |
| model-5 | 3 | ok |
| model-1 | 0 | （degraded，未持久化） |

共 12 条执行日志记录，每条包含 trace_id、agent_id、parcel_id、input_params（JSON）、output_result（JSON）、status、started_at、completed_at。

### 结果表

| 结果表 | 记录数 | 关联 execution_id |
|--------|--------|-------------------|
| stability_risk_result | 0 | （Model-1 degraded，未持久化） |
| quality_grade_result | 3 | 13, 14, 15 |
| obstacle_diagnosis_result | 3 | 16, 17, 18 |
| acidification_remediation_result | 3 | 19, 20, 21 |
| organic_matter_result | 3 | 22, 23, 24 |
| comprehensive_fertility_result | 0 | （Model-6 未调用） |

所有持久化记录包含 `input_snapshot`（JSON 快照）、`simulated` 标志和 `created_at` 时间戳，`execution_id` 外键正确关联到 `model_execution_log.id`。

## 4. 数据流验证总结

```
parcel_info.soil_indicators (JSON)
    ↓ ParcelDataAccessor.get_parcel_indicators(parcel_id)
Agent._collect_inputs(task)
    ↓ _map_indicators_to_inputs(indicators)
Agent.execute(task)
    ↓ 计算逻辑（规则/ML/外部模型）
Agent._persist_result(execution_id, result)
    ↓ model_execution_log + 结果表（同事务）
PostgreSQL
```

### DB 优先读取验证

| 模型 | DB 读取 | 降级路径 | 说明 |
|------|---------|----------|------|
| Model-1 | 未触发 | 未触发 | LLM 初始化失败导致 degraded |
| Model-2 | **成功** | N/A | data_source=db |
| Model-3 | **成功** | N/A | data_source=db |
| Model-4 | **成功** | N/A | data_source=db |
| Model-5 | **成功** | N/A | data_source=db |

### 键名映射验证

Model-5 的键名映射正确：
- `soil_ph` → `pH` / `soil_ph`
- `organic_matter` → `SOMbe` / `organic_matter`
- `available_potassium` → `AK`
- `available_phosphorus` → `AP`
- `total_nitrogen` → `TN`

Model-4 的键名映射正确：
- `soil_ph` → `SJD`
- `exchangeable_hydrogen` → `JHX`

Model-2/Model-3 存在键名不匹配问题：
- `soil_indicators` 中的 `bulk_density` 未映射到 Agent 期望的 `soil_bulk_density`
- `soil_indicators` 中的 `soil_texture` 未映射到 Agent 期望的 `topsoil_texture`
- `irrigation_condition` 未映射到 `irrigation_capacity`

## 5. 发现的问题

### CRITICAL

1. **Model-1 完全不可用**: `StabilityRiskAgent` 依赖 LLM 和 ChromaDB，在 embedding API 不可用时降级，不从 DB 读取数据，不返回计算结果，不持久化。需修复为 DB 优先 + 规则降级路径。

### IMPORTANT

2. **Model-2/Model-3 计算结果为占位值**: `quality_grade=0`、`obstacle_type=未知` 表明 Agent 的计算逻辑未充分实现。DB 数据已正确读取，但隶属度计算和等级评价逻辑缺失。

3. **键名映射不完整**: `soil_indicators` JSON 中的部分字段（`bulk_density`、`soil_texture`、`irrigation_condition`）未映射到 Agent 期望的键名（`soil_bulk_density`、`topsoil_texture`、`irrigation_capacity`），导致这些指标为 None。

### SUGGESTION

4. **Model-4 外部模型缺失**: 酸化改良的外部 `.exe` 模型不可用（model_unavailable），但 DB 数据流和持久化框架正常工作。建议补充纯 Python 实现的降级计算路径。

5. **model_execution_log 中 Model-4 的 status=ok**: Agent 返回 `status=rejected`，但持久化到 `model_execution_log` 时 status 为 `ok`。建议统一 Agent 返回状态与持久化状态。

## 6. 最终评估

| 验证维度 | 结果 |
|----------|------|
| DB 连接 | PASS（PostgreSQL 16 + PostGIS 3.4） |
| parcel_info 数据读取 | PASS（3 个地块成功读取） |
| ParcelDataAccessor | PASS（get_parcel_indicators 正确返回 soil_indicators） |
| Model-1 稳定性 | FAIL（LLM 依赖导致 degraded） |
| Model-2 质量等级 | PARTIAL（DB 读取成功，计算逻辑未实现） |
| Model-3 障碍诊断 | PARTIAL（DB 读取成功，隶属度计算未实现） |
| Model-4 酸化改良 | PARTIAL（DB 读取成功，外部模型不可用） |
| Model-5 有机质培肥 | PASS（DB 读取 + 规则计算 + 持久化全链路通过） |
| model_execution_log 持久化 | PASS（12 条记录，FK 关联正确） |
| 结果表持久化 | PASS（4 张结果表各 3 条记录，execution_id FK 正确） |

**总结**: 5 个专题模型中，Model-5 完整验证了 DB 优先读取→计算→持久化的全链路；Model-2/3/4 的 DB 数据流和持久化框架正常，但计算逻辑或外部依赖存在缺口；Model-1 因 LLM 依赖完全降级。建议优先修复 Model-1 的 DB 优先降级路径和 Model-2/3 的键名映射问题。
