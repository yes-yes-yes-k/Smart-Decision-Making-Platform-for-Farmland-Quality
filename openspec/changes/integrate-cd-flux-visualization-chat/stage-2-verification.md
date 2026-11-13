# 第2阶段验收

2026-11-10：实现范围为数据服务和管理入口；对话/附件未接入。

## 2.1 迁移与持久化

- v2并行表、年度来源键、企业空值、输入revision和输出公式版本已实现。
- 迁移前备份：artifacts/cd-chat-stage2/pre-v2-20261110.dump，92344036字节，SHA256 `5c61f9f06a516db227e7c099874360bf200dc76f7d1314a06c0910c35399f840`，pg_restore --list通过。没有执行整库灾难恢复。
- 恢复开发库db_enterprise_qa_cd_20261103：两次--apply均成功，复制0/0行。post-migration.json确认两张v2表存在且0行；原legacy flux表仍不存在。其他表未写入。
- PostgreSQL隔离schema测试验证未知年度唯一性、多个年度共存、重复迁移、历史值保留、失败后回滚恢复；测试schema结束即回滚并确认不存在。
- 回滚采用关闭v2入口、保留新数据，管理API测试确认已有年度数据未丢失。无破坏性降级。

## 2.2–2.5 实现

- 新版/legacy CSV管理入口分开，整批校验、批内重复拒绝、企业缺失不填0；重导递增revision，使旧结果退出当前查询。
- 全域独立source过滤；v2来源显式记录，unknown单列；旧接口修复全域过滤。移植映射按启用行政父链上推，检查父类型、缺失与循环，统计返回未映射记录数。支持parcel_id。
- 年度筛选、分年分来源统计与对比，未知年度不进入指定年；返回覆盖差异而非直接断言改善。legacy公式版本不混入新版。
- 无写库纯计算核验证明：八项20/10/10、600g/ha初始储量得0.2346153846mg/kg；0.3mg/kg初始浓度转换780g/ha得0.3038461538mg/kg。企业未知只返回已知小计，明确0可计算。默认须明确接受，初始浓度/储量与单位冲突拒绝。
- JWT管理接口覆盖导入/核算/结果/统计/对比。旧入口补充legacy版本标记；新工具未进入对话白名单。

## 2.6 验证与限制

测试命令（项目根虚拟环境，CD_MIGRATION_TEST_DB指向恢复库，CD_MIGRATION_ENV_FILE指向根.env）：

```text
python -m pytest tests/test_cd_flux_v2.py tests/test_cd_flux_v2_migration_pg.py tests/test_cd_flux.py tests/test_heavy_metal_cd_visualization.py tests/test_cd_conversation.py tests/test_cd_trial.py -q --tb=short
python -m pytest tests/test_heavy_metal_cd_spatial.py tests/test_heavy_metal_cd_statistics.py tests/test_heavy_metal_cd_ported.py -q --tb=short
```

第一组45项、第二组48项通过。新计算、HTTP管理契约和迁移测试使用有明确预期的隔离数据，并在完成后回滚，非真实年度/企业业务覆盖证明。业务v2表仍空；真实年度、企业通量供给及历史单位依据仍未知。阶段3–5保持未完成。

运行配置、CSV、回滚命令及限制见docs/cd-flux-v2-api-and-migration.md。本阶段能力交付通过，不代表真实数据已补齐或自然语言对话已上线。
