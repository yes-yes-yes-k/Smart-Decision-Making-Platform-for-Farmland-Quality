# 不可信降级指标退役 Runbook

适用变更：`retire-unverified-fallback-metrics`。执行日期与审批记录应使用实际维护窗口时间；本文命令示例基于 2026-09-05 的项目结构。

## 范围与边界

- PostgreSQL：只处理 `organic_matter_result` 中无法由 `model_execution_log` 证明为真实 RF/ETR 输出的活动定量字段。
- SQLite：只处理运维人员通过 `--sqlite` 明确指定的数据库，并归档、删除整个 `acidification_results` 表。
- 保留 `model_execution_log` 审计事实、`evaluation_results`、`diagnosis_results` 及真实模型记录。
- 不按数值大小或旧公式相似度猜测来源，不把旧值转换成新的真实预测。

## 1. 部署顺序

1. 先部署停止生成和消费旧数值的应用版本。
2. 确认 API 降级响应包含 `MODEL5_QUANTITATIVE_UNAVAILABLE`，报告显示“暂无可靠估计”。
3. 在维护窗口前运行 dry-run，保存 JSON 审计并完成人工审批。
4. 审批后执行 `--apply`，随后完成数据库与业务验证。

## 2. Dry-run

必须使用项目指定解释器，并显式给出每个目标；脚本不会搜索未知数据库。

```powershell
& 'C:\Users\PC\.conda\envs\agent_culti_demo_py312\python.exe' scripts\retire_unverified_fallback_metrics.py `
  --postgres-dsn 'postgresql://USER:PASSWORD@HOST:5432/DB' `
  --sqlite 'D:\explicit\farmland_diagnosis.db' `
  --archive-dir 'D:\restricted-backups\retire-unverified-fallback-metrics' `
  --audit-output 'D:\restricted-backups\retire-unverified-fallback-metrics\dry-run.json'
```

审批时检查：待退役数量、原因分布、来源不明数量、SQLite 表结构、记录总数、非空 `expected_effect` 数量、受保护表计数和计划备份位置。任何 Schema 不匹配必须先人工确认，不得直接 apply。

## 3. Apply

在已审批的相同参数后追加 `--apply`。脚本先创建备份并验证 SHA-256；备份或 Schema 校验失败时，在修改前中止。

```powershell
& 'C:\Users\PC\.conda\envs\agent_culti_demo_py312\python.exe' scripts\retire_unverified_fallback_metrics.py `
  --postgres-dsn 'postgresql://USER:PASSWORD@HOST:5432/DB' `
  --sqlite 'D:\explicit\farmland_diagnosis.db' `
  --archive-dir 'D:\restricted-backups\retire-unverified-fallback-metrics' `
  --audit-output 'D:\restricted-backups\retire-unverified-fallback-metrics\apply.json' `
  --apply
```

PostgreSQL 备份是候选结果行与关联执行输出的 JSON 导出；SQLite 同时保存完整数据库副本和 `acidification_results` 只读 JSON 归档。备份目录必须限制应用账户读取，并按组织数据保留策略设置到期时间。

## 4. 迁移后验证

1. 再次运行 dry-run，`retirement_candidates` 应为 `0`，SQLite `table_exists` 应为 `false`。
2. 查询真实 RF/ETR 样本，确认 Dose、置信度、模型版本和 `simulated=false` 保持不变。
3. 查询规则、模拟、来源不明和孤立样本，确认活动施用量、提升量及执行输出旧别名均为空。
4. 运行酸化按需计算与障碍诊断测试，确认 `evaluation_results`、`diagnosis_results` 记录数不变。
5. 生成 Model-5 报告，确认不可信历史值和所有 `potential_increase` 显示为“暂无可靠估计”。

## 5. 回滚

先停止新版本流量，再恢复与应用版本匹配的数据库备份。SQLite 使用校验通过的完整副本恢复；PostgreSQL 按审计 JSON 和组织数据库恢复流程恢复。禁止只回滚应用后静默重建 `acidification_results`，也不得把恢复的旧数值重新声明为可信业务事实。恢复后仍应在 API 和报告层隐藏这些值，直至完成重新验证。
