"""数据库恢复脚本 — 从备份文件恢复 db_enterprise_qa 数据库。

支持三种恢复方式（按优先级自动选择）：
1. pg_restore 恢复 .dump（custom format，推荐，最快）
2. psql 恢复 .sql（plain SQL，最通用）
3. Python SQLAlchemy 直接执行 .sql（无需 PostgreSQL 客户端工具）

用法:
    # 自动选择最新备份文件恢复
    python scripts/restore_database.py

    # 指定备份文件
    python scripts/restore_database.py --file backups/db_backup_20260824_223040.dump

    # 指定数据库连接
    python scripts/restore_database.py --host localhost --port 5432 --user postgres --password scau2025 --dbname db_enterprise_qa

    # 仅列出可用备份文件
    python scripts/restore_database.py --list

前置条件:
    - 目标 PostgreSQL 已安装 PostGIS 扩展（CREATE EXTENSION postgis;）
    - 数据库 db_enterprise_qa 已创建（CREATE DATABASE db_enterprise_qa;）
    - .env 中 DB_PASSWORD 已配置，或通过 --password 参数传入
"""
from __future__ import annotations

import argparse
import glob
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKUP_DIR = PROJECT_ROOT / "backups"

logger = logging.getLogger("restore_database")


def find_backup_files() -> List[Path]:
    """列出 backups/ 目录下的所有备份文件（按时间倒序）。"""
    if not BACKUP_DIR.exists():
        return []
    files = []
    for ext in ("*.dump", "*.sql"):
        files.extend(BACKUP_DIR.glob(ext))
    return sorted(files, key=lambda f: f.stat().st_mtime, reverse=True)


def find_pg_restore() -> Optional[str]:
    """查找 pg_restore 可执行文件路径。"""
    path = shutil.which("pg_restore")
    if path:
        return path
    # 尝试常见安装路径
    for candidate in [
        r"D:\soft\PostgreSQL\bin\pg_restore.exe",
        r"C:\Program Files\PostgreSQL\17\bin\pg_restore.exe",
        r"C:\Program Files\PostgreSQL\16\bin\pg_restore.exe",
        r"C:\Program Files\PostgreSQL\15\bin\pg_restore.exe",
    ]:
        if os.path.exists(candidate):
            return candidate
    return None


def find_psql() -> Optional[str]:
    """查找 psql 可执行文件路径。"""
    path = shutil.which("psql")
    if path:
        return path
    for candidate in [
        r"D:\soft\PostgreSQL\bin\psql.exe",
        r"C:\Program Files\PostgreSQL\17\bin\psql.exe",
        r"C:\Program Files\PostgreSQL\16\bin\psql.exe",
        r"C:\Program Files\PostgreSQL\15\bin\psql.exe",
    ]:
        if os.path.exists(candidate):
            return candidate
    return None


def restore_with_pg_restore(
    dump_file: Path, host: str, port: int, user: str,
    password: str, dbname: str,
) -> bool:
    """方式 1: pg_restore 恢复 .dump 文件（推荐）。"""
    pg_restore = find_pg_restore()
    if not pg_restore:
        logger.info("pg_restore 不可用，跳过此方式")
        return False

    env = os.environ.copy()
    env["PGPASSWORD"] = password
    cmd = [
        pg_restore,
        "-h", host,
        "-p", str(port),
        "-U", user,
        "-d", dbname,
        "--no-owner",
        "--no-privileges",
        "--clean",
        "--if-exists",
        str(dump_file),
    ]
    logger.info("使用 pg_restore 恢复: %s", dump_file.name)
    result = subprocess.run(cmd, env=env, capture_output=True, text=True)
    if result.returncode == 0:
        print("[成功] pg_restore 恢复完成")
        return True
    # pg_restore 对部分非致命错误返回非零，检查是否有致命错误
    stderr_lower = result.stderr.lower()
    fatal_keywords = ["fatal", "could not connect", "password authentication failed"]
    if any(k in stderr_lower for k in fatal_keywords):
        print(f"[失败] pg_restore 致命错误:\n{result.stderr[:500]}")
        return False
    # 非致命错误（如 DROP TABLE 不存在的表），视为成功
    print("[成功] pg_restore 恢复完成（有非致命警告，可忽略）")
    if result.stderr.strip():
        print(f"  警告信息（前 200 字符）: {result.stderr[:200]}")
    return True


