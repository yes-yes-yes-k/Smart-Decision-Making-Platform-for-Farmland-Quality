# 迁移与统一框架实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 AI_culti_demo 和 org-backend 两个项目的代码迁移到当前项目，并开发一个统一框架，集成 RAG、Function Calling 和多智能体架构。

**Architecture:** 采用模块化单体架构，包含11个核心模块（LLM服务、Embedding服务、向量存储、RAG链、多智能体编排器、函数调用系统、数据库模型、认证系统、文件上传、专业模型、API层），使用 Flask + SQLAlchemy + LangChain + LangGraph 技术栈。

**Tech Stack:** Python 3.10+, Flask 3.x, SQLAlchemy 2.x, LangChain 0.2.x, LangGraph, ChromaDB, Flask-JWT-Extended, pandas, numpy

## Global Constraints

- Embedding 模型统一为 bge-m3
- API 统一为 `/api/v1/` 前缀
- 并发限制基于 CPU 核心数：`max(2, min(6, cpu_count()))`
- 数据库使用 MySQL 8，连接池配置
- 文件上传大小限制 50MB
- 支持六种专业模型的动态调度

---

## 文件结构规划

```
framework/
├── __init__.py
├── config.py                    # 统一配置管理
├── api/
│   ├── __init__.py
│   ├── app.py                   # Flask应用入口
│   └── routes/
│       ├── __init__.py
│       ├── auth.py              # 认证路由
│       ├── chat.py              # 聊天路由
│       ├── models.py            # 模型执行路由
│       ├── docs.py              # 文档管理路由
│       └── county.py            # 县域诊断路由
├── llm/
│   ├── __init__.py
│   └── service.py               # 统一LLM服务
├── embedding/
│   ├── __init__.py
│   └── service.py               # 统一Embedding服务(bge-m3)
├── vector_store/
│   ├── __init__.py
│   └── chroma_store.py          # Chroma向量存储
├── rag/
│   ├── __init__.py
│   └── chain.py                 # RAG问答链
├── agents/
│   ├── __init__.py
│   ├── state.py                 # 多智能体状态定义
│   ├── nodes.py                 # 并发执行节点
│   └── orchestrator.py          # 多智能体编排器
├── function_calling/
│   ├── __init__.py
│   ├── registry.py              # 工具注册表
│   ├── langchain_tools.py       # LangChain Tools集成
│   ├── custom_tools.py          # 自定义工具接口
│   └── executor.py              # 工具执行器
├── models/
│   ├── __init__.py
│   ├── user.py                  # 用户模型
│   ├── conversation.py          # 对话模型
│   ├── message.py               # 消息模型
│   └── document.py              # 文档模型
├── auth/
│   ├── __init__.py
│   ├── jwt.py                   # JWT认证模块
│   └── decorators.py            # 认证装饰器
├── upload/
│   ├── __init__.py
│   ├── file_upload.py           # 文件上传管理
│   └── document_parser.py       # 文档解析模块
└── domain/
    ├── __init__.py
    ├── assessment/
    │   ├── __init__.py
    │   └── acidification.py     # 酸化评估模型
    ├── calculation/
    │   ├── __init__.py
    │   └── lime_calculator.py   # 石灰计算模型
    ├── data/
    │   ├── __init__.py
    │   └── soil_data_loader.py  # 土壤数据加载
    └── other_models/            # 其他四个专业模型
```

---

### Task 1: 创建统一框架目录结构

**Files:**
- Create: `framework/__init__.py`
- Create: `framework/api/__init__.py`
- Create: `framework/api/routes/__init__.py`
- Create: `framework/llm/__init__.py`
- Create: `framework/embedding/__init__.py`
- Create: `framework/vector_store/__init__.py`
- Create: `framework/rag/__init__.py`
- Create: `framework/agents/__init__.py`
- Create: `framework/function_calling/__init__.py`
- Create: `framework/models/__init__.py`
- Create: `framework/auth/__init__.py`
- Create: `framework/upload/__init__.py`
- Create: `framework/domain/__init__.py`
- Create: `framework/domain/assessment/__init__.py`
- Create: `framework/domain/calculation/__init__.py`
- Create: `framework/domain/data/__init__.py`
- Create: `framework/domain/other_models/__init__.py`

**Interfaces:**
- Produces: 完整的目录结构，为后续模块提供基础

- [x] **Step 1: 创建所有目录和 __init__.py 文件**

```bash
mkdir -p framework/api/routes framework/llm framework/embedding framework/vector_store framework/rag framework/agents framework/function_calling framework/models framework/auth framework/upload framework/domain/assessment framework/domain/calculation framework/domain/data framework/domain/other_models

touch framework/__init__.py framework/api/__init__.py framework/api/routes/__init__.py framework/llm/__init__.py framework/embedding/__init__.py framework/vector_store/__init__.py framework/rag/__init__.py framework/agents/__init__.py framework/function_calling/__init__.py framework/models/__init__.py framework/auth/__init__.py framework/upload/__init__.py framework/domain/__init__.py framework/domain/assessment/__init__.py framework/domain/calculation/__init__.py framework/domain/data/__init__.py framework/domain/other_models/__init__.py
```

- [x] **Step 2: 验证目录结构**

```bash
find framework -name "__init__.py" | head -20
```
Expected: 显示20个 __init__.py 文件路径

- [x] **Step 3: Commit**

```bash
git add framework/
git commit -m "feat: create unified framework directory structure"
```

---

### Task 2: 创建统一配置管理模块

**Files:**
- Create: `framework/config.py`

**Interfaces:**
- Produces: `Config` 类，包含数据库、JWT、LLM、Embedding、Chroma、文件上传等配置
- Consumes: 环境变量

- [x] **Step 1: 编写配置模块**

```python
import os
from typing import Optional

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'enterprise-qa-secret-key-2024'

    DB_HOST = os.environ.get('DB_HOST') or 'localhost'
    DB_PORT = int(os.environ.get('DB_PORT') or 3306)
    DB_USER = os.environ.get('DB_USER') or 'root'
    DB_PASSWORD = os.environ.get('DB_PASSWORD') or '12345678'
    DB_NAME = os.environ.get('DB_NAME') or 'db_enterprise_qa'

    SQLALCHEMY_DATABASE_URI = (
        f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}?charset=utf8mb4"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_size': 20,
        'max_overflow': 50,
        'pool_timeout': 30,
        'pool_recycle': 1800,
    }

    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY') or 'jwt-enterprise-qa-secret-key-2024-secure'
    JWT_ACCESS_TOKEN_EXPIRES = 24 * 60 * 60

    SILICONFLOW_API_KEY = os.environ.get('SILICONFLOW_API_KEY') or ''
    SILICONFLOW_CHAT_MODEL = os.environ.get('SILICONFLOW_CHAT_MODEL') or 'deepseek-ai/DeepSeek-V4-Flash'
    SILICONFLOW_EMBED_MODEL = os.environ.get('SILICONFLOW_EMBED_MODEL') or 'BAAI/bge-m3'
    SILICONFLOW_BASE_URL = os.environ.get('SILICONFLOW_BASE_URL') or 'https://api.siliconflow.cn/v1'

    CHROMA_PERSIST_DIR = os.environ.get('CHROMA_PERSIST_DIR') or './chroma_db'
    CHROMA_COLLECTION_NAME = os.environ.get('CHROMA_COLLECTION_NAME') or 'enterprise_kb'

    UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER') or './uploads'
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024

    CHUNK_SIZE = 800
    CHUNK_OVERLAP = 150
    RETRIEVAL_TOP_K = 5

    MAX_CONCURRENT_MODELS = int(os.environ.get('MAX_CONCURRENT_MODELS') or '0')

    @classmethod
    def get_max_concurrent(cls) -> int:
        if cls.MAX_CONCURRENT_MODELS > 0:
            return cls.MAX_CONCURRENT_MODELS
        import multiprocessing
        return max(2, min(6, multiprocessing.cpu_count()))

class DevelopmentConfig(Config):
    DEBUG = True

class ProductionConfig(Config):
    DEBUG = False

config_map = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
```

- [x] **Step 2: 测试配置模块**

```python
from framework.config import Config, config_map
print(f"DB_HOST: {Config.DB_HOST}")
print(f"Max concurrent: {Config.get_max_concurrent()}")
print(f"Embed model: {Config.SILICONFLOW_EMBED_MODEL}")
```
Expected: 输出正确的配置值

- [x] **Step 3: Commit**

```bash
git add framework/config.py
git commit -m "feat: add unified configuration management module"
```

---

### Task 3: 更新 pyproject.toml 添加依赖

**Files:**
- Modify: `pyproject.toml`

**Interfaces:**
- Produces: 更新后的项目依赖配置
- Consumes: 当前 pyproject.toml

- [x] **Step 1: 读取当前 pyproject.toml**

```bash
cat pyproject.toml
```

- [x] **Step 2: 更新依赖配置**

```toml
[project]
name = "agent_culti_demo"
version = "0.1.0"
description = "Unified framework for RAG, Function Calling, and Multi-Agent architecture"
requires-python = ">=3.10"

[project.dependencies]
Flask = "^3.0.0"
Flask-SQLAlchemy = "^3.1.0"
Flask-JWT-Extended = "^4.6.0"
Flask-CORS = "^4.0.0"
pymysql = "^1.1.0"
langchain = "^0.2.0"
langchain-openai = "^0.1.0"
langgraph = "^0.1.0"
chromadb = "^0.5.0"
pandas = "^2.2.0"
numpy = "^1.26.0"
python-dotenv = "^1.0.0"
python-docx = "^1.1.0"
PyPDF2 = "^3.0.0"
openpyxl = "^3.1.0"
```

- [x] **Step 3: 安装依赖**

