# 阶段 6/7（移除项、未来预测）迁入 v2 基线的对齐评估

> 评估日期 2026-11-14，分支 `zsj_1114`（基于 `origin/master` 4ddf14f）。
> 目的：阶段 6/7 的实现在 `zsj_1107_full_stage67` 分支上已完成并归档（2026-11-07），但该实现基于**v1 通量契约**；`origin/master` 已把通量升级为**v2**（年度 + 来源 + 企业输入 + 输入修订）。本文给出移植前必须核对的差异与待决策项，不代替实施。

## 一、现状（可复核）

| 项 | 事实 | 依据 |
| --- | --- | --- |
| 阶段 6/7 工件 | `2026-11-07-add-cd-removal-calculation`、`2026-11-07-add-future-cd-projection`、`2026-11-07-align-cd-legacy-semantics` 均已归档 | `git ls-tree zsj_1107_full_stage67 openspec/changes/archive/` |
| 阶段 6/7 实现 | `framework/domain/other_models/cd_removal.py`(734)、`cd_projection.py`(422)、`tests/test_cd_removal.py`(362)、`tests/test_cd_projection.py`(200) | 同分支 |
| 端点 | stage67 在 `framework/api/routes/cd_flux.py` 新增 removal 5 个 + projection 5 个端点 | `git show zsj_1107_full_stage67:framework/api/routes/cd_flux.py` |
| master 状态 | **无** removal/projection 任何实现 | `git ls-tree -r --name-only origin/master \| grep -Ei 'cd_removal\|future_cd'` 为空 |
| master 通量已 v2 | `framework/domain/other_models/cd_flux_v2.py`（298 行）、表 `cd_flux_input_v2`/`cd_flux_output_v2`、ADR 0007、`docs/cd-flux-v2-api-and-migration.md` | origin/master |

## 二、v1 与 v2 的契约差异（移植的真实工作量所在）

| 维度 | v1（stage67 实现所依赖） | v2（master 现状） |
| --- | --- | --- |
| 输入表 | `cd_flux_input`，列 `ZL_Cd`/`JG_Cd`/`DX_Cd`/`DB_Cd`/`Initial_Cd`/`bd020_90` | `cd_flux_input_v2`，列 `grain_removal`/`straw_removal`/`groundwater_leaching`/`surface_runoff`/`initial_cd`/`bulk_density_g_cm3`/`soil_depth_m` |
| 行身份 | 唯一约束 `(parcel_id, sample_id)` | `UNIQUE NULLS NOT DISTINCT (source, parcel_id, sample_id, accounting_year)` |
| 写回输入 | `bulk_update_mappings` 原地改两列 | 必须**递增 `input_revision`**，旧输出保留但不再作为当前结果 |
| 重算 | 调 `cd_flux.calculate(...)` | 调 `cd_flux_v2.calculate(**scope)`，跳过 `contract_version='legacy_v1'` 行 |
| 末期浓度 | `(Initial + Net) / (2000 × bd020_90)` | 由 `soil_depth_m` × `bulk_density_g_cm3` 推导土重（`cd_flux_v2.trial`） |
| 初始量单位 | mg/kg 浓度语义 | `initial_cd` 为 **g/ha** 储量；浓度→储量需厚度+容重 |
| 端点前缀 | `/api/v1/cd-flux/...` | `/api/v1/cd-flux/v2/...`，`CD_FLUX_V2_ENABLED=false` 时返回 503 |

## 三、移植必须改的六处

1. **写回目标与键**：`cd_removal._write_back()`（stage67 第 280–320 行）按 `(parcel_id, sample_id)` 全表匹配 `existing`，在 v2 下同一地块样点可能存在**多年份、多来源**多行，照搬会批量写错行。必须改为按 `select_inputs(**scope)` 返回的 `id` 精确写，并把年份/来源作为必需 scope 参数（或显式要求 `year`）。
2. **写回语义**：v2 的输入变更通过 `ON CONFLICT ... DO UPDATE SET ..., input_revision = input_revision + 1`（`cd_flux_v2.import_csv` 第 196 行）表达。写回两列应复用同一语义，只更新 `grain_removal`/`straw_removal` 并递增修订，不得把其他列置空。
3. **legacy 行隔离**：`contract_version='legacy_v1'` 的行不参与计算（`cd_flux_v2.calculate` 第 212 行），写回也必须跳过，并在返回值中披露跳过数。
4. **重算调用与结果口径**：改调 `cd_flux_v2.calculate(**scope)`；返回需分别给出 `updated_inputs` / `missing_input_rows` / `skipped_invalid_denominator` / `recalculated`，重算失败不得报整体成功（沿用阶段 6 已归档规格）。
5. **阶段 7 的外推口径**：`Future_Cd = (Initial + Net × years) / (2000 × bd020_90)` 在 v2 落成 `(initial_cd + net_cd × years) / (soil_depth_m × bulk_density_g_cm3 × 1000)` 的等价形式前，必须先确认单位链（v2 `initial_cd` 是 g/ha 储量，`Net_Cd` 是 g/ha/a）。**这是数值口径问题，不是重构问题**，须与"迁移期与原系统一致"的纪律对齐后再动手。
6. **端点归属**：阶段 6/7 的 10 个端点要么挂到 `/api/v1/cd-flux/v2` 前缀下按 v2 scope 取值，要么保留 v1 兼容入口。需先确认 master 上 `integrate-cd-flux-visualization-chat` 是否已占用同名路由。

