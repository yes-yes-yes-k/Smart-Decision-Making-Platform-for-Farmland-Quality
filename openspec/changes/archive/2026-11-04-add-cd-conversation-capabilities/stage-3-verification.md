# 阶段 3 多轮草稿与试算保存

地块、地区、年份或模型变化时，上一组参数退出当前草稿。已验证地块会按新时期读取可映射的参数，自动填入有实测来源、单位明确且与请求时期相容的值。插补、默认值、未知来源和单位待核验的字段保留为缺项。行政区汇总参数目前返回层级不支持。

普通聊天和 SSE 可通过「保存这次试算结果」保存当前已完成试算。保存记录含地区、年份、完整参数及其单位和来源、资产校验和与预测输出。服务端根据已认证用户、会话和助手消息重新读取试算，数据库以会话及结果版本唯一约束处理重复保存。未完成草稿无可保存结果。会话删除时其试算记录随之删除。

## 数据库迁移

在目标开发环境运行以下 PowerShell 命令。这里使用独立恢复库完成建表、空表回滚和重新建表验证。

```powershell
$env:DB_NAME = 'db_enterprise_qa_cd_20261103'
& .venv/Scripts/python.exe scripts/migrate_add_cd_trial_table.py
& .venv/Scripts/python.exe scripts/migrate_add_cd_trial_table.py --drop
& .venv/Scripts/python.exe scripts/migrate_add_cd_trial_table.py
```

迁移仅创建 `cd_conversation_trial`。应用回滚时可保留该表。数据库回滚命令仅删除空表，已有记录时会拒绝执行，需先导出并保留记录。测试覆盖年份切换后重新补参、归属校验、重复保存、新结果保存以及并发保存同一结果。
