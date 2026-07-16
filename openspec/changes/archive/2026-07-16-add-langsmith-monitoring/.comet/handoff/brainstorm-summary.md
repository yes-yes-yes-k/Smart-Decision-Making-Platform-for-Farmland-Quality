# Brainstorm Summary

- Change: add-langsmith-monitoring
- Date: 2026-07-14

## 确认的技术方案

1. **代码改动（1 处）**：在 `start_http_server.py` 中添加 `load_dotenv()`（2 行），与生产环境 `start_production_server.py` 保持一致，使开发环境也能通过 `.env` 控制 LangSmith 开关。
2. **配置改动**：在 `deploy/production.env.example` 新增 LangSmith 配置段（`LANGCHAIN_TRACING_V2=true`、`LANGCHAIN_API_KEY`、`LANGCHAIN_ENDPOINT`、`LANGCHAIN_PROJECT=agent-culti-demo`）。
3. **文档更新**：`README.md` 配置章节新增 LangSmith 说明；`deploy/deployment.md` 新增配置步骤和故障排查。
4. **依赖**：无需新增，`pyproject.toml` 已有 `langchain ^0.2.0` 和 `python-dotenv ^1.0.0`。
5. **集成方式**：环境变量自动追踪（`LANGCHAIN_TRACING_V2=true`），零业务代码改动。

## 关键取舍与风险

- **取舍**：在 `start_http_server.py` 添加 `load_dotenv()` 是微小代码改动，但非业务代码——为保持开发/生产环境配置一致性而接受。
- **风险**：`load_dotenv()` 默认不覆盖已有系统环境变量，风险极低。
- **风险**：LangSmith 服务不可达时，langchain tracing 异步上报超时静默跳过，不影响主流程。
- **风险**：API Key 泄露——`.env` 已在 `.gitignore` 排除，`production.env.example` 仅占位符。

## 测试策略

- 运行现有 78 个测试确认不受影响
- 手动验证未设置 `LANGCHAIN_API_KEY` 时应用正常启动（graceful degradation）

## Spec Patch

无。open 阶段创建的 `specs/langsmith-monitoring/spec.md` 已覆盖全部验收场景。
