## 1. 框架搭建

- [ ] 1.1 创建统一框架目录结构（framework/）
- [ ] 1.2 更新 pyproject.toml 添加依赖（Flask、SQLAlchemy、ChromaDB、LangGraph 等）
- [ ] 1.3 创建统一配置管理模块

## 2. 核心服务实现

- [ ] 2.1 实现统一 LLM 服务（framework/llm/service.py）
- [ ] 2.2 实现统一 Embedding 服务（framework/embedding/service.py）
- [ ] 2.3 实现向量存储模块（framework/vector_store/chroma_store.py）
- [ ] 2.4 实现 RAG 问答链（framework/rag/chain.py）

## 3. 函数调用系统

- [ ] 3.1 实现工具注册表（framework/function_calling/registry.py）
- [ ] 3.2 实现 LangChain Tools 集成
- [ ] 3.3 实现自定义工具接口（JSON Schema）
- [ ] 3.4 实现工具调用执行器

## 4. 多智能体编排器

- [ ] 4.1 实现多智能体状态机定义（framework/agents/state.py）
- [ ] 4.2 实现并发模型执行节点（framework/agents/nodes.py）
- [ ] 4.3 实现多智能体编排器（framework/agents/orchestrator.py）
- [ ] 4.4 扩展支持六个专业模型的并发处理

## 5. 数据库模型迁移

- [ ] 5.1 创建数据库模型（framework/models/user.py、conversation.py、message.py、document.py）
- [ ] 5.2 配置 SQLAlchemy 数据库连接
- [ ] 5.3 创建数据库初始化脚本

## 6. 认证系统迁移

- [ ] 6.1 实现 JWT 认证模块（framework/auth/jwt.py）
- [ ] 6.2 实现密码哈希和验证
- [ ] 6.3 实现认证装饰器

## 7. 文件上传管理

- [ ] 7.1 实现文件上传模块（framework/upload/file_upload.py）
- [ ] 7.2 实现文档解析模块（PDF、Word、Excel）
- [ ] 7.3 实现文档管理 API

## 8. 专业模型迁移

- [ ] 8.1 迁移酸化评估模型（framework/domain/assessment/acidification.py）
- [ ] 8.2 迁移石灰需求量计算模型（framework/domain/calculation/lime_calculator.py）
- [ ] 8.3 迁移土壤数据加载模块（framework/domain/data/soil_data_loader.py）
- [ ] 8.4 迁移其他四个专业模型

## 9. HTTP API 合并

- [ ] 9.1 创建 Flask 应用（framework/api/app.py）
- [ ] 9.2 迁移 org-backend 的聊天 API（framework/api/routes/chat.py）
- [ ] 9.3 迁移原有的诊断/概览 API（framework/api/routes/county.py）
- [ ] 9.4 迁移认证 API（framework/api/routes/auth.py）
- [ ] 9.5 迁移文档管理 API（framework/api/routes/documents.py）

## 10. 集成测试

- [ ] 10.1 测试 RAG 问答功能
- [ ] 10.2 测试多智能体并发工作流
- [ ] 10.3 测试 Function Calling 功能
- [ ] 10.4 测试用户认证功能
- [ ] 10.5 测试文档上传和管理功能

## 11. 数据迁移

- [ ] 11.1 迁移 MySQL 数据库表结构和数据
- [ ] 11.2 迁移 Chroma 向量库数据