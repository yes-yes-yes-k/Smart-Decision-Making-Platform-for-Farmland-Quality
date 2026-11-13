# 阶段 4 验收记录

| 任务 | 验收场景 |
| --- | --- |
| 4.1 | 同名乡镇返回候选，预测查询要求指定模型；区域层级、预测时间限制、来源拆分、土壤加权和预测分布口径由 Cd 与既有土壤统计测试覆盖 |
| 4.2 | 必需输入和单位校验、显式接受训练集中位数后的降级计算、跨消息补参、年度切换和较早响应晚到 |
| 4.3 | 越权保存拒绝，失败写入回滚后可重试，重复及并发请求收敛为同一记录，重新计算的结果生成独立记录 |
| 4.4 | 使用 Flask 测试客户端验证普通聊天及 SSE。替身只负责解析语言模型意图和提供指定地块服务数据，预测计算、会话快照、序列化与保存均执行实际代码 |
| 4.5 | 运行分析上下文、Cd 模型和数据服务、土壤统计 API 与工具调用回归 |
| 4.6 | 更新 API 契约并运行 OpenSpec 严格校验 |

真实恢复库的区域预测和参数快照核验见 [阶段 1 与阶段 2 核验记录](stage-1-verification.md)。试算表迁移与回滚见 [阶段 3 验收记录](stage-3-verification.md)。聊天验收使用确定性语言模型替身，未调用在线语言模型。

回归结果为 227 项通过。普通聊天与 SSE 均通过缺参、显式接受默认值、实际降级预测和重复保存场景。

```powershell
& .venv/Scripts/python.exe -m pytest tests/analysis_context tests/test_cd_conversation.py tests/test_cd_trial.py tests/test_heavy_metal_cd.py tests/test_heavy_metal_cd_db.py tests/test_heavy_metal_cd_statistics.py tests/test_heavy_metal_cd_spatial.py tests/test_heavy_metal_cd_ported.py tests/test_farmland_statistics_service.py tests/test_farmland_statistics_api.py tests/test_specialized_tools.py -q --tb=short
openspec validate add-cd-conversation-capabilities --strict
git diff --check
```
