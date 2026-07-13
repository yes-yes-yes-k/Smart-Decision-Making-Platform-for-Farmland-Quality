# 耕地土壤酸化治理智能问答系统

集成 RAG、Function Calling 和多智能体架构的统一能力底座，面向耕地质量管理场景沉淀数据整合、专业诊断、方案生成与 Agent 编排能力。

## 功能特性

- **统一框架**：Flask + SQLAlchemy + JWT + ChromaDB + LangChain + LangGraph
- **核心引擎**：县域概览、结构化诊断、6 个专题模型、报告汇总（`src/ai_culti_demo`）
- **多智能体编排**：6 个专业智能体 + AgentManager + RoleRouter
  - 稳定性风险识别 / 潜力评估 / 问题识别
  - 酸化改良 / 有机质培肥 / 综合地力提升
- **RAG 知识检索**：基于 ChromaDB 的向量检索与 SiliconFlow LLM 问答
- **Function Calling**：工具注册表 + LangChain Tools 集成 + 自定义工具接口
- **JWT 认证**：用户体系、会话管理、权限装饰器
- **文档管理**：PDF / Word / Excel 解析、向量化入库、检索引用
- **15 个 REST API**：认证、聊天、模型调用、文档、县域、报告

## 技术栈

| 层级 | 组件 |
|------|------|
| Web 框架 | Flask 3.0 + Flask-CORS + Flask-JWT-Extended |
| ORM | Flask-SQLAlchemy |
| 数据库 | 开发环境 SQLite / 生产环境 MySQL |
| 向量库 | ChromaDB 0.5 |
| LLM | SiliconFlow（DeepSeek-V4-Flash / BAAI/bge-m3） |
| 编排 | LangChain 0.2 + LangGraph 0.1 |
| 文档解析 | PyPDF2 / python-docx / openpyxl |

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

# 数据库（生产环境）
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=
DB_NAME=db_enterprise_qa

# 向量库
CHROMA_PERSIST_DIR=./chroma_db
CHROMA_COLLECTION_NAME=enterprise_kb
```

开发环境默认使用 SQLite（`instance/development.db`），无需额外配置数据库。

### 初始化数据库

```bash
python init_db.py
```

创建表结构并写入默认账号：
- 管理员：`admin` / `admin123`
- 普通用户：`user` / `user123`

### 启动服务

```bash
python start_http_server.py
# 或指定参数
python start_http_server.py --host 0.0.0.0 --port 5000 --config development
```

服务启动后访问 http://localhost:5000

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

完整 OpenAPI 规范见 [docs/openapi.json](docs/openapi.json)，可导入 Apifox 等工具查看。

## 目录结构

```
agent_culti_demo/
├── src/ai_culti_demo/          # 核心引擎（县域概览/诊断/专题模型/报告）
│   ├── overview.py             #   县域总览
│   ├── diagnosis.py            #   结构化诊断
│   ├── thematic_models.py      #   6 个专题模型
│   ├── report.py               #   报告汇总
│   └── catalog.py              #   数据目录加载
├── framework/                  # 统一框架
│   ├── api/                    #   Flask 应用与路由
│   │   ├── app.py              #     应用工厂
│   │   └── routes/             #     auth/chat/models/docs/county/report
│   ├── agents/                 #   多智能体编排
│   │   ├── base.py             #     智能体基类
│   │   ├── manager.py          #     AgentManager
│   │   ├── router.py           #     RoleRouter 角色路由
│   │   ├── orchestrator.py     #     LangGraph 编排器
│   │   └── specialized/        #     6 个专业智能体实现
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
├── docs/                       # 文档
│   ├── openapi.json            #   OpenAPI 3.0 规范
│   └── superpowers/            #   设计文档与验证报告
├── tests/                      # 测试套件（78 个测试）
├── openspec/                   # OpenSpec 规范与变更归档
├── scripts/                    # 迁移脚本
├── init_db.py                  # 数据库初始化
├── start_http_server.py        # 服务启动入口
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
RoleRouter（角色判定）
   ↓
AgentManager（编排调度）
   ↓
┌──────────────────────────────────────────┐
│ 稳定性风险 │ 潜力评估 │ 问题识别         │
│ 酸化改良   │ 有机质   │ 综合地力提升     │
└──────────────────────────────────────────┘
   ↓
结果汇总 + 推荐建议
```

6 个专业智能体基于 [src/ai_culti_demo/thematic_models.py](src/ai_culti_demo/thematic_models.py) 的 6 个专题模型实现，通过 [framework/core_engine/adapter.py](framework/core_engine/adapter.py) 桥接调用。

## 配置说明

支持四种配置环境（[framework/config.py](framework/config.py)）：

| 配置 | 数据库 | 用途 |
|------|--------|------|
| `development`（默认） | SQLite | 本地开发 |
| `sqlite` | SQLite | 显式指定 SQLite |
| `production` | MySQL | 生产部署 |

切换配置：

```bash
python start_http_server.py --config production
```

## 项目规范

- OpenSpec 规范目录：[openspec/specs/](openspec/specs/)（17 个 capability spec）
- 变更归档：[openspec/changes/archive/](openspec/changes/archive/)
- 项目总纲：[openspec/project.md](openspec/project.md)

## 开发约定

- 密码哈希使用 `werkzeug.security`（非 MD5）
- 新框架通过 `framework/core_engine/adapter.py` 访问核心引擎
- 专题模型在 `thematic_models.py` 中对应 question_types 1-3
- 开发环境使用 SQLite（`instance/development.db`）
- API 认证头格式：`Authorization: Bearer <token>`

## License

私有项目，未授权。