```bash
pip install -e .
```
Expected: 依赖安装成功

- [x] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "feat: update dependencies for unified framework"
```

---

### Task 4: 实现统一 LLM 服务

**Files:**
- Create: `framework/llm/service.py`

**Interfaces:**
- Produces: `LLMService` 类，提供 `generate()` 和 `is_available()` 方法
- Consumes: `framework/config.py`

- [x] **Step 1: 编写 LLM 服务**

```python
from __future__ import annotations
import os
from typing import Any, Dict, Optional
from langchain_openai import ChatOpenAI
from framework.config import Config

class LLMService:
    DEFAULT_API_BASE = "https://api.siliconflow.cn/v1"

    def __init__(self):
        self._client = None
        self._initialized = False
        self._init_client()

    def _init_client(self):
        api_key = os.environ.get("SILICONFLOW_KEY") or os.environ.get("SILICONFLOW_API_KEY") or Config.SILICONFLOW_API_KEY
        api_base = os.environ.get("SILICONFLOW_API_BASE") or os.environ.get("SILICONFLOW_BASE_URL") or Config.SILICONFLOW_BASE_URL

        if api_key:
            try:
                self._client = ChatOpenAI(
                    model=Config.SILICONFLOW_CHAT_MODEL,
                    api_key=api_key,
                    base_url=api_base,
                    temperature=0.3,
                    max_tokens=2048,
                    timeout=30,
                )
                self._initialized = True
            except Exception as e:
                print(f"LLM初始化失败，将使用降级模式: {e}")
                self._initialized = False

    def is_available(self) -> bool:
        return self._initialized and self._client is not None

    def generate(
        self,
        prompt: str,
        messages: Optional[list] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        if not self.is_available():
            return self._get_fallback_response(prompt)

        try:
            if messages:
                full_messages = messages.copy()
                full_messages.append({"role": "user", "content": prompt})
            else:
                full_messages = [{"role": "user", "content": prompt}]

            response = self._client.invoke(full_messages)
            content = response.content if hasattr(response, "content") else str(response)

            return {
                "success": True,
                "content": content,
                "model": Config.SILICONFLOW_CHAT_MODEL,
                "type": "llm",
            }
        except Exception as e:
            print(f"LLM调用失败，使用降级模式: {e}")
            return self._get_fallback_response(prompt)

    def _get_fallback_response(self, prompt: str) -> Dict[str, Any]:
        return {
            "success": False,
            "content": "",
            "model": "fallback",
            "type": "fallback",
            "message": "LLM服务不可用，将使用规则输出",
        }

llm_service = LLMService()
```

- [x] **Step 2: 测试 LLM 服务**

```python
from framework.llm.service import llm_service
print(f"LLM available: {llm_service.is_available()}")
```
Expected: 根据API密钥配置输出 True 或 False

- [x] **Step 3: Commit**

```bash
git add framework/llm/service.py
git commit -m "feat: implement unified LLM service"
```

---

### Task 5: 实现统一 Embedding 服务（bge-m3）

**Files:**
- Create: `framework/embedding/service.py`

**Interfaces:**
- Produces: `EmbeddingService` 类，提供 `embed_query()` 和 `embed_documents()` 方法
- Consumes: `framework/config.py`

- [x] **Step 1: 编写 Embedding 服务**

```python
from __future__ import annotations
import os
from typing import List
from langchain_openai import OpenAIEmbeddings
from framework.config import Config

class EmbeddingService:
    DEFAULT_API_BASE = "https://api.siliconflow.cn/v1"

    def __init__(self):
        self._embeddings = None
        self._initialized = False
        self._init_embeddings()

    def _init_embeddings(self):
        api_key = os.environ.get("SILICONFLOW_KEY") or os.environ.get("SILICONFLOW_API_KEY") or Config.SILICONFLOW_API_KEY
        api_base = os.environ.get("SILICONFLOW_API_BASE") or os.environ.get("SILICONFLOW_BASE_URL") or Config.SILICONFLOW_BASE_URL

        if api_key:
            try:
                self._embeddings = OpenAIEmbeddings(
                    model=Config.SILICONFLOW_EMBED_MODEL,
                    api_key=api_key,
                    base_url=api_base,
                    timeout=30,
                )
                self._initialized = True
            except Exception as e:
                print(f"Embedding初始化失败，将使用关键词匹配降级模式: {e}")
                self._initialized = False

    def is_available(self) -> bool:
        return self._initialized and self._embeddings is not None

    def embed_query(self, text: str) -> List[float]:
        if not self.is_available():
            return []

        try:
            return self._embeddings.embed_query(text)
        except Exception as e:
            print(f"Embedding查询失败，使用降级模式: {e}")
            return []

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        if not self.is_available():
            return [[] for _ in texts]

        try:
            return self._embeddings.embed_documents(texts)
        except Exception as e:
            print(f"Embedding批量查询失败，使用降级模式: {e}")
            return [[] for _ in texts]

embedding_service = EmbeddingService()
```

- [x] **Step 2: 测试 Embedding 服务**

```python
from framework.embedding.service import embedding_service
print(f"Embedding available: {embedding_service.is_available()}")
```
Expected: 根据API密钥配置输出 True 或 False

- [x] **Step 3: Commit**

```bash
git add framework/embedding/service.py
git commit -m "feat: implement unified Embedding service with bge-m3"
```

---

### Task 6: 实现向量存储模块

**Files:**
- Create: `framework/vector_store/chroma_store.py`

**Interfaces:**
- Produces: `ChromaVectorStore` 类，提供 `add_documents()`, `search()`, `delete_by_source()` 方法
- Consumes: `framework/config.py`, `framework/embedding/service.py`

- [x] **Step 1: 编写向量存储模块**

```python
from __future__ import annotations
import os
from typing import Optional, List, Dict, Any
import chromadb
from chromadb.config import Settings
from framework.config import Config
from framework.embedding.service import embedding_service

class ChromaVectorStore:
    def __init__(self):
        self._client = None
        self._collection = None
        self._init_client()

    def _init_client(self):
        persist_dir = Config.CHROMA_PERSIST_DIR
        collection_name = Config.CHROMA_COLLECTION_NAME

        os.makedirs(persist_dir, exist_ok=True)

        try:
            self._client = chromadb.PersistentClient(
                path=persist_dir,
                settings=Settings(
                    anonymized_telemetry=False,
                    allow_reset=False,
                )
            )
            self._collection = self._client.get_or_create_collection(name=collection_name)
        except Exception as e:
            print(f"Chroma初始化失败: {e}")

    def add_documents(self, texts: List[str], metadatas: Optional[List[Dict]] = None, ids: Optional[List[str]] = None) -> int:
        if not self._collection:
            return 0

        try:
            self._collection.add(
                documents=texts,
                metadatas=metadatas or [],
                ids=ids or [f"doc_{i}" for i in range(len(texts))]
            )
            return len(texts)
        except Exception as e:
            print(f"添加文档失败: {e}")
            return 0

    def search(self, query: str, n_results: int = 3, filters: Optional[Dict] = None) -> Dict[str, Any]:
        if not self._collection:
            return {"results": [], "count": 0}

        try:
            results = self._collection.query(
                query_texts=[query],
                n_results=n_results,
                where=filters,
            )

            formatted_results = []
            for i in range(len(results.get("documents", []))):
                docs = results["documents"][i]
                metadatas = results.get("metadatas", [[]])[i]
                distances = results.get("distances", [[]])[i]

                for j, doc in enumerate(docs):
                    formatted_results.append({
                        "content": doc,
                        "metadata": metadatas[j] if j < len(metadatas) else {},
                        "distance": distances[j] if j < len(distances) else 0,
                    })

            return {
                "results": formatted_results,
                "count": len(formatted_results),
            }
        except Exception as e:
            print(f"搜索失败: {e}")
            return {"results": [], "count": 0}

    def delete_by_source(self, source_doc_name: str) -> int:
        if not self._collection:
            return 0

        try:
            count_before = self._collection.count()
            self._collection.delete(where={"source": source_doc_name})
            count_after = self._collection.count()
            return count_before - count_after
        except Exception as e:
            print(f"删除失败: {e}")
            return 0

    def get_collection_stats(self) -> Dict[str, Any]:
        if not self._collection:
            return {"count": 0, "name": ""}

        try:
            return {
                "count": self._collection.count(),
                "name": self._collection.name,
            }
        except Exception as e:
            print(f"获取统计失败: {e}")
            return {"count": 0, "name": ""}

vector_store = ChromaVectorStore()
```

- [x] **Step 2: 测试向量存储**

```python
from framework.vector_store.chroma_store import vector_store
stats = vector_store.get_collection_stats()
print(f"Collection stats: {stats}")
```
Expected: 输出集合名称和文档数量

- [x] **Step 3: Commit**

```bash
git add framework/vector_store/chroma_store.py
git commit -m "feat: implement Chroma vector store module"
```

---

### Task 7: 实现 RAG 问答链

**Files:**
- Create: `framework/rag/chain.py`

**Interfaces:**
- Produces: `RAGChain` 类，提供 `chat()` 方法
- Consumes: `framework/llm/service.py`, `framework/vector_store/chroma_store.py`, `framework/config.py`

- [x] **Step 1: 编写 RAG 问答链**

```python
from __future__ import annotations
from typing import Optional, List, Dict, Any
from framework.llm.service import llm_service
from framework.vector_store.chroma_store import vector_store
from framework.config import Config

class RAGChain:
    def __init__(self):
        self.llm_service = llm_service
        self.vector_store = vector_store

    def chat(self, query: str, conversation_history: Optional[List[Dict]] = None, valid_doc_names: Optional[set] = None) -> Dict[str, Any]:
        retrieval_results = self._retrieve_documents(query, valid_doc_names)

        if retrieval_results["count"] == 0:
            llm_response = self.llm_service.generate(query, conversation_history)
            return {
                "success": llm_response.get("success", False),
                "answer": llm_response.get("content", ""),
                "sources": [],
                "model": llm_response.get("model", "fallback"),
            }

        context = self._build_context(retrieval_results["results"])
        prompt = self._build_prompt(query, context)

        llm_response = self.llm_service.generate(prompt, conversation_history)

        sources = []
        for result in retrieval_results["results"]:
            metadata = result.get("metadata", {})
            sources.append({
                "doc_name": metadata.get("source", "unknown"),
                "content": result.get("content", "")[:200] + "...",
                "score": 1 - result.get("distance", 0),
            })

        return {
            "success": llm_response.get("success", False),
            "answer": llm_response.get("content", ""),
            "sources": sources,
            "model": llm_response.get("model", "fallback"),
            "retrieved_count": retrieval_results["count"],
        }

    def _retrieve_documents(self, query: str, valid_doc_names: Optional[set]) -> Dict[str, Any]:
        filters = None
        if valid_doc_names:
            filters = {"source": {"$in": list(valid_doc_names)}}

        return self.vector_store.search(
            query=query,
            n_results=Config.RETRIEVAL_TOP_K,
            filters=filters,
        )

    def _build_context(self, results: List[Dict]) -> str:
        context_parts = []
        for i, result in enumerate(results):
            content = result.get("content", "")
            metadata = result.get("metadata", {})
            source = metadata.get("source", "unknown")
            context_parts.append(f"文档{i+1}({source}): {content}")
        return "\n\n".join(context_parts)

    def _build_prompt(self, query: str, context: str) -> str:
        return f"""基于以下文档内容，回答用户的问题。如果文档中没有相关信息，请根据你的知识回答，并明确说明信息来源。

文档内容：
{context}

用户问题：
{query}

请以自然、专业的语言回答。"""

rag_chain = RAGChain()
```

- [x] **Step 2: 测试 RAG 链**

```python
from framework.rag.chain import rag_chain
result = rag_chain.chat("测试问题")
print(f"RAG result: {result}")
```
Expected: 输出问答结果字典

- [x] **Step 3: Commit**

```bash
git add framework/rag/chain.py
git commit -m "feat: implement RAG QA chain"
```

---

### Task 8: 实现工具注册表

**Files:**
- Create: `framework/function_calling/registry.py`

**Interfaces:**
- Produces: `ToolRegistry` 类，提供 `register()`, `get()`, `list()`, `deregister()` 方法
- Consumes: 无

- [x] **Step 1: 编写工具注册表**

```python
from __future__ import annotations
from typing import Dict, Optional, Any, Callable
from langchain.tools import Tool

class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, Dict[str, Any]] = {}

    def register(self, name: str, tool: Tool, schema: Optional[Dict] = None) -> None:
        self._tools[name] = {
            "tool": tool,
            "schema": schema or tool.args if hasattr(tool, 'args') else None,
        }

    def get(self, name: str) -> Optional[Tool]:
        entry = self._tools.get(name)
        return entry["tool"] if entry else None

    def list(self) -> List[Dict[str, Any]]:
        tools_info = []
        for name, entry in self._tools.items():
            tool = entry["tool"]
            tools_info.append({
                "name": name,
                "description": tool.description if hasattr(tool, 'description') else "",
                "schema": entry.get("schema", {}),
            })
        return tools_info

    def deregister(self, name: str) -> None:
        if name in self._tools:
            del self._tools[name]

    def get_all(self) -> Dict[str, Tool]:
        return {name: entry["tool"] for name, entry in self._tools.items()}

