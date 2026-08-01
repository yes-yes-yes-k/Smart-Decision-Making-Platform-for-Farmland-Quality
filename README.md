# 耕地土壤酸化治理智能问答系统

集成 RAG、Function Calling 和多智能体架构的统一能力底座，面向耕地质量管理场景沉淀数据整合、专业诊断、方案生成与 Agent 编排能力。

## 功能特性

- **统一框架**：Flask + SQLAlchemy + JWT + ChromaDB + LangChain + LangGraph
- **核心引擎**：县域概览、结构化诊断、7 个正式专业模型与 3 个辅助/实验性能力、报告汇总（`src/ai_culti_demo`）
- **多智能体编排**：7 个专业智能体 + AgentManager + QuestionTypeRouter（基于 question_type 1:1 映射）
  - model-1 稳定性风险识别 / model-2 潜力评估 / model-3 问题识别
  - model-4 酸化改良 / model-5 有机质培肥 / model-6 肥力 SOC/Dose 预测（ML）
  - model-7 耕地质量等级评价（Fortran exe）
- **RAG 知识检索**：基于 ChromaDB 的向量检索与 SiliconFlow LLM 问答，知识性问题自动路由到 RAG
- **Function Calling**：工具注册表 + LangChain Tools 集成 + 自定义工具接口
- **JWT 认证**：用户体系、会话管理、权限装饰器
- **文档管理**：PDF / Word / Excel 解析、向量化入库、检索引用
- **15 个 REST API**：认证、聊天、模型调用、文档、县域、报告、数据导入

## 技术栈

| 层级 | 组件 |
|------|------|
| Web 框架 | Flask 3.0 + Flask-CORS + Flask-JWT-Extended |
| ORM | Flask-SQLAlchemy |
| 数据库 | SQLite（开发与生产环境均使用） |
| 向量库 | ChromaDB 0.5 |
| LLM | SiliconFlow（DeepSeek-V4-Flash / BAAI/bge-m3） |
| 编排 | LangChain 0.2 + LangGraph 0.1 |
| 文档解析 | PyPDF2 / python-docx / openpyxl |
| 生产服务器 | waitress |

## 快速开始

### 环境要求

- Python ≥ 3.10
- Node.js（可选，用于 OpenSpec / Comet 工作流）

### 安装

```bash
# 克隆仓库
git clone http://139.9.51.218:3000/Ding/agent_culti_demo.git
cd agent_culti_demo

# 安装依赖
pip install -e .
```

### 配置

环境变量（可选，均有默认值）：

```bash
# LLM 与 Embedding
SILICONFLOW_API_KEY=your-key-here
SILICONFLOW_CHAT_MODEL=deepseek-ai/DeepSeek-V4-Flash
SILICONFLOW_EMBED_MODEL=BAAI/bge-m3

# 向量库
CHROMA_PERSIST_DIR=./chroma_db
CHROMA_COLLECTION_NAME=enterprise_kb
```

开发与生产环境均使用 SQLite，无需额外配置数据库服务。数据库文件：
- 开发环境：`instance/development.db`
- 生产环境：`instance/production.db`

### LangSmith 监控（可选）

通过 LangSmith 追踪多智能体全链路执行（LangGraph 节点、智能体调用、LLM 调用、RAG 检索）：

```bash
# .env 中配置（生产环境默认开启，开发环境默认关闭）
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=your-langsmith-api-key
LANGCHAIN_ENDPOINT=https://api.smith.langchain.com
LANGCHAIN_PROJECT=agent-culti-demo
```

