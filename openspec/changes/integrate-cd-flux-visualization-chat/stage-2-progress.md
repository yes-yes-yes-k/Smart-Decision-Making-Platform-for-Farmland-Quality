# 第 2 阶段进展

2026-11-10 更新：第2阶段已完成，见 stage-2-verification.md。以下保留最初启动时的检查记录，后续完成情况以验收文档和tasks.md为准。

## 环境前置检查已通过

在项目根 `.venv` 安装 matplotlib3.11.2、rasterio1.5.2、seaborn0.13.2及其缺失依赖，满足 pyproject.toml 既有版本约束。pip卡顿调用栈位于缓存临时文件写入；使用 `--no-cache-dir` 和工作区 TEMP/TMP 解决，无需修改系统配置。

`python -m pip check`：No broken requirements found。

`python -m pytest tests/test_cd_flux.py tests/test_heavy_metal_cd_visualization.py tests/test_cd_conversation.py tests/test_cd_trial.py -q --tb=short`：31 passed in 9.07s。运行时 MPLCONFIGDIR 指向工作区 artifacts/matplotlib-config。第1阶段依赖阻断现已解除。

## 2.1 已完成的迁移准备

- 可执行SQL固定在 scripts/sql/cd_flux_v2.sql，与第1阶段评审DDL一致。
- scripts/migrate_cd_flux_v2.py：PostgreSQL15+，事务和咨询锁；默认演练回滚，显式 --apply 才持久化。旧表保持原样，新表保留年度未知、企业未知及legacy公式结果，容重原值放入未核验provenance，不伪装为明确单位。重复键/孤立输出会中止事务。
- 恢复开发库实际演练：rehearsal_rolled_back，源flux表不存在，复制0/0行，没有持久建表。
- PostgreSQL隔离schema测试2 passed：未知年度不可重复，不同年度共存；历史七项输入/输出复制且重跑无新增，原值不变，企业/年度/容重单位保持未知。fixture结束回滚并确认schema不存在。

复现：设置 CD_MIGRATION_TEST_DB=db_enterprise_qa_cd_20261103 和 CD_MIGRATION_ENV_FILE=<项目根>/.env，运行 `python -m pytest tests/test_cd_flux_v2_migration_pg.py -q --tb=short`。

## 启动时剩余事项（现已完成）

已有schema校验、失败恢复、备份和非破坏性回滚交付已完成；恢复库已两次apply并审计确认。2.2–2.6的数据服务及管理接口已实现并通过测试。真实业务年度和企业数据仍未提供，不与能力实现混淆。
