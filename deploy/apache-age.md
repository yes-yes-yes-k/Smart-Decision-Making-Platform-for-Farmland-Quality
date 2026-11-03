# Apache AGE 1.6.0 / PostgreSQL 16 运维手册

## 固定版本与边界

- PostgreSQL 主版本：`16`；其他主版本健康检查直接失败。
- Apache AGE：`1.6.0`，官方标签 `PG16/v1.6.0-rc0`。
- 官方源码提交：`2db2f060c4c9265a14d40f007eb8c56febf31e4c`。
- Docker 多架构 manifest：`apache/age@sha256:16aa423d20a31aed36a3313244bf7aa00731325862f20ed584510e381f2feaed`。
- amd64 镜像 digest：`sha256:80c8b2c6e90680374db0fe721516dbc854c0ca0cd2705e803e19a835a94b37a7`。
- 图名：`cultivated_land_kg`。应用只使用稳定业务 ID；AGE 的内部 graphid 不得进入 API 或审核数据。

Windows 应用进程通过 PostgreSQL 协议连接 Linux 容器或 Linux 数据库主机；不把 Linux AGE 二进制加载到 Windows PostgreSQL。首次部署和任何升级前必须执行全库备份。不得使用浮动 `latest` 标签。

## 安装与初始化

拉取固定镜像，并使用组织密钥管理系统注入密码：

```powershell
docker pull apache/age@sha256:16aa423d20a31aed36a3313244bf7aa00731325862f20ed584510e381f2feaed
docker run --name culti-pg-age -p 5432:5432 `
  -e POSTGRES_USER=app -e POSTGRES_PASSWORD=$env:AGE_DB_PASSWORD `
  -e POSTGRES_DB=db_enterprise_qa `
  -v culti-pg-age-data:/var/lib/postgresql/data `
  -d apache/age@sha256:16aa423d20a31aed36a3313244bf7aa00731325862f20ed584510e381f2feaed
```

以数据库管理员执行一次：

```sql
CREATE EXTENSION IF NOT EXISTS age;
LOAD 'age';
SET search_path = ag_catalog, "$user", public;
```

确认 `SHOW server_version_num` 以 `16` 开头、`pg_extension.extversion` 为 `1.6.0`。随后运行应用迁移：

```powershell
python scripts/check_age_graph.py --dsn $env:AGE_SQLALCHEMY_DSN
python scripts/migrate_v04_to_age.py --dsn $env:AGE_SQLALCHEMY_DSN `
  --activate --audit-output artifacts/knowledge_platform/age-v04-audit.json
python scripts/verify_graph_store_dual_read.py --dsn $env:AGE_SQLALCHEMY_DSN `
  --report artifacts/knowledge_platform/age-dual-read.json
```

初次 `check_age_graph.py` 在图尚未创建时应失败；迁移创建图、反向导出并校验 38 个实体、66 条关系和 94 条证据引用。只有迁移带 `--activate` 且双读报告 `eligible_for_primary=true` 后，才允许把 `KG_GRAPH_STORE` 从 `json` 改为 `age`。当前部署模板默认 `json`。

## 健康检查

```powershell
python scripts/check_age_graph.py --dsn $env:AGE_SQLALCHEMY_DSN
```

就绪条件：PostgreSQL 16、AGE 1.6.0、目标图存在、存在活动且已验证的 release。查询适配器还会把每次 Cypher 查询限制为 1–2 跳、top-k ≤ 100，并设置 PostgreSQL `statement_timeout`。

## 备份与恢复演练

使用全数据库 custom-format 备份，确保 AGE catalog、图 schema、候选审核表和关系证据位于同一个一致性恢复点：

```powershell
python scripts/age_backup_restore.py backup --dsn $env:AGE_SQLALCHEMY_DSN `
  --database-name db_enterprise_qa --output backups/age/knowledge.dump
