import os
import secrets
from typing import Optional

ENV = os.environ.get('FLASK_ENV') or os.environ.get('ENV') or 'development'

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY')
    if not SECRET_KEY:
        if ENV == 'production':
            raise ValueError("SECRET_KEY must be set in production environment")
        SECRET_KEY = 'dev-secret-key-change-in-production'

    DB_HOST = os.environ.get('DB_HOST') or 'localhost'
    DB_PORT = int(os.environ.get('DB_PORT') or 5432)
    DB_USER = os.environ.get('DB_USER') or 'root'
    DB_PASSWORD = os.environ.get('DB_PASSWORD') or ''
    DB_NAME = os.environ.get('DB_NAME') or 'db_enterprise_qa'

    SQLALCHEMY_DATABASE_URI = (
        f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
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

    SILICONFLOW_API_KEY = os.environ.get('SILICONFLOW_API_KEY') or 'sk-truhokzloepabjhdeepqtrzifzwaoyffocmaodsyqfepzwfy'
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
    RETRIEVAL_TOP_K = 5

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

