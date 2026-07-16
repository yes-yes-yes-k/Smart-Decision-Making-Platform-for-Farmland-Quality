---
comet_change: add-langsmith-monitoring
role: technical-design
canonical_spec: openspec
---

# Design Doc: LangSmith 监控智能体整体流程

## 1. 背景与目标

### 背景

项目多智能体流程基于 LangGraph StateGraph 构建，编排路径为 `initialize → identify_question → (rag_chat | execute_models → llm_generate) → aggregate_results → finalize`。6 个专业智能体通过 AgentManager 管理，LLM 调用通过 SiliconFlow API，RAG 检索基于 ChromaDB。

当前缺少可观测性手段：当智能体调用失败、LLM 响应异常或检索质量下降时，只能通过应用日志排查，无法可视化全链路执行轨迹。

### 目标

通过 LangSmith 环境变量自动追踪方式，覆盖 4 个环节：LangGraph 编排图节点、专业智能体调用、LLM API 调用、RAG 检索链。零业务代码改动，未配置 API Key 时静默关闭。

### 非目标

- 不添加 `@traceable` 装饰器或自定义 Callbacks
- 不在 `framework/config.py` 中新增 LangSmith 配置类
- 不实现 LangSmith 的 evaluation 或 dataset 功能

## 2. 技术方案

### 2.1 集成机制

LangChain ≥ 0.2 的 `langchain-core` 内置 tracing v2 机制。设置环境变量 `LANGCHAIN_TRACING_V2=true` 后，LangChain 自动拦截以下调用并上报 LangSmith：

| 追踪环节 | 自动拦截点 | Trace 内容 |
|---------|-----------|-----------|
| LangGraph 编排图节点 | `StateGraph.invoke()` | 节点执行顺序、耗时、状态变更 |
| 专业智能体调用 | AgentManager 内部的 LLM/工具调用 | 智能体名称、输入输出、耗时 |
| LLM API 调用 | `ChatOpenAI.invoke()` | token 用量、模型名称、延迟、响应 |
| RAG 检索链 | `ChromaDB.similarity_search()` | 查询文本、召回文档数、检索耗时 |

无需修改 `framework/agents/`、`framework/rag/`、`framework/llm/` 中任何业务代码。

### 2.2 环境变量配置

通过 `.env` 文件管理，与现有配置体系一致：

| 环境变量 | 作用 | 默认值 |
|---------|------|--------|
| `LANGCHAIN_TRACING_V2` | tracing 开关（`true` 启用） | 未设置（关闭） |
| `LANGCHAIN_API_KEY` | LangSmith API Key | 未设置（静默关闭） |
| `LANGCHAIN_ENDPOINT` | LangSmith API 端点 | `https://api.smith.langchain.com` |
| `LANGCHAIN_PROJECT` | LangSmith 项目名称 | `agent-culti-demo` |

**环境约定**：
- 开发环境：`.env` 不设置 `LANGCHAIN_TRACING_V2`（默认关闭，避免噪音）
- 生产环境：`deploy/production.env.example` 设置 `LANGCHAIN_TRACING_V2=true`

### 2.3 开发环境 .env 加载

**问题**：`start_http_server.py`（开发环境启动入口）没有 `load_dotenv()` 调用，`.env` 文件中的环境变量不会被加载。

**解决方案**：在 `start_http_server.py` 的 `main()` 函数开头添加 `load_dotenv()`，与 `start_production_server.py` 保持一致。

```python
# start_http_server.py main() 开头
def main(argv: list[str] | None = None) -> int:
    from dotenv import load_dotenv
    load_dotenv()

    parser = argparse.ArgumentParser(...)
```

`load_dotenv()` 默认不覆盖已有系统环境变量，风险极低。

### 2.4 Graceful Degradation

LangChain tracing 机制在以下情况自动降级，不影响主流程：

1. **未设置 `LANGCHAIN_API_KEY`**：tracing 不初始化，无任何上报请求
2. **`LANGCHAIN_TRACING_V2` 非 `true`**：tracing 不启用
3. **LangSmith 服务不可达**：tracing 异步上报超时后静默跳过，不抛出异常

### 2.5 依赖确认

`pyproject.toml` 已有的依赖完全满足需求：

| 依赖 | 版本要求 | 用途 |
|------|---------|------|
| `langchain` | `^0.2.0` | 内置 LangSmith tracing v2 支持 |
| `python-dotenv` | `^1.0.0` | `.env` 文件加载 |

无需新增任何依赖。

## 3. 实现任务

| 编号 | 任务 | 文件 | 改动类型 |
|------|------|------|---------|
| 1.1 | 添加 LangSmith 配置项 | `deploy/production.env.example` | 新增配置段 |
| 1.2 | 确认 .gitignore 排除 .env | `.gitignore` | 验证（可能无改动） |
| 2.1 | 确认 langchain 版本支持 tracing | `pyproject.toml` | 验证（无改动） |
| 3.1 | 添加 LangSmith 配置说明 | `README.md` | 文档更新 |
| 3.2 | 添加 LangSmith 配置和故障排查 | `deploy/deployment.md` | 文档更新 |
| 3.3 | 添加 load_dotenv() | `start_http_server.py` | 2 行代码 |
| 4.1 | 运行全部测试 | - | 验证 |
| 4.2 | 验证 graceful degradation | - | 手动验证 |

## 4. 测试策略

### 4.1 自动化测试

运行现有 78 个测试（`python -m pytest tests/ -q`），确认：
- 所有测试通过
- 未因 `load_dotenv()` 引入副作用

### 4.2 手动验证

| 场景 | 验证方法 | 预期结果 |
|------|---------|---------|
| 未设置 API Key | 不设置 `.env` 启动应用 | 正常启动，无报错 |
| 开发环境默认关闭 | `.env` 不设置 `LANGCHAIN_TRACING_V2` | tracing 不生效 |
| 生产环境开启 | `.env` 设置 `LANGCHAIN_TRACING_V2=true` + `LANGCHAIN_API_KEY` | trace 在 LangSmith 可见 |

## 5. 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| `load_dotenv()` 加载未预期变量 | 低 | 默认不覆盖已有系统环境变量 |
| LangSmith 服务不可达 | 低 | 异步上报超时静默跳过 |
| API Key 泄露 | 中 | `.env` 在 `.gitignore` 排除，模板仅占位符 |
| trace 数据量超限 | 低 | 可通过 `LANGCHAIN_TRACING_SAMPLING_RATE` 控制采样率 |

## 6. 边界条件

- **LangGraph 节点异常**：tracing 记录异常节点和错误信息，不影响异常处理流程
- **LLM 调用超时**：tracing 记录超时事件，不影响重试逻辑
- **RAG 检索为空**：tracing 记录零召回结果，不影响后续 LLM 生成
- **并发请求**：LangSmith tracing 支持并发，每个请求独立 trace