tool_registry = ToolRegistry()
```

- [x] **Step 2: 测试工具注册表**

```python
from framework.function_calling.registry import tool_registry
from langchain.tools import Tool

def dummy_tool():
    return "dummy result"

tool = Tool(name="dummy", func=dummy_tool, description="Dummy tool")
tool_registry.register("dummy", tool)
print(f"Registered tools: {tool_registry.list()}")
print(f"Get tool: {tool_registry.get('dummy')}")
tool_registry.deregister("dummy")
print(f"After deregister: {tool_registry.list()}")
```
Expected: 输出注册、获取、注销工具的结果

- [x] **Step 3: Commit**

```bash
git add framework/function_calling/registry.py
git commit -m "feat: implement tool registry"
```

---

### Task 9: 实现 LangChain Tools 集成

**Files:**
- Create: `framework/function_calling/langchain_tools.py`

**Interfaces:**
- Produces: LangChain Tool 实例，注册到工具注册表
- Consumes: `framework/function_calling/registry.py`, `framework/vector_store/chroma_store.py`

- [x] **Step 1: 编写 LangChain Tools 集成**

```python
from __future__ import annotations
from langchain.tools import Tool
from framework.function_calling.registry import tool_registry
from framework.vector_store.chroma_store import vector_store

def document_search(query: str, n_results: int = 3) -> str:
    results = vector_store.search(query=query, n_results=n_results)
    if results["count"] == 0:
        return "未找到相关文档"
    
    formatted_results = []
    for i, result in enumerate(results["results"]):
        metadata = result.get("metadata", {})
        source = metadata.get("source", "unknown")
        content = result.get("content", "")[:300]
        formatted_results.append(f"文档{i+1}({source}): {content}")
    
    return "\n\n".join(formatted_results)

document_search_tool = Tool(
    name="document_search",
    func=document_search,
    description="搜索知识库中的相关文档，用于回答用户问题时查找参考资料",
)

tool_registry.register("document_search", document_search_tool)
```

- [x] **Step 2: 测试工具集成**

```python
from framework.function_calling.langchain_tools import document_search_tool
result = document_search_tool.run("测试")
print(f"Search result: {result}")
```
Expected: 输出搜索结果

- [x] **Step 3: Commit**

```bash
git add framework/function_calling/langchain_tools.py
git commit -m "feat: implement LangChain Tools integration"
```

---

### Task 10: 实现自定义工具接口（JSON Schema）

**Files:**
- Create: `framework/function_calling/custom_tools.py`

**Interfaces:**
- Produces: `CustomTool` 类和 `register_custom_tool()` 函数
- Consumes: `framework/function_calling/registry.py`

- [x] **Step 1: 编写自定义工具接口**

```python
from __future__ import annotations
from typing import Dict, Any, Callable, Optional
from pydantic import BaseModel, Field
from langchain.tools import Tool
from framework.function_calling.registry import tool_registry

class CustomTool:
    def __init__(self, name: str, description: str, schema: Dict[str, Any], func: Callable):
        self.name = name
        self.description = description
        self.schema = schema
        self.func = func

def register_custom_tool(tool: CustomTool) -> None:
    def tool_wrapper(**kwargs):
        return tool.func(**kwargs)

    langchain_tool = Tool(
        name=tool.name,
        func=tool_wrapper,
        description=tool.description,
    )

    tool_registry.register(tool.name, langchain_tool, tool.schema)
```

- [x] **Step 2: 测试自定义工具注册**

```python
from framework.function_calling.custom_tools import CustomTool, register_custom_tool

def hello_tool(name: str) -> str:
    return f"Hello, {name}!"

schema = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "description": "要打招呼的人的名字"}
    },
    "required": ["name"]
}

custom_tool = CustomTool(
    name="hello",
    description="向某人打招呼",
    schema=schema,
    func=hello_tool
)

register_custom_tool(custom_tool)
from framework.function_calling.registry import tool_registry
print(f"Tools: {tool_registry.list()}")
```
Expected: 输出包含 hello 工具的列表

- [x] **Step 3: Commit**

```bash
git add framework/function_calling/custom_tools.py
git commit -m "feat: implement custom tool interface with JSON Schema"
```

---

### Task 11: 实现工具调用执行器

**Files:**
- Create: `framework/function_calling/executor.py`

**Interfaces:**
- Produces: `ToolExecutor` 类，提供 `execute()` 和 `execute_batch()` 方法
- Consumes: `framework/function_calling/registry.py`

- [x] **Step 1: 编写工具执行器**

```python
from __future__ import annotations
from typing import Dict, Any, List, Optional
from framework.function_calling.registry import tool_registry

