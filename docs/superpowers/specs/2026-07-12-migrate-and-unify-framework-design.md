---
comet_change: migrate-and-unify-framework
role: technical-design
canonical_spec: openspec
archived-with: 2026-07-13-migrate-and-unify-framework
status: final
---

# 统一框架深度设计文档

## 1. 架构设计

### 1.1 整体架构

采用**模块化单体**架构，将所有组件集成在一个项目中，便于开发和部署。

```
┌─────────────────────────────────────────────────────────────────────┐
│                      API Layer (Flask)                             │
│  /api/v1/chat, /api/v1/models/run, /api/v1/auth, /api/v1/docs      │
├─────────────────────────────────────────────────────────────────────┤
│                    Framework Core                                   │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────────────────────┐   │
│  │ LLM Service │ │ Embedding   │ │ Multi-Agent Orchestrator    │   │
│  │             │ │ Service     │ │ (Dynamic Scheduling)        │   │
│  └──────┬──────┘ └──────┬──────┘ └──────────────┬──────────────┘   │
│         │               │                       │                  │
│         └──────┬────────┴───────────┬───────────┘                  │
│                ▼                   ▼                              │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │              Function Calling System                         │  │
│  │  LangChain Tools + Custom JSON Schema Interfaces             │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                ▲                                                  │
│  ┌────────────┼────────────┐ ┌────────────────┐                   │
│  │ RAG Chain  │            │ │ Vector Store   │                   │
│  │            │            │ │ (Chroma)       │                   │
│  └────────────┴────────────┘ └────────────────┘                   │
├─────────────────────────────────────────────────────────────────────┤
│                    Domain Modules                                   │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────────────────────┐ │
│  │ 酸化评估 │ │ 石灰计算 │ │ 其他4个  │ │ 数据加载模块            │ │
│  │ 模型     │ │ 模型     │ │ 专业模型 │ │                        │ │
│  └──────────┘ └──────────┘ └──────────┘ └────────────────────────┘ │
├─────────────────────────────────────────────────────────────────────┤
│                    Data Layer                                       │
│  MySQL (用户/对话/消息/文档)  │  Chroma (向量库 - bge-m3)           │
└─────────────────────────────────────────────────────────────────────┘
```

### 1.2 模块划分

| 模块 | 职责 | 状态 |
|------|------|------|
| `framework/llm/` | 统一 LLM 服务封装 | 新增 |
| `framework/embedding/` | 统一 Embedding 服务（bge-m3） | 新增 |
| `framework/vector_store/` | Chroma 向量存储 | 新增 |
| `framework/rag/` | RAG 问答链 | 新增 |
| `framework/agents/` | 多智能体编排器（动态调度） | 新增 |
| `framework/function_calling/` | 函数调用系统 | 新增 |
| `framework/models/` | 数据库模型 | 迁移 |
| `framework/auth/` | JWT 认证 | 迁移 |
| `framework/upload/` | 文件上传管理 | 迁移 |
| `framework/domain/` | 专业模型（6个） | 迁移 |
| `framework/api/` | Flask API 服务 | 合并 |

## 2. 核心服务设计

### 2.1 LLM 服务

**接口定义：**
```python
class LLMService:
    def generate(prompt: str, messages: Optional[list] = None, **kwargs) -> dict
    def is_available() -> bool
```

**配置项：**
- `SILICONFLOW_API_KEY`: 硅基流动 API 密钥
- `SILICONFLOW_CHAT_MODEL`: 聊天模型（默认 DeepSeek-V4-Flash）
- `SILICONFLOW_BASE_URL`: API 地址

### 2.2 Embedding 服务

**统一为 bge-m3 模型**

**接口定义：**
```python
class EmbeddingService:
    def embed_query(text: str) -> List[float]
    def embed_documents(texts: List[str]) -> List[List[float]]
    def is_available() -> bool
```

**配置项：**
- `SILICONFLOW_API_KEY`: 硅基流动 API 密钥
- `SILICONFLOW_EMBED_MODEL`: 嵌入模型（固定为 BAAI/bge-m3）
- `SILICONFLOW_BASE_URL`: API 地址

### 2.3 向量存储

**接口定义：**
```python
class ChromaVectorStore:
    def add_documents(texts: list, metadatas: list = None, ids: list = None)
    def search(query: str, n_results: int = 3) -> dict
    def delete_by_source(source_doc_name: str) -> int
    def get_collection_stats() -> int
```

**配置项：**
- `CHROMA_PERSIST_DIR`: 持久化目录（默认 ./chroma_db）
- `CHROMA_COLLECTION_NAME`: 集合名称

### 2.4 RAG 问答链

**接口定义：**
```python
class RAGChain:
    def chat(query: str, conversation_history: list = None, valid_doc_names: set = None) -> dict
```