## 四、待决策项（请先拍板，不要替用户决定）

| 编号 | 问题 | 影响面 |
| --- | --- | --- |
| A | 写回是否必须显式提供 `accounting_year`（缺失即拒绝），还是允许按 `source + parcel + sample` 匹配全部年度？ | 决定 v2 上年份维度的安全边界 |
| B | `f11`（亩产量）在 v2 下是否仍固定默认 800、来源仍标"原系统 Parameters(area='韶关')"？v2 企业输入机制是否应扩展为按区域/年度取亩产？ | 决定是否需要新输入字段 |
| C | 阶段 7 外推的土重口径：沿用 v2 `soil_depth_m × bulk_density` 推导，还是保留原系统固定 2000 kg/ha（不乘容重）？ | 直接影响未来浓度数值与历史可比性 |
| D | 端点放置：v2 前缀 / v1 兼容 / 双份 | 与同事在途 change 的冲突面 |
| E | 移植方式：在 `zsj_1114` 上按 v2 重写数据访问层（保留公式与统计），还是先合并 stage67 原样代码再迭代？ | 提交历史与回归风险 |

## 五、建议的实施顺序（待 A–E 拍板后执行）

1. 从 `zsj_1107_full_stage67` 取 `cd_removal.py` / `cd_projection.py` 的**公式与统计部分**（`_evaluate`、`_summary`、`_preview`、分布与导出），这部分与 v1/v2 无关，可原样复用。
2. 重写数据访问层：`_crop_rows`（作物 Cd 读数）、`_input_series`、`_write_back`，改为走 `cd_flux_v2.select_inputs` 与 v2 修订写回。
3. 按新口径重跑 `tests/test_cd_removal.py` / `test_cd_projection.py`，并补"多年份同地块样点不被误写"的回归用例。
4. 工件侧不需要新 change：阶段 6/7 的 spec 已归档在 stage67 分支，应随实现一起移植（`openspec/specs/cd-removal-calculation`、`cd-future-projection`），然后按"规格追平实现"补一条 v2 适配的 delta。

## 六、开发库实测（2026-11-14，只读探针）

探针：`D:\temp\probe_cd_flux_v2.py`（psycopg2，`set_session(readonly=True)`，口令取自 `.env` 且不回显）。

| 库 | 实测结果 |
| --- | --- |
| `db_enterprise_qa_20261013`（`.env` 当前指向） | `cd_flux_input_v2` / `cd_flux_output_v2` **不存在**；`cd_flux_input` / `cd_flux_output` 各 0 行；`cd_crop_prediction_result` 40100 行；`cd_ported_parcel_township` 40100 行 |
| `db_enterprise_qa_cd_20261103`（`docs/cd-flux-v2-api-and-migration.md` 记录的 apply 库） | **不存在**。实例内数据库仅：`acid_test`、`db_enterprise_qa`、`db_enterprise_qa_20261013`、`postgres`、`soilgd`、`soilgd_test` |

**结论（2026-11-14 当日已解决）**：v2 的两张表当时尚未创建，现已按用户授权完成建表与端到端验证：

1. 全库备份 → `D:\temp\cd_backup\db_enterprise_qa_20261013_20261114.dump`（89 MB，SHA-256 `b77c5cad…d609`，archive_list 校验通过）；
2. `scripts/migrate_cd_flux_v2.py --apply` 建表（先无 `--apply` 演练确认 `rehearsal_rolled_back`），v1 两表原样保留；
3. `D:\temp\probe_stage67_v2.py` 端到端：3 个真实 `SGD_` 地块 → v2 导入 → 重算 → 阶段 6 写回（grain/straw 与公式逐位吻合、`input_revision` 1→2、其他列未动）→ 阶段 7 十年预测（逐点 diff=0）；
4. 探针行全部清理，两表回到 0 行，`cd_crop_prediction_result` 40100 行与 `parcel_info` 45588 行均未变。

**这带来一个设计后果**：v2 下写回必须显式携带 `accounting_year`（v2 唯一键含年度，而 `cd_crop_prediction_result` 无年度字段，无法自动推导）。这一条已从"待决策 A"变成技术必然，并已在实现与规格中固化。
