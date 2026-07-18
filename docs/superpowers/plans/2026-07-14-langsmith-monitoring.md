---
change: add-langsmith-monitoring
design-doc: docs/superpowers/specs/2026-07-14-langsmith-monitoring-design.md
base-ref: 35a0b535896eb864548ce08b866cee888951ed9f
archived-with: 2026-07-16-add-langsmith-monitoring
---

# 实施计划：LangSmith 监控智能体整体流程

## 概述

为项目多智能体流程添加 LangSmith 可观测性监控，通过环境变量自动追踪 LangGraph 编排图节点、专业智能体调用、LLM API 调用和 RAG 检索链。

参考设计：[docs/superpowers/specs/2026-07-14-langsmith-monitoring-design.md](../specs/2026-07-14-langsmith-monitoring-design.md)

## 任务列表

### 阶段 1：环境变量配置

#### 任务 1.1：添加 LangSmith 配置到生产环境模板

- **文件**：`deploy/production.env.example`
- **操作**：在文件末尾新增 LangSmith 配置段
- **内容**：
  ```ini
  # === LangSmith 监控（生产环境默认开启） ===
  LANGCHAIN_TRACING_V2=true
  LANGCHAIN_API_KEY=请替换为LangSmith API Key
  LANGCHAIN_ENDPOINT=https://api.smith.langchain.com
  LANGCHAIN_PROJECT=agent-culti-demo
  ```
- **验证**：文件包含 4 个 LangSmith 环境变量，每项有注释说明

#### 任务 1.2：确认 .gitignore 排除 .env

- **文件**：`.gitignore`
- **操作**：验证 `.env` 已在排除列表中
- **验证**：`grep '.env' .gitignore` 有匹配项

### 阶段 2：依赖确认

#### 任务 2.1：确认 langchain 版本支持 tracing

- **文件**：`pyproject.toml`
- **操作**：确认 `langchain ^0.2.0` 已在依赖中
- **验证**：`pyproject.toml` 包含 `langchain = "^0.2.0"`，无需新增依赖

### 阶段 3：代码改动

#### 任务 3.1：在 start_http_server.py 添加 load_dotenv()

- **文件**：`start_http_server.py`
- **操作**：在 `main()` 函数开头添加 `load_dotenv()` 调用
- **改动**：
  ```python
  def main(argv: list[str] | None = None) -> int:
      from dotenv import load_dotenv
      load_dotenv()

      parser = argparse.ArgumentParser(...)
  ```
- **验证**：应用启动时 `.env` 中的环境变量被加载

### 阶段 4：文档更新

#### 任务 4.1：README.md 添加 LangSmith 配置说明

- **文件**：`README.md`
- **操作**：在配置章节新增 LangSmith 环境变量说明
- **内容**：说明 4 个环境变量、开发环境默认关闭、生产环境默认开启
- **验证**：README 配置章节包含 LangSmith 说明

#### 任务 4.2：deployment.md 添加 LangSmith 配置和故障排查

- **文件**：`deploy/deployment.md`
- **操作**：新增 LangSmith 配置步骤和故障排查说明
- **内容**：如何在 .env 中配置、如何在 LangSmith 平台查看 trace、tracing 不生效的排查
- **验证**：deployment.md 包含 LangSmith 章节

### 阶段 5：验证

#### 任务 5.1：运行全部测试

- **操作**：`python -m pytest tests/ -q`
- **验证**：78 个测试全部通过，无回归

#### 任务 5.2：验证 graceful degradation

- **操作**：不设置 `LANGCHAIN_API_KEY`，启动应用
- **验证**：应用正常启动，无报错

## 执行顺序

按阶段顺序执行：1 → 2 → 3 → 4 → 5

## 风险

- 低风险：`load_dotenv()` 默认不覆盖已有系统环境变量
- 低风险：LangSmith tracing 异步上报，不影响主流程

