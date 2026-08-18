"""PostgreSQL 数据库导入脚本。

将 db_enterprise_qa_20260818_225332.dump 导入到 PostgreSQL 数据库。
导入前请确保:
1. PostgreSQL 已安装并运行
2. PostGIS 扩展已安装
3. 目标数据库已创建 (或由本脚本创建)

用法:
    python backups/import_database.py                       # 导入到默认数据库
    python backups/import_database.py --dbname mydb         # 导入到指定数据库
    python backups/import_database.py --create              # 创建数据库后导入
    python backups/import_database.py --host 192.168.1.100  # 指定主机
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path

# 数据库默认配置（可被命令行参数覆盖）
DB_HOST = "localhost"
DB_PORT = "5432"
DB_USER = "postgres"
DB_PASSWORD = "scau2025"
DB_NAME = "db_enterprise_qa"

DUMP_FILE = Path(__file__).parent / "db_enterprise_qa_20260818_225332.dump"


def run_psql(sql: str, dbname: str = "postgres", host: str = DB_HOST, port: str = DB_PORT, user: str = DB_USER, password: str = DB_PASSWORD):
    """执行 psql 命令。"""
    env = os.environ.copy()
    env["PGPASSWORD"] = password
    cmd = ["psql", "-h", host, "-p", port, "-U", user, "-d", dbname, "-c", sql]
    result = subprocess.run(cmd, env=env, capture_output=True, text=True)
    return result


def run_pg_restore(dbname: str, host: str, port: str, user: str, password: str, create: bool = False):
    """执行 pg_restore 命令。"""
    env = os.environ.copy()
    env["PGPASSWORD"] = password

    cmd = [
        "pg_restore",
        "-h", host,
        "-p", port,
        "-U", user,
        "-d", dbname,
        "-v",
        "--no-owner",
        "--no-privileges",
    ]
    if create:
        cmd.append("--create")
    else:
        cmd.append("--clean")
        cmd.append("--if-exists")
    cmd.append(str(DUMP_FILE))

    print(f"正在导入 {DUMP_FILE.name} 到 {dbname}...")
    print(f"执行: pg_restore -h {host} -p {port} -U {user} -d {dbname} ...")

    result = subprocess.run(cmd, env=env, capture_output=True, text=True)

    if result.returncode != 0:
        # pg_restore 对已存在对象会报 warning，不一定致命
        print(f"pg_restore 返回码: {result.returncode}")
        if result.stderr:
            # 过滤掉 "already exists" 等非致命警告
            warnings = []
            errors = []
            for line in result.stderr.split("\n"):
                if "already exists" in line or "does not exist" in line:
                    warnings.append(line)
                elif line.strip():
                    errors.append(line)
            if warnings:
                print(f"  警告 ({len(warnings)} 条): {warnings[0]}...")
            if errors:
                print(f"  错误 ({len(errors)} 条):")
                for e in errors[:10]:
                    print(f"    {e}")
    else:
        print("导入成功!")

    if result.stdout:
        lines = result.stdout.strip().split("\n")
        for line in lines[-3:]:
            print(f"  {line}")

    return result.returncode == 0


def ensure_postgis(host: str, port: str, user: str, password: str, dbname: str):
    """确保 PostGIS 扩展已安装。"""
    print("检查 PostGIS 扩展...")
    result = run_psql(
        f"CREATE EXTENSION IF NOT EXISTS postgis;",
        dbname=dbname, host=host, port=port, user=user, password=password,
    )
    if result.returncode != 0:
        print(f"警告: 无法创建 PostGIS 扩展: {result.stderr}")
        print("请确保已安装 postgis 包 (如: apt install postgis)")
        return False
    print("  PostGIS 扩展已确保创建")
    return True


def main():
    parser = argparse.ArgumentParser(description="导入数据库备份")
    parser.add_argument("--host", default=DB_HOST, help=f"数据库主机 (默认: {DB_HOST})")
    parser.add_argument("--port", default=DB_PORT, help=f"数据库端口 (默认: {DB_PORT})")
    parser.add_argument("--user", default=DB_USER, help=f"数据库用户 (默认: {DB_USER})")
    parser.add_argument("--password", default=DB_PASSWORD, help="数据库密码")
    parser.add_argument("--dbname", default=DB_NAME, help=f"目标数据库名 (默认: {DB_NAME})")
    parser.add_argument("--create", action="store_true", help="创建数据库后导入 (需 superuser)")
    args = parser.parse_args()

    if not DUMP_FILE.exists():
        print(f"错误: 备份文件不存在: {DUMP_FILE}")
        sys.exit(1)

    print(f"备份文件: {DUMP_FILE}")
    print(f"文件大小: {DUMP_FILE.stat().st_size / 1024 / 1024:.1f} MB")
    print(f"目标: {args.user}@{args.host}:{args.port}/{args.dbname}")
    print()

    if args.create:
        # 创建数据库
        print(f"创建数据库 {args.dbname}...")
        result = run_psql(
            f"CREATE DATABASE {args.dbname};",
            dbname="postgres", host=args.host, port=args.port, user=args.user, password=args.password,
        )
        if result.returncode != 0 and "already exists" not in (result.stderr or ""):
            print(f"创建数据库失败: {result.stderr}")
            sys.exit(1)
        print("  数据库已创建")

    # 确保 PostGIS
    ensure_postgis(args.host, args.port, args.user, args.password, args.dbname)

    # 导入数据
    success = run_pg_restore(
        args.dbname, args.host, args.port, args.user, args.password,
        create=False,
    )

    if success:
        print("\n导入完成! 验证:")
        result = run_psql(
            "SELECT "
            "(SELECT COUNT(*) FROM parcel_info) AS parcels, "
            "(SELECT COUNT(*) FROM parcel_history_snapshot) AS history, "
            "(SELECT COUNT(*) FROM thematic_model_registry) AS models;",
            dbname=args.dbname, host=args.host, port=args.port, user=args.user, password=args.password,
        )
        if result.stdout:
            print(f"  {result.stdout.strip()}")
    else:
        print("\n导入遇到问题，请检查上方日志")
        sys.exit(1)


if __name__ == "__main__":
    main()
