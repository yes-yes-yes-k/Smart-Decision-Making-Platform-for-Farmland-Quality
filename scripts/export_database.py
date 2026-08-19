"""PostgreSQL 数据库导出脚本。

导出 db_enterprise_qa 数据库（schema + data）为压缩备份文件，
并生成对应的导入脚本，方便其他成员快速导入。

用法:
    python scripts/export_database.py            # 导出全部
    python scripts/export_database.py --schema   # 仅导出 schema
    python scripts/export_database.py --data      # 仅导出 data
"""
import argparse
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

# 读取 .env
env_path = _PROJECT_ROOT / ".env"
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())

# 数据库配置
DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = os.environ.get("DB_PORT", "5432")
DB_USER = os.environ.get("DB_USER", "postgres")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
DB_NAME = os.environ.get("DB_NAME", "db_enterprise_qa")

# 备份目录
BACKUP_DIR = _PROJECT_ROOT / "backups"
BACKUP_DIR.mkdir(exist_ok=True)

# 排除的表（PostGIS 内置表，导入时由 CREATE EXTENSION 自动创建）
EXCLUDE_TABLES = [
    "spatial_ref_sys",
]

# 关键表（用于显示导出进度）
KEY_TABLES = [
    "parcel_info", "parcel_history_snapshot",
    "stability_risk_result", "quality_grade_result",
    "obstacle_diagnosis_result", "acidification_remediation_result",
    "organic_matter_result",
    "thematic_model_registry", "model_execution_log",
]


def run_pg_dump(output_path: str, schema_only: bool = False, data_only: bool = False):
    """执行 pg_dump 命令。"""
    env = os.environ.copy()
    env["PGPASSWORD"] = DB_PASSWORD

    cmd = [
        "pg_dump",
        "-h", DB_HOST,
        "-p", str(DB_PORT),
        "-U", DB_USER,
        "-d", DB_NAME,
        "-Fc",          # custom format (compressed)
        "-v",           # verbose
        "-f", output_path,
    ]

    # 排除 PostGIS 内置表
    for table in EXCLUDE_TABLES:
        cmd.extend(["--exclude-table", table])

    if schema_only:
        cmd.append("--schema-only")
    elif data_only:
        cmd.append("--data-only")

    print(f"执行: {' '.join(cmd[:8])}... -f {output_path}")
    result = subprocess.run(cmd, env=env, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"pg_dump 失败 (exit code {result.returncode}):")
        print(result.stderr)
        return False

    # 显示 pg_dump 的 verbose 输出（最后几行）
    if result.stderr:
        lines = result.stderr.strip().split("\n")
        for line in lines[-5:]:
            print(f"  {line}")

    return True


def get_table_count(table_name: str) -> int:
    """获取表行数。"""
    import psycopg2
    conn = psycopg2.connect(
        host=DB_HOST, port=int(DB_PORT),
        user=DB_USER, password=DB_PASSWORD, dbname=DB_NAME,
    )
    cur = conn.cursor()
    try:
        cur.execute(f"SELECT COUNT(*) FROM {table_name}")
        count = cur.fetchone()[0]
    except Exception:
        count = 0
    conn.close()
    return count


