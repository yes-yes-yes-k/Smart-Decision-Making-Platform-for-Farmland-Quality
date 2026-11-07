# add-heavy-metal-cd-visualization Proposal

## Why

阶段 1–3 已把 Cd 双模型结果落库、提供 8 项统计、乡镇/区域聚合与点位 GeoJSON，但结果只有数字、表格和点位，业务方看到的不是一个「能放进汇报的分布图」。原系统 AcidMap 已有这套能力（`app/utils/mapping_utils.py` 的 `create_raster_map` / `create_histogram`、`cd_prediction.py` 的 `latest-map` / `latest-histogram` 端点、`VISUALIZATION_CONFIG` 的作物 Cd 三档分级），本项目迁移时尚未搬过来。

核验原系统实现时发现两处不能照抄的缺陷：① `create_raster_map` 用 `json.loads(gdf.to_json())["features"][0]["geometry"]` 取边界，只处理第一个 feature，多乡镇边界会画错；② `latest-map/{area_name}` 用区域名字拼 glob 找文件，重名或改名即失效。本 change 在迁移能力的同时用区域标识 + 多 feature 边界修正这两点。

## What Changes

- 新增 Cd 可视化服务：结果表 + 地块质心 → 栅格化 → 可选空间插值 → 分级地图；同源栅格出直方图。
- 迁移原系统 `template.tif` 作为受控栅格模板（记录来源与 SHA-256），保证分辨率与覆盖范围可复现。
- 分级口径与原系统一致：作物 Cd 三档（0–0.2 / 0.2–0.3 / ≥0.3 mg/kg），有效态 Cd 用分位数 6 级显示分级；有效态不做统计分箱。
- 产物目录化：每次生成写真受控目录（地图 JPG、直方图 JPG、可选 GeoTIFF、meta.json），支持列表与按产物 ID 下载。
- 新增 3 个 HTTP 端点（生成 / 列表 / 下载），复用既有 JWT 与错误语义；无数据返回机器可读错误，不产出空图。
- 依赖补充 `rasterio`、`seaborn`、`matplotlib`（环境已实测可用，numpy 2.x 组合）。

## Capabilities

### New Capabilities

- `heavy-metal-cd-visualization`: Cd 结果栅格化、可选空间插值、分级地图与直方图、栅格与图片产物导出。

### Modified Capabilities

无。本 change 只读既有结果表与区域边界，不改变统计口径、归属规则与既有端点响应。

## Impact

- 代码：新增 `framework/domain/other_models/heavy_metal_cd_visualization.py`、`framework/api/routes/heavy_metal_cd.py` 增补端点、`pyproject.toml` 依赖、`data/model_artifacts/heavy_metal_cd/visualization/` 资产。
- 接口：新增 `/api/v1/heavy-metal-cd/visualization*` 三个端点（JWT）；既有端点不变。
- 数据：只读 `cd_crop_prediction_result` / `cd_effective_prediction_result`、`parcel_info`、区域目录；产物写 `data/cd_visualization/`，不写业务表。
- 依赖：`rasterio>=1.4,<2`、`seaborn>=0.13,<1`、`matplotlib>=3.8,<4`；与 numpy 2.x / geopandas 1.x / scipy 1.18 实测兼容。

## Roadmap

- 阶段：**4 / 7**（阶段 0–3 与 D1 已归档）
- 前置：`add-heavy-metal-cd-spatial-analysis`（已归档，提供区域归属与点位）
- 后续：`add-cd-flux-accounting`（阶段 5）
- 单一真相源：`docs/cd-migration-roadmap.md`；归档时需回填该文件状态

## Non-Goals

- 不接 GeoServer / WMS 图层服务（原系统 `geoserver.py` 依赖外部服务）。
- 不做 `raster2pgsql` 栅格入库（原系统 `raster.py` 的通用栅格管理，与 Cd 可视化无关）。
- 不做通量级联更新、不做前端地图交互（本阶段只产出图片与栅格文件）。
- 不改统计口径：地图分级是显示分级，不是统计分箱。
