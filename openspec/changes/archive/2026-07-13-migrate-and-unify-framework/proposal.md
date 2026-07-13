## Why

当前存在两个独立的项目（AI_culti_demo 和 org-backend），各自拥有独立的 LLM 服务、嵌入模型、向量存储和工作流编排能力，导致代码重复、维护成本高、功能难以协同。需要将这两个项目的核心能力迁移到统一框架中，整合 RAG、Function Calling 和多智能体架构，支持六个专业模型的并发处理，提升系统整体效率和可扩展性。

## What Changes

- 迁移 `AI_culti_demo -send` 的 LangGraph 多智能体工作流、LLM 服务、嵌入服务、专业评估模型到统一框架
- 迁移 `org-backend` 的 RAG 问答链、Chroma 向量存储、数据库模型、JWT 认证、文件上传和文档管理到统一框架
- 开发统一的框架架构，整合 RAG、Function Calling 和多智能体组件
- 支持六个专业模型的并发处理能力
- 统一嵌入模型配置，支持多种模型切换
- 合并 HTTP 服务，提供统一的 API 接口

## Capabilities

### New Capabilities

- `unified-llm-service`: 统一的 LLM 服务封装，支持多种模型和配置
- `unified-embedding-service`: 统一的嵌入服务，支持多种嵌入模型切换
- `vector-store`: 内置 Chroma 向量存储，支持文档向量化和语义检索
- `rag-chain`: RAG 问答链，整合检索与生成
- `multi-agent-orchestrator`: 多智能体编排器，支持六个专业模型并发处理
- `function-calling-system`: 函数调用系统，混合使用 LangChain Tools 和自定义接口
- `database-models`: 数据库模型，包含用户、对话、消息、文档等
- `jwt-authentication`: JWT 认证系统
- `file-upload-management`: 文件上传和文档管理

### Modified Capabilities

- `callable-thematic-model-stubs`: 扩展支持六个专业模型的并发调用接口
- `county-smart-diagnosis`: 集成多智能体工作流，支持并发模型调用

## Impact

- 代码结构重构：新增 `framework/` 目录作为统一框架核心
- API 接口变更：合并原有 HTTP 服务，提供统一 API
- 依赖更新：整合两个项目的依赖，移除重复包
- 数据迁移：需要迁移 org-backend 的数据库表结构和向量库数据
- 配置统一：整合配置管理，支持环境变量和配置文件