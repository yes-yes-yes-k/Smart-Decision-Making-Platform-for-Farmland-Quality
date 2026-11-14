# align-cd-removal-projection-v2 Design

## Context

阶段 6/7 的原实现在 `zsj_1107_full_stage67`（2026-11-07），基于 **v1 通量契约**：

| 环节 | v1（原实现假设） | v2（`origin/master` 现状） |
|---|---|---|
| 输入表 | `cd_flux_input`，列 `ZL_Cd`/`JG_Cd`/`DX_Cd`/`DB_Cd`/`bd020_90` | `cd_flux_input_v2`，列 `grain_removal`/`straw_removal`/`groundwater_leaching`/`surface_runoff`/`bulk_density_g_cm3`/`soil_depth_m` |
| 行身份 | 唯一 `(parcel_id, sample_id)` | 唯一 `NULLS NOT DISTINCT (source, parcel_id, sample_id, accounting_year)` |
| 写回语义 | `bulk_update_mappings` 原地改两列 | 必须递增 `input_revision`，旧输出保留但不再是当前结果 |
| 重算 | `cd_flux.calculate(...)` | `cd_flux_v2.calculate(**scope)`，跳过 `contract_version='legacy_v1'` |
| 当年浓度 | `(Initial+Net)/(2000×bd020_90)` | `1000×remaining/(1e7×soil_depth_m×bulk_density)` |
| 端点前缀 | `/api/v1/cd-flux/...` | `/api/v1/cd-flux/v2/...`，`CD_FLUX_V2_ENABLED=false` 时 503 |

结论：v1 版**不能直接合入**。按 `(parcel_id, sample_id)` 全表匹配写回，在 v2 下会把同一地块样点的**多年份、多来源**行一起改掉，属于数据破坏。

## Goals / Non-Goals

**Goals**：阶段 6/7 在 v2 契约上可用；写回绝不误伤其他年度/来源；口径与原系统一致；测试可重复且不污染开发库。

**Non-Goals**：不改公式本体、统计口径、分级与导出上限；不修正原系统已知问题；不实现跨年度批量编排。

## Decisions

### 1. 写回按主键精确定位，不做键匹配

`_write_back` 先用 `cd_flux_v2.select_inputs(source, year)` 取候选行，再以返回的 `id` 逐条 `UPDATE ... WHERE id=:id`，只置 `grain_removal` / `straw_removal` 并把 `input_revision` 加 1。

放弃"按 `(parcel_id, sample_id)` 建索引匹配"的原因：v2 下该组合不再唯一，任何字典索引都会静默覆盖或批量命中。用 `id` 是唯一的正确做法。

### 2. 年度成为写回必填参数

v2 唯一键含 `accounting_year`，而 `cd_crop_prediction_result` 没有年度字段，系统无法推导某条作物结果属于哪个核算年度。因此 `write_back=true` 时 `year` 必填，缺失抛 `year_required`。

考虑过的替代方案：按 `select_inputs` 返回的全年度批量写回（被否，会一次改多个年度）；从导入时间猜年度（被否，猜测即错误）。

### 3. legacy 行隔离 + 多来源歧义拒绝

`contract_version='legacy_v1'` 的行在 v2 计算里本就被跳过，写回同样跳过，并按地块统计数量披露（`legacy_input_skipped`）——它没有年度，会被年度筛选排除，所以单独查一次而不是在结果集里数。

同一 `(parcel_id, sample_id)` 在所选范围内命中多条（不同 `source`）时，判为歧义、**拒绝写回**并披露（`ambiguous_input_rows`）。宁可少写，不可写错。

### 4. 土重口径严格照抄原系统（用户拍板）

经确认，原系统公式是 `(Initial + Net×years)/(2000×bd020_90)`——**含容重**，2000 是固定耕层常数。v2 的 `end_cd` 走 `soil_depth_m × bulk_density × 1e7` 推导，两者仅在 `soil_depth_m=0.2` 时等价（实测：`1000/(1e7×0.2×bd) = 1/(2000×bd)`）。

按"迁移期与原系统一致"的纪律，选**照抄**：分母固定 `2000 × bulk_density_g_cm3`，不读 `soil_depth_m`。代价是与 v2 当年浓度在非 0.2m 耕层时不一致，已登记 `docs/cd-legacy-known-issues.md` 第 11 条。

### 5. 阶段 7 取当前修订的输出

`_base_rows` 用原生 SQL join：`cd_flux_output_v2 ON input_id=i.id AND input_revision=i.input_revision`，并限定 `calculation_version='cd_flux_mass_balance_v2'`。这样写回后重算产生的新修订会被自动选中，旧修订的输出不会被误用。

`accounting_year` 作为**可选**筛选：给出则按年度取数，不给则不限年度（保持原系统"全量一套结果"的可比性），响应记录实际生效值。

### 6. 端点挂 v2 前缀，复用既有开关

10 个端点放在 `/v2/removal/*` 与 `/v2/projection/*`，复用 `cd_flux.py` 已有的 `before_request`（路径含 `/v2/` 且 `CD_FLUX_V2_ENABLED=false` 即 503），不新增开关。

### 7. 测试改 PG 临时 schema

v2 表用 `UNIQUE NULLS NOT DISTINCT`（PG 15+），SQLite 建不了，原 SQLite 内存测试无法复用。

方案：连真实 PG 的**临时 schema**，用 `CREATE TABLE <schema>.x (LIKE public.x INCLUDING DEFAULTS INCLUDING CONSTRAINTS)` 复制列定义（含 PostGIS 类型、不复制索引），测试连接 `search_path` 只指向临时 schema，结束后 `DROP SCHEMA CASCADE`。

> 踩坑记录：第一版把 `public` 也放进 `search_path`，导致 `checkfirst` 认为表已存在而把测试数据写进 public（已清理并复核）。教训是**隔离测试的连接绝不能看见 public**。

公式部分（`_evaluate`、`project_values`、`_stats`）保留纯函数单测，无 PG 时也能跑。

## Risks / Trade-offs

- **年度必填**提高了调用方门槛：批处理必须按年度分批。这是 v2 数据模型的固有代价，不是实现选择。
- **土重口径差异**：非 0.2m 耕层时未来预测与当年浓度不自洽，已登记待议。
- **歧义即拒绝**可能让部分地块静默不写（有计数披露），需要业务侧保证同一地块样点单来源，或明确指定 `source`。

## Migration and Rollback

- 代码：无表结构变更（v2 表由既有 `scripts/migrate_cd_flux_v2.py` 管理）。
- 开发库：2026-11-14 已执行 `--apply` 建表，v1 两表未动；回滚 `DROP TABLE IF EXISTS cd_flux_output_v2, cd_flux_input_v2;`，或还原 `D:\temp\cd_backup\db_enterprise_qa_20261013_20261114.dump`。
- 测试：不设 `CD_MIGRATION_TEST_DB` 时只跑纯公式用例，不影响 CI。

## Open Questions

1. f11 在原库的真实取值（当前默认 800）。
2. 秸秆经验系数 `0.76 / 0.0034` 的出处。
3. 未来年份上限 100 是否按业务调整。
4. 负浓度是否截断到 0。
5. 是否需要跨年度批量重算的编排入口。
