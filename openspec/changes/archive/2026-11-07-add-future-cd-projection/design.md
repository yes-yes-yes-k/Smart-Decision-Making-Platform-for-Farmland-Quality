# add-future-cd-projection Design

## Context

原系统 `predict_future_cd`（`app/services/cd_flux_service.py` 876–1029 行）已核验：

| 环节 | 原系统实现 |
|---|---|
| 公式 | `Future_Cd = (Initial_Cd + Net_Cd × years) / (2000 × bd020_90)`，years 1–100 |
| 数据源 | `FluxCd_input_data` + `SoilData.bd020_90` + `FarmlandData(lon, lan)` |
| 区域筛选 | **未实现**：`area` 只进日志，查询全量（源码 TODO） |
| 统计 | `count/mean/std/min/max/median/p25/p75`，其中 `std` 是 pandas 默认**样本标准差**（n−1） |
| 回退 | `bd020_90` 缺失→1.0；`initial_cd` 缺失→0；`soil_mass<=0`→0 |
| 输出 | 统计 + 预测列表 + 可选地图/直方图/CSV；不落库 |

## Goals / Non-Goals

**Goals**：按恒定净通量线性外推未来 N 年；多年份对比；区域/来源过滤真实生效；统计与阶段 2 口径一致；空间分布与导出。

**Non-Goals**：气候变化/管理措施情景建模；预测结果落库。

## Decisions

### 1. 公式照抄，不做非线性外推

`Future_Cd = (Initial_Cd + Net_Cd × years) / (2000 × bd020_90)`。净通量取阶段 5 输出表（已含阶段 6 写回的籽粒/秸秆移除），不在本阶段重算。回退规则与阶段 5 一致（`bd020_90→1.0`、`initial_cd→0`、`soil_mass<=0→0`），回退计数写入响应。

### 2. 区域过滤真实生效（修正原系统 TODO）

区域过滤复用阶段 3 归属依据（自有→面积最大、移植→点面判断）与 `source` 过滤。原系统"area 只用于日志"属于未完成实现，不照抄。

### 3. 统计统一阶段 2 口径（有意偏差）

原系统用 `pandas.std()`（样本标准差 n−1）与 `quantile`（线性插值），本项目阶段 2 已确立**总体标准差**与**下标直取分位数**为统一口径。本阶段复用 `heavy_metal_cd_statistics.basic_statistics`，与阶段 2/3/5 保持一致；差异写进 spec，避免调用方误以为是回归。

### 4. 多年份情景

请求接受 `years`（int 或 int 列表，1–100）。返回结构按年份分键：`{1: {统计, 逐点}, 5: {...}, 10: {...}}`。逐点值不默认返回（40100 点 × 多份会很大），只在 `points`/`export` 端点按单一年份返回。

### 5. 不落库 + 导出

预测按需计算、不写业务表（与原系统一致）；需要留存时用 `export.csv`。空间分布沿用阶段 4 产物目录（`data/cd_visualization/projection_<years>/<artifact_id>/`）。

### 6. 端点

- `POST /api/v1/cd-flux/projection`：body `{years: 1|5|10 或 [1,5,10], region_type?, region_id?, source?}` → 各年份统计 + 回退计数
- `GET /api/v1/cd-flux/projection/statistics?years=N&...`：单年份完整统计（8 项 + 分布三档 GB15618）
- `GET /api/v1/cd-flux/projection/points?years=N&...`：点位 GeoJSON（地块质心）
- `GET /api/v1/cd-flux/projection/export.csv?years=N&...`：CSV（10 万行上限）
- `POST /api/v1/cd-flux/projection/visualization`：body `{years, ...}` → 地图/直方图

## Risks / Trade-offs

- **线性外推的局限**：恒定净通量假设忽略了土壤缓冲、作物吸收变化等非线性因素；响应与文档必须标注"线性情景推算，非实测预测"。
- **年数过大失真**：years 上限 100，超出范围拒绝；结果可能为负（净通量为负时），按公式如实返回不裁剪（调用方自行判断）。
- **口径差异**：与原系统 std/分位数不同（见决策 3），并列旧值需换算。

## Migration and Rollback

- 无表变更。回滚 = 删除模块与端点。

## Open Questions

1. 未来年份上限是否按业务调整为 30/50（当前 100，照抄原系统）。
2. 净通量为负时结果可能出现负浓度，是否需要截断到 0。
3. 是否需要把多年份对比结果落库/缓存（当前按需计算）。
