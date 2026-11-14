# Tasks

## 1. 阶段 6 数据访问层迁到 v2

- [x] 1.1 `_write_back` 改为按 `select_inputs` 的 `id` 精确更新，只写 `grain_removal` / `straw_removal` 并递增 `input_revision`
- [x] 1.2 `write_back=true` 且缺 `year` 时抛 `year_required`（不猜测、不写全年度）
- [x] 1.3 legacy 行不写回并按地块统计披露；多来源同键判歧义、拒绝写回
- [x] 1.4 重算改调 `cd_flux_v2.calculate(source=..., year=...)`
- [x] 1.5 `leaching` / `runoff` 改读 v2 表的 `groundwater_leaching` / `surface_runoff`
- [x] 1.6 统计/点位/导出/出图统一接受可选 `year` 并透传

## 2. 阶段 7 数据访问层迁到 v2

- [x] 2.1 `_base_rows` 改为 `cd_flux_input_v2 ⋈ cd_flux_output_v2`，按 `input_id + input_revision` 取当前修订
- [x] 2.2 跳过 `contract_version='legacy_v1'` 行
- [x] 2.3 容重列更名 `bulk_density_g_cm3`，回退计数键同步
- [x] 2.4 新增可选 `accounting_year` 筛选并在响应记录

## 3. 口径与端点

- [x] 3.1 土重严格照抄原系统：`2000 × bulk_density`，不读 `soil_depth_m`（附守门用例）
- [x] 3.2 10 个端点挂到 `/api/v1/cd-flux/v2/removal/*` 与 `/api/v1/cd-flux/v2/projection/*`，受 `CD_FLUX_V2_ENABLED` 约束
- [x] 3.3 错误码补 `year_required` / `invalid_year` / `invalid_accounting_year` 到 400 白名单

## 4. 测试

- [x] 4.1 `tests/test_cd_removal.py` 重写：公式单测 + PG 临时 schema 写回用例（年度隔离、legacy 跳过、歧义拒绝、修订递增、HTTP）
- [x] 4.2 `tests/test_cd_projection.py` 重写：公式单测 + PG 用例（当前修订、年度隔离、legacy 跳过、HTTP）
- [x] 4.3 临时 schema 用 `LIKE public.x` 复制列，测试连接 `search_path` 仅指向临时 schema，public 零写入
- [x] 4.4 全量回归：Cd 相关 163 passed / 2 skipped；开发库复核 `cd_crop_prediction_result` 40100 行未变、无残留 schema

## 5. 文档

- [x] 5.1 `docs/cd-migration-roadmap.md` 回填阶段 6/7 状态
- [x] 5.2 `docs/cd-legacy-known-issues.md` 追加第 11–13 条（土重口径差异、年度必填、按年度覆盖）
- [x] 5.3 `openspec/specs/cd-removal-calculation`、`cd-future-projection` 更新为 v2 语义
