## Why

当前路由可观测性体系依赖文件存储：路由日志写入 JSONL 文件（`logs/routing_calls_YYYYMMDD.jsonl`），排他规则硬编码在 `framework/agents/exclusive_rules.py` 的 Python 元组中，混淆矩阵评估结果输出为 JSON 文件（`logs/confusion_matrix.json`）。这种存储方式无法支持结构化查询、跨时间维度聚合分析、动态配置管理和多实例并发写入。

数据库设计 V2.0 已定义 `routing_decision_log`、`model_evaluation_metrics`、`exclusive_rule_config` 三张表，需将上述存储迁移到 DB，同时保留 JSONL 作为降级备份，确保观测副作用的写入失败不影响路由主流程。

## What Changes

- `observe.py` 的 `_safe_write_log` 增加双写逻辑：同时写入 JSONL 文件和 `routing_decision_log` 表，DB 写入失败时回退 JSONL 并告警
- `routing_log.py` 增加 DB 写入层（`write_routing_log_to_db`），封装 SQLAlchemy session 写入，DB 不可用时回退 JSONL
- `exclusive_rules.py` 增加 `from_database()` 加载方法，从 `exclusive_rule_config` 表动态加载规则；DB 不可用时回退硬编码 `EXCLUSIVE_RULES`
- `run_routing_regression.py` 增加评估结果写入 `model_evaluation_metrics` 表（model_pair, tp, fp, fn, tn, accuracy, confusion_rate 等字段）
- `observe.py` 的 entry 结构与 `routing_decision_log` 表字段对齐：补充 `router_method`、`llm_reason`、`llm_duration_ms`、`total_duration_ms`、`five_dim_context`、`relevance`、`logged_at` 等字段，统一命名

## Capabilities

### New Capabilities

- `routing-log-persistence`: 路由日志 DB 持久化能力，定义双写策略、降级回退和字段对齐要求

### Modified Capabilities

- `routing-observability`: 观测字段对齐 `routing_decision_log` 表结构，混淆矩阵评估结果落库 `model_evaluation_metrics`
- `role-based-routing`: 排他规则支持从 `exclusive_rule_config` 表动态加载，DB 不可用时回退硬编码规则

## Impact

- `framework/observability/observe.py`：entry 结构调整、双写逻辑接入
- `framework/observability/routing_log.py`：新增 DB 写入层
- `framework/agents/exclusive_rules.py`：新增 `from_database()` 动态加载
- `scripts/run_routing_regression.py`：评估结果落库
- 新增 SQLAlchemy 模型：`routing_decision_log`、`model_evaluation_metrics`、`exclusive_rule_config`（注册到 `framework/models/`）
- 依赖：复用现有 `framework/models/user.py` 的 `db` 实例和 SQLAlchemy ORM 基础设施
