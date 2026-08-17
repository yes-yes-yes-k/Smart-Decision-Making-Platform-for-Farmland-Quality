## Purpose

为路由可观测性体系提供 DB 持久化能力：路由日志、混淆矩阵评估结果、排他规则配置从文件/硬编码存储迁移到数据库表，同时保留 JSONL 文件作为降级备份，确保观测副作用写入失败不影响路由主流程。

## ADDED Requirements

### Requirement: 路由日志 DB 双写

系统 SHALL 在每次路由判定时同时写入 JSONL 文件和 `routing_decision_log` 数据库表。DB 写入失败时 SHALL 回退至 JSONL 文件写入并发出告警，不得传播异常或掩盖路由结果。双写 entry 结构 SHALL 与 `routing_decision_log` 表字段对齐，包含 trace_id、question、question_type、relevance、routing_status、router_method、candidate_agents、hit_exclusive_rules、llm_reason、llm_duration_ms、total_duration_ms、degradation、five_dim_context、data_version、agent_version、result_version、failure_reason、logged_at。

#### Scenario: 正常双写路由日志

- **WHEN** 一次路由判定完成且数据库可用
- **THEN** 系统 SHALL 同时向 JSONL 文件和 `routing_decision_log` 表写入一条记录
- **AND** 两条记录的 trace_id、question_type、routing_status 等核心字段一致

#### Scenario: DB 写入失败回退 JSONL

- **WHEN** 路由判定完成但 `routing_decision_log` 表写入抛出异常
- **THEN** 系统 SHALL 回退至 JSONL 文件写入
- **AND** 系统 SHALL 发出告警提示 DB 写入失败
- **AND** 路由主流程 SHALL 不受影响，正常返回路由结果

#### Scenario: entry 字段与表结构对齐

- **WHEN** 系统构造路由日志 entry
- **THEN** entry SHALL 包含 `routing_decision_log` 表定义的全部业务字段
- **AND** router_method、llm_reason、llm_duration_ms、total_duration_ms、five_dim_context、relevance 字段 SHALL 被填充

### Requirement: 混淆矩阵评估结果落库

系统 SHALL 在路由回归脚本执行完成后，将混淆矩阵评估结果写入 `model_evaluation_metrics` 数据库表，包含 model_pair、positive_label、tp、fp、fn、tn、total、accuracy、confusion_rate、evaluation_mode、sample_count、evaluated_at 字段。

#### Scenario: 评估结果写入 DB

- **WHEN** 路由回归脚本完成一组易混淆对的混淆矩阵计算
- **THEN** 系统 SHALL 将该对的评估指标写入 `model_evaluation_metrics` 表
- **AND** 记录包含 model_pair、tp、fp、fn、tn、accuracy、confusion_rate、evaluation_mode、sample_count、evaluated_at

#### Scenario: DB 不可用时保留 JSON 文件输出

- **WHEN** 路由回归脚本完成但 `model_evaluation_metrics` 表写入失败
- **THEN** 系统 SHALL 保留原有 JSON 文件输出
- **AND** 系统 SHALL 发出告警提示 DB 写入失败
- **AND** 脚本退出码 SHALL 不因 DB 写入失败而改变

### Requirement: 排他规则动态加载

系统 SHALL 支持从 `exclusive_rule_config` 数据库表动态加载排他规则配置，包含 rule_name、rule_pair、discriminator、condition、target、dimension_conditions、enabled 字段。DB 不可用或表为空时 SHALL 回退至硬编码的 `EXCLUSIVE_RULES`。

#### Scenario: 从 DB 动态加载规则

- **WHEN** 系统初始化排他规则且 `exclusive_rule_config` 表可用且含已启用规则
- **THEN** 系统 SHALL 从 DB 加载 enabled=true 的规则
- **AND** 加载的规则 SHALL 与硬编码规则结构兼容，支持 pair、discriminator、condition、target、dimension_conditions 字段

#### Scenario: DB 不可用回退硬编码

- **WHEN** `exclusive_rule_config` 表不可用或查询失败
- **THEN** 系统 SHALL 回退至硬编码的 `EXCLUSIVE_RULES`
- **AND** 系统 SHALL 发出告警提示规则降级
- **AND** 路由判定行为 SHALL 与硬编码模式一致

#### Scenario: DB 规则为空回退硬编码

- **WHEN** `exclusive_rule_config` 表可用但无 enabled=true 的规则
- **THEN** 系统 SHALL 回退至硬编码的 `EXCLUSIVE_RULES`
- **AND** 系统 SHALL 发出告警提示无可用 DB 规则