**流程：**
1. 语义检索相关文档片段
2. 构建系统提示词（包含检索到的上下文）
3. 调用 LLM 生成回答
4. 返回回答及引用来源

## 3. 多智能体编排器设计

### 3.1 动态调度策略

根据用户请求的问题类型，动态决定需要执行哪些模型：

| 问题类型 | 执行的模型 |
|----------|-----------|
| 酸化程度查询 | 酸化评估模型 |
| 治理方案查询 | 酸化评估 + 石灰计算 |
| 氮肥影响模拟 | 氮肥影响模型 |
| 综合查询 | 多个相关模型并发 |

### 3.2 并发限制

**基于 CPU 核心数动态计算最大并发数：**
- 公式：`max_concurrent = max(2, min(6, cpu_count()))`
- 最小 2 个并发，最大 6 个并发

**配置项：**
- `MAX_CONCURRENT_MODELS`: 可通过环境变量覆盖默认值

### 3.3 状态机定义

```python
class MultiAgentState(TypedDict):
    request: dict
    data: dict
    model_results: dict  # {model_name: result}
    llm_response: dict
    status: str
    error: Optional[str]
```

### 3.4 节点设计

| 节点 | 职责 | 是否异步 |
|------|------|----------|
| `initialize` | 初始化状态 | 否 |
| `identify_question` | 识别问题类型 | 否 |
| `route_models` | 根据问题类型路由模型 | 否 |
| `execute_models` | 并发执行选中的模型 | 是 |
| `aggregate_results` | 聚合模型结果 | 否 |
| `llm_generate` | LLM 生成总结 | 是 |
| `finalize` | 输出最终结果 | 否 |

## 4. 函数调用系统设计

### 4.1 工具注册表

```python
class ToolRegistry:
    def register(name: str, tool: Tool, schema: dict = None)
    def get(name: str) -> Optional[Tool]
    def list() -> list
    def deregister(name: str)
```

### 4.2 LangChain Tools 集成

核心工具（文档检索、数据查询）使用 LangChain Tools：

```python
from langchain.tools import Tool

document_search_tool = Tool(
    name="document_search",
    func=vector_store.search,
    description="搜索知识库中的相关文档"
)
```

### 4.3 自定义工具接口

专业模型使用自定义 JSON Schema 接口：

```python
class CustomTool:
    name: str
    description: str
    schema: dict  # JSON Schema
    func: Callable
```

### 4.4 工具调用执行器

```python
class ToolExecutor:
    def execute(tool_name: str, arguments: dict) -> dict
    def execute_batch(tools: list) -> list
```

## 5. 数据库模型设计

### 5.1 用户模型

```python
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
```

### 5.2 对话模型

```python
class Conversation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    title = db.Column(db.String(200), default='新对话')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    update_time = db.Column(db.DateTime, onupdate=datetime.utcnow)
```

### 5.3 消息模型

```python
class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey('conversation.id'), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # user/assistant
    content = db.Column(db.Text, nullable=False)
    sources = db.Column(db.JSON)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
```

### 5.4 文档模型

```python
class Document(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    doc_name = db.Column(db.String(255), nullable=False)
    file_path = db.Column(db.String(500))
    status = db.Column(db.Integer, default=0)  # 0: processing, 1: completed, 2: failed
    error_message = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
```

## 6. 认证系统设计

### 6.1 JWT 认证

```python
class AuthService:
    def generate_token(user_id: int) -> str
    def verify_token(token: str) -> Optional[int]
    def refresh_token(token: str) -> str
```

### 6.2 密码安全

- 使用 bcrypt 进行密码哈希
- 存储密码哈希，不存储明文密码

### 6.3 认证装饰器

```python
@jwt_required()
def protected_route():
    user_id = get_jwt_identity()
```

## 7. 文件上传管理设计

### 7.1 文件上传

**支持文件类型：** PDF、Word、Excel、Markdown

**大小限制：** 50MB

### 7.2 文档解析

```python
class DocumentParser:
    def parse_pdf(file_path: str) -> str
    def parse_word(file_path: str) -> str
    def parse_excel(file_path: str) -> str
    def parse_markdown(file_path: str) -> str
```

### 7.3 文档处理流程

1. 用户上传文件
2. 保存到上传目录
3. 解析文件内容
4. 向量化并存储到向量库
5. 更新文档状态

## 8. API 设计

### 8.1 版本控制

统一为 `/api/v1/` 前缀

### 8.2 路由结构