class ToolExecutor:
    def __init__(self):
        self._registry = tool_registry

    def execute(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        tool = self._registry.get(tool_name)
        if not tool:
            return {
                "success": False,
                "error": f"工具 {tool_name} 未注册",
            }

        try:
            result = tool.run(**arguments)
            return {
                "success": True,
                "result": result,
                "tool_name": tool_name,
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"工具执行失败: {str(e)}",
                "tool_name": tool_name,
            }

    def execute_batch(self, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        results = []
        for tool_info in tools:
            tool_name = tool_info.get("name")
            arguments = tool_info.get("arguments", {})
            result = self.execute(tool_name, arguments)
            results.append(result)
        return results

tool_executor = ToolExecutor()
```

- [x] **Step 2: 测试工具执行器**

```python
from framework.function_calling.executor import tool_executor
result = tool_executor.execute("document_search", {"query": "测试", "n_results": 2})
print(f"Execute result: {result}")
```
Expected: 输出工具执行结果

- [x] **Step 3: Commit**

```bash
git add framework/function_calling/executor.py
git commit -m "feat: implement tool executor"
```

---

### Task 12: 实现多智能体状态机定义

**Files:**
- Create: `framework/agents/state.py`

**Interfaces:**
- Produces: `MultiAgentState` TypedDict 定义
- Consumes: 无

- [x] **Step 1: 编写状态机定义**

```python
from __future__ import annotations
from typing import TypedDict, Any, Optional

class MultiAgentState(TypedDict):
    request: dict[str, Any]
    data: dict[str, Any]
    model_results: dict[str, Any]
    llm_response: dict[str, Any]
    status: str
    error: Optional[str]
    question_type: Optional[int]
    relevance: Optional[float]
```

- [x] **Step 2: 测试状态定义**

```python
from framework.agents.state import MultiAgentState
state: MultiAgentState = {
    "request": {"question": "测试问题"},
    "data": {},
    "model_results": {},
    "llm_response": {},
    "status": "pending",
    "error": None,
    "question_type": None,
    "relevance": None,
}
print(f"State created: {state}")
```
Expected: 输出状态字典

- [x] **Step 3: Commit**

```bash
git add framework/agents/state.py
git commit -m "feat: implement multi-agent state definition"
```

---

### Task 13: 实现并发模型执行节点

**Files:**
- Create: `framework/agents/nodes.py`

**Interfaces:**
- Produces: 各种节点函数（initialize_state, identify_question_node, route_models, execute_models, aggregate_results, llm_generate, finalize）
- Consumes: `framework/agents/state.py`, `framework/llm/service.py`, `framework/embedding/service.py`, `framework/config.py`

- [x] **Step 1: 编写节点函数**

```python
from __future__ import annotations
import asyncio
import numpy as np
from typing import Any, Tuple, List, Dict, Optional
from .state import MultiAgentState
from framework.config import Config

try:
    from framework.llm.service import llm_service
    LLM_AVAILABLE = True
except ImportError:
    LLM_AVAILABLE = False

try:
    from framework.embedding.service import embedding_service
    EMBEDDING_AVAILABLE = True
except ImportError:
    EMBEDDING_AVAILABLE = False

QUESTION_TYPE_1_KEYWORDS = ["酸化程度", "酸化等级", "pH分级", "酸度", "酸化现状", "土壤酸性", "酸性分级"]
QUESTION_TYPE_2_KEYWORDS = ["治理", "调理剂", "石灰", "碱性材料", "改良", "修复", "调理", "施加", "用量"]
QUESTION_TYPE_3_KEYWORDS = ["氮肥", "pH下降", "施氮", "酸化原因", "氮素", "化肥", "施肥"]

RELEVANCE_KEYWORDS = [
    "酸化", "pH", "土壤", "耕地", "治理", "改良", "氮肥", "施肥",
    "调理剂", "石灰", "碱性", "酸性", "交换性酸", "CEC", "阳离子交换量",
    "土壤质量", "农业", "农田", "养分", "种植", "作物", "水稻", "小麦",
    "玉米", "肥料", "有机质", "酸碱度", "酸性土", "碱性土", "改良剂"
]

REFERENCE_QUESTIONS: Dict[int, List[str]] = {
    1: ["全省耕地酸化程度如何", "土壤pH分布情况", "酸化等级面积统计", "耕地酸性现状评估"],
    2: ["如何治理强酸性耕地", "石灰施用量计算", "土壤改良方案", "酸性土壤调理方法"],
    3: ["施氮肥会导致土壤pH下降多少", "氮肥对土壤酸化的影响", "不同施氮量对pH的影响"],
}

REFERENCE_VECTORS: Dict[int, List[List[float]]] = {}

def _precompute_reference_vectors() -> None:
    if not EMBEDDING_AVAILABLE or not embedding_service.is_available():
        return
    global REFERENCE_VECTORS
    for q_type, questions in REFERENCE_QUESTIONS.items():
        vectors = embedding_service.embed_documents(questions)
        REFERENCE_VECTORS[q_type] = vectors

def _cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    if not vec1 or not vec2 or len(vec1) != len(vec2):
        return 0.0
    v1 = np.array(vec1)
    v2 = np.array(vec2)
    dot_product = np.dot(v1, v2)
    norm1 = np.linalg.norm(v1)
    norm2 = np.linalg.norm(v2)
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return float(dot_product / (norm1 * norm2))

_precompute_reference_vectors()

def check_relevance(question: str) -> float:
    if not question:
        return 0.0
    if EMBEDDING_AVAILABLE and embedding_service.is_available():
        return _check_relevance_vector(question)
    else:
        return _check_relevance_keyword(question)

def _check_relevance_vector(question: str) -> float:
    query_vector = embedding_service.embed_query(question)
    if not query_vector:
        return _check_relevance_keyword(question)
    max_similarity = 0.0
    for q_type, vectors in REFERENCE_VECTORS.items():
        for ref_vector in vectors:
            similarity = _cosine_similarity(query_vector, ref_vector)
            if similarity > max_similarity:
                max_similarity = similarity
    return max_similarity

def _check_relevance_keyword(question: str) -> float:
    if not question:
        return 0.0
    match_count = sum(1 for keyword in RELEVANCE_KEYWORDS if keyword in question)
    return min(match_count / 3, 1.0)

def identify_question_type(question: str) -> tuple[int, float]:
    if EMBEDDING_AVAILABLE and embedding_service.is_available():
        return _identify_question_type_vector(question)
    else:
        return _identify_question_type_keyword(question)

def _identify_question_type_vector(question: str) -> tuple[int, float]:
    query_vector = embedding_service.embed_query(question)
    if not query_vector:
        return _identify_question_type_keyword(question)
    max_similarity = 0.0
    best_type = 1
    for q_type, vectors in REFERENCE_VECTORS.items():
        for ref_vector in vectors:
            similarity = _cosine_similarity(query_vector, ref_vector)
            if similarity > max_similarity:
                max_similarity = similarity
                best_type = q_type
    if max_similarity < 0.5:
        return 0, max_similarity
    return best_type, max_similarity

def _identify_question_type_keyword(question: str) -> tuple[int, float]:
    relevance = _check_relevance_keyword(question)
    if relevance < 0.3:
        return 0, relevance
    if any(keyword in question for keyword in QUESTION_TYPE_1_KEYWORDS):
        return 1, relevance
    elif any(keyword in question for keyword in QUESTION_TYPE_2_KEYWORDS):
        return 2, relevance
    elif any(keyword in question for keyword in QUESTION_TYPE_3_KEYWORDS):
        return 3, relevance
    else:
        return 1, relevance

def initialize_state(state: MultiAgentState) -> MultiAgentState:
    return {
        **state,
        "status": "running",
        "error": None,
        "data": {},
        "model_results": {},
        "llm_response": {},
        "question_type": None,
        "relevance": None,
    }

def identify_question_node(state: MultiAgentState) -> MultiAgentState:
    question = state["request"].get("question", "")
    question_type, relevance = identify_question_type(question)
    return {
        **state,
        "question_type": question_type,
        "relevance": relevance,
        "error": None,
    }

def route_models(state: MultiAgentState) -> str:
    question_type = state["question_type"]
    if question_type == 0:
        return "finalize"
    if question_type == 1:
        return "execute_models"
    elif question_type == 2:
        return "execute_models"
    elif question_type == 3:
        return "execute_models"
    else:
        return "execute_models"

async def _execute_model_concurrent(model_name: str, func: Callable, **kwargs) -> Tuple[str, Any]:
    try:
        result = func(**kwargs)
        return model_name, {"success": True, "result": result}
    except Exception as e:
        return model_name, {"success": False, "error": str(e)}

def execute_models(state: MultiAgentState) -> MultiAgentState:
    question_type = state["question_type"]
    request = state["request"]
    data = state["data"]

    models_to_run = []
    if question_type == 1:
        models_to_run.append("acidification_assessment")
    elif question_type == 2:
        models_to_run.append("acidification_assessment")
        models_to_run.append("lime_calculation")
    elif question_type == 3:
        models_to_run.append("nitrogen_impact")

    max_concurrent = Config.get_max_concurrent()

    async def run_concurrent():
        tasks = []
        for model_name in models_to_run[:max_concurrent]:
            if model_name == "acidification_assessment":
                from framework.domain.assessment.acidification import assess_acidification
                tasks.append(_execute_model_concurrent("acidification_assessment", assess_acidification, soil_data=data))
            elif model_name == "lime_calculation":
                from framework.domain.calculation.lime_calculator import calculate_lime_demand
                tasks.append(_execute_model_concurrent("lime_calculation", calculate_lime_demand,
                    assessment=state.get("model_results", {}).get("acidification_assessment", {}).get("result", {}),
                    target_ph=request.get("target_ph", 6.0),
                    soil_depth=request.get("soil_depth", 20),
                    bulk_density=request.get("bulk_density", 1.2),
                    safety_factor=request.get("safety_factor", 1.3),
                ))
            elif model_name == "nitrogen_impact":
                from framework.domain.assessment.acidification import simulate_nitrogen_impact
                tasks.append(_execute_model_concurrent("nitrogen_impact", simulate_nitrogen_impact,
                    assessment=state.get("model_results", {}).get("acidification_assessment", {}).get("result", {}),
                    current_ph=request.get("current_ph", 5.5),
                    nitrogen_rates=request.get("nitrogen_rates", [0, 50, 100, 150, 200]),
                ))

        results = await asyncio.gather(*tasks)
        return dict(results)

    model_results = asyncio.run(run_concurrent())

    return {
        **state,
        "model_results": model_results,
        "error": None,
    }

def llm_generate(state: MultiAgentState) -> MultiAgentState:
    if not llm_service.is_available():
        return {**state, "llm_response": {}, "error": None}

    question = state["request"].get("question", "")
    question_type = state.get("question_type", 1)

    if not question or question_type not in [1, 2, 3]:
        return {**state, "llm_response": {}, "error": None}

    try:
        prompt = f"基于以下数据回答问题：\n问题类型: {question_type}\n问题: {question}\n数据: {state.get('model_results', {})}"
        llm_result = llm_service.generate(prompt)
        return {**state, "llm_response": llm_result, "error": None}
    except Exception as e:
        return {**state, "llm_response": {"success": False, "error": str(e)}, "error": None}

def aggregate_results(state: MultiAgentState) -> MultiAgentState:
    try:
        question = state["request"].get("question", "")
        question_type = state.get("question_type", 1)
        relevance = state.get("relevance", 0.0)
        model_results = state.get("model_results", {})
        llm_response = state.get("llm_response", {})

        final_result = {
            "status": "ok",
            "question": question,
            "question_type": question_type,
            "relevance": relevance,
            "model_results": model_results,
            "llm_response": llm_response.get("content", ""),
        }

        if question_type == 0:
            final_result["status"] = "rejected"
            final_result["message"] = "问题与耕地土壤酸化主题不相关"

        return {**state, "model_results": final_result, "status": "completed", "error": None}
    except Exception as e:
        return {**state, "status": "failed", "error": str(e)}

def finalize(state: MultiAgentState) -> MultiAgentState:
    return state
```

- [x] **Step 2: 测试节点函数**

```python
from framework.agents.nodes import initialize_state, identify_question_node, identify_question_type
from framework.agents.state import MultiAgentState

state: MultiAgentState = {"request": {"question": "酸化程度"}, "data": {}, "model_results": {}, "llm_response": {}, "status": "pending", "error": None, "question_type": None, "relevance": None}
state = initialize_state(state)
print(f"Initialized: {state}")
state = identify_question_node(state)
print(f"Identified: {state}")
```
Expected: 输出初始化和识别后的状态

- [x] **Step 3: Commit**

```bash
git add framework/agents/nodes.py
git commit -m "feat: implement concurrent model execution nodes"
```

---

### Task 14: 实现多智能体编排器

**Files:**
- Create: `framework/agents/orchestrator.py`

**Interfaces:**
- Produces: `MultiAgentOrchestrator` 类，提供 `run()` 方法
- Consumes: `framework/agents/state.py`, `framework/agents/nodes.py`

- [x] **Step 1: 编写多智能体编排器**

```python
from __future__ import annotations
from typing import Any, Dict
from langgraph.graph import StateGraph, END
from .state import MultiAgentState
from .nodes import (
    initialize_state,
    identify_question_node,
    route_models,
    execute_models,
    llm_generate,
    aggregate_results,
    finalize,
)

class MultiAgentOrchestrator:
    def __init__(self):
        self._graph = None
        self._app = None

    def build_graph(self) -> StateGraph:
        graph = StateGraph(MultiAgentState)

        graph.add_node("initialize", initialize_state)
        graph.add_node("identify_question", identify_question_node)
        graph.add_node("execute_models", execute_models)
        graph.add_node("llm_generate", llm_generate)
        graph.add_node("aggregate_results", aggregate_results)
        graph.add_node("finalize", finalize)

        graph.set_entry_point("initialize")

        graph.add_edge("initialize", "identify_question")

        graph.add_conditional_edges(
            "identify_question",
            route_models,
            {
                "finalize": "finalize",
                "execute_models": "execute_models",
            },
        )

        graph.add_edge("execute_models", "llm_generate")
        graph.add_edge("llm_generate", "aggregate_results")
        graph.add_edge("aggregate_results", "finalize")
        graph.add_edge("finalize", END)

        return graph

    def run(self, request: Dict[str, Any]) -> Dict[str, Any]:
        if self._app is None:
            self._graph = self.build_graph()
            self._app = self._graph.compile()

        initial_state: MultiAgentState = {
            "request": request,
            "data": {},
            "model_results": {},
            "llm_response": {},
            "status": "pending",
            "error": None,
            "question_type": None,
            "relevance": None,
        }

        result = self._app.invoke(initial_state)

        if result["status"] == "completed":
            return result["model_results"]
        else:
            return {
                "status": "error",
                "error": {
                    "code": "PROCESS_FAILED",
                    "message": result.get("error", "流程执行失败"),
                },
            }

multi_agent_orchestrator = MultiAgentOrchestrator()
```

- [x] **Step 2: 测试编排器**

```python
from framework.agents.orchestrator import multi_agent_orchestrator
result = multi_agent_orchestrator.run({"question": "测试问题"})
print(f"Orchestrator result: {result}")
```
Expected: 输出编排器执行结果

- [x] **Step 3: Commit**

```bash
git add framework/agents/orchestrator.py
git commit -m "feat: implement multi-agent orchestrator"
```

---

### Task 15: 迁移数据库模型

**Files:**
- Create: `framework/models/user.py`
- Create: `framework/models/conversation.py`
- Create: `framework/models/message.py`
- Create: `framework/models/document.py`
- Create: `framework/models/__init__.py`

**Interfaces:**
- Produces: SQLAlchemy 模型类
- Consumes: `framework/config.py`

- [x] **Step 1: 创建数据库模型**

```python
# framework/models/__init__.py
from .user import User
from .conversation import Conversation
from .message import Message
from .document import Document
```

```python
# framework/models/user.py
from datetime import datetime
from framework.config import Config
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class User(db.Model):
    __tablename__ = 'sys_user'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True, comment='用户ID')
    username = db.Column(db.String(50), nullable=False, unique=True, comment='用户名')
    password = db.Column(db.String(255), nullable=False, comment='MD5加密后的密码')
    nickname = db.Column(db.String(50), default='', comment='用户昵称')
    role = db.Column(db.String(50), nullable=False, default='user', comment='角色编码')
    status = db.Column(db.SmallInteger, default=1, comment='状态: 1-正常, 0-禁用')
    create_time = db.Column(db.DateTime, default=db.func.current_timestamp(), comment='创建时间')
    update_time = db.Column(db.DateTime, default=db.func.current_timestamp(), onupdate=db.func.current_timestamp(), comment='更新时间')

    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'nickname': self.nickname,
            'role': self.role,
            'status': self.status,
            'create_time': self.create_time.strftime('%Y-%m-%d %H:%M:%S') if self.create_time else None,
            'update_time': self.update_time.strftime('%Y-%m-%d %H:%M:%S') if self.update_time else None
        }

    def is_admin(self):
        return self.role == 'admin'
