# 数据库备份说明

**导出时间**: 2026-08-27 18:34:54
**数据库**: db_enterprise_qa
**PostgreSQL**: 17.4 + PostGIS 3.4

## 文件清单

| 文件 | 说明 |
|------|------|
| `db_enterprise_qa_20260827_183450.dump` | 压缩备份文件 (pg_dump custom format, 19.4 MB) |
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
pg_restore -U postgres -d db_enterprise_qa --no-owner --no-privileges -v db_enterprise_qa_20260827_183450.dump
```

### 方式 3: Docker 导入

```bash
# 1. 启动 PostgreSQL + PostGIS 容器
docker run -d --name pg-gis \
  -e POSTGRES_PASSWORD=scau2025 \
  -e POSTGRES_DB=db_enterprise_qa \
  -p 5432:5432 \
  postgis/postgis:16-3.4

# 2. 等待容器就绪后导入
pg_restore -h localhost -U postgres -d db_enterprise_qa \
  --no-owner --no-privileges -v db_enterprise_qa_20260827_183450.dump
```

## 数据概览

| 表名 | 行数 | 说明 |
|------|------|------|
| parcel_info | 5,491 | 关键数据 |
| parcel_history_snapshot | 16,464 | 关键数据 |
| stability_risk_result | 16 | 关键数据 |
| quality_grade_result | 17 | 关键数据 |
| obstacle_diagnosis_result | 17 | 关键数据 |
| acidification_remediation_result | 16 | 关键数据 |
| organic_matter_result | 17 | 关键数据 |
| thematic_model_registry | 6 | 关键数据 |
| model_execution_log | 84 | 关键数据 |

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
