# 单地块综合诊断发布与回滚

1. 先完成分析对象计划并运行完整验证。
2. 安装锁定依赖，设置 `LANGGRAPH_STRICT_MSGPACK=true`。
3. 运行 `python scripts/setup_langgraph_checkpoint.py` 创建持久化表。
4. 以 `COMPREHENSIVE_WORKFLOW_MODE=off` 部署。
5. 切换为 `shadow`，观察意图与计划差异；影子模式不执行专业模型。
6. 配置内部 `COMPREHENSIVE_ALLOWED_USER_IDS` 后切换为 `enabled`。
7. 逐步放量，监控失败率、重试、降级和 P95，再默认启用。
8. 回滚时切回 `off` 并重启进程。不要删除 checkpoint 表，原快路径持续可用。

综合任务仅支持空间模式下已验证的单一地块。model-2、model-3 为核心任务；model-1、model-4、model-5 按条件执行；model-6 不参与综合任务。恢复请求必须携带原 `run_id` 与预期 checkpoint 版本。
