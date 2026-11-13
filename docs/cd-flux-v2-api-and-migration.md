# 年度 Cd 通量 v2：管理契约与迁移

本文描述 OpenSpec 第2阶段的管理和迁移契约。对话与附件的消费方式见 [Cd 对话接口契约](api-contract.md)。

## 管理接口

以下接口前缀 `/api/v1/cd-flux/v2`，均要求 JWT：

| 方法/路径 | 参数/行为 |
| --- | --- |
| POST `/inputs/import` | multipart file；新版CSV默认；`?mode=legacy`接受旧字段并保留未知年度/企业/单位 |
| POST `/calculate` | JSON范围：source/year/parcel_id/region_type/region_id；只核算v2输入，不升级legacy |
| GET `/results` | 同一范围，calculation_version可选，limit默认100最多1000，offset非负；返回输入及当前修订输出 |
| GET `/statistics` | 同一范围，field为in_cd/out_cd/net_cd/end_cd；按来源和年度分组，记录统计而非区域总量 |
| GET `/compare` | 重复参数years，如 `years=2023&years=2024`，最多20年；返回各年覆盖和差异提示 |

source允许native/ported/unknown/all，全域也独立执行来源过滤。year不提供时返回所有年度并分组，包括未知年度；指定年度不混入未知记录。地区支持province/city/county/township，地块使用parcel_id，不能同时指定地区和地块。移植来源沿经核验父链聚合；未映射数是当前来源/年度候选记录中未能映射的数量，不代表缺失人口或完整区域样本数。

新版CSV列：source,accounting_year,parcel_id,sample_id，以及cd_flux_v2.NUMBERS列出的8个分项、initial_cd、bulk_density_g_cm3、soil_depth_m。列必需，空数值表示未知。分项g/ha/a、初始储量g/ha、容重g/cm³、厚度m；使用此版本CSV即明确采用该单位契约，原始数据应先核验转换，系统不猜测单位。

整批先验证，非法行/重复批内键拒绝整批。同来源/地块/样点/年度重导递增input_revision，旧输出保留但不再作为当前结果。计算按输入修订/公式版本幂等。企业空值返回partial，只有已覆盖小计；明确0参与计算。旧七项结果标legacy_v1，年度及企业未知，不能被新八项统计默认采纳。无数据返回has_data=false。

## 纯计算契约

`cd_flux_v2.trial(parameters, units, defaults=None, accepted_defaults=())` 不写数据库。缺失参数保持未知；默认必须含value和basis并在accepted_defaults中逐项接受，企业输入不得默认零。初始浓度可用initial_concentration且单位mg/kg，须具备明确厚度和容重以转换初始储量；与initial_cd同时给出必须一致。跨度固定一年，不是多年预测。

显式单位不等于真实来源已认证。公式条件与独立样例见stage-1-contract.md；负容重、非有限值、负末期储量和单位冲突拒绝。缺少初始储量/容重/厚度时可提供完整通量收支，但end_cd保持未知。

## 备份与执行

先运行 `scripts/backup_cd_development_db.py --env-file <根>/.env --database <库> --output <未存在的本地dump>`。脚本生成custom备份并通过pg_restore --list验证，写校验和；不回显密码。目录校验不等于完整恢复演练。

迁移入口 `scripts/migrate_cd_flux_v2.py --env-file <根>/.env --database <库>` 默认全量回滚演练；显式`--apply`持久化。PostgreSQL15+；咨询锁防并发迁移，检查部分schema/关键列/NULLS NOT DISTINCT年度键。旧表只读，复制年度、来源未知和旧单位依据；遇重复键/孤立输出或不兼容结构中止事务。已有不兼容表须人工核对，脚本不自动删表。

升级后检查两表存在、行数、版本、旧行不变，再重复执行验证幂等。默认开发库与恢复库分开；本次仅在db_enterprise_qa_cd_20261103执行apply。

## 安全回滚

将 `CD_FLUX_V2_ENABLED=false` 后重启服务，v2接口返回503，旧入口继续可用。新表及年度/企业数据保持原样；恢复开关即可恢复访问。隔离数据库测试验证关闭入口后新数据仍在。不提供自动drop或将多年度压平到旧键的降级脚本。

若升级事务失败，连接rollback后重试；schema不兼容则修复配置/结构再试。若需从备份灾难恢复，应先在单独新库中使用pg_restore验证，再切换应用；本次未覆盖整库灾难恢复演练，不允许直接清空原库。
