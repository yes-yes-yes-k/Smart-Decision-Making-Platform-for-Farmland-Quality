# add-heavy-metal-cd-database-backend Proposal

## Why

`add-heavy-metal-cd-prediction` 已经交付了参数级推理：给出 14 个（作物 Cd）/ 21 个（有效态 Cd）特征值，本地 torch 返回一个预测数，15 个测试通过。但它还不能做真正的业务：**当前系统数据库里没有任何一条 Cd 结果**，也没有"从地块数据取数 → 批量预测 → 结果落库"的链路。

原 AcidMap 系统的这条链路是完整的（实测源码 `app/services/cd_prediction_database_service.py` 第 245–291 行）：

- 取本批次涉及的 `farmland_id` 列表；
- `DELETE FROM EffCd_output_data WHERE Farmland_ID IN (...)` 清掉这些地块的旧记录；
- `bulk_insert_mappings` 分批（5000 条/批）插入本次结果；
- 整个操作在一个事务里，失败整体 rollback。
- 结果表只存自然对数值：`EffCd_output_data(ID, Farmland_ID, Sample_ID, LnEffCd)`、`CropCd_output_data(ID, Farmland_ID, Sample_ID, LnCropCd)`，无唯一约束、无批次号、无历史表、无模型版本、无计算时间。
- 单位在原系统里是明确的：`EffCd = exp(LnEffCd) [单位：mg/kg]`、`CropCd = exp(LnCropCd) [单位：mg/kg]`（`app/models/EffCd_output.py`、`CropCd_output.py` 的类文档与列注释）。

当前系统的缺口（实测，非推断）：

- `framework/models/soil_data.py` 有 `third_survey_topsoils.cd` 等原始字段，但**没有任何 Cd 结果表**；
- `framework/models/thematic_model.py` 的 15 张结果表里没有 Cd；
- `prefill_from_parcel()` 只做单地块的"部分预填"（5 个字段有映射），没有批量取数、没有持久化；
- 哪些库存字段能映射到 14/21 个模型特征，此前从未逐字段核实过。2026-10-31 已实测：**两模型能凑齐全部特征的地块数均为 0**（详见 `docs/cd-input-coverage-report.md`），硬缺口是质地三组分、全铝、全钙、全镁、OC-Fe 与 MSM 输出。

## What Changes

- 新增两张结果表 `cd_crop_prediction_result`、`cd_effective_prediction_result`，列与原系统同构（只存自然对数值），注释标明单位 mg/kg。
- 新增数据库输入适配层：按已确认的映射把地块库存字段转成模型特征，无法映射的进 `missing_fields`，不填默认值、不用区域均值。
- 新增两个批量预测服务函数（作物 Cd、有效态 Cd）：读库 → 推理 → **按地块覆盖写库**，单事务提交。
- 新增结果读取函数：从自然对数值还原为 mg/kg 后返回。
- 修正单位口径：`unit_status` 由 `unverified` 改为 `verified`，依据是原系统模型类文档与列注释（`effc_d = exp(LnEffCd) [单位：mg/kg]`）。
- 附一份逐字段映射表，把"已确认可映射"与"未确认"分开，未确认项进 Open Questions。

## Capabilities

### New Capabilities

- **heavy-metal-cd-database-backend**：从当前系统数据库取数执行 Cd 双模型预测，按地块覆盖写结果表，并提供还原为 mg/kg 的读取入口。

### Modified Capabilities

- **heavy-metal-cd-prediction**：输出单位状态由 `unverified` 改为 `verified` 并标注 `mg/kg`（依据原系统模型注释）；仍然不提供任何阈值分箱或法规结论。

## Impact

- **数据库**：新增 2 张表。走现有迁移路线（`db.create_all()` + `scripts/migrate_add_cd_result_tables.py`），不引入 Alembic，无 `ALTER` 需求。
- **代码**：新增 `framework/domain/other_models/heavy_metal_cd_db.py`（适配 + 服务 + 读取）；模型定义加入 `framework/models/`；新增 `scripts/run_cd_prediction.py` 批处理入口。
- **对外契约**：`available_models()` 与 `predict()` 返回新增 `unit="mg/kg"` 与 `unit_basis` 两个只读键；`unit_status` **维持 `unverified`**（实测 `exp(LnEffCd)` 落在 1.004–2.295 mg/kg，量级待核），因此仓库内既有的两处 `unverified` 断言不需要改动。
- **数据边界**：只读写当前系统数据库（`.env` 的 `DB_*`，当前库 `db_enterprise_qa_20261013`）；**不读**本机 `soilgd` 库，**不依赖** AcidMap 在线服务。
- **上游依赖**：`solution` / `cdsolution` 由上游 MSM 络合模型提供（原系统链路 `MSM_output_data.Cd.solution → solution = LN(POR_Layer/bd020_90*112000*Cd.solution)`）。本仓库尚未集成 MSM，阶段 1 以"该输入由上游提供"为前提；MSM 集成留后续 change。
- **不产生** HTTP 接口（阶段 2 才出 API）。

## Roadmap

- 阶段：**1 / 7**（阶段 0 `add-heavy-metal-cd-prediction` 已归档，2026-10-25）
- 前置：`add-heavy-metal-cd-prediction`（提供参数级 callable 与模型资产）
- 后续：`add-heavy-metal-cd-statistics-api`（阶段 2：统计、查询、导出）
- 单一真相源：`docs/cd-migration-roadmap.md`；归档时需回填该文件状态

## Non-Goals

- 不做统计/查询/导出接口（阶段 2）。
- 不做空间结果、乡镇统计、地图、直方图、栅格（阶段 3/4）。
- 不做 Cd 通量收支、移除过程、未来情景预测（阶段 5–7）。
- 不建批次表与历史表，不记录 `model_version`、`computed_at`、`execution_id`（按用户口径与原系统保持一致，不做"哪个模型算的"追踪）。
- 不接入 `VersionedModelResult` 统一发布层（同上口径；后果见 design 决策 4）。
- 不做有效态 Cd 的阈值分箱（原系统没有，本项目也不做）。
