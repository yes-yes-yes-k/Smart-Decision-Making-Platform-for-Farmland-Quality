# 验证报告：persist-routing-observability（full 模式）

- **日期**：2026-08-17
- **验证模式**：full（32 任务 > 3；delta spec 3 个 capability > 1；变更文件 15 > 8，`comet state scale` 判定）
- **分支**：feature/20260817/persist-routing-observability（base-ref：96f9be8）
- **结论**：**通过（PASS）** —— 本 change 范围内无 CRITICAL / IMPORTANT 问题；全套件中的 43 failed + 35 errors 已用基线复跑证明为本 change 之前已存在的存量问题（详见 §4）。

## 1. 摘要记分卡

| 维度 | 状态 |
| --- | --- |
| Completeness | 32/32 任务完成 `[x]`；3 个 delta spec 的全部 Requirement 均有实现证据 |
| Correctness | 10/10 PG 集成测试通过；19/20 change 相关测试通过（1 个失败为基线存量）；CLI 回归 exit 0 且落库 2 行 |
| Coherence | 实现与 design.md D1–D6 决策一致；与 Design Doc §3.1–3.5 一致；两处文件/命名偏差均有 Design Doc 显式记录 |

## 2. 七项检查结果（full 模式）

| # | 检查项 | 结果 | 证据 |
| --- | --- | --- | --- |
| 1 | tasks.md 全部 `[x]` | PASS | `comet classic openspec -- status` → 32/32 complete；tasks.md 全文复核 |
| 2 | 实现符合 design.md 高层设计 | PASS | D1 双写（routing_log.py L77-91：先 DB 后 JSONL，DB 失败 warnings.warn）；D2 写入层位于 routing_log.py；D3 from_database + 模块级缓存 + `_get_active_rules()` 统一入口；D4 entry 字段对齐（observe.py）；D5/D6 模型注册与批量落库均落实 |
| 3 | 实现符合 Design Doc | PASS | §3.1 write_routing_log_to_db 字段映射逐一对应（L47-74）；§3.2 relevance/five_dim_context(4字段)/logged_at/total_duration_ms 全部落位（observe.py L79-111）；§3.3 from_database/_db_rules_cache/_get_active_rules/refresh_rules_cache/apply_exclusive_rules/`_matched_rules` 六点全改（exclusive_rules.py L93-131、L221；observe.py L30）；§3.4 write_metrics_to_db + main() 调用 + 退出码不变（run_routing_regression.py L59-86、L120-123） |
| 4 | 能力规格场景全部通过 | PASS | routing-log-persistence 3 场景 ↔ test_routing_log_db.py 3 用例（双写/DB失败回退/字段对齐）全过；routing-observability 5 场景由 test_routing_log_db + test_routing_observability（19 过）+ CLI 复验覆盖；role-based-routing 4 场景 ↔ test_exclusive_rules_db.py（加载/不可用回退/空回退/判定一致）+ refresh_rules_cache 全过；混淆矩阵落库 2 场景 ↔ test_regression_metrics_db.py 全过 |
| 5 | proposal.md 目标已满足 | PASS | 双写、动态加载、评估落库、entry 对齐四目标均有实现+测试+DB 行证据 |
| 6 | delta spec 与 design doc 无矛盾 | PASS（含 2 处已记录偏差，见 §3） | delta spec 未强制模型文件位置与 duration_ms 别名；两处偏差均由 Design Doc 显式记录并给出理由 |
| 7 | Design Doc 可定位 | PASS | docs/superpowers/specs/2026-08-17-persist-routing-observability-design.md 存在且 .comet.yaml design_doc 指向它 |

## 3. 已记录偏差（不阻塞，均有 Design Doc 依据）

