import os
import secrets
import sys
from typing import Optional

ENV = os.environ.get('FLASK_ENV') or os.environ.get('ENV') or 'development'

def _warn(prompt: str):
    """打印到 stderr，避免污染标准输出并随正常日志一起可见。"""
    print(prompt, file=sys.stderr, flush=True)

class Config:
    CD_FLUX_V2_ENABLED = os.environ.get('CD_FLUX_V2_ENABLED', 'true').lower() == 'true'
    PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
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

    SILICONFLOW_API_KEY = os.environ.get('SILICONFLOW_API_KEY', '')
    SILICONFLOW_CHAT_MODEL = os.environ.get('SILICONFLOW_CHAT_MODEL') or 'deepseek-ai/DeepSeek-V4.1-Flash'
    SILICONFLOW_EMBED_MODEL = os.environ.get('SILICONFLOW_EMBED_MODEL') or 'BAAI/bge-m3'
    SILICONFLOW_EMBED_BATCH_SIZE = int(os.environ.get('SILICONFLOW_EMBED_BATCH_SIZE') or 32)
    SILICONFLOW_EMBED_MAX_RETRIES = int(os.environ.get('SILICONFLOW_EMBED_MAX_RETRIES') or 3)
    SILICONFLOW_EMBED_RETRY_BACKOFF = float(os.environ.get('SILICONFLOW_EMBED_RETRY_BACKOFF') or 1)
    SILICONFLOW_BASE_URL = os.environ.get('SILICONFLOW_BASE_URL') or 'https://api.siliconflow.cn/v1'
    # 聊天接口的整体时延由单次最终总结调用控制。DeepSeek-V4-Flash 公测期响应较慢，
    # 20s 会频繁触发超时降级导致"对话无法使用"；放宽到 90s 并允许 1 次重试。
    SILICONFLOW_LLM_TIMEOUT = float(os.environ.get('SILICONFLOW_LLM_TIMEOUT') or 90)
    SILICONFLOW_LLM_MAX_RETRIES = int(os.environ.get('SILICONFLOW_LLM_MAX_RETRIES') or 1)

    CHROMA_PERSIST_DIR = os.environ.get('CHROMA_PERSIST_DIR') or os.path.join(
        PROJECT_ROOT, 'chroma_db'
    )
    CHROMA_COLLECTION_NAME = os.environ.get('CHROMA_COLLECTION_NAME') or 'enterprise_kb'
    # Explicit opt-in: this store is migrated separately, never at app startup.
    LITERATURE_EVIDENCE_DATABASE_URI = os.environ.get("LITERATURE_EVIDENCE_DATABASE_URI") or None

    UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER') or os.path.join(
        PROJECT_ROOT, 'uploads'
    )
    MAX_CONTENT_LENGTH = 200 * 1024 * 1024  # 200MB，对齐 MAX_DATA_IMPORT_SIZE，允许数据导入大文件

    CHUNK_SIZE = 800
    CHUNK_OVERLAP = 150
    PDF_OCR_THRESHOLD = 50  # 平均字符/页阈值，低于则触发 OCR 主路径
    # CAJ 先由 caj2pdf 转换为临时 PDF，再复用 PDF/OCR 解析链路。
    # 留空时从 PATH 查找 caj2pdf；也可配置为 caj2pdf 可执行文件或 caj2pdf.py 的绝对路径。
    CAJ_CONVERTER_PATH = os.environ.get('CAJ_CONVERTER_PATH', '')
    CAJ_CONVERTER_TIMEOUT = int(os.environ.get('CAJ_CONVERTER_TIMEOUT') or 300)
    LITERATURE_RETAIN_DERIVED_PDF = (
        os.environ.get('LITERATURE_RETAIN_DERIVED_PDF', 'false').lower() == 'true'
    )
    LITERATURE_STAGING_ROOTS_JSON = os.environ.get(
        'LITERATURE_STAGING_ROOTS_JSON', '{}'
    )
    INGESTION_WORKERS = int(os.environ.get('INGESTION_WORKERS') or 2)
    INGESTION_MAX_QUEUED = int(os.environ.get('INGESTION_MAX_QUEUED') or 100)
    RETRIEVAL_TOP_K = 5
    RECALL_TOP_K = int(os.environ.get("RECALL_TOP_K") or 20)      # 混合召回阶段候选数
    RRF_K = int(os.environ.get("RRF_K") or 60)                    # RRF 平滑常数
    HYBRID_SEARCH_ENABLED = os.environ.get("HYBRID_SEARCH_ENABLED", "true").lower() == "true"
    RERANK_ENABLED = os.environ.get("RERANK_ENABLED", "true").lower() == "true"
    RERANK_MODEL = os.environ.get("RERANK_MODEL") or "BAAI/bge-reranker-v2-m3"
    RERANK_TIMEOUT = int(os.environ.get("RERANK_TIMEOUT") or 30)

    # 经材料核验的耕地质量最小知识图谱。图谱只提供证据定位，实际内容仍
    # 必须从带权限过滤的向量库读取；关闭后完整回退到原混合检索链路。
    KG_RETRIEVAL_ENABLED = os.environ.get(
        "KG_RETRIEVAL_ENABLED", "true"
    ).lower() == "true"
    KG_GRAPH_PATH = os.environ.get("KG_GRAPH_PATH") or os.path.join(
        PROJECT_ROOT,
        "artifacts",
        "minimal_kg",
        "cultivated_land_minimal_graph_v0.4.json",
    )
    KG_RETRIEVAL_TOP_K = int(os.environ.get("KG_RETRIEVAL_TOP_K") or 5)
    KG_MANIFEST_PATH = os.environ.get("KG_MANIFEST_PATH") or os.path.splitext(
        KG_GRAPH_PATH
    )[0] + ".manifest.json"
    KG_EXPECTED_SHA256 = os.environ.get("KG_EXPECTED_SHA256") or ""
    KG_ROLLOUT_MODE = os.environ.get("KG_ROLLOUT_MODE") or (
        "enabled" if ENV != "production" else "shadow"
    )
    if KG_ROLLOUT_MODE not in {"off", "shadow", "canary", "enabled"}:
        raise ValueError("KG_ROLLOUT_MODE must be off, shadow, canary, or enabled")
    KG_CANARY_PERCENT = int(os.environ.get("KG_CANARY_PERCENT") or 10)
    if not 0 <= KG_CANARY_PERCENT <= 100:
        raise ValueError("KG_CANARY_PERCENT must be between 0 and 100")
    KG_CANARY_USER_IDS = tuple(
        int(value) for value in os.environ.get("KG_CANARY_USER_IDS", "").split(",")
        if value.strip()
    )
    KG_PROFESSIONAL_EVIDENCE_ENABLED = os.environ.get(
        "KG_PROFESSIONAL_EVIDENCE_ENABLED", "true"
    ).lower() == "true"
    KG_FAIL_CLOSED_AUTHORITATIVE = os.environ.get(
        "KG_FAIL_CLOSED_AUTHORITATIVE", "true"
    ).lower() == "true"
    # AGE stays opt-in until dual-read verification explicitly promotes it.
    KG_GRAPH_STORE = os.environ.get("KG_GRAPH_STORE", "json").lower()
    if KG_GRAPH_STORE not in {"json", "age"}:
        raise ValueError("KG_GRAPH_STORE must be json or age")
    KG_AGE_DATABASE_URI = os.environ.get("KG_AGE_DATABASE_URI") or None
    KG_AGE_GRAPH_NAME = os.environ.get("KG_AGE_GRAPH_NAME", "cultivated_land_kg")
    KG_AUDIT_EXPORT_DIR = os.environ.get("KG_AUDIT_EXPORT_DIR") or os.path.join(
        PROJECT_ROOT, "artifacts", "knowledge_platform", "release_audits",
    )

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