- 未设置 `LANGCHAIN_API_KEY` 时 tracing 静默关闭，不影响系统运行
- 开发环境不设置 `LANGCHAIN_TRACING_V2` 即可关闭 tracing
- 配置后在 [LangSmith 平台](https://smith.langchain.com)查看完整 trace

### 初始化数据库

```bash
python init_db.py
```

创建表结构并写入默认账号：
- 管理员：`admin` / `admin123`
- 普通用户：`user` / `user123`

### 启动服务

**开发环境：**

```bash
python start_http_server.py
# 或指定参数
python start_http_server.py --host 0.0.0.0 --port 5000 --config development
```

服务启动后访问 http://localhost:5000

**生产环境：**

```bash
python start_production_server.py
# 或指定参数
python start_production_server.py --host 127.0.0.1 --port 8000 --threads 8
```

生产环境部署详见 [deploy/deployment.md](deploy/deployment.md)，支持 Windows 服务注册、日志管理、配置校验等。

## API 概览

所有 API 需通过 JWT 认证（`Authorization: Bearer <token>`）。

### 认证

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/auth/login` | 登录获取 Token |
| POST | `/api/v1/auth/register` | 注册新用户 |
| GET | `/api/v1/auth/me` | 获取当前用户信息 |

### 聊天与对话

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/chat/` | 智能问答（RAG + 多智能体编排） |
| GET | `/api/v1/chat/conversations` | 会话列表 |
| GET | `/api/v1/chat/conversations/{id}` | 会话详情 |
| GET | `/api/v1/chat/conversations/{id}/messages` | 会话消息列表 |

### 模型调用

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/models/` | 可用模型列表 |
| POST | `/api/v1/models/run` | 执行指定模型 |

### 文档管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/docs/` | 文档列表 |
| POST | `/api/v1/docs/upload` | 上传文档（PDF/Word/Excel） |
| DELETE | `/api/v1/docs/{id}` | 删除文档 |

### 县域能力

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/county/overview` | 县域耕地质量总览 |
| POST | `/api/v1/county/diagnose` | 结构化诊断 |
| POST | `/api/v1/report/summary` | 报告汇总 |

### 数据导入

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/data/import` | 上传部署专题模型数据（CSV/shapefile/.dat，需 admin） |

完整 OpenAPI 规范见 [docs/openapi.json](docs/openapi.json)，可导入 Apifox 等工具查看。

## 目录结构

```
agent_culti_demo/
├── src/ai_culti_demo/          # 核心引擎（县域概览/诊断/专题模型/报告）
│   ├── overview.py             #   县域总览
│   ├── diagnosis.py            #   结构化诊断
│   ├── thematic_models.py      #   正式专业模型与辅助/实验性能力入口
│   ├── report.py               #   报告汇总
│   └── catalog.py              #   数据目录加载
├── framework/                  # 统一框架
│   ├── api/                    #   Flask 应用与路由
│   │   ├── app.py              #     应用工厂
│   │   └── routes/             #     auth/chat/models/docs/county/report
│   ├── agents/                 #   多智能体编排
│   │   ├── base.py             #     智能体基类
│   │   ├── manager.py          #     AgentManager
│   │   ├── router.py           #     QuestionTypeRouter 问题类型路由（1:1 映射）
│   │   ├── orchestrator.py     #     LangGraph 编排器
│   │   └── specialized/        #     7 个专业智能体实现
│   ├── auth/                   #   JWT 认证与权限装饰器
│   ├── core_engine/            #   核心引擎适配器
│   │   └── adapter.py          #     桥接 src/ai_culti_demo
│   ├── domain/                 #   专业模型实现
│   ├── embedding/              #   统一 Embedding 服务
│   ├── function_calling/       #   函数调用系统
│   ├── llm/                    #   统一 LLM 服务
│   ├── models/                 #   数据库模型（user/conversation/message/document）
│   ├── rag/                    #   RAG 问答链
│   ├── upload/                 #   文件上传与解析
│   ├── vector_store/           #   ChromaDB 向量存储
│   └── config.py               #   配置管理
├── data/lechang/               # 乐昌市样例数据
│   └── catalog.json            #   数据资产目录
├── deploy/                     # 生产部署
│   ├── deployment.md           #   部署指南
│   ├── production.env.example  #   环境变量模板
│   └── windows-service.ps1     #   Windows 服务管理脚本
├── docs/                       # 文档
│   ├── openapi.json            #   OpenAPI 3.0 规范
│   └── superpowers/            #   设计文档与验证报告
├── tests/                      # 测试套件（78 个测试）
├── openspec/                   # OpenSpec 规范与变更归档
├── init_db.py                  # 数据库初始化
├── start_http_server.py        # 开发环境启动入口
├── start_production_server.py  # 生产环境启动入口
└── pyproject.toml              # 项目配置
```

## 测试

```bash
# 运行全部测试
python -m pytest tests/ -q

# 运行指定模块测试
python -m pytest tests/test_multi_agent.py -q
python -m pytest tests/test_rag.py -q
```

当前测试覆盖：认证、多智能体、RAG、Function Calling、专题模型、文档上传、接口契约。

## 多智能体架构

```
用户请求
   ↓
identify_question_type（问题类型识别）
   ├─ 知识性问题预检（"什么是X"等） → type 0
   ├─ 关键词匹配 → type 1-7
   └─ 向量降级匹配 → type 1-7/0
   ↓
route_models（路由分发）
   ├─ type 0 → RAG 链（知识库问答）
   └─ type 1-7 → execute_models
       ↓
       QuestionTypeRouter（1:1 映射）
       ├─ type 1 → model-1（稳定性风险）
       ├─ type 2 → model-4（酸化改良）
       ├─ type 3 → model-3（障碍诊断）
       ├─ type 4 → model-6（肥力 ML 预测）
       ├─ type 5 → model-7（耕地质量等级评价）
       ├─ type 6 → model-2（提升潜力评估）
       └─ type 7 → model-5（有机质培肥）
       ↓
       AgentManager（编排调度）
       ↓
       结果汇总 + 推荐建议
```

7 个专业智能体通过统一能力注册表与 [src/ai_culti_demo/thematic_models.py](src/ai_culti_demo/thematic_models.py) 的正式模型 API 一一对应。空间结构解析和关键指标解析为辅助能力，多项协同提升为实验性能力，不参与聊天路由。

## 配置说明

支持多种配置环境（[framework/config.py](framework/config.py)）：

| 配置 | 数据库 | 用途 |
|------|--------|------|
| `development`（默认） | SQLite (`instance/development.db`) | 本地开发 |
| `sqlite` | SQLite (`instance/development.db`) | 显式指定 SQLite |
| `production` | SQLite (`instance/production.db`) | 生产部署 |

切换配置：

```bash
python start_http_server.py --config production
```

## 生产部署

生产环境使用 waitress WSGI 服务器，支持多线程并发、Windows 服务注册和日志管理。

**快速启动：**

```bash
# 1. 配置环境变量
copy deploy\production.env.example .env
# 编辑 .env 填写 SECRET_KEY 和 SILICONFLOW_API_KEY

# 2. 初始化数据库
python init_db.py

# 3. 启动生产服务器
python start_production_server.py
```

**注册为 Windows 服务：**

```powershell
.\deploy\windows-service.ps1 install
.\deploy\windows-service.ps1 start
```

完整部署步骤、故障排查和安全清单详见 [deploy/deployment.md](deploy/deployment.md)。

## 项目规范

- OpenSpec 规范目录：[openspec/specs/](openspec/specs/)（17 个 capability spec）
- 变更归档：[openspec/changes/archive/](openspec/changes/archive/)
- 项目总纲：[openspec/project.md](openspec/project.md)

## 开发约定

- 密码哈希使用 `werkzeug.security`（非 MD5）
- 新框架通过 `framework/core_engine/adapter.py` 访问核心引擎
- 专题模型通过统一能力注册表对应 question_types 1-7（1=稳定性、2=酸化、3=障碍诊断、4=SOC/Dose 预测、5=质量等级、6=提升潜力、7=有机质培肥），通过 QuestionTypeRouter 1:1 映射到单一专业智能体
- 开发环境使用 SQLite（`instance/development.db`）
- 生产环境使用 SQLite（`instance/production.db`）
- API 认证头格式：`Authorization: Bearer <token>`

## License

私有项目，未授权。
