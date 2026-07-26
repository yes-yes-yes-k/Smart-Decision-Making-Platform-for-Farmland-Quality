## Why

一次多智能体聊天请求会让每个专业智能体分别执行检索和 LLM 调用。多个调用按依赖顺序串行执行时，单次上游超时或客户端重试会被放大为数分钟等待，尽管专业模型本身已能生成可用的规则结果。

## What Changes

- 多智能体路线中的专业智能体默认只生成领域规则和计算结果，不再逐个调用 RAG 与 LLM。
- 所有多智能体路线在专业结果生成后，仅调用一次 LLM 进行统一中文整合与润色。
- LLM 失败或超时时保留专业智能体汇总结果，不以失败文本覆盖已有答案。
- 新增单次 LLM 调用超时、重试次数配置和调用耗时日志。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `unified-llm-service`: 支持通过环境变量控制单次调用超时与重试次数，并记录调用耗时。
- `multi-agent-orchestrator`: 多智能体路线只进行一次最终 LLM 总结，并在 LLM 失败时保留专业结果。

## Impact

- **代码**：`framework/agents/base.py`、`framework/agents/nodes.py`、`framework/llm/service.py`、`framework/config.py`。
- **配置**：新增 `SILICONFLOW_LLM_TIMEOUT` 和 `SILICONFLOW_LLM_MAX_RETRIES`。
- **运行时**：多智能体请求由多个串行 LLM 调用收敛为一次；纯 RAG 路线维持原有调用方式。
- **测试**：新增 LLM 编排与降级回归测试。
