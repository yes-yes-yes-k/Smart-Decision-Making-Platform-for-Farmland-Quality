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
    DB_PORT = int(os.environ.get('DB_PORT') or 3306)
    DB_USER = os.environ.get('DB_USER') or 'root'
    DB_PASSWORD = os.environ.get('DB_PASSWORD') or ''
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

    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY') or SECRET_KEY
    JWT_ACCESS_TOKEN_EXPIRES = 24 * 60 * 60

    SILICONFLOW_API_KEY = os.environ.get('SILICONFLOW_API_KEY') or ''
    SILICONFLOW_CHAT_MODEL = os.environ.get('SILICONFLOW_CHAT_MODEL') or 'deepseek-ai/DeepSeek-V4-Flash'
    SILICONFLOW_EMBED_MODEL = os.environ.get('SILICONFLOW_EMBED_MODEL') or 'BAAI/bge-m3'
    SILICONFLOW_BASE_URL = os.environ.get('SILICONFLOW_BASE_URL') or 'https://api.siliconflow.cn/v1'

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

    @classmethod
    def get_max_concurrent(cls) -> int:
        if cls.MAX_CONCURRENT_MODELS > 0:
            return cls.MAX_CONCURRENT_MODELS
        import multiprocessing
        return max(2, min(6, multiprocessing.cpu_count()))

class DevelopmentConfig(Config):
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///./development.db'

class ProductionConfig(Config):
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = 'sqlite:///instance/production.db'

class SQLiteConfig(Config):
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///./development.db'

config_map = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig,
    'sqlite': SQLiteConfig
}