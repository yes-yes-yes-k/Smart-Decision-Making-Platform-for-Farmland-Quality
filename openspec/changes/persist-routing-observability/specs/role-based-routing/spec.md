## ADDED Requirements

### Requirement: 排他规则动态加载

系统 SHALL 支持从 `exclusive_rule_config` 数据库表动态加载排他规则配置，包含 rule_name、rule_pair、discriminator、condition、target、dimension_conditions、enabled 字段。DB 不可用或表为空时 SHALL 回退至硬编码的 `EXCLUSIVE_RULES`，确保路由判定行为不中断。动态加载的规则 SHALL 与硬编码规则结构兼容，支持 pair（FrozenSet）、discriminator、condition、target、dimension_conditions 字段。

#### Scenario: 从 DB 动态加载规则

- **WHEN** 系统初始化排他规则且 `exclusive_rule_config` 表可用且含 enabled=true 的规则
- **THEN** 系统 SHALL 从 DB 加载 enabled=true 的规则
- **AND** 加载的规则 SHALL 与硬编码 `EXCLUSIVE_RULES` 结构兼容
- **AND** `apply_exclusive_rules` SHALL 使用动态加载的规则进行判定

#### Scenario: DB 不可用回退硬编码

- **WHEN** `exclusive_rule_config` 表不可用或查询失败
- **THEN** 系统 SHALL 回退至硬编码的 `EXCLUSIVE_RULES`
- **AND** 系统 SHALL 发出告警提示规则降级
- **AND** 路由判定行为 SHALL 与硬编码模式一致

#### Scenario: DB 规则为空回退硬编码

- **WHEN** `exclusive_rule_config` 表可用但无 enabled=true 的规则
- **THEN** 系统 SHALL 回退至硬编码的 `EXCLUSIVE_RULES`
- **AND** 系统 SHALL 发出告警提示无可用 DB 规则

#### Scenario: 动态规则不影响路由判定逻辑

- **WHEN** 使用 DB 加载的规则进行排他规则判定
- **THEN** 匹配算法 SHALL 保持 AND 逻辑（condition 与 dimension_conditions 同时满足）
- **AND** 优先级冲突时 SHALL 返回 boundary_pending
- **AND** 路由判定结果 SHALL 与等价硬编码规则一致