```

```python
# framework/models/conversation.py
from datetime import datetime
from .user import db

class Conversation(db.Model):
    __tablename__ = 'kb_conversation'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True, comment='对话ID')
    user_id = db.Column(db.Integer, nullable=False, comment='创建者用户ID')
    title = db.Column(db.String(255), default='新对话', comment='对话标题')
    create_time = db.Column(db.DateTime, default=db.func.current_timestamp(), comment='创建时间')
    update_time = db.Column(db.DateTime, default=db.func.current_timestamp(), onupdate=db.func.current_timestamp(), comment='更新时间')

    messages = db.relationship(
        'Message',
        backref='conversation',
        lazy=True,
        cascade='all, delete-orphan',
        order_by='Message.create_time'
    )

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'title': self.title,
            'create_time': self.create_time.strftime('%Y-%m-%d %H:%M:%S') if self.create_time else None,
            'update_time': self.update_time.strftime('%Y-%m-%d %H:%M:%S') if self.update_time else None
        }
```

```python
# framework/models/message.py
from datetime import datetime
from .user import db

class Message(db.Model):
    __tablename__ = 'kb_message'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True, comment='消息ID')
    conversation_id = db.Column(db.Integer, db.ForeignKey('kb_conversation.id'), nullable=False, comment='所属对话ID')
    role = db.Column(db.String(20), nullable=False, comment='消息角色: user/assistant')
    content = db.Column(db.Text, nullable=False, comment='消息内容')
    sources = db.Column(db.JSON, default=None, comment='AI回答的引用来源')
    create_time = db.Column(db.DateTime, default=db.func.current_timestamp(), comment='发送时间')

    def to_dict(self):
        return {
            'id': self.id,
            'conversation_id': self.conversation_id,
            'role': self.role,
            'content': self.content,
            'sources': self.sources,
            'create_time': self.create_time.strftime('%Y-%m-%d %H:%M:%S') if self.create_time else None
        }
```

```python
# framework/models/document.py
from datetime import datetime
from .user import db

class Document(db.Model):
    __tablename__ = 'kb_document'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True, comment='文档ID')
    doc_name = db.Column(db.String(255), nullable=False, comment='文档原始文件名')
    file_path = db.Column(db.String(500), nullable=False, comment='文件存储相对路径')
    file_type = db.Column(db.String(20), nullable=False, comment='文件类型')
    file_size = db.Column(db.BigInteger, default=0, comment='文件大小(字节)')
    chunk_count = db.Column(db.Integer, default=0, comment='文本分割后的片段数量')
    status = db.Column(db.SmallInteger, default=1, comment='状态')
    category = db.Column(db.String(30), default='other', comment='文档分类')
    treatment_type = db.Column(db.String(30), nullable=True, comment='治理类型')
    create_by = db.Column(db.Integer, nullable=False, comment='上传者用户ID')
    create_time = db.Column(db.DateTime, default=db.func.current_timestamp(), comment='上传时间')
    update_time = db.Column(db.DateTime, default=db.func.current_timestamp(), onupdate=db.func.current_timestamp(), comment='更新时间')

    def to_dict(self):
        return {
            'id': self.id,
            'doc_name': self.doc_name,
            'file_type': self.file_type,
            'file_size': self.file_size,
            'chunk_count': self.chunk_count,
            'status': self.status,
            'category': self.category,
            'treatment_type': self.treatment_type,
            'create_by': self.create_by,
            'create_time': self.create_time.strftime('%Y-%m-%d %H:%M:%S') if self.create_time else None,
            'update_time': self.update_time.strftime('%Y-%m-%d %H:%M:%S') if self.update_time else None
        }
