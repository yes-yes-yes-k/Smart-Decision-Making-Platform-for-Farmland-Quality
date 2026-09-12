# 开发数据库快照（2026-09-12）

本目录中的最新快照来自本机 `db_enterprise_qa`，用于项目成员搭建 PostgreSQL/PostGIS 开发环境。导出文件不包含数据库连接密码，但数据库内容可能包含应用账号、日志和业务数据，仅限授权的项目成员使用。

## 最新文件

| 文件 | 格式 | 大小 | 用途 |
|------|------|------|------|
| `db_backup_20260912_165227.dump` | pg_dump custom | 26,078,381 字节（约 24.87 MB） | 推荐，使用 `pg_restore` 快速恢复 |
| `db_backup_20260912_165227.sql` | plain SQL | 69,768,667 字节（约 66.54 MB） | 通用备用，使用 `psql` 恢复 |

SHA-256：

```text
95F3C877862542548C659427960C495753DBEAF7266D9BE70A2F3A73371DFA33  db_backup_20260912_165227.dump
A7EDF252F5A8B6D2AEFECCEE1D12E5966EE1FB2DFFBD594929C7FC2E70008000  db_backup_20260912_165227.sql
```

## 快照概览

- PostgreSQL 17.4
- PostGIS 3.5
- public 基础表：38 张
- `parcel_info`：5,488 条
- 地块 `area_code`：10 种，无空值；`440233` 为 721 条，不再是全部地块的硬编码值
- `spatial_region_catalog`：314 条
  - 省：1
  - 市：1
  - 县：1
  - 镇：17
  - 普通村：221
  - 村间争议区：73

压缩备份目录已通过 `pg_restore --list` 校验，并确认包含 PostGIS、`parcel_info` 和 `spatial_region_catalog` 的结构与数据。`.dump` 和 `.sql` 均已分别恢复到独立临时数据库并通过记录数核对，验证库随后已删除。

## 推荐恢复方式

目标机器需要 PostgreSQL 14+、PostGIS 3.0+、Python 3.9+，并已安装项目依赖。

先将本目录和仓库代码放在同一项目结构中，在项目根目录执行：

```bash
# 建议恢复到空的本地开发数据库；命令会清理同名对象
python scripts/restore_database.py \
  --file backups/db_backup_20260912_165227.dump \
  --host localhost \
  --port 5432 \
  --user postgres \
  --password <本机数据库密码> \
  --dbname db_enterprise_qa
```

也可以手动恢复：

```bash
createdb -U postgres db_enterprise_qa
psql -U postgres -d db_enterprise_qa -c "CREATE EXTENSION IF NOT EXISTS postgis;"
pg_restore -U postgres -d db_enterprise_qa \
  --clean --if-exists --no-owner --no-privileges \
  backups/db_backup_20260912_165227.dump
```

无法使用 `pg_restore` 时，可改用 SQL 文件：

```bash
psql -U postgres -d db_enterprise_qa -v ON_ERROR_STOP=1 \
  -f backups/db_backup_20260912_165227.sql
```

## 恢复后核对

```sql
SELECT postgis_version();
SELECT COUNT(*) FROM parcel_info;                  -- 5488
SELECT COUNT(*) FROM spatial_region_catalog;       -- 314
SELECT COUNT(DISTINCT area_code) FROM parcel_info; -- 10
SELECT COUNT(*) FROM parcel_info WHERE area_code IS NULL; -- 0
```

## 注意事项

1. 恢复脚本对目标数据库使用 `--clean --if-exists`，请勿指向需要保留数据的数据库。
2. 备份不导出数据库角色密码；每位成员应使用自己的本地账号和密码。
3. 几何数据使用 EPSG:4326，目标 PostgreSQL 必须安装 PostGIS。
4. `.dump` 和 `.sql` 已在 `.gitignore` 中排除，不应提交到 Git；请通过受控网盘或团队文件共享传递。
5. 恢复后应按本节 SQL 核对记录数，并用上述 SHA-256 校验文件完整性。
