## Context

当前路由可观测性体系的三类数据均依赖文件存储：

1. **路由日志**：`framework/observability/routing_log.py` 的 `write_routing_log(entry)` 追加 JSON 行到 `logs/routing_calls_YYYYMMDD.jsonl`，由 `observe.py` 的 `_safe_write_log` 调用
2. **排他规则**：`framework/agents/exclusive_rules.py` 的 `EXCLUSIVE_RULES` 硬编码为 Python 元组，包含 8 条规则（v1 关键词 + v1.1 维度驱动）
3. **混淆矩阵**：`scripts/run_routing_regression.py` 输出 JSON 文件到 `logs/confusion_matrix.json`

现有 DB 基础设施：SQLAlchemy ORM，`db` 实例定义于 `framework/models/user.py`，开发环境使用 SQLite，生产环境支持 MySQL。`observe.py` 的 entry 已包含 trace_id、question、question_type、candidate_agents、hit_exclusive_rules、router_method、llm_reason、llm_duration_ms、duration_ms、degradation、data_version、agent_version、result_version、failure_reason 等字段，但命名与 `routing_decision_log` 表结构未完全对齐（如 `duration_ms` vs `total_duration_ms`，缺少 `relevance`、`five_dim_context`、`logged_at`）。

## Goals / Non-Goals

**Goals:**

- 路由日志双写：JSONL 文件 + `routing_decision_log` 表，DB 失败回退 JSONL
- 排他规则动态加载：从 `exclusive_rule_config` 表加载，DB 不可用回退硬编码
- 混淆矩阵评估结果落库 `model_evaluation_metrics` 表
- entry 结构与 `routing_decision_log` 表字段对齐

**Non-Goals:**

- 不修改路由判定逻辑（`identify_question_type`、`apply_exclusive_rules` 的匹配算法不变）
- 不删除 JSONL 文件存储（作为降级备份保留）
- 不迁移历史 JSONL 数据到 DB
- 不修改 `routing-exclusive-rules` spec（五维路由特征判定逻辑不变）

## Decisions

### D1: 双写架构 — DB 优先，JSONL 兜底

**选择**: `_safe_write_log` 先写 DB，DB 失败时回退 JSONL；JSONL 始终写入（作为降级备份）

**理由**: DB 是主存储（支持结构化查询），JSONL 是降级备份。DB 失败时 JSONL 保证观测数据不丢失。双写而非单写 DB，因为 JSONL 已被看板和追溯链消费，移除会破坏现有功能。

**备选**: 仅写 DB（风险：DB 故障时观测数据丢失）；仅写 JSONL + 异步同步 DB（复杂度高，引入一致性问题）

### D2: DB 写入层封装位置 — routing_log.py

**选择**: 在 `routing_log.py` 新增 `write_routing_log_to_db(entry)` 函数，`write_routing_log` 调用 DB 写入后再写 JSONL

**理由**: `routing_log.py` 已是路由日志的单一写入入口，DB 写入层与 JSONL 写入共存于此模块，调用方（`observe.py`）无需感知存储细节

**备选**: 在 `observe.py` 的 `_safe_write_log` 中直接写 DB（违反单一职责，observe.py 应只负责观测编排）

### D3: 排他规则动态加载 — from_database() + 模块级缓存

**选择**: 在 `exclusive_rules.py` 新增 `from_database()` 类方法/函数，从 `exclusive_rule_config` 表加载规则到 `ExclusiveRule` 对象列表；模块级缓存避免每次路由判定查询 DB；`apply_exclusive_rules` 使用 `_get_active_rules()` 统一入口，优先 DB 规则，回退硬编码

**理由**: 排他规则在路由判定中被频繁调用，每次查询 DB 不可接受。模块级缓存 + 首次加载策略平衡性能与动态性。`_get_active_rules()` 统一入口使调用方无感知

**备选**: 每次路由判定查询 DB（性能差）；启动时全量加载不支持运行时更新（不灵活）

### D4: entry 字段对齐策略 — 补充缺失字段 + 重命名

**选择**: 在 `observe.py` 的 entry 中补充 `relevance`、`five_dim_context`、`logged_at` 字段，将 `duration_ms` 重命名为 `total_duration_ms`（保留 `duration_ms` 别名向后兼容）

**理由**: 与 `routing_decision_log` 表字段对齐是 DB 双写的前提。`five_dim_context` 从 `identify_question_type` 的上下文提取，`relevance` 已在 `identify_question_type` 返回值中但未记入 entry

**备选**: 在 DB 写入层做字段映射（分散逻辑，难以维护）

### D5: SQLAlchemy 模型位置 — framework/models/

**选择**: 新增 `framework/models/routing_observability.py`，定义 `RoutingDecisionLog`、`ModelEvaluationMetric`、`ExclusiveRuleConfig` 三个模型，注册到 `framework/models/__init__.py`

**理由**: 遵循现有模型组织（`soil_data.py`、`data_file.py` 等均按领域分文件），`db` 实例复用 `framework/models/user.py`

**备选**: 分散到各模块（违反模型集中管理约定）

### D6: 混淆矩阵落库时机 — 脚本执行后批量写入

**选择**: `run_routing_regression.py` 在所有易混淆对计算完成后，批量写入 `model_evaluation_metrics` 表

**理由**: 回归脚本是非频繁的离线任务，批量写入减少 DB 交互。DB 写入失败不改变脚本退出码（退出码反映混淆率目标达成，不反映 DB 写入）

**备选**: 每个易混淆对计算后立即写入（增加 DB 交互，无显著收益）

## Risks / Trade-offs

- [DB 写入延迟影响路由主流程] → `_safe_write_log` 已用 try/except 隔离，DB 写入异常不传播；可考虑异步写入但增加复杂度，当前同步写入可接受
- [双写数据一致性] → DB 和 JSONL 可能出现短暂不一致（DB 写入成功但 JSONL 失败，或反之）。以 DB 为主存储，JSONL 为降级备份，不一致时以 DB 为准
- [排他规则缓存过期] → 模块级缓存不自动刷新，规则更新需重启服务或手动调用刷新。可接受（规则变更频率低）
- [entry 字段重命名破坏现有消费者] → `duration_ms` → `total_duration_ms` 保留 `duration_ms` 别名，看板和追溯链不受影响
- [SQLite 并发写入限制] → 开发环境 SQLite 在高并发双写下可能锁定。生产环境 MySQL 无此问题；开发环境可接受偶发锁定（观测副作用，非主流程）

## Migration Plan

1. 新增 `framework/models/routing_observability.py`，定义三个 SQLAlchemy 模型
2. 更新 `framework/models/__init__.py` 注册新模型
3. 更新 `init_db.py` 确保 `db.create_all()` 包含新表
4. 更新 `framework/observability/routing_log.py`，新增 `write_routing_log_to_db` 和双写逻辑
5. 更新 `framework/observability/observe.py`，对齐 entry 字段结构
6. 更新 `framework/agents/exclusive_rules.py`，新增 `from_database()` 和 `_get_active_rules()`
7. 更新 `scripts/run_routing_regression.py`，增加评估结果落库
8. 运行 `init_db.py` 创建新表
9. 验证双写、降级、动态加载、评估落库功能
10. 回滚策略：删除新表、还原 4 个文件

## Open Questions

- `five_dim_context` 的具体提取来源：是从 `identify_question_type` 的 context 参数直接取，还是需要从 routing 模块的五维特征提取函数获取？当前 context 参数可能不含完整五维信息，需确认提取路径