```

- [x] **Step 2: 测试模型导入**

```python
from framework.models import User, Conversation, Message, Document
print("Models imported successfully")
```
Expected: 输出成功信息

- [x] **Step 3: Commit**

```bash
git add framework/models/
git commit -m "feat: migrate database models from org-backend"
```

---

### Task 16: 实现 JWT 认证模块

**Files:**
- Create: `framework/auth/jwt.py`
- Create: `framework/auth/decorators.py`

**Interfaces:**
- Produces: JWT 认证工具函数和装饰器
- Consumes: `framework/config.py`, `framework/models/user.py`

- [x] **Step 1: 编写 JWT 认证模块**

```python
# framework/auth/jwt.py
import hashlib
from flask_jwt_extended import create_access_token, verify_jwt_in_request, get_jwt_identity

def md5_hash(password: str) -> str:
    return hashlib.md5(password.encode('utf-8')).hexdigest()

def generate_token(user_id: int) -> str:
    return create_access_token(identity=str(user_id))

def get_current_user_id() -> int:
    verify_jwt_in_request()
    return int(get_jwt_identity())
```

```python
# framework/auth/decorators.py
from functools import wraps
from flask_jwt_extended import jwt_required, get_jwt_identity
from framework.models.user import User, db

def admin_required(fn):
    @wraps(fn)
    @jwt_required()
    def wrapper(*args, **kwargs):
        current_user_id = get_jwt_identity()
        user = User.query.get(current_user_id)
        if not user or not user.is_admin():
            from flask import jsonify
            return jsonify({"status": "error", "message": "权限不足"}), 403
        return fn(*args, **kwargs)
    return wrapper
```

- [x] **Step 2: 测试认证模块**

```python
from framework.auth.jwt import md5_hash, generate_token
print(f"MD5 test: {md5_hash('test')}")
```
Expected: 输出 MD5 哈希值

- [x] **Step 3: Commit**

```bash
git add framework/auth/
git commit -m "feat: implement JWT authentication module"
```

---

### Task 17: 实现文件上传管理

**Files:**
- Create: `framework/upload/file_upload.py`
- Create: `framework/upload/document_parser.py`

**Interfaces:**
- Produces: 文件上传和文档解析功能
- Consumes: `framework/config.py`, `framework/vector_store/chroma_store.py`

- [x] **Step 1: 编写文件上传模块**

```python
# framework/upload/file_upload.py
import os
import uuid
from flask import request
from framework.config import Config

ALLOWED_EXTENSIONS = {'txt', 'md', 'pdf', 'docx', 'xlsx', 'xls'}

def allowed_file(filename: str) -> bool:
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def save_uploaded_file(file) -> tuple[str, str]:
    os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)

    filename = file.filename
    extension = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
    new_filename = f"{uuid.uuid4().hex}.{extension}"
    file_path = os.path.join(Config.UPLOAD_FOLDER, new_filename)

    file.save(file_path)

    return new_filename, file_path

def get_file_type(filename: str) -> str:
    extension = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
    type_map = {
        'txt': 'txt',
        'md': 'md',
        'pdf': 'pdf',
        'docx': 'docx',
        'xlsx': 'xlsx',
        'xls': 'xlsx',
    }
    return type_map.get(extension, 'other')
```

```python
# framework/upload/document_parser.py
from __future__ import annotations
import os
from typing import Optional

def parse_document(file_path: str, file_type: str) -> Optional[str]:
    if file_type == 'txt':
        return _parse_txt(file_path)
    elif file_type == 'md':
        return _parse_txt(file_path)
    elif file_type == 'pdf':
        return _parse_pdf(file_path)
    elif file_type == 'docx':
        return _parse_docx(file_path)
    elif file_type == 'xlsx':
        return _parse_excel(file_path)
    else:
        return None

def _parse_txt(file_path: str) -> str:
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        return f.read()

def _parse_pdf(file_path: str) -> str:
    try:
        from PyPDF2 import PdfReader
        reader = PdfReader(file_path)
        text = ""
        for page in reader.pages:
            text += page.extract_text() + "\n"
        return text
    except Exception:
        return ""

def _parse_docx(file_path: str) -> str:
    try:
        from docx import Document
        doc = Document(file_path)
        return "\n".join([para.text for para in doc.paragraphs])
    except Exception:
        return ""

def _parse_excel(file_path: str) -> str:
    try:
        import pandas as pd
        df = pd.read_excel(file_path)
        return df.to_string()
    except Exception:
        return ""
```

- [x] **Step 2: 测试文件上传模块**

```python
from framework.upload.file_upload import allowed_file, get_file_type
print(f"Allowed pdf: {allowed_file('test.pdf')}")
print(f"File type: {get_file_type('test.pdf')}")
```
Expected: 输出 True 和 pdf

- [x] **Step 3: Commit**

```bash
git add framework/upload/
git commit -m "feat: implement file upload and document parsing modules"
```

---

### Task 18: 迁移专业模型

**Files:**
- Create: `framework/domain/assessment/acidification.py`
- Create: `framework/domain/calculation/lime_calculator.py`
- Create: `framework/domain/data/soil_data_loader.py`

**Interfaces:**
- Produces: 六个专业模型（酸化评估、石灰计算、土壤数据加载、其他四个模型）
- Consumes: `framework/config.py`

- [x] **Step 1: 迁移酸化评估模型**

```python
# framework/domain/assessment/acidification.py
from __future__ import annotations
from typing import Any, Dict, List
import numpy as np
import pandas as pd

def assess_acidification(soil_data: Dict[str, Any]) -> Dict[str, Any]:
    third_survey_df = soil_data.get("third_survey", pd.DataFrame())
    formula_df = soil_data.get("formula_fertilization", pd.DataFrame())
    combined_df = pd.concat([third_survey_df, formula_df], ignore_index=True)

    if combined_df.empty:
        return {
            "summary": {"total_points": 0, "normal_count": 0, "light_count": 0, "moderate_count": 0, "severe_count": 0, "very_severe_count": 0},
            "stats": {"ph_mean": None, "ph_min": None, "ph_max": None, "exchangeable_acid_mean": None},
        }

    ph_grades = classify_ph(combined_df["pH"])
    acid_grades = classify_exchangeable_acid(combined_df.get("交换性酸", pd.Series()))
    al_grades = classify_exchangeable_al(combined_df.get("交换性Al", pd.Series()))
    cec_grades = classify_cec(combined_df.get("CEC", pd.Series()))

    combined_df["pH分级"] = ph_grades
    combined_df["交换性酸分级"] = acid_grades
    combined_df["交换性Al分级"] = al_grades
    combined_df["CEC分级"] = cec_grades
    combined_df["综合分级"] = combined_df.apply(calculate_comprehensive_grade, axis=1)

    summary = {
        "total_points": len(combined_df),
        "normal_count": int((combined_df["综合分级"] == "正常").sum()),
        "light_count": int((combined_df["综合分级"] == "轻度").sum()),
        "moderate_count": int((combined_df["综合分级"] == "中度").sum()),
        "severe_count": int((combined_df["综合分级"] == "重度").sum()),
        "very_severe_count": int((combined_df["综合分级"] == "严重").sum()),
    }

    stats = {
        "ph_mean": float(combined_df["pH"].mean()),
        "ph_min": float(combined_df["pH"].min()),
        "ph_max": float(combined_df["pH"].max()),
        "exchangeable_acid_mean": float(combined_df["交换性酸"].mean()),
        "cec_mean": float(combined_df["CEC"].mean()),
    }

    return {"summary": summary, "stats": stats}

def classify_ph(ph_values: pd.Series) -> pd.Series:
    conditions = [ph_values < 4.5, (ph_values >= 4.5) & (ph_values < 5.0), (ph_values >= 5.0) & (ph_values < 5.5), (ph_values >= 5.5) & (ph_values < 6.0), ph_values >= 6.0]
    choices = ["严重", "重度", "中度", "轻度", "正常"]
    return np.select(conditions, choices, default="未知")

def classify_exchangeable_acid(acid_values: pd.Series) -> pd.Series:
    conditions = [acid_values < 1.0, (acid_values >= 1.0) & (acid_values < 2.0), acid_values >= 2.0]
    choices = ["低", "中", "高"]
    return np.select(conditions, choices, default="未知")

def classify_exchangeable_al(al_values: pd.Series) -> pd.Series:
    conditions = [al_values < 0.5, (al_values >= 0.5) & (al_values < 1.5), al_values >= 1.5]
    choices = ["低", "中", "高"]
    return np.select(conditions, choices, default="未知")

def classify_cec(cec_values: pd.Series) -> pd.Series:
    conditions = [cec_values < 10, (cec_values >= 10) & (cec_values < 20), cec_values >= 20]
    choices = ["低", "中", "高"]
    return np.select(conditions, choices, default="未知")

def calculate_comprehensive_grade(row: pd.Series) -> str:
    grade_scores = {"正常": 0, "轻度": 1, "中度": 2, "重度": 3, "严重": 4}
    acid_scores = {"低": 0, "中": 2, "高": 4}
    al_scores = {"低": 0, "中": 2, "高": 4}
    cec_scores = {"高": 0, "中": 1, "低": 2}

    ph_score = grade_scores.get(row.get("pH分级", "未知"), 2)
    acid_score = acid_scores.get(row.get("交换性酸分级", "未知"), 2)
    al_score = al_scores.get(row.get("交换性Al分级", "未知"), 2)
    cec_score = cec_scores.get(row.get("CEC分级", "未知"), 1)

    total_score = ph_score * 0.4 + acid_score * 0.25 + al_score * 0.15 + cec_score * 0.2

    if total_score < 1.0: return "正常"
    elif total_score < 2.0: return "轻度"
    elif total_score < 3.0: return "中度"
    elif total_score < 3.8: return "重度"
    else: return "严重"