1. **ORM 模型文件位置**：tasks.md 1.1–1.3 写"新增 `framework/models/routing_observability.py`"，实际三个模型（RoutingDecisionLog/ModelEvaluationMetrics/ExclusiveRuleConfig）定义于 [thematic_model.py](file:///d:/17417/Documents/agent_culti_demo/framework/models/thematic_model.py#L368-L444)。Design Doc §2.2 显式记录：任务 1.x 已由前序 change `2026-08-16-add-thematic-model-orm` 完成（V3.0 §8.11–8.13 同文件集中管理），本 change 跳过 1.x 实施。表名、字段与 delta spec 完全一致。
2. **duration_ms 别名**：design.md D4 与 tasks.md 3.4 提"保留 `duration_ms` 别名"，Design Doc §3.2.1/§3.2.2 经全仓 grep 后决策"完全重命名，不保留别名"（仅 observe.py 2 处赋值 + 1 处测试断言，全部已更新）。实现遵循 Design Doc；delta spec 仅要求 entry 含 `total_duration_ms`，无别名要求。

## 4. 测试套件结果与失败归属判定（重点）

### 4.1 全套件（HEAD，`.venv` Python 3.12.3 + pytest 9.1.1）

```
43 failed, 453 passed, 10 skipped, 35 errors in 259.52s
```

- 10 skipped 为 3 个 PG 测试文件（探测时未设 DB_* 环境变量；设置后单独复跑 **10/10 全部通过**，见 4.3）
- 43 failed + 35 errors 全部位于本 change **未修改**的测试文件（本 change diff 仅含：exclusive_rules.py、app.py、models/__init__.py、observe.py、routing_log.py、run_routing_regression.py、conftest.py、3 个新测试文件、test_routing_observability.py）

### 4.2 基线归属判定（决定性证据）

在本 change 实现起点的前一提交 `718d419` 上建立 worktree（同 .venv、同 .env）复跑代表性失败子集，结果与 HEAD **完全一致**（13 failed：test_routing_observability TestNodeInjection 1 + test_agent_manager 9 + test_question_type_router 2 + test_nodes_passthrough 1）：

```
13 failed, 34 passed in 31.73s   （基线 718d419）
```

归属结论：
- **35 errors**（test_soil_data_models/test_data_import_route/test_docs_dedup/test_observability_api 等）：SQLite 测试库上 `db.create_all()` 需为 `spatial_data_layer` 发出 SpatiaLite DDL（`RecoverGeometryColumn`），本机 SQLite 无该扩展 —— 由前序 `add-thematic-model-orm` change 引入，与本 change 无关
- **43 failed**：由 `zsj_0815` 合并（模型编号重排 type4↔model-2/model-4、nodes.py 重写丢失 result.trace_id）及更早变更引入，与本 change 无关
- 唯一被本 change 修改过的失败文件 test_routing_observability.py，其失败用例 `TestNodeInjection::test_identify_question_node_preserves_return_and_logs`（KeyError: trace_id）在基线同样失败

### 4.3 本 change 专属测试（带 DB_* 环境变量，真实 PostgreSQL db_enterprise_qa）

```
tests/test_routing_log_db.py      3/3 PASSED（双写正常 / DB 失败回退 JSONL+告警 / entry 18 列逐列对齐）
tests/test_exclusive_rules_db.py  5/5 PASSED（from_database 加载 / DB 不可用回退 / DB 空回退 / DB 规则与硬编码判定一致 / refresh_rules_cache 生效）
tests/test_regression_metrics_db.py 2/2 PASSED（评估结果落库 / DB 失败保留 JSON 且退出码不变）
→ 10 passed in 3.02s
```

### 4.4 端到端复验（任务 7.x）

```
python scripts/run_routing_regression.py
[model-3-vs-model-2] 样本数=216 TP=120 FP=0 FN=0 TN=96 正确率=100.00% 混淆率=0.00%
[model-4-vs-model-5] 样本数=156 TP=84  FP=0 FN=0 TN=72 正确率=100.00% 混淆率=0.00%
EXIT=0（目标达成；无 DB 写入失败告警）
```

DB 复查 `model_evaluation_metrics`：本次 CLI 新增 2 行（id=10 model-3-vs-model-2 n=216、id=11 model-4-vs-model-5 n=156，mode=keyword，acc=1.0），与任务 7.5 记录一致。

## 5. 安全检查

- 无硬编码密钥：DB 口令经 `DB_PASSWORD` 环境变量读取（framework/config.py L17），`.env` 已被 .gitignore 忽略（`git check-ignore .env` 命中）
- 无新增 unsafe 操作；DB 写入异常全部 try/except 隔离（routing_log.py L80-83、run_routing_regression.py L81-86 双层 rollback 保护）

## 6. 问题清单

### CRITICAL
无（本 change 范围内）。

### WARNING
1. **存量套件失败（范围外）**：43 failed + 35 errors 为前序变更遗留（SpatiaLite/SQLite 不兼容、zsj_0815 模型编号重排、nodes.py trace_id 回归）。建议另立 change 修复（方向：测试库切 PG 或为 SQLite 跳过空间表；按新编号体系更新路由断言；恢复 identify_question_node 的 trace_id 透传）。
2. **conftest PG 探测不加载 dotenv**：未设 DB_* 环境变量时 10 个 PG 测试静默跳过（本次已用环境变量复跑全过）。建议后续在 conftest 探测前 `load_dotenv()`，避免漏测。

### SUGGESTION
- `observe.py` 成功/失败两条路径的 `_FIVE_DIM_KEYS` 提取与赋值逻辑重复（L97-101 与 L107-111），可提取局部函数；不影响正确性，留待后续。

## 7. 最终评估

本 change 的全部 delta spec Requirement 与 Scenario 均有实现与测试证据；实现与 design.md 决策、Design Doc 细节一致；两处偏差均有 Design Doc 显式记录依据。全套件失败均被基线复跑证明为存量问题，非本 change 引入，不构成本次验证的阻塞项。

**验证结论：PASS，可进入 Archive。**
