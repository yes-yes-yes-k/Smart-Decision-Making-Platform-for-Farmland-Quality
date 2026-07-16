import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
SRC_DIR = PROJECT_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


def main(argv: list[str] | None = None) -> int:
    from dotenv import load_dotenv
    load_dotenv()

    parser = argparse.ArgumentParser(description="启动耕地土壤酸化治理智能问答系统")
    parser.add_argument("--host", default="0.0.0.0", help="监听地址")
    parser.add_argument("--port", type=int, default=5000, help="监听端口")
    parser.add_argument("--config", default="default", help="配置环境 (development/production/default)")
    parser.add_argument("--debug", action="store_true", help="启用调试模式")
    parser.add_argument("--init-db", action="store_true", help="初始化数据库表")
    args = parser.parse_args(argv)

    from framework.api.app import create_app
    from framework.models.user import db
    from framework.config import config_map

    print(f"[启动] 耕地土壤酸化治理智能问答系统")
    print(f"[配置] 环境: {args.config}")
    print(f"[配置] 地址: http://{args.host}:{args.port}")

    app = create_app(args.config)

    if args.init_db:
        with app.app_context():
            db.create_all()
            print("[数据库] 表结构初始化完成")

    app.run(host=args.host, port=args.port, debug=args.debug)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())