def simulate_scenarios(assessment: Dict[str, Any], soil_depth: float = 20, bulk_density: float = 1.2, safety_factor: float = 1.3) -> Dict[str, Any]:
    scenarios = {"light": {"target_ph": 5.5, "name": "轻度调控"}, "moderate": {"target_ph": 5.8, "name": "中度调控"}, "deep": {"target_ph": 6.0, "name": "深度调控"}}
    summary = assessment.get("summary", {})
    total_points = summary.get("total_points", 0)
    results = {}
    for scenario_key, scenario_params in scenarios.items():
        target_ph = scenario_params["target_ph"]
        name = scenario_params["name"]
        results[scenario_key] = {"name": name, "target_ph": target_ph, "total_lime_demand_kg": 0, "affected_area_ratio": 0}
    return results

def simulate_nitrogen_impact(assessment: Dict[str, Any], current_ph: float = 5.5, nitrogen_rates: List[float] = None) -> Dict[str, Any]:
    if nitrogen_rates is None:
        nitrogen_rates = [0, 50, 100, 150, 200]
    predictions = []
    for nitrogen_rate in nitrogen_rates:
        ph_decrease = nitrogen_rate * 0.002
        predictions.append({"nitrogen_rate": nitrogen_rate, "predicted_ph": round(max(3.5, current_ph - ph_decrease), 2), "ph_decrease": round(ph_decrease, 2)})
    return {"current_ph": current_ph, "predictions": predictions}

def prioritize_governance(assessment: Dict[str, Any], area_code: str = "lechang") -> Dict[str, Any]:
    return {"priorities": [], "total_towns": 0}
```

- [x] **Step 2: 迁移石灰计算模型**

```python
# framework/domain/calculation/lime_calculator.py
from __future__ import annotations
from typing import Any, Dict
import numpy as np

def calculate_lime_demand(assessment: Dict[str, Any], target_ph: float = 6.0, soil_depth: float = 20, bulk_density: float = 1.2, safety_factor: float = 1.3) -> Dict[str, Any]:
    stats = assessment.get("stats", {})
    current_ph = stats.get("ph_mean", 5.0)
    exchangeable_acid = stats.get("exchangeable_acid_mean", 1.0)
    cec = stats.get("cec_mean", 15.0)

    method1 = exchangeable_acid * soil_depth * bulk_density * 100 * safety_factor
    method2 = cec * max(0, _calculate_base_saturation(target_ph) - _calculate_base_saturation(current_ph)) * soil_depth * bulk_density * 100 * safety_factor
    method3 = cec * max(0, _estimate_base_saturation(target_ph, cec) - _estimate_base_saturation(current_ph, cec)) * soil_depth * bulk_density * 100 * safety_factor

    return {
        "method_exchangeable_acid": {"name": "交换性酸法", "value": round(method1, 2)},
        "method_target_ph": {"name": "目标pH法", "value": round(method2, 2)},
        "method_cec": {"name": "CEC法", "value": round(method3, 2)},
        "target_ph": target_ph,
        "current_ph": current_ph,
    }

def _calculate_base_saturation(pH: float) -> float:
    return 1.0 / (1.0 + 10 ** (7 - pH))

def _estimate_base_saturation(pH: float, cec: float) -> float:
    if pH >= 7.0: return 1.0
    elif pH <= 4.0: return 0.1
    else: return 0.1 + (pH - 4.0) * 0.3

def check_method_consistency(calculation: Dict[str, Any]) -> Dict[str, Any]:
    values = [calculation.get("method_exchangeable_acid", {}).get("value", 0), calculation.get("method_target_ph", {}).get("value", 0), calculation.get("method_cec", {}).get("value", 0)]
    valid_values = [v for v in values if v > 0]
    if len(valid_values) < 2:
        return {"consistency_level": "low", "recommended_value": max(values)}
    mean_val = np.mean(valid_values)
    std_val = np.std(valid_values)
    cv = std_val / mean_val * 100 if mean_val > 0 else 0
    consistency_level = "high" if cv < 20 else ("medium" if cv < 50 else "low")
    return {"consistency_level": consistency_level, "cv": round(cv, 2), "recommended_value": round(np.median(valid_values), 2)}
```

- [x] **Step 3: 迁移土壤数据加载模块**

```python
# framework/domain/data/soil_data_loader.py
from __future__ import annotations
import os
from typing import Any, Dict
import pandas as pd
import numpy as np

def load_soil_data(area_code: str = "lechang") -> Dict[str, Any]:
    data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", area_code)
    if not os.path.exists(data_dir):
        return _generate_mock_data()
    try:
        third_survey_data = _load_third_survey_data(data_dir)
        formula_data = _generate_formula_mock()
        return {"third_survey": third_survey_data, "formula_fertilization": formula_data}
    except Exception:
        return _generate_mock_data()

def _load_third_survey_data(data_dir: str) -> pd.DataFrame:
    topsoil_path = os.path.join(data_dir, "01_乐昌市土壤三普表层土点位数据_fake.xlsx")
    if os.path.exists(topsoil_path):
        return pd.read_excel(topsoil_path)
    return pd.DataFrame()

def _generate_mock_data() -> Dict[str, Any]:
    return {"third_survey": _generate_third_survey_mock(), "formula_fertilization": _generate_formula_mock()}

def _generate_third_survey_mock() -> pd.DataFrame:
    np.random.seed(42)
    n_points = 623
    ph_values = np.random.uniform(4.0, 7.0, n_points)
    return pd.DataFrame({
        "pH": ph_values.round(2),
        "交换性酸": np.random.uniform(0.5, 3.0, n_points).round(2),
        "交换性Al": np.random.uniform(0.1, 2.5, n_points).round(2),
        "交换性H": np.random.uniform(0.05, 0.8, n_points).round(2),
        "CEC": np.random.uniform(8.0, 25.0, n_points).round(2),
        "容重": np.random.uniform(1.0, 1.4, n_points).round(2),
        "有机质": np.random.uniform(10.0, 30.0, n_points).round(2),
    })

def _generate_formula_mock() -> pd.DataFrame:
    np.random.seed(123)
    n_points = 1256
    ph_values = np.random.uniform(4.0, 7.0, n_points)
    return pd.DataFrame({
        "pH": ph_values.round(2),
        "交换性酸": np.random.uniform(0.5, 3.0, n_points).round(2),
        "交换性Al": np.random.uniform(0.1, 2.5, n_points).round(2),
        "交换性H": np.random.uniform(0.05, 0.8, n_points).round(2),
        "CEC": np.random.uniform(8.0, 25.0, n_points).round(2),
        "容重": np.random.uniform(1.0, 1.4, n_points).round(2),
        "有机质": np.random.uniform(10.0, 30.0, n_points).round(2),
    })
```

- [x] **Step 4: Commit**

```bash
git add framework/domain/
git commit -m "feat: migrate professional models from AI_culti_demo"
```

---

### Task 19: 创建 Flask 应用入口

**Files:**
- Create: `framework/api/app.py`

**Interfaces:**
- Produces: Flask 应用实例，注册所有蓝图和扩展
- Consumes: `framework/config.py`, `framework/models/user.py`, `framework/api/routes/`

- [x] **Step 1: 创建 Flask 应用**

```python
from flask import Flask
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from framework.config import Config, config_map
from framework.models.user import db
from framework.api.routes.auth import auth_bp
from framework.api.routes.chat import chat_bp
from framework.api.routes.models import models_bp
from framework.api.routes.docs import docs_bp
from framework.api.routes.county import county_bp

def create_app(config_name: str = 'default') -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_map[config_name])

    CORS(app)
    JWTManager(app)
    db.init_app(app)

    app.register_blueprint(auth_bp, url_prefix='/api/v1/auth')
    app.register_blueprint(chat_bp, url_prefix='/api/v1/chat')
    app.register_blueprint(models_bp, url_prefix='/api/v1/models')
    app.register_blueprint(docs_bp, url_prefix='/api/v1/docs')
    app.register_blueprint(county_bp, url_prefix='/api/v1/county')

    @app.route('/')
    def index():
        return {"status": "ok", "message": "Unified Framework API"}

    return app

if __name__ == '__main__':
    app = create_app()
    app.run(host='0.0.0.0', port=5000)
```

- [x] **Step 2: Commit**

```bash
git add framework/api/app.py
git commit -m "feat: create Flask application entry"
```

---

### Task 20: 创建 API 路由

**Files:**
- Create: `framework/api/routes/auth.py`
- Create: `framework/api/routes/chat.py`
- Create: `framework/api/routes/models.py`
- Create: `framework/api/routes/docs.py`
- Create: `framework/api/routes/county.py`

**Interfaces:**
- Produces: RESTful API 端点
- Consumes: `framework/models/`, `framework/rag/chain.py`, `framework/agents/orchestrator.py`, `framework/upload/`

- [x] **Step 1: 创建认证路由**

```python
# framework/api/routes/auth.py
import hashlib
from flask import Blueprint, request, jsonify
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity
from framework.models.user import User, db

auth_bp = Blueprint('auth', __name__)

def md5_hash(password: str) -> str:
    return hashlib.md5(password.encode('utf-8')).hexdigest()

@auth_bp.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    if not data:
        return jsonify({"status": "error", "message": "请求参数不能为空"}), 400
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    if not username or not password:
        return jsonify({"status": "error", "message": "用户名和密码不能为空"}), 400
    user = User.query.filter_by(username=username).first()
    if not user or user.password != md5_hash(password):
        return jsonify({"status": "error", "message": "用户名或密码错误"}), 401
    access_token = create_access_token(identity=str(user.id))
    return jsonify({"status": "ok", "data": {"token": access_token, "user": user.to_dict()}, "message": "登录成功"})

