# add-cd-removal-calculation Design

## Context

原系统移除项链路（`app/services/cd_flux_removal_service.py`，已逐行核验）：

| 环节 | 原系统实现 |
|---|---|
| 籽粒移除 | `grain = EXP(LnCropCd) × F11 × 0.5 × 15 / 1000`（g/ha/a） |
| 秸秆移除 | `straw = [EXP(LnCropCd) / (EXP(LnCropCd)×0.76 − 0.0034)] × F11 × 0.5 × 15 / 1000`；分母 ≤0 时**静默跳过**该样点 |
| 参数 | `Parameters` 表 `area="韶关"` 的 `F11`（作物亩产量，斤/亩），模型默认 800 |
| 数据源 | 遍历 `CropCd_output_data` 全部行（不按区域过滤，area 只用于地图边界） |
| 地下渗漏/地表径流 | `update_groundwater_leaching_to_database` / `update_surface_runoff_to_database` 是**空壳**，直接返回"数据已存在，无需更新"——数值来自 `FluxCd_input_data` 的 `DX_Cd/DB_Cd` |
| 可视化/导出 | 四类各自地图/直方图/CSV，使用独立模板 `app/static/cd_flux/meanTemp.tif` |

系数语义推演（与原系统注释与量纲一致）：`0.5` = 斤→kg（0.5 kg/斤），`15` = 亩→公顷（15 亩/ha），`1000` = mg→g。验证：浓度 0.1 mg/kg × 800 斤/亩 × 0.5 × 15 / 1000 = 0.6 g/ha/a ✓。

## Goals / Non-Goals

**Goals**：把籽粒/秸秆移除算出来并写回 `cd_flux_input`，触发阶段 5 重算；四类移除项可统计/点位/导出/出图；f11 可配置。

**Non-Goals**：地下渗漏/地表径流的物理计算（原系统即空壳）、未来预测、F1–F10 参数。

## Decisions

### 1. 公式逐项照抄

籽粒：`grain = exp(ln_crop_cd) × f11 × 0.5 × 15 / 1000`
秸秆：`straw = exp(ln_crop_cd) / (exp(ln_crop_cd) × 0.76 − 0.0034) × f11 × 0.5 × 15 / 1000`

不做"改良"（例如不把 0.76/0.0034 换成别的经验式）。系数 0.5/15/1000 按量纲说明写进 spec，防止后人误改。

### 2. 秸秆分母非正：跳过但必须计数

原系统对 `C×0.76−0.0034 ≤ 0` 的样点静默跳过（日志 warning），调用方无从得知。本实现跳过这些样点，但返回 `skipped_invalid_denominator` 计数与样点列表前 N 条，写入响应与产物元信息——跳过不能是隐形的。

### 3. f11 由请求提供，默认 800

原系统从 `Parameters` 表按 `area="韶关"` 取，本机无法读取原库（认证失败），且新库没有 `Parameters` 表。因此把 `f11` 作为请求参数（默认 800，即原模型默认值），响应记录实际使用值；是否需要建参数表/按区域配置写进 Open Questions。

### 4. 写回 + 触发重算的边界

流程：计算 → 按 `(parcel_id, sample_id)` 更新 `cd_flux_input.ZL_Cd / JG_Cd`（只更新这两列，不动其他分量）→ **提交** → 调用阶段 5 `cd_flux.calculate()` 重算输出表。

写回与重算分两步而非一个事务：重算是批量读取 + 覆盖写，耗时可观；若重算失败，写回仍然有效（重算可重试），响应里分别报告 `updated_inputs` 与 `recalculated` 状态。**不允许**重算失败时静默成功。

### 5. 地下渗漏/地表径流不计算

照抄原系统语义：`DX_Cd/DB_Cd` 从输入表读，本能力只提供统计/点位/导出/可视化（复用阶段 5 的 `statistics/points/export` 逻辑，字段固定为这两项）。不新增物理模型。

### 6. 区域过滤与数据源

作物 Cd 结果按 `source`（自有/移植）过滤，区域过滤复用阶段 3 归属依据；写回只针对参与计算的样点。区域参数只影响"算哪些样点"，与原系统"area 仅用于地图边界"不同——本实现让区域过滤真正生效（有意偏差，写进 spec）。

### 7. 端点

- `POST /api/v1/cd-flux/removal/calculate`：body `{f11?, region_type?, region_id?, source?, recalculate: true}` → `{grain: {...}, straw: {...}, updated_inputs, recalculated, skipped_invalid_denominator}`
- `GET /api/v1/cd-flux/removal/statistics?field=grain|straw|leaching|runoff`：8 项统计 + 单位
- `GET /api/v1/cd-flux/removal/points?field=...`：点位 GeoJSON（同阶段 5 形状）
- `GET /api/v1/cd-flux/removal/export.csv?field=...`：导出（10 万行上限）
- `POST /api/v1/cd-flux/removal/visualization`：地图/直方图（复用阶段 4/5 引擎）

## Risks / Trade-offs

- **f11 口径不确定**：默认 800 是模型默认值，原库实际值无法验证；若业务方参数不同，grain/straw 会同比例偏移（响应记录 f11，可追溯）。
- **写回覆盖**：ZL/JG 被重算覆盖，人工填过的值会丢失——端点默认 `recalculate=true`，但也允许只计算不写回（`write_back=false`）供核对。
- **秸秆经验式**：`0.76/0.0034` 出处未知（原系统无注释），照抄后在 spec 标注"经验系数、来源未考证"。
- **区域过滤差异**：原系统全量计算、area 仅作边界；本实现区域过滤真实生效，跨区域对比时口径需注意。

## Migration and Rollback

- 不新增表：只写 `cd_flux_input.ZL_Cd / JG_Cd`。回滚 = 删除模块与端点；已写入的 ZL/JG 可用阶段 5 的 CSV 导入覆盖回原值。

## Open Questions

1. `f11` 原库（`Parameters.area="韶关"`）的实际值（本机无法读取原库，认证失败）；是否要建参数表按区域配置？
2. 秸秆转换式 `C×0.76−0.0034` 的出处与适用范围（经验式，来源未考证）。
3. 是否允许 `write_back=false` 只算不写（当前设计允许，便于核对）。