```
/api/v1/auth/
    POST /login - 用户登录
    POST /register - 用户注册
    POST /refresh - 刷新令牌

/api/v1/chat/
    GET /conversations - 获取对话列表
    POST /conversations - 创建新对话
    DELETE /conversations/<id> - 删除对话
    GET /conversations/<id>/messages - 获取消息列表
    POST / - 发送消息并获取回答

/api/v1/models/
    GET / - 获取可用模型列表
    POST /run - 运行指定模型

/api/v1/docs/
    GET / - 获取文档列表
    POST /upload - 上传文档
    GET /<id> - 获取文档详情
    DELETE /<id> - 删除文档

/api/v1/county/
    GET /overview - 县域概览
    POST /diagnose - 智能诊断
```

### 8.3 响应格式

```json
{
  "status": "ok",
  "data": {},
  "message": "操作成功"
}
```

## 9. 配置管理

### 9.1 配置项

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `SILICONFLOW_API_KEY` | 硅基流动 API 密钥 | 空 |
| `SILICONFLOW_CHAT_MODEL` | 聊天模型 | deepseek-ai/DeepSeek-V4-Flash |
| `SILICONFLOW_EMBED_MODEL` | 嵌入模型 | BAAI/bge-m3 |
| `SILICONFLOW_BASE_URL` | API 地址 | https://api.siliconflow.cn/v1 |
| `CHROMA_PERSIST_DIR` | 向量库目录 | ./chroma_db |
| `CHROMA_COLLECTION_NAME` | 集合名称 | enterprise_kb |
| `MAX_CONCURRENT_MODELS` | 最大并发模型数 | 基于 CPU 核心数 |
| `DB_HOST` | 数据库主机 | localhost |
| `DB_PORT` | 数据库端口 | 3306 |
| `DB_USER` | 数据库用户 | root |
| `DB_PASSWORD` | 数据库密码 | 空 |
| `DB_NAME` | 数据库名称 | db_enterprise_qa |
| `JWT_SECRET_KEY` | JWT 密钥 | 随机生成 |
| `UPLOAD_FOLDER` | 上传目录 | ./uploads |
| `MAX_CONTENT_LENGTH` | 最大上传大小 | 50MB |

### 9.2 配置优先级

1. 环境变量（最高优先级）
2. 配置文件（`.env`）
3. 默认值（最低优先级）

## 10. 数据迁移

### 10.1 数据库迁移

**步骤：**
1. 创建数据库表结构
2. 从 org-backend 导出数据
3. 导入到新数据库
4. 验证数据完整性

**迁移脚本：** `scripts/migrate_db.py`

### 10.2 向量库迁移

**步骤：**
1. 备份旧向量库数据
2. 使用 bge-m3 重新向量化所有文档
3. 导入到新向量库
4. 验证检索效果

**迁移脚本：** `scripts/migrate_vector_db.py`

## 11. 测试策略

### 11.1 单元测试

- 核心服务（LLM、Embedding、Vector Store）
- 工具注册表和执行器
- 数据库模型
- 文档解析模块

### 11.2 集成测试

- RAG 问答链端到端测试
- 多智能体工作流测试（动态调度）
- API 接口测试
- 认证系统测试

### 11.3 并发测试

- 模拟多用户并发请求
- 验证并发限制是否生效
- 验证资源使用情况

### 11.4 兼容性测试

- 验证原有 API 客户端是否兼容新接口
- 验证数据库迁移后数据完整性

## 12. 部署方案

### 12.1 依赖安装

```bash
pip install -e .
```

### 12.2 启动服务

```bash
python -m framework.api.app
```

### 12.3 Docker 部署

```dockerfile
FROM python:3.10-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
CMD ["python", "-m", "framework.api.app"]
```

## 13. 错误处理

### 13.1 LLM 调用失败

- 实现降级机制，返回预设响应
- 记录错误日志，便于排查

### 13.2 向量库不可用

- 返回友好错误提示
- 提供缓存机制，减少对向量库的依赖

### 13.3 模型执行失败

- 单个模型失败不影响其他模型
- 记录失败模型信息，在结果中标记

### 13.4 数据库连接失败

- 重试连接机制
- 返回 503 错误，提示服务暂时不可用

## 14. 性能优化

### 14.1 缓存策略

- LLM 响应缓存（相同请求直接返回缓存结果）
- 向量检索结果缓存
- 热门文档预加载

### 14.2 异步处理

- 文档上传异步处理（后台解析和向量化）
- 非关键路径使用异步执行

### 14.3 连接池

- 数据库连接池
- HTTP 连接池

## 15. 安全考虑

### 15.1 认证授权

- JWT 认证保护所有 API 端点
- 基于用户 ID 的数据隔离

### 15.2 输入验证

- 参数类型和格式验证
- 防止 SQL 注入
- 防止 XSS 攻击

### 15.3 文件安全

- 文件类型白名单
- 文件大小限制
- 文件名清理（防止路径遍历）

### 15.4 日志安全

- 不记录敏感信息（密码、API 密钥）
- 日志脱敏处理
