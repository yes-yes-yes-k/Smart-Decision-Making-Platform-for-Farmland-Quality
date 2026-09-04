# 聊天分析对象发布、迁移与回滚

本功能采用“先兼容数据结构，再启用执行守卫”的顺序。生产发布不得跳步。

## 发布顺序

1. 备份业务数据库，记录备份校验值，然后运行 `python scripts/migrate_analysis_context.py upgrade`。
2. 从已启用且精确的区域映射导入 `spatial_region_catalog`；禁止导入默认回退区域。
3. 回填已经人工或权威数据确认的 `parcel_info.legacy_parcel_code` 映射；不确定映射保持为空。
4. 部署支持新旧请求读取的应用版本，保持中央专业执行守卫关闭。
5. 数据抽查通过后启用中央守卫，使 Function Calling、关键词回退和 AgentManager 使用同一校验结果。
6. 观察 `needs_analysis_object`、`needs_scenario_inputs`、HTTP 422/409/503 和旧字段使用次数，并按对象类型、区域、模型、状态、日期核对执行统计。
7. 客户端切换到 `analysis_context` 的 `set/inherit/clear` 协议；旧字段使用量归零后再计划移除兼容读取。
8. 若需回滚，先关闭中央守卫，再执行下述带非空检查的 downgrade。

## 发布验证

- 对一个地块和一个县级对象分别验证 set、inherit、clear 与版本冲突。
- 验证 Model-4 scenario 缺参数返回 needs，参数完整时 provenance 标记 `scenario_result=true`。
- 对同一确定性请求比较 HTTP 与 SSE 的上下文、trace 和 provenance。
- 查询 dashboard，确认交互计数与 `model_execution_log` 分组结果一致；不要从执行日志推断业务面积或指标均值。

## 回滚保护

运行 downgrade 前必须确认不存在依赖新字段且无法恢复的数据，并导出
`kb_conversation.analysis_object`、`kb_message.analysis_context_snapshot` 和新增执行溯源列。
迁移脚本检测到非空数据时应停止；只有在备份已验证、中央守卫已关闭且客户端已恢复旧协议后，
才允许显式确认删除新增列/表。应用回滚失败时保留数据库升级状态，优先恢复兼容读取版本。
