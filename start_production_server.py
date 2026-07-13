"""生产级 WSGI 服务器启动入口。

使用 waitress 作为 WSGI 服务器，提供多线程并发处理能力，
适合 Windows 生产环境部署。

用法:
    python start_production_server.py
    python start_production_server.py --host 127.0.0.1 --port 8000 --threads 8
    python start_production_server.py --init-db

环境变量:
    生产环境必须设置以下变量（或通过 .env 文件加载）:
    - SECRET_KEY: 应用密钥（必填）
    - JWT_SECRET_KEY: JWT 签名密钥（不设则回退到 SECRET_KEY）
    - SILICONFLOW_API_KEY: LLM 服务密钥（必填）
"""

import argparse
import logging
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
SRC_DIR = PROJECT_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

# 加载 .env 文件（如果存在）
try:
    from dotenv import load_dotenv
    env_file = PROJECT_ROOT / ".env"
    if env_file.exists():
        load_dotenv(env_file)
        print(f"[配置] 已加载环境变量文件: {env_file}")
except ImportError:
    pass


def configure_logging(log_level: str = "INFO", log_file: str | None = None) -> None:
    """配置生产级日志。"""
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if log_file:
        log_path = PROJECT_ROOT / log_file
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_path, encoding="utf-8"))

    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=handlers,
    )


def validate_production_config() -> list[str]:
    """校验生产环境必需配置，返回缺失项列表。"""
    missing: list[str] = []
    if not os.environ.get("SECRET_KEY"):
        missing.append("SECRET_KEY")
    if not os.environ.get("SILICONFLOW_API_KEY"):
        missing.append("SILICONFLOW_API_KEY")
    return missing


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="启动生产级 WSGI 服务器（waitress）"
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="监听地址（默认 127.0.0.1，对外服务时改为 0.0.0.0）",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="监听端口（默认 8000）",
    )
    parser.add_argument(
        "--threads",
        type=int,
        default=8,
        help="工作线程数（默认 8）",
    )
    parser.add_argument(
        "--channel-timeout",
        type=int,
        default=120,
        help="请求超时秒数（默认 120，LLM 调用可能较慢）",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="日志级别（默认 INFO）",
    )
    parser.add_argument(
        "--log-file",
        default="logs/production.log",
        help="日志文件路径（默认 logs/production.log，留空则只输出到控制台）",
    )
    parser.add_argument(
        "--init-db",
        action="store_true",
        help="启动前初始化数据库表结构",
    )
    parser.add_argument(
        "--skip-check",
        action="store_true",
        help="跳过生产配置校验（不推荐）",
    )
    args = parser.parse_args(argv)

    # 配置日志
    configure_logging(args.log_level, args.log_file)
    logger = logging.getLogger("production")

    logger.info("=" * 60)
    logger.info("耕地土壤酸化治理智能问答系统 - 生产服务器")
    logger.info("=" * 60)

    # 生产配置校验
    if not args.skip_check:
        missing = validate_production_config()
        if missing:
            logger.error("生产环境配置校验失败，缺失以下必需环境变量:")
            for item in missing:
                logger.error(f"  - {item}")
            logger.error("请通过环境变量或 .env 文件配置后重试")
            logger.error("参考 deploy/production.env.example 获取完整配置模板")
            return 1
        logger.info("生产环境配置校验通过")

    # 强制使用 production 配置
    os.environ["FLASK_ENV"] = "production"
    os.environ["ENV"] = "production"

    # 创建 Flask 应用
    from framework.api.app import create_app
    from framework.models.user import db

    logger.info(f"[配置] 环境: production")
    logger.info(f"[配置] 监听: http://{args.host}:{args.port}")
    logger.info(f"[配置] 线程数: {args.threads}")
    logger.info(f"[配置] 请求超时: {args.channel_timeout}s")

    app = create_app("production")

    # 初始化数据库
    if args.init_db:
        with app.app_context():
            db.create_all()
            logger.info("[数据库] 表结构初始化完成")

    # 健康检查端点
    @app.route("/health")
    def health_check():
        return {"status": "ok", "service": "agent_culti_demo", "version": "1.3.0"}

    # 启动 waitress
    try:
        from waitress import serve
    except ImportError:
        logger.error("waitress 未安装，请运行: pip install waitress")
        return 1

    logger.info("[启动] waitress WSGI 服务器已就绪")
    logger.info("[提示] 对外服务时使用 --host 0.0.0.0 监听所有网卡")

    serve(
        app,
        host=args.host,
        port=args.port,
        threads=args.threads,
        channel_timeout=args.channel_timeout,
        recv_bytes=65536,
        send_bytes=65536,
        cleanup_interval=30,
        connection_limit=1000,
        ident="agent_culti_demo/1.3.0",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