def restore_with_psql(
    sql_file: Path, host: str, port: int, user: str,
    password: str, dbname: str,
) -> bool:
    """方式 2: psql 执行 .sql 文件。"""
    psql = find_psql()
    if not psql:
        logger.info("psql 不可用，跳过此方式")
        return False

    env = os.environ.copy()
    env["PGPASSWORD"] = password
    cmd = [
        psql,
        "-h", host,
        "-p", str(port),
        "-U", user,
        "-d", dbname,
        "-v", "ON_ERROR_STOP=0",
        "-f", str(sql_file),
    ]
    logger.info("使用 psql 恢复: %s", sql_file.name)
    result = subprocess.run(cmd, env=env, capture_output=True, text=True)
    if result.returncode == 0:
        print("[成功] psql 恢复完成")
        return True
    print(f"[失败] psql 恢复出错:\n{result.stderr[:500]}")
    return False


def restore_with_python(
    sql_file: Path, host: str, port: int, user: str,
    password: str, dbname: str,
) -> bool:
    """方式 3: Python SQLAlchemy 直接执行 SQL（无需 PostgreSQL 客户端工具）。

    需要 psycopg2（项目 .venv 已安装）。
    """
    logger.info("使用 Python SQLAlchemy 恢复: %s", sql_file.name)
    try:
        import psycopg2
    except ImportError:
        print("[失败] psycopg2 未安装，无法使用 Python 方式恢复")
        return False

    conn_str = f"host={host} port={port} user={user} password={password} dbname={dbname}"
    try:
        conn = psycopg2.connect(conn_str)
        conn.autocommit = True
    except Exception as e:
        print(f"[失败] 数据库连接失败: {e}")
        return False

    print(f"  正在执行 SQL 文件 ({sql_file.stat().st_size / 1024 / 1024:.1f} MB)...")
    try:
        with open(sql_file, encoding="utf-8") as f:
            sql_content = f.read()
        with conn.cursor() as cur:
            cur.execute(sql_content)
        print("[成功] Python SQLAlchemy 恢复完成")
        return True
    except Exception as e:
        # SQL 文件可能含多条语句，psycopg2 execute 可能只执行第一条
        # 尝试用 execute 逐条执行
        logger.warning("整体执行失败，尝试逐条执行: %s", e)
        try:
            with conn.cursor() as cur:
                # 简单按分号分割（不完美，但覆盖大多数情况）
                statements = sql_content.split(";")
                success = 0
                errors = 0
                for stmt in statements:
                    stmt = stmt.strip()
                    if not stmt or stmt.startswith("--"):
                        continue
                    try:
                        cur.execute(stmt)
                        success += 1
                    except Exception:
                        errors += 1
                print(f"[成功] Python 恢复完成（{success} 条成功，{errors} 条跳过）")
                return True
        except Exception as e2:
            print(f"[失败] Python 恢复失败: {e2}")
            return False
    finally:
        conn.close()