@auth_bp.route('/register', methods=['POST'])
@jwt_required()
def register():
    current_user_id = get_jwt_identity()
    current_user = User.query.get(current_user_id)
    if not current_user or not current_user.is_admin():
        return jsonify({"status": "error", "message": "权限不足"}), 403
    data = request.get_json()
    if not data:
        return jsonify({"status": "error", "message": "请求参数不能为空"}), 400
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    if not username or not password:
        return jsonify({"status": "error", "message": "用户名和密码不能为空"}), 400
    if User.query.filter_by(username=username).first():
        return jsonify({"status": "error", "message": "用户名已存在"}), 400
    new_user = User(username=username, password=md5_hash(password), nickname=data.get('nickname', username), role=data.get('role', 'user'))
    db.session.add(new_user)
    db.session.commit()
    return jsonify({"status": "ok", "data": new_user.to_dict(), "message": "用户创建成功"})

@auth_bp.route('/me', methods=['GET'])
@jwt_required()
def get_current_user():
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    if not user:
        return jsonify({"status": "error", "message": "用户不存在"}), 404
    return jsonify({"status": "ok", "data": user.to_dict()})
```

- [x] **Step 2: 创建聊天路由**

```python
# framework/api/routes/chat.py
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from framework.models.conversation import Conversation
from framework.models.message import Message
from framework.models.user import db
from framework.rag.chain import rag_chain

chat_bp = Blueprint('chat', __name__)

@chat_bp.route('/conversations', methods=['GET'])
@jwt_required()
def get_conversations():
    user_id = get_jwt_identity()
    conversations = Conversation.query.filter_by(user_id=user_id).order_by(Conversation.update_time.desc()).all()
    return jsonify({"status": "ok", "data": [c.to_dict() for c in conversations]})

@chat_bp.route('/conversations', methods=['POST'])
@jwt_required()
def create_conversation():
    user_id = get_jwt_identity()
    data = request.get_json()
    title = data.get('title', '新对话')
    conversation = Conversation(user_id=user_id, title=title)
    db.session.add(conversation)
    db.session.commit()
    return jsonify({"status": "ok", "data": conversation.to_dict(), "message": "对话创建成功"})

@chat_bp.route('/conversations/<int:id>', methods=['DELETE'])
@jwt_required()
def delete_conversation(id):
    user_id = get_jwt_identity()
    conversation = Conversation.query.filter_by(id=id, user_id=user_id).first()
    if not conversation:
        return jsonify({"status": "error", "message": "对话不存在"}), 404
    db.session.delete(conversation)
    db.session.commit()
    return jsonify({"status": "ok", "message": "对话删除成功"})

@chat_bp.route('/conversations/<int:id>/messages', methods=['GET'])
@jwt_required()
def get_messages(id):
    user_id = get_jwt_identity()
    conversation = Conversation.query.filter_by(id=id, user_id=user_id).first()
    if not conversation:
        return jsonify({"status": "error", "message": "对话不存在"}), 404
    return jsonify({"status": "ok", "data": [m.to_dict() for m in conversation.messages]})

@chat_bp.route('/', methods=['POST'])
@jwt_required()
def chat():
    user_id = get_jwt_identity()
    data = request.get_json()
    conversation_id = data.get('conversation_id')
    message = data.get('message', '')

    if conversation_id:
        conversation = Conversation.query.filter_by(id=conversation_id, user_id=user_id).first()
        if not conversation:
            return jsonify({"status": "error", "message": "对话不存在"}), 404
    else:
        conversation = Conversation(user_id=user_id, title=message[:50] if message else '新对话')
        db.session.add(conversation)
        db.session.commit()

    user_message = Message(conversation_id=conversation.id, role='user', content=message)
    db.session.add(user_message)
    db.session.commit()

    result = rag_chain.chat(message)

    assistant_message = Message(conversation_id=conversation.id, role='assistant', content=result.get('answer', ''), sources=result.get('sources'))
    db.session.add(assistant_message)
    db.session.commit()

    return jsonify({"status": "ok", "data": {"answer": result.get('answer', ''), "sources": result.get('sources', []), "message_id": assistant_message.id}})
```

- [x] **Step 3: 创建模型执行路由**

```python
# framework/api/routes/models.py
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from framework.agents.orchestrator import multi_agent_orchestrator

models_bp = Blueprint('models', __name__)

@models_bp.route('/', methods=['GET'])
@jwt_required()
def get_models():
    models = [
        {"name": "acidification_assessment", "description": "酸化程度评估模型"},
        {"name": "lime_calculation", "description": "石灰需求量计算模型"},
        {"name": "nitrogen_impact", "description": "氮肥影响模拟模型"},
    ]
    return jsonify({"status": "ok", "data": models})

@models_bp.route('/run', methods=['POST'])
@jwt_required()
def run_model():
    data = request.get_json()
    question = data.get('question', '')
    if not question:
        return jsonify({"status": "error", "message": "问题不能为空"}), 400

    result = multi_agent_orchestrator.run({"question": question})
    return jsonify(result)
```

- [x] **Step 4: 创建文档管理路由**

```python
# framework/api/routes/docs.py
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from framework.models.document import Document
from framework.models.user import db
from framework.upload.file_upload import allowed_file, save_uploaded_file, get_file_type
from framework.upload.document_parser import parse_document
from framework.vector_store.chroma_store import vector_store

docs_bp = Blueprint('docs', __name__)

@docs_bp.route('/', methods=['GET'])
@jwt_required()
def get_documents():
    user_id = get_jwt_identity()
    documents = Document.query.filter_by(create_by=user_id).all()
    return jsonify({"status": "ok", "data": [d.to_dict() for d in documents]})

@docs_bp.route('/upload', methods=['POST'])
@jwt_required()
def upload_document():
    user_id = get_jwt_identity()
    if 'file' not in request.files:
        return jsonify({"status": "error", "message": "未选择文件"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"status": "error", "message": "未选择文件"}), 400
    if not allowed_file(file.filename):
        return jsonify({"status": "error", "message": "不支持的文件类型"}), 400

    new_filename, file_path = save_uploaded_file(file)
    file_type = get_file_type(file.filename)

    content = parse_document(file_path, file_type)
    if content:
        chunks = [content[i:i+800] for i in range(0, len(content), 800)]
        metadatas = [{"source": file.filename} for _ in chunks]
        vector_store.add_documents(chunks, metadatas)

    document = Document(
        doc_name=file.filename,
        file_path=new_filename,
        file_type=file_type,
        file_size=os.path.getsize(file_path),
        chunk_count=len(chunks) if content else 0,
        status=1,
        create_by=user_id,
    )
    db.session.add(document)
    db.session.commit()

    return jsonify({"status": "ok", "data": document.to_dict(), "message": "文档上传成功"})

@docs_bp.route('/<int:id>', methods=['GET'])
@jwt_required()
def get_document(id):
    user_id = get_jwt_identity()
    document = Document.query.filter_by(id=id, create_by=user_id).first()
    if not document:
        return jsonify({"status": "error", "message": "文档不存在"}), 404
    return jsonify({"status": "ok", "data": document.to_dict()})

@docs_bp.route('/<int:id>', methods=['DELETE'])
@jwt_required()
def delete_document(id):
    user_id = get_jwt_identity()
    document = Document.query.filter_by(id=id, create_by=user_id).first()
    if not document:
        return jsonify({"status": "error", "message": "文档不存在"}), 404

    vector_store.delete_by_source(document.doc_name)
    db.session.delete(document)
    db.session.commit()

    return jsonify({"status": "ok", "message": "文档删除成功"})
```

- [x] **Step 5: 创建县域诊断路由**

```python
# framework/api/routes/county.py
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from framework.domain.data.soil_data_loader import load_soil_data
from framework.domain.assessment.acidification import assess_acidification
from framework.domain.calculation.lime_calculator import calculate_lime_demand

county_bp = Blueprint('county', __name__)

@county_bp.route('/overview', methods=['GET'])
@jwt_required()
def get_overview():
    area_code = request.args.get('area_code', 'lechang')
    soil_data = load_soil_data(area_code)
    assessment = assess_acidification(soil_data)
    return jsonify({"status": "ok", "data": {"area": area_code, "assessment": assessment}})

@county_bp.route('/diagnose', methods=['POST'])
@jwt_required()
def diagnose():
    data = request.get_json()
    area_code = data.get('area_code', 'lechang')
    target_ph = data.get('target_ph', 6.0)

    soil_data = load_soil_data(area_code)
    assessment = assess_acidification(soil_data)
    calculation = calculate_lime_demand(assessment, target_ph=target_ph)

    return jsonify({"status": "ok", "data": {"area": area_code, "assessment": assessment, "calculation": calculation}})
```

- [x] **Step 6: Commit**

```bash
git add framework/api/routes/
git commit -m "feat: create API routes"
```

---

## 计划完成

计划已创建完成，包含以下主要任务：

1. **框架搭建** (Tasks 1-3) - 目录结构、配置管理、依赖更新
2. **核心服务** (Tasks 4-7) - LLM服务、Embedding服务、向量存储、RAG链
3. **函数调用系统** (Tasks 8-11) - 工具注册表、LangChain Tools、自定义工具、执行器
4. **多智能体编排器** (Tasks 12-14) - 状态定义、并发节点、编排器
5. **数据库模型** (Task 15) - 用户、对话、消息、文档模型
6. **认证系统** (Task 16) - JWT认证、装饰器
7. **文件上传** (Task 17) - 文件上传、文档解析
8. **专业模型** (Task 18) - 酸化评估、石灰计算、土壤数据加载
9. **API层** (Tasks 19-20) - Flask应用、认证路由、聊天路由、模型路由、文档路由、县域路由

接下来需要用户选择执行方式：

**1. Subagent-Driven (推荐)** - 每个任务派一个独立 subagent 执行，逐任务审查
**2. Inline Execution** - 在当前会话中使用 executing-plans 批量执行

请选择执行方式。