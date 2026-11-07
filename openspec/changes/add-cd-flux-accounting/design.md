# add-cd-flux-accounting Design

## Context

原系统 Cd 通量链路（已逐行核验）：

| 环节 | 原系统实现 |
|---|---|
| 输入表 | `FluxCd_input_data`：`Initial_Cd`（g/ha）+ `DQCJ_Cd`（大气沉降）+ `GGS_Cd`（灌溉）+ `NCP_Cd`（农化投入）+ `DX_Cd`（地下渗漏，默认 0.023）+ `DB_Cd`（地表径流，默认 0.368）+ `ZL_Cd`（籽粒移除）+ `JG_Cd`（秸秆移除） |
| 计算 | `calculate_and_update_output_data`：`In = DQCJ+GGS+NCP`；`Out = DX+DB+ZL+JG`（从输入表读实际值）；`Net = In−Out`；`End = (Initial+Net) / (2000×bd020_90)`，`bd020_90` 来自 `SoilData`，缺失回退 1.0、`Initial_Cd` 缺失回退 0 |
| 输出表 | `FluxCd_output_data`：`In_Cd/Out_Cd/Net_Cd/End_Cd`，按 `(Farmland_ID, Sample_ID)` 更新或插入，无唯一约束 |
| 统计 | `FluxCdStatisticsService.get_flux_statistics_by_town`：用 `ST_Contains(town, point(lon,lan))` 判定乡镇；单位 `g/ha/a`（浓度 `mg/kg`） |
| 分布 | `end_cd` 三档 `<0.3 / 0.3–0.6 / ≥0.6`（GB 15618-2018）；`net_cd` 负/接近平衡(-5~5)/正；`in/out` 相对均值三档 |
| 可视化 | `generate_cd_{input,output,net}_flux_map` 复用 `MappingUtils`；未来预测 `predict_future_cd` 属阶段 7 |
| CSV | `FluxCdUpdateService.update_from_csv` + 各字段导出端点 |

新库实测（`db_enterprise_qa_20261013`，64 张表）：**无任何 flux 相关表**；`third_survey_bulk_densities` **0 行**；`third_survey_topsoils` 无容重字段。即通量输入分量与容重在新库均无现成来源。

## Goals / Non-Goals

**Goals**

- 建立与原系统同构的 flux 输入/输出表，支持完整输入行导入、计算、区域统计、分布、空间结果与 CSV 导出。
- 修正原系统两处缺陷：分箱重叠、两套公式不一致。
- 统计与归属口径与已归档阶段 2/3 保持一致；可视化复用阶段 4 引擎。

**Non-Goals**：阶段 6 的移除项独立计算、阶段 7 的未来预测、从第三方数据自动推导输入分量。

## Decisions

### 1. 表结构与唯一约束（有意偏差）

`cd_flux_input`：`parcel_id, sample_id, initial_cd, atmospheric_deposition(DQCJ), irrigation_input(GGS), agro_chemicals_input(NCP), groundwater_leaching(DX), surface_runoff(DB), grain_removal(ZL), straw_removal(JG), bd020_90`；`cd_flux_output`：`parcel_id, sample_id, in_cd, out_cd, net_cd, end_cd`。

与原系统同构（只存数值、无模型版本/执行标识），但给两表都加 `(parcel_id, sample_id)` 唯一约束——原系统无约束、覆盖写遗漏会重复累积（与阶段 1 相同的修正理由，对调用方透明）。

### 2. 输入数据外部供给（覆盖率实测 0）

新库无 flux 表、容重表 0 行、topsoils 无容重字段，`DQCJ/GGS/NCP`（大气沉降/灌溉/农化）也无现成来源。因此本阶段不承诺「从现有数据自动算」，而是提供 **CSV 导入**把完整输入行灌入 `cd_flux_input`；自动推导留作后续 change。导入契约：必需列 `parcel_id, sample_id, initial_cd, DQCJ_Cd, GGS_Cd, NCP_Cd, DX_Cd, DB_Cd, ZL_Cd, JG_Cd`，可选 `bd020_90`（缺省按计算回退规则处理）。

### 3. 公式统一为数据库模式

