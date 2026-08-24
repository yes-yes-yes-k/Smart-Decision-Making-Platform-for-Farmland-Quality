"""数据库导出脚本 — 将 db_enterprise_qa 数据库备份到 backups/ 目录。

同时导出两种格式：
1. .dump（pg_dump custom format，压缩，需 pg_restore 恢复）
2. .sql（plain SQL，通用，可用 psql 或 Python 恢复）

用法:
    # 导出两种格式（默认）
    python scripts/export_database.py

    # 仅导出 .dump 格式
    python scripts/export_database.py --format dump

    # 仅导出 .sql 格式
    python scripts/export_database.py --format sql

    # 指定数据库连接
    python scripts/export_database.py --host localhost --port 5432 --user postgres --password scau2025

前置条件:
    - PostgreSQL 客户端工具 pg_dump 已安装
    - .env 中 DB_PASSWORD 已配置，或通过 --password 参数传入
"""
from __future__ import annotations

import argparse
import datetime
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKUP_DIR = PROJECT_ROOT / "backups"

logger = logging.getLogger("export_database")


def find_pg_dump() -> Optional[str]:
    """查找 pg_dump 可执行文件路径。"""
    path = shutil.which("pg_dump")
    if path:
        return path
    for candidate in [
        r"D:\soft\PostgreSQL\bin\pg_dump.exe",
        r"C:\Program Files\PostgreSQL\17\bin\pg_dump.exe",
        r"C:\Program Files\PostgreSQL\16\bin\pg_dump.exe",
        r"C:\Program Files\PostgreSQL\15\bin\pg_dump.exe",
    ]:
        if os.path.exists(candidate):
            return candidate
    return None


def export_format(
    pg_dump: str, fmt: str, host: str, port: int, user: str,
    password: str, dbname: str, output_file: Path,
) -> bool:
    """导出指定格式的备份。"""
    env = os.environ.copy()
    env["PGPASSWORD"] = password

    if fmt == "dump":
        cmd = [pg_dump, "-h", host, "-p", str(port), "-U", user, "-d", dbname, "-Fc", "-f", str(output_file)]
    else:  # sql
        cmd = [pg_dump, "-h", host, "-p", str(port), "-U", user, "-d", dbname,
               "--no-owner", "--no-privileges", "-f", str(output_file)]

    result = subprocess.run(cmd, env=env, capture_output=True, text=True)
    if result.returncode == 0:
        size = output_file.stat().st_size / 1024 / 1024
        print(f"  [成功] {output_file.name} ({size:.2f} MB)")
        return True
    print(f"  [失败] {result.stderr[:300]}")
    return False


def export_database(
    host: str = "localhost",
    port: int = 5432,
    user: str = "postgres",
    password: str = "",
    dbname: str = "db_enterprise_qa",
    fmt: str = "both",
) -> bool:
    """导出数据库备份。"""
    pg_dump = find_pg_dump()
    if not pg_dump:
        print("[错误] 未找到 pg_dump，请安装 PostgreSQL 客户端工具")
        print("  常见路径: C:\\Program Files\\PostgreSQL\\17\\bin\\pg_dump.exe")
        return False

    # 从 .env 读取密码
    if not password:
        env_file = PROJECT_ROOT / ".env"
        if env_file.exists():
            with open(env_file, encoding="utf-8") as f:
                for line in f:
                    if line.startswith("DB_PASSWORD="):
                        password = line.split("=", 1)[1].strip()
                        break

    if not password:
        print("[错误] 未找到 DB_PASSWORD，请通过 --password 参数传入")
        return False

    BACKUP_DIR.mkdir(exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

    print(f"\n=== 数据库导出 ===")
    print(f"  数据库: {user}@{host}:{port}/{dbname}")
    print(f"  输出目录: {BACKUP_DIR}")
    print()

    formats = []
    if fmt in ("both", "dump"):
        formats.append(("dump", BACKUP_DIR / f"db_backup_{timestamp}.dump"))
    if fmt in ("both", "sql"):
        formats.append(("sql", BACKUP_DIR / f"db_backup_{timestamp}.sql"))

    all_success = True
    for f, output_file in formats:
        print(f"导出 {f.upper()} 格式...")
        if not export_format(pg_dump, f, host, port, user, password, dbname, output_file):
            all_success = False

    print()
    if all_success:
        print("[完成] 所有格式导出成功")
        print()
        print("恢复方法:")
        print("  python scripts/restore_database.py --file <备份文件>")
        print("  或自动选择最新备份:")
        print("  python scripts/restore_database.py")
    return all_success


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(
        description="导出 db_enterprise_qa 数据库备份",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--host", default="localhost", help="数据库主机")
    parser.add_argument("--port", type=int, default=5432, help="数据库端口")
    parser.add_argument("--user", default="postgres", help="数据库用户")
    parser.add_argument("--password", default="", help="数据库密码（不指定则从 .env 读取）")
    parser.add_argument("--dbname", default="db_enterprise_qa", help="数据库名")
    parser.add_argument("--format", choices=["both", "dump", "sql"], default="both",
                        help="备份格式：both(默认)/dump/sql")
    args = parser.parse_args()

    success = export_database(
        host=args.host,
        port=args.port,
        user=args.user,
        password=args.password,
        dbname=args.dbname,
        fmt=args.format,
    )
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
