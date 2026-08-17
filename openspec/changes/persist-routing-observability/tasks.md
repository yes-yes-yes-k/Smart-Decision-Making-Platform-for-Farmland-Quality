## 1. SQLAlchemy 模型定义

- [ ] 1.1 新增 `framework/models/routing_observability.py`，定义 `RoutingDecisionLog` 模型（表 `routing_decision_log`），字段：trace_id, question, question_type, relevance, routing_status, router_method, candidate_agents(JSONB), hit_exclusive_rules(JSONB), llm_reason, llm_duration_ms, total_duration_ms, degradation, five_dim_context(JSONB), data_version, agent_version, result_version, failure_reason, logged_at
- [ ] 1.2 在同文件定义 `ModelEvaluationMetric` 模型（表 `model_evaluation_metrics`），字段：model_pair, positive_label, tp, fp, fn, tn, total, accuracy, confusion_rate, evaluation_mode, sample_count, evaluated_at
- [ ] 1.3 在同文件定义 `ExclusiveRuleConfig` 模型（表 `exclusive_rule_config`），字段：rule_name, rule_pair(JSONB), discriminator, condition, target, dimension_conditions(JSONB), enabled, created_at, updated_at
- [ ] 1.4 更新 `framework/models/__init__.py` 注册三个新模型
- [ ] 1.5 更新 `init_db.py` 确保 `db.create_all()` 包含新表

## 2. 路由日志 DB 双写层

- [x] 2.1 在 `framework/observability/routing_log.py` 新增 `write_routing_log_to_db(entry)` 函数，封装 SQLAlchemy session 写入 `routing_decision_log` 表
- [x] 2.2 修改 `write_routing_log(entry)` 实现双写逻辑：先写 DB，DB 失败时告警并回退 JSONL；JSONL 始终写入作为降级备份
- [x] 2.3 确保 DB 写入异常被 try/except 隔离，不传播到 `observe.py` 的 `_safe_write_log`

## 3. observe.py entry 字段对齐

- [x] 3.1 在 `observe.py` 的 entry 中补充 `relevance` 字段（从 `identify_question_type` 返回值获取）
- [x] 3.2 在 entry 中补充 `five_dim_context` 字段（从 context 参数或 routing 模块五维特征提取）
- [x] 3.3 在 entry 中补充 `logged_at` 字段（写入时间戳）
- [x] 3.4 将 entry 的 `duration_ms` 重命名为 `total_duration_ms`，保留 `duration_ms` 别名向后兼容

## 4. 排他规则动态加载

- [x] 4.1 在 `framework/agents/exclusive_rules.py` 新增 `from_database()` 函数，从 `exclusive_rule_config` 表加载 enabled=true 的规则到 `ExclusiveRule` 对象列表
- [x] 4.2 新增模块级缓存 `_db_rules_cache`，首次加载后缓存，避免每次路由判定查询 DB
- [x] 4.3 新增 `_get_active_rules()` 统一入口函数，优先返回 DB 规则，DB 不可用或为空时回退硬编码 `EXCLUSIVE_RULES`
- [x] 4.4 修改 `apply_exclusive_rules` 使用 `_get_active_rules()` 替代硬编码 `EXCLUSIVE_RULES`
- [x] 4.5 修改 `_matched_rules`（observe.py）使用 `_get_active_rules()` 保持一致性

## 5. 混淆矩阵评估结果落库

- [x] 5.1 在 `scripts/run_routing_regression.py` 新增 `write_metrics_to_db(matrix, evaluation_mode)` 函数，批量写入 `model_evaluation_metrics` 表
- [x] 5.2 在 `main()` 函数末尾调用 `write_metrics_to_db`，DB 写入失败时保留 JSON 文件输出并告警
- [x] 5.3 确保 DB 写入失败不改变脚本退出码

## 6. 测试

- [x] 6.1 新增 `tests/test_routing_log_db.py`：测试双写正常路径、DB 失败回退 JSONL、entry 字段对齐
- [ ] 6.2 新增 `tests/test_exclusive_rules_db.py`：测试 from_database() 加载、DB 不可用回退、DB 为空回退、动态规则与硬编码规则判定一致
- [ ] 6.3 新增 `tests/test_regression_metrics_db.py`：测试评估结果落库、DB 失败保留 JSON 输出
- [ ] 6.4 运行现有测试套件确保无回归（`pytest tests/`）

## 7. 验证

- [ ] 7.1 运行 `init_db.py` 创建三张新表
- [ ] 7.2 验证路由日志双写：执行一次路由判定，确认 JSONL 和 DB 表均有记录
- [ ] 7.3 验证 DB 写入失败降级：模拟 DB 异常，确认 JSONL 写入正常且告警输出
- [ ] 7.4 验证排他规则动态加载：向 `exclusive_rule_config` 表插入测试规则，确认路由判定使用 DB 规则
- [ ] 7.5 验证混淆矩阵落库：运行 `run_routing_regression.py`，确认 `model_evaluation_metrics` 表有记录