原系统 CSV 模式用固定常量（0.023/0.368/0.0/0.0）与固定 2000 kg/ha，数据库模式从输入表读实际值并乘 `bd020_90`——同一概念两套口径。本阶段只保留数据库模式公式：

```
In  = DQCJ + GGS + NCP
Out = DX + DB + ZL + JG
Net = In − Out
End = (Initial + Net) / (2000 × bd020_90)      # bd020_90 缺失→1.0；Initial 缺失→0；soil_mass<=0→0
```

响应/元信息记录 `bd020_90` 与 `initial_cd` 的回退计数。

### 4. 分箱互斥化（修正原系统缺陷）

- `end_cd`：`<0.3` 安全 / `0.3–0.6` 预警 / `≥0.6` 超标（GB 15618-2018，照抄）。
- `net_cd`：**互斥**三档 `v < -5` 负通量 / `-5 ≤ v ≤ 5` 接近平衡 / `v > 5` 正通量（原系统 `v<0` 与 `-5~5` 重叠，占比可超 100%；本阶段修正，写进 spec 的「占比之和 MUST ≤ 100%」断言）。
- `in_cd/out_cd`：相对本批均值三档 `<0.5×mean / 0.5–1.5×mean / ≥1.5×mean`（照抄，标注 `relative: true`——跨批次不可比）。

### 5. 统计与归属复用既有阶段

区域/乡镇聚合复用阶段 3 的归属依据（自有→面积最大、移植→点面判断），不重建 `town` 表点面 SQL；8 项基础统计复用阶段 2 的总体标准差与下标分位数口径。区域过滤支持 `region_type/region_id` 与 `source`。

### 6. 空间结果复用阶段 4 引擎

点位 GeoJSON 复用「结果表 + 地块质心」取数形状；分级地图/直方图调用阶段 4 `heavy_metal_cd_visualization` 的栅格化/渲染内部函数（同包调用，不改其规格与端点）。地图分级：`net_cd` 用三档互斥分箱（负/平衡/正），`end_cd` 用 GB15618 三档，`in/out` 用分位数 6 级（与有效态展示一致，标注相对分级）。

### 7. 端点与错误语义

- `POST /api/v1/cd-flux/inputs/import`：CSV 上传（multipart），返回导入/覆盖/跳过计数。
- `POST /api/v1/cd-flux/calculate`：body `{region_type?, region_id?, source?}`，重算并覆盖写输出表，返回更新/新增/回退计数。
- `GET /api/v1/cd-flux/statistics`：`model=in_cd|out_cd|net_cd|end_cd`（默认 in_cd）+ `region_type/region_id/source`。
- `GET /api/v1/cd-flux/results`：分页明细。
- `GET /api/v1/cd-flux/export.csv`：CSV 导出（`max_rows` 上限 10 万，与阶段 2 一致）。
- `POST /api/v1/cd-flux/visualization`：生成 flux 地图/直方图（复用阶段 4 产物目录规范）。
- 空数据返回 200 + `has_data=false`（与阶段 2 一致）；非法字段/区域 400；区域不存在 404。

## Risks / Trade-offs

- **输入数据靠外部**：没有 CSV 供给时全链路无数据；`calculate` 在输入表为空时返回 `has_data=false` 而不是报错。
- **相对分箱**：`in/out` 相对菜均值分级跨批次不可比，元信息标注 `relative: true`。
- **容重缺失面大**：`bd020_90` 回退 1.0 会让 `end_cd` 偏大/偏小，必须把回退计数暴露给调用方。
- **重算覆盖**：`calculate` 按唯一键覆盖写，历史不保留（与原系统同口径）；需要历史对比时另建快照。

## Migration and Rollback

- 建表脚本 `scripts/migrate_cd_flux_tables.py`（`db.create_all()` + 幂等），与既有手写迁移路线一致。
- 回滚 = 删两张表、删代码与端点；不影响 Cd 预测结果表与已归档能力。

## Open Questions

1. `bd020_90` 的权威来源（新库容重表 0 行）：是否需要后续 change 从第三方普查数据导入容重？
2. `net_cd` 平衡区间阈值 ±5 g/ha/a 为原系统硬编码，是否随业务口径调整？
3. `end_cd` 三档阈值沿用 GB 15618-2018（0.3/0.6 mg/kg），是否按土壤 pH/土地利用类型细分？