def generate_restore_script(dump_filename: str):
    """生成导入脚本。"""
    script_path = BACKUP_DIR / "import_database.py"
    script_content = f'''"""PostgreSQL 数据库导入脚本。

将 {dump_filename} 导入到 PostgreSQL 数据库。
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
DB_HOST = "{DB_HOST}"
DB_PORT = "{DB_PORT}"
DB_USER = "{DB_USER}"
DB_PASSWORD = "{DB_PASSWORD}"
DB_NAME = "{DB_NAME}"

DUMP_FILE = Path(__file__).parent / "{dump_filename}"


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

    print(f"正在导入 {{DUMP_FILE.name}} 到 {{dbname}}...")
    print(f"执行: pg_restore -h {{host}} -p {{port}} -U {{user}} -d {{dbname}} ...")

    result = subprocess.run(cmd, env=env, capture_output=True, text=True)

    if result.returncode != 0:
        # pg_restore 对已存在对象会报 warning，不一定致命
        print(f"pg_restore 返回码: {{result.returncode}}")
        if result.stderr:
            # 过滤掉 "already exists" 等非致命警告
            warnings = []
            errors = []
            for line in result.stderr.split("\\n"):
                if "already exists" in line or "does not exist" in line:
                    warnings.append(line)
                elif line.strip():
                    errors.append(line)
            if warnings:
                print(f"  警告 ({{len(warnings)}} 条): {{warnings[0]}}...")
            if errors:
                print(f"  错误 ({{len(errors)}} 条):")
                for e in errors[:10]:
                    print(f"    {{e}}")
    else:
        print("导入成功!")

    if result.stdout:
        lines = result.stdout.strip().split("\\n")
        for line in lines[-3:]:
            print(f"  {{line}}")

    return result.returncode == 0


def ensure_postgis(host: str, port: str, user: str, password: str, dbname: str):
    """确保 PostGIS 扩展已安装。"""
    print("检查 PostGIS 扩展...")
    result = run_psql(
        f"CREATE EXTENSION IF NOT EXISTS postgis;",
        dbname=dbname, host=host, port=port, user=user, password=password,
    )
    if result.returncode != 0:
        print(f"警告: 无法创建 PostGIS 扩展: {{result.stderr}}")
        print("请确保已安装 postgis 包 (如: apt install postgis)")
        return False
    print("  PostGIS 扩展已确保创建")
    return True


def main():
    parser = argparse.ArgumentParser(description="导入数据库备份")
    parser.add_argument("--host", default=DB_HOST, help=f"数据库主机 (默认: {{DB_HOST}})")
    parser.add_argument("--port", default=DB_PORT, help=f"数据库端口 (默认: {{DB_PORT}})")
    parser.add_argument("--user", default=DB_USER, help=f"数据库用户 (默认: {{DB_USER}})")
    parser.add_argument("--password", default=DB_PASSWORD, help="数据库密码")
    parser.add_argument("--dbname", default=DB_NAME, help=f"目标数据库名 (默认: {{DB_NAME}})")
    parser.add_argument("--create", action="store_true", help="创建数据库后导入 (需 superuser)")
    args = parser.parse_args()

    if not DUMP_FILE.exists():
        print(f"错误: 备份文件不存在: {{DUMP_FILE}}")
        sys.exit(1)

    print(f"备份文件: {{DUMP_FILE}}")
    print(f"文件大小: {{DUMP_FILE.stat().st_size / 1024 / 1024:.1f}} MB")
    print(f"目标: {{args.user}}@{{args.host}}:{{args.port}}/{{args.dbname}}")
    print()

    if args.create:
        # 创建数据库
        print(f"创建数据库 {{args.dbname}}...")
        result = run_psql(
            f"CREATE DATABASE {{args.dbname}};",
            dbname="postgres", host=args.host, port=args.port, user=args.user, password=args.password,
        )
        if result.returncode != 0 and "already exists" not in (result.stderr or ""):
            print(f"创建数据库失败: {{result.stderr}}")
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
        print("\\n导入完成! 验证:")
        result = run_psql(
            "SELECT "
            "(SELECT COUNT(*) FROM parcel_info) AS parcels, "
            "(SELECT COUNT(*) FROM parcel_history_snapshot) AS history, "
            "(SELECT COUNT(*) FROM thematic_model_registry) AS models;",
            dbname=args.dbname, host=args.host, port=args.port, user=args.user, password=args.password,
        )
        if result.stdout:
            print(f"  {{result.stdout.strip()}}")
    else:
        print("\\n导入遇到问题，请检查上方日志")
        sys.exit(1)


if __name__ == "__main__":
    main()
'''

    with open(script_path, "w", encoding="utf-8") as f:
        f.write(script_content)
    print(f"  导入脚本已生成: {script_path}")


