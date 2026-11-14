## 为什么

阶段 6（移除项计算）与阶段 7（未来 Cd 情景预测）的实现完成于 2026-11-07 的 `zsj_1107_full_stage67` 分支，基于当时的 **v1 通量契约**（`cd_flux_input` / `cd_flux_output`，键为 `(parcel_id, sample_id)`）。此后 `origin/master` 把通量能力升级为 **v2**（`cd_flux_v2.py`、`cd_flux_input_v2` / `cd_flux_output_v2`，唯一键含 `accounting_year` 与 `source`，写回通过 `input_revision` 递增表达）。

v1 版本无法直接合入主线：

- 写回按 `(parcel_id, sample_id)` 全表匹配，在 v2 下同一地块样点可能存在**多年份、多来源**多行，照搬会批量写错行；
- v2 的输入变更语义是"递增 `input_revision`、旧输出保留但不作为当前结果"，原地改两列不成立；
- `contract_version='legacy_v1'` 的行在 v2 计算中被跳过，写回也必须跳过；
- 阶段 7 的 `bd020_90` 列在 v2 中更名为 `bulk_density_g_cm3`，且取数需按 `(input_id, input_revision)` 取当前修订。

对齐评估见 `docs/cd-removal-projection-v2-alignment.md`（2026-11-14）。

## 变更内容

1. **阶段 6 数据访问层迁到 v2**（`framework/domain/other_models/cd_removal.py`）：
   - 写回目标改为 `cd_flux_input_v2`，按 `select_inputs` 返回的 `id` 精确定位，只更新 `grain_removal` / `straw_removal` 两列并递增 `input_revision`；
   - `write_back=true` 时 `year` 必填（v2 唯一键含年度，作物结果表无年度字段），缺失返回 `year_required`；
   - 跳过 `legacy_v1` 行并在 `legacy_input_skipped` 披露；同地块样点命中多个来源时判歧义、拒绝写回并在 `ambiguous_input_rows` 披露；
   - 重算改调 `cd_flux_v2.calculate(**scope)`；
   - `leaching` / `runoff` 改读 v2 表 `groundwater_leaching` / `surface_runoff`。
2. **阶段 7 数据访问层迁到 v2**（`framework/domain/other_models/cd_projection.py`）：
   - 取数改为 `cd_flux_input_v2 ⋈ cd_flux_output_v2`（按 `input_id + input_revision` 取当前修订，`calculation_version='cd_flux_mass_balance_v2'`），跳过 legacy 行；
   - 容重列改为 `bulk_density_g_cm3`，回退计数键同步更名；
   - 新增可选 `accounting_year` 数据维度筛选（默认不限年度，保持原系统全量可比性）。
3. **土重口径按用户拍板严格照抄原系统**：`Future_Cd=(Initial+Net×years)/(2000×bulk_density_g_cm3)`，**不读 `soil_depth_m`**。该式与 v2 `calculate.end_cd` 仅在 0.2m 耕层等价，差异登记到 `docs/cd-legacy-known-issues.md` 第 11 条。
4. **端点挂到 v2 前缀**：10 个端点分别位于 `/api/v1/cd-flux/v2/removal/*` 与 `/api/v1/cd-flux/v2/projection/*`，受 `CD_FLUX_V2_ENABLED` 开关约束。
5. **测试改为 PG 隔离**：v2 表使用 `UNIQUE NULLS NOT DISTINCT`，SQLite 无法建表，因此落库用例走真实 PostgreSQL 的**临时 schema**（`LIKE public.x` 复制列、只读 public 之外零写入），无库时自动 skip；公式部分保留无 DB 单测。

## 非目标

- 不改动公式本体、统计口径（样本标准差 ddof=1 + 线性插值分位）、分布分级与导出上限。
- 不改动区域参数"仅记录不参与查询"的原系统行为。
- 不修正原系统已知问题本身，只记录。
- 不实现跨年度批量编排入口。

## 影响

- 阶段 6/7 在 v2 基线上可用，且不会写错多年份/多来源行。
- 调用方写回时必须提供 `accounting_year`；这是行为变化，已在规格与 known-issues 中声明。
- 测试从内存 SQLite 改为 PG 临时 schema，回归命令需带 `CD_MIGRATION_TEST_DB` / `CD_MIGRATION_ENV_FILE`，否则仅跑公式单测。
- 实测：`test_cd_removal` 15 passed、`test_cd_projection` 10 passed，Cd 相关回归 163 passed / 2 skipped。

## Roadmap

本 change 对应 Cd 迁移路线图的**阶段 6 + 阶段 7**（v2 适配版），前置为阶段 5 与主线通量 v2 契约，后续为阶段 7 之上的多年份对比增强与对话接入。
