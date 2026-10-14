import os
import secrets
import sys
from typing import Optional

ENV = os.environ.get('FLASK_ENV') or os.environ.get('ENV') or 'development'

def _warn(prompt: str):
    """打印到 stderr，避免污染标准输出并随正常日志一起可见。"""
    print(prompt, file=sys.stderr, flush=True)

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY')
    if not SECRET_KEY:
        if ENV == 'production':
            raise ValueError("SECRET_KEY must be set in production environment")
        SECRET_KEY = 'dev-secret-key-change-in-production'

    # --- 数据库连接参数（可被环境变量覆盖）---
    DB_HOST = os.environ.get('DB_HOST') or 'localhost'
    DB_PORT = int(os.environ.get('DB_PORT') or 5432)
    DB_USER = os.environ.get('DB_USER') or 'postgres'
    DB_PASSWORD = os.environ.get('DB_PASSWORD') or '123456'
    DB_NAME = os.environ.get('DB_NAME') or 'db_enterprise_qa'

    # --- 防御：连接参数非 ASCII 校验 ---
    # 服务器若通过环境变量 / GBK 编码的 .env 注入中文或乱码，
    # psycopg2 会在连接前报 UnicodeDecodeError（如 0xd6 字节），
    # 这里启动时提前暴露原因并打印当前生效参数，便于一眼定位。
    _db_fields = [
        ("DB_HOST", DB_HOST),
        ("DB_PORT", str(DB_PORT)),
        ("DB_USER", DB_USER),
        ("DB_NAME", DB_NAME),
    ]
    for _var, _val in _db_fields:
        try:
            _val.encode("ascii")
        except UnicodeEncodeError:
            raise ValueError(
                f"数据库配置 {_var} 含非 ASCII 字符（可能被 GBK 编码污染）：{_val!r}。"
                "请改为纯 ASCII 值，并确保环境变量或 .env 以 UTF-8 编码保存。"
            )
    try:
        DB_PASSWORD.encode("ascii")
    except UnicodeEncodeError:
        raise ValueError(
            f"数据库配置 DB_PASSWORD 含非 ASCII 字符（可能被 GBK 编码污染）：{DB_PASSWORD!r}。"
            "请改为纯 ASCII 密码。"
        )
    _warn(
        f"[config] 数据库连接生效参数 -> user: {DB_USER} | host: {DB_HOST}:{DB_PORT} | "
        f"db: {DB_NAME}"
    )

    SQLALCHEMY_DATABASE_URI = (
        f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    )
    COMPREHENSIVE_WORKFLOW_MODE = os.environ.get(
        "COMPREHENSIVE_WORKFLOW_MODE", "off"
    ).lower()
    if COMPREHENSIVE_WORKFLOW_MODE not in {"off", "shadow", "enabled"}:
        raise ValueError(
            "COMPREHENSIVE_WORKFLOW_MODE must be off, shadow, or enabled"
        )
    COMPREHENSIVE_ALLOWED_USER_IDS = tuple(
        int(value)
        for value in os.environ.get(
            "COMPREHENSIVE_ALLOWED_USER_IDS", ""
        ).split(",")
        if value.strip()
    )
    LANGGRAPH_CHECKPOINT_URI = os.environ.get(
        "LANGGRAPH_CHECKPOINT_URI", SQLALCHEMY_DATABASE_URI
    )
    LANGGRAPH_CHECKPOINT_AUTO_SETUP = (
        os.environ.get("LANGGRAPH_CHECKPOINT_AUTO_SETUP", "false").lower()
        == "true"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_size': 20,
        'max_overflow': 50,
        'pool_timeout': 30,
        'pool_recycle': 1800,
    }

    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY') or SECRET_KEY
    JWT_ACCESS_TOKEN_EXPIRES = 24 * 60 * 60

    SILICONFLOW_API_KEY = os.environ.get('SILICONFLOW_API_KEY') or 'sk-ticprznnmtypnvwisfdmftieuaqiyzgjuurwuzvqbiaotezb'
    SILICONFLOW_CHAT_MODEL = os.environ.get('SILICONFLOW_CHAT_MODEL') or 'deepseek-ai/DeepSeek-V3'
    SILICONFLOW_EMBED_MODEL = os.environ.get('SILICONFLOW_EMBED_MODEL') or 'BAAI/bge-m3'
    SILICONFLOW_BASE_URL = os.environ.get('SILICONFLOW_BASE_URL') or 'https://api.siliconflow.cn/v1'
    # 聊天接口的整体时延由单次最终总结调用控制。DeepSeek-V4-Flash 公测期响应较慢，
    # 20s 会频繁触发超时降级导致"对话无法使用"；放宽到 90s 并允许 1 次重试。
    SILICONFLOW_LLM_TIMEOUT = float(os.environ.get('SILICONFLOW_LLM_TIMEOUT') or 90)
    SILICONFLOW_LLM_MAX_RETRIES = int(os.environ.get('SILICONFLOW_LLM_MAX_RETRIES') or 1)

    CHROMA_PERSIST_DIR = os.environ.get('CHROMA_PERSIST_DIR') or './chroma_db'
    CHROMA_COLLECTION_NAME = os.environ.get('CHROMA_COLLECTION_NAME') or 'enterprise_kb'

    UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER') or './uploads'
    MAX_CONTENT_LENGTH = 200 * 1024 * 1024  # 200MB，对齐 MAX_DATA_IMPORT_SIZE，允许数据导入大文件

    CHUNK_SIZE = 800
    CHUNK_OVERLAP = 150
    PDF_OCR_THRESHOLD = 50  # 平均字符/页阈值，低于则触发 OCR 主路径
    RETRIEVAL_TOP_K = 5
    RECALL_TOP_K = int(os.environ.get("RECALL_TOP_K") or 20)      # 混合召回阶段候选数
    RRF_K = int(os.environ.get("RRF_K") or 60)                    # RRF 平滑常数
    HYBRID_SEARCH_ENABLED = os.environ.get("HYBRID_SEARCH_ENABLED", "true").lower() == "true"
    RERANK_ENABLED = os.environ.get("RERANK_ENABLED", "true").lower() == "true"
    RERANK_MODEL = os.environ.get("RERANK_MODEL") or "BAAI/bge-reranker-v2-m3"
    RERANK_TIMEOUT = int(os.environ.get("RERANK_TIMEOUT") or 30)

    MAX_CONCURRENT_MODELS = int(os.environ.get('MAX_CONCURRENT_MODELS') or '0')

    # 数据导入接口配置
    MAX_DATA_IMPORT_SIZE = 200 * 1024 * 1024  # 200MB
    DATA_IMPORT_TIMEOUT = 600  # 秒
    DATA_IMPORT_TARGETS = {
        'csv': 'data/farmland_diagnosis',
        'shapefile': 'data/farmland_stability',
        'dat': 'bin/farmland_quality_eval',
    }
    BACKUP_RETENTION_COUNT = 3

    # 路由模式开关：llm（默认，LLM 初判+回退）/ keyword（纯关键词+向量）
    # 受 2026-08-11 llm-routing-judgment 特性引入；test_llm_routing.py 依赖此字段存在
    ROUTING_MODE = os.environ.get("ROUTING_MODE", "llm")

    # Function calling 配置（2026-08-22 function-calling-refactor 引入）
    # FUNCTION_CALLING_ENABLED=false 时 execute_models 直接走旧关键词路由
    FUNCTION_CALLING_ENABLED = os.environ.get("FUNCTION_CALLING_ENABLED", "true").lower() == "true"
    # 多轮工具调用最大迭代数
    FUNCTION_CALLING_MAX_ITERATIONS = int(os.environ.get("FUNCTION_CALLING_MAX_ITERATIONS") or 3)
    # SiliconFlow 模型是否支持 OpenAI 兼容的 function calling（运行时首次失败后翻为 False）
    SILICONFLOW_SUPPORTS_TOOL_CALLING = os.environ.get("SILICONFLOW_SUPPORTS_TOOL_CALLING", "true").lower() == "true"

    @classmethod
    def get_max_concurrent(cls) -> int:
        if cls.MAX_CONCURRENT_MODELS > 0:
            return cls.MAX_CONCURRENT_MODELS
        import multiprocessing
        return max(2, min(6, multiprocessing.cpu_count()))

class SQLiteConfig(Config):
    """SQLite 降级配置，仅供测试套件临时数据库使用。"""
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///./development.db'

config_map = {
    'development': Config,
    'production': Config,
    'default': Config,
    'sqlite': SQLiteConfig,
}