def generate_readme(dump_filename: str, dump_size_mb: float, table_counts: dict):
    """生成 README 说明。"""
    readme_path = BACKUP_DIR / "README.md"
    readme_content = f"""# 数据库备份说明

**导出时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**数据库**: {DB_NAME}
**PostgreSQL**: 17.4 + PostGIS 3.4

## 文件清单

| 文件 | 说明 |
|------|------|
| `{dump_filename}` | 压缩备份文件 (pg_dump custom format, {dump_size_mb:.1f} MB) |
| `import_database.py` | 导入脚本 |
| `schema.sql` | 纯文本 schema (参考用) |

## 快速导入

### 方式 1: 使用导入脚本 (推荐)

```bash
# 1. 确保 PostgreSQL + PostGIS 已安装
# 2. 复制 backups/ 目录到目标机器
# 3. 执行导入

# 导入到默认数据库 (db_enterprise_qa)
python backups/import_database.py

# 创建新数据库后导入 (需 superuser 权限)
python backups/import_database.py --create --dbname db_enterprise_qa

# 指定远程主机
python backups/import_database.py --host 192.168.1.100 --password yourpassword
```

### 方式 2: 手动 pg_restore

```bash
# 1. 创建数据库并启用 PostGIS
createdb -U postgres db_enterprise_qa
psql -U postgres -d db_enterprise_qa -c "CREATE EXTENSION IF NOT EXISTS postgis;"

# 2. 导入备份
pg_restore -U postgres -d db_enterprise_qa --no-owner --no-privileges -v {dump_filename}
```

### 方式 3: Docker 导入

```bash
# 1. 启动 PostgreSQL + PostGIS 容器
docker run -d --name pg-gis \\
  -e POSTGRES_PASSWORD=scau2025 \\
  -e POSTGRES_DB=db_enterprise_qa \\
  -p 5432:5432 \\
  postgis/postgis:16-3.4

# 2. 等待容器就绪后导入
pg_restore -h localhost -U postgres -d db_enterprise_qa \\
  --no-owner --no-privileges -v {dump_filename}
```

## 数据概览

| 表名 | 行数 | 说明 |
|------|------|------|
"""
    for table, count in table_counts.items():
        readme_content += f"| {table} | {count:,} | {'关键数据' if table in KEY_TABLES else ''} |\n"

    readme_content += f"""
## 环境要求

- PostgreSQL >= 14
- PostGIS >= 3.0
- Python >= 3.9 (仅导入脚本需要)

## 注意事项

1. `spatial_ref_sys` 表未导出 (PostGIS 内置，由 `CREATE EXTENSION postgis` 自动创建)
2. 导入时使用 `--no-owner --no-privileges` 确保跨用户兼容
3. 如果目标数据库已有同名表，使用 `--clean --if-exists` 自动清理
4. 几何数据使用 EPSG:4326 (WGS84) 坐标系

## 连接配置

```
DB_HOST=localhost
DB_PORT=5432
DB_USER=postgres
DB_PASSWORD=scau2025
DB_NAME=db_enterprise_qa
```
"""
    with open(readme_path, "w", encoding="utf-8") as f:
        f.write(readme_content)
    print(f"  README 已生成: {readme_path}")


def main():
    parser = argparse.ArgumentParser(description="导出 PostgreSQL 数据库")
    parser.add_argument("--schema", action="store_true", help="仅导出 schema")
    parser.add_argument("--data", action="store_true", help="仅导出 data")
    args = parser.parse_args()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    if args.schema:
        dump_filename = f"schema_{timestamp}.sql"
        dump_path = BACKUP_DIR / dump_filename
        # schema 用纯文本格式
        env = os.environ.copy()
        env["PGPASSWORD"] = DB_PASSWORD
        cmd = [
            "pg_dump", "-h", DB_HOST, "-p", str(DB_PORT),
            "-U", DB_USER, "-d", DB_NAME,
            "--schema-only", "-Fp",
            "-f", str(dump_path),
        ]
        for table in EXCLUDE_TABLES:
            cmd.extend(["--exclude-table", table])
        result = subprocess.run(cmd, env=env, capture_output=True, text=True)
        if result.returncode == 0:
            print(f"Schema 已导出: {dump_path}")
        return

    # 完整导出
    dump_filename = f"db_enterprise_qa_{timestamp}.dump"
    dump_path = BACKUP_DIR / dump_filename

    print(f"=== 导出数据库: {DB_NAME} ===")
    print(f"输出: {dump_path}")
    print()

    # 获取关键表行数
    print("数据概览:")
    table_counts = {}
    for table in KEY_TABLES:
        count = get_table_count(table)
        table_counts[table] = count
        print(f"  {table}: {count:,} 行")
    print()

    # 执行导出
    success = run_pg_dump(str(dump_path))
    if not success:
        print("导出失败!")
        sys.exit(1)

    dump_size = dump_path.stat().st_size / 1024 / 1024
    print(f"\n导出成功: {dump_path} ({dump_size:.1f} MB)")

    # 导出 schema.sql (参考用)
    schema_path = BACKUP_DIR / "schema.sql"
    env = os.environ.copy()
    env["PGPASSWORD"] = DB_PASSWORD
    cmd = [
        "pg_dump", "-h", DB_HOST, "-p", str(DB_PORT),
        "-U", DB_USER, "-d", DB_NAME,
        "--schema-only", "-Fp",
        "-f", str(schema_path),
    ]
    for table in EXCLUDE_TABLES:
        cmd.extend(["--exclude-table", table])
    subprocess.run(cmd, env=env, capture_output=True, text=True)
    print(f"Schema 参考文件: {schema_path}")

    # 生成导入脚本和 README
    print("\n生成辅助文件...")
    generate_restore_script(dump_filename)
    generate_readme(dump_filename, dump_size, table_counts)

    print(f"\n=== 完成 ===")
    print(f"备份目录: {BACKUP_DIR}")
    print(f"备份文件: {dump_filename} ({dump_size:.1f} MB)")
    print(f"导入脚本: import_database.py")
    print(f"说明文档: README.md")


if __name__ == "__main__":
    main()