```

命令同时生成 `knowledge.dump.manifest.json`，记录 dump SHA-256、PostgreSQL/AGE 版本、活动 release、实体/关系/证据计数和规范图校验和。每次发布前至少在隔离数据库演练：

```powershell
python scripts/age_backup_restore.py restore --dsn $env:AGE_RESTORE_TEST_DSN `
  --dump backups/age/knowledge.dump `
  --manifest backups/age/knowledge.dump.manifest.json --apply
```

恢复只有在 dump 校验和、AGE 健康、活动 release、38/66/94（或当前 manifest 计数）及图校验和全部一致时成功。禁止直接对生产数据库执行恢复演练。

## 回退与升级

运行异常时先将 `KG_GRAPH_STORE=json` 并重启应用；文献、Chroma 和候选关系表不回滚。AGE 数据保留用于审计，不立即 `DROP EXTENSION`。如需回退数据库，停止写入消费者，在隔离环境验证备份后按变更流程恢复整库，再运行健康检查和双读。

AGE 升级不得原地使用浮动镜像：先建立新实例、恢复备份、执行官方升级说明、重新运行反向校验和双读，最后切换连接。任何版本、源码 revision 或镜像 digest 变化都必须更新 SBOM 并重新通过金标与双读门禁。


## Windows 本机独立 AGE 实例（2026-11 联调）

业务 PostgreSQL 17 保持原库；AGE 使用 WSL Ubuntu 内的 PostgreSQL 16.10 / AGE 1.6.0。
容器 `culti-age-live` 仅映射 `127.0.0.1:55432`，数据卷 `culti-age-pg16-data`，重启策略 `unless-stopped`。
`.env` 设置 `KG_GRAPH_STORE=age`、`KG_AGE_DATABASE_URI`（专用数据库 URI，包含密码，不提交），图名保持不变。
`deploy/production.env.example` 提供空配置项。未配置专用 URI 时仍复用业务数据库连接。

启动或恢复本地服务：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start_local_age.ps1
.\.venv\Scripts\python.exe scripts/check_age_graph.py
```

启动脚本在隐藏后台保持 WSL 在线，再启动 Docker 和现有容器；不安装系统组件、不重启 Windows、不修改登录启动项。
Windows 重启后需重新运行此脚本；容器重启策略仅在 Docker/WSL 已启动后生效。

真实联调修复了 AGE 1.6 的两个执行约束：Cypher 第三个参数必须是 PostgreSQL 服务端参数；
`SET +=` 右侧必须为语法上的 map。执行器通过 PREPARE/EXECUTE 和受校验属性名的 map 完成绑定，值始终作为参数传入。
EXECUTE 使用 savepoint，失败后也会释放 prepared statement。

基线采用新的 `kg-v0.4-evidence-repaired-20261101`，而非覆盖旧 JSON release：
38 实体、66 关系、100 条精确证据定位（旧版 94 条，跨页来源拆分后增加）。
38 个实体的两跳双读全部匹配；迁移报告、修复计划与校验结果位于 `artifacts/frontend-live-20261101/`。
原始 JSON 文件和源文献保留；业务库、AGE 库分别备份于 `backups/age-integration-20261102/`。
两库部署须一并备份业务发布审计和 AGE 图数据，且在停止发布写入时取得一致恢复点；单独恢复其中一库不足以完成系统恢复。


本次隔离恢复演练发现并验证了 [Apache AGE #2503](https://github.com/apache/age/issues/2503) 中的
逻辑恢复图 OID 偏移：`namespace` 已指向新 schema，而 `graphid`/`ag_label.graph` 仍为旧库 OID。
`age_backup_restore.py restore` 增加显式 `--repair-age-catalog`，仅在 `--apply` 恢复完成后执行目录修复，
不会在普通读取/健康检查时自动修改目录。修复在事务内锁定目录，重建外键并释放缓存连接；存在 OID 交叉冲突则拒绝自动修复。
修复后仍必须通过原 dump SHA256、活动 release、计数及图校验和验证，不能仅凭 pg_restore 退出码认定恢复成功。
本次 `culti_age_restore_20261102` 隔离恢复库已验证 38/68/103 和图校验和一致，修复重复执行无变化。