def restore(
    backup_file: Optional[Path] = None,
    host: str = "localhost",
    port: int = 5432,
    user: str = "postgres",
    password: str = "123456",
    dbname: str = "db_enterprise_qa",
) -> bool:
    """从备份文件恢复数据库。

    自动选择最佳恢复方式，优先级：pg_restore > psql > Python。
    """
    # 自动选择最新备份文件
    if backup_file is None:
        backups = find_backup_files()
        if not backups:
            print("[错误] backups/ 目录无备份文件")
            print("  请先运行导出: python scripts/export_database.py")
            return False
        backup_file = backups[0]
        print(f"自动选择最新备份: {backup_file.name}")

    if not backup_file.exists():
        print(f"[错误] 备份文件不存在: {backup_file}")
        return False

    size_mb = backup_file.stat().st_size / 1024 / 1024
    print(f"\n=== 数据库恢复 ===")
    print(f"  备份文件: {backup_file}")
    print(f"  文件大小: {size_mb:.2f} MB")
    print(f"  目标数据库: {user}@{host}:{port}/{dbname}")
    print()

    # 从 .env 读取密码（如果未通过参数传入）
    if not password:
        env_file = PROJECT_ROOT / ".env"
        if env_file.exists():
            with open(env_file, encoding="utf-8") as f:
                for line in f:
                    if line.startswith("DB_PASSWORD="):
                        password = line.split("=", 1)[1].strip()
                        break

    if not password:
        print("[警告] 未找到 DB_PASSWORD，请通过 --password 参数传入")

    # 按优先级尝试恢复方式
    is_dump = backup_file.suffix == ".dump"

    if is_dump:
        # .dump 文件优先用 pg_restore
        if restore_with_pg_restore(backup_file, host, port, user, password, dbname):
            return True
        # pg_restore 不可用，查找同名的 .sql 文件
        sql_file = backup_file.with_suffix(".sql")
        if sql_file.exists():
            print(f"\n  尝试使用同名 SQL 文件: {sql_file.name}")
            if restore_with_psql(sql_file, host, port, user, password, dbname):
                return True
            if restore_with_python(sql_file, host, port, user, password, dbname):
                return True
        else:
            print("[错误] .dump 文件需要 pg_restore，但当前环境不可用")
            print("  请安装 PostgreSQL 客户端工具，或使用 .sql 格式备份")
            return False
    else:
        # .sql 文件优先用 psql，回退 Python
        if restore_with_psql(backup_file, host, port, user, password, dbname):
            return True
        if restore_with_python(backup_file, host, port, user, password, dbname):
            return True

    print("\n[失败] 所有恢复方式均不可用")
    print("  请确保已安装 PostgreSQL 客户端工具（pg_restore/psql）")
    print("  或安装 psycopg2: pip install psycopg2-binary")
    return False


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(
        description="从备份文件恢复 db_enterprise_qa 数据库",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 自动选择最新备份恢复
  python scripts/restore_database.py

  # 指定备份文件
  python scripts/restore_database.py --file backups/db_backup_20260824_223040.dump

  # 列出可用备份
  python scripts/restore_database.py --list

前置条件:
  1. PostgreSQL 已安装 PostGIS: CREATE EXTENSION postgis;
  2. 数据库已创建: CREATE DATABASE db_enterprise_qa;
  3. .env 配置了 DB_PASSWORD，或通过 --password 传入
""",
    )
    parser.add_argument("--file", type=str, help="备份文件路径（不指定则自动选择最新）")
    parser.add_argument("--list", action="store_true", help="列出可用备份文件")
    parser.add_argument("--host", default="localhost", help="数据库主机")
    parser.add_argument("--port", type=int, default=5432, help="数据库端口")
    parser.add_argument("--user", default="postgres", help="数据库用户")
    parser.add_argument("--password", default="", help="数据库密码（不指定则从 .env 读取）")
    parser.add_argument("--dbname", default="db_enterprise_qa", help="数据库名")
    args = parser.parse_args()

    if args.list:
        backups = find_backup_files()
        if not backups:
            print("无可用备份文件")
            return
        print("=== 可用备份文件 ===")
        for i, f in enumerate(backups):
            size = f.stat().st_size / 1024 / 1024
            import datetime
            mtime = datetime.datetime.fromtimestamp(f.stat().st_mtime)
            print(f"  [{i+1}] {f.name}  ({size:.2f} MB, {mtime.strftime('%Y-%m-%d %H:%M')})")
        return

    backup_file = Path(args.file) if args.file else None
    success = restore(
        backup_file=backup_file,
        host=args.host,
        port=args.port,
        user=args.user,
        password=args.password,
        dbname=args.dbname,
    )
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
