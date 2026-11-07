# add-heavy-metal-cd-visualization Design

## Context

阶段 1–3 已交付：两张 Cd 结果表（只存 ln 值，读取时 `exp` 还原 mg/kg）、地块级覆盖写库、统计 API、乡镇/区域聚合与点位 GeoJSON（坐标取 `parcel_info` 质心，`coordinate_source=parcel_centroid`）。区域边界由 `spatial_region_catalog` 维护，`/api/v1/farmland-statistics/boundaries` 已能按 `region_type` / `parent_*` / `bbox` / `zoom` 返回 GeoJSON FeatureCollection。

原系统 AcidMap 的可视化链路（已逐行核验）：

| 环节 | 原系统实现 |
|---|---|
| 数据入口 | `predict_and_visualize`（CSV/上传）与 `generate-from-database`（按 `area`/`level` 从输入表重跑模型） |
| 栅格化 | `dataframe_to_raster_workflow` → `dataframe_to_geodataframe` → `geodataframe_to_raster`：`rasterize(fill=nan)` + 边界掩膜（无边界时凸包）+ 可选 `scipy.griddata` 插值 + 最近邻兜底 + 掩膜回扣 |
| 分级地图 | `create_raster_map`：裁剪 → 重采样 → 插值 → `BoundaryNorm` 分级（默认 `[0,20,40,60,80,90,100]` 百分位 6 级；作物 Cd 自定义 `[0,0.2,0.3,inf]` 三档）→ 边界黑线 1px → 采样点（可选）→ JPG（figsize 10×8、dpi 300） |
| 直方图 | `create_histogram`：读 TIF → 去 nodata → `sns.histplot(stat=density)` + `sns.kdeplot` → JPG；单值时特殊绘制 |
| 面向前端 | `latest-map/{area_name}`、`latest-histogram/{area_name}`（glob 按文件名找最新）、`generate-from-database` 直接回 `FileResponse` |
| 模板 | `app/models/cd_prediction/common/template.tif`（227×197、EPSG:4326、bounds 112.85–114.74E / 23.89–25.53N、0.01°、float32、nodata -999） |

## Goals / Non-Goals

**Goals**

- 从既有结果表出发，产出可复现的 Cd 分布图、直方图与栅格，覆盖全量或指定区域。
- 分级与颜色保持与原系统可比的形态（作物三档阈值不变）。
- 所有产物落受控目录，可列、可下载、可回溯（meta.json 记录口径与输入参数）。
- 不改变既有统计口径与端点行为。

**Non-Goals**

- GeoServer/WMS、栅格入库、通量级联、前端地图交互。
- 不改结果表结构、不新增业务数据表。

## Decisions

### 1. 数据源用「结果表 + 地块质心」，不重跑模型

原系统 `generate-from-database` 从输入表重跑模型再可视化，是因为它没有「结果表与可视化分离」的层；本项目阶段 1 已把结果持久化，且阶段 3 已定义点位坐标口径（地块质心）。本阶段直接读结果表 + `parcel_info.centroid_lon/lat`，`exp(ln)` 还原 mg/kg，`source` 过滤（自有/移植）复用阶段 2/3 的 `source_filter`。

**取舍**：这是与原系统的有意偏差——可视化不再绑定「同一次预测运行」，而是反映结果表的当前内容；换来的是一次生成秒级完成、可随时对任意区域重出图，且不会重复跑模型引入新的数值差异。代价是图与「某次预测批次」不再一一对应，meta.json 记录 `generated_at` 与数据来源（`source` 过滤值）作为替代追溯。

### 2. 模板栅格迁移为受控资产，不动态生成

把原系统 `template.tif` 复制到 `data/model_artifacts/heavy_metal_cd/visualization/template.tif`，manifest 记录源路径、大小、SHA-256、CRS/尺寸/范围。栅格化以模板网格为基准做 `resolution_factor` 放大（与原系统 `resolution_factor=4.0` 的调用一致），不按每次请求的 bbox 动态造网格。

**理由**：与原系统输出在同一网格上可比；避免两套网格规则；模板仅 175KB。**风险**：模板范围若与未来新增区域不重合，需要新增模板或改为按区域 bbox 裁剪——写进 Open Questions。

### 3. 插值默认关闭，按参数开启

`RASTER_CONFIG.enable_interpolation` 原系统默认 `False`，`engine.create_visualization` 调用时也传 `False`、`interpolation_method='nearest'`。本阶段照抄：默认不插值（保留 NaN 为空白），请求可显式开启 `nearest|linear|cubic`（`scipy.griddata`），插值后**重新回扣边界掩膜**（原系统的关键修正，避免边界外被填充）。

实现时实测到一处需要加固：`linear` / `cubic` 依赖 Qhull 三角剖分，有效像元少于 4 个（小区域、稀疏点位）时会抛 `QhullError`。原系统没有这层保护，本实现降级为 `nearest` 并在 `meta.interpolation_effective` 标注实际方法——插值不足不该让整张图失败。

**取舍**：不默认开启是因为插值会凭空造出采样点之间不存在的数值，与「数值必须可追溯」的项目口径冲突；开启时必须在响应里标注 `interpolated: true` 与方法名。

### 4. 分级：作物三档照抄，有效态用分位数 6 级（显示分级）

- 作物 Cd：`[0.0, 0.2, 0.3, inf]` 三档，颜色 `#15B392 / #FFEB55 / #D91656`（安全绿 / 预警黄 / 超标红），标签 `0.0~0.2 / 0.2~0.3 / ≥0.3 mg/kg`——与原系统 `VISUALIZATION_CONFIG.crop_cd_config` 一致。
- 有效态 Cd：原系统无统计分箱，地图按有效像元 `nanpercentile([0,20,40,60,80,90,100])` 6 级显示，颜色 `green_yellow_red_purple`。

**取舍**：有效态 6 级是**显示分级**，不是统计分箱；响应 meta 中 `legend.mode: "quantile"` 与 `bounds` 明确列出，防止被读成「超标判定」。作物三档则同时标注 `legend.mode: "threshold"`。

### 5. 边界掩膜与描边支持多 feature（修正原系统缺陷）

原系统 `json.loads(gdf.to_json())["features"][0]["geometry"]` 只取第一个 feature。新实现把区域内所有要素合并成 MultiPolygon/GeometryCollection 后整体 `geometry_mask` / `mask`，并支持「无匹配边界 → 点集凸包」的原有兜底路径（在 meta 中标注 `boundary_source: "catalog"|"convex_hull"`）。

### 6. 产物目录 + 产物 ID + 下载校验

```
data/cd_visualization/<model_id>/<artifact_id>/
    map.jpg            # 分级地图（JPG，dpi 300）
    histogram.jpg      # 直方图
    raster.tif         # 可选（save_raster=true 时）
    meta.json          # 参数、口径、统计摘要、文件清单、generated_at
```

`artifact_id` 为 `uuid4().hex`；下载端点只接受 `[0-9a-f]{32}` 与该目录白名单文件名（`map.jpg` / `histogram.jpg` / `raster.tif`），用 `os.path.realpath` 校验仍在受控根内，防路径穿越。

**取舍**：不引入数据库表存产物，轻量且可人工清理；列表直接扫目录读 `meta.json`。

### 7. 端点形态：生成用 POST + JSON（重操作），查询/下载用 GET

沿用仓库风格（Blueprint + JWT + `{code,message,data}` 包络），但生成是重操作，不用 GET：

- `POST /api/v1/heavy-metal-cd/visualization`：body `{model_id, region_type?, region_id?, source?, enable_interpolation?, interpolation_method?, resolution_factor?, save_raster?}` → `data`: `{artifact_id, files:{map,histogram,raster}, stats:{count,...}, legend:{...}, boundary_source, generated_at}`
- `GET /api/v1/heavy-metal-cd/visualization/artifacts?model_id=&region_type=&region_id=`：列出产物（读 meta.json），按 `generated_at` 降序
- `GET /api/v1/heavy-metal-cd/visualization/artifacts/<artifact_id>/<kind>`：`kind ∈ {map, histogram, raster}`，返回文件流（`image/jpeg` / `image/tiff`）

### 8. 依赖与 numpy 2.x 兼容

pyproject 增补 `rasterio>=1.4,<2`、`seaborn>=0.13,<1`、`matplotlib>=3.8,<4`。本机 `agent_culti_demo_py312` 实测：numpy 2.5.4 + rasterio 1.5.2 + seaborn 0.13.2 + matplotlib 3.11.1 + scipy 1.18.0 + geopandas 1.1.4 全部可导入；`rasterio` 读模板元数据正常。**注意**：pip 安装时曾把 numpy 顶到 2.5.4 而旧安装包元数据（`agent-culti-demo 0.1.0`）声明 `numpy<2` 报警——以仓库 `pyproject.toml`（`numpy>=2,<3`）为准，不是环境损坏。

## Risks / Trade-offs

- **模板范围固定**：模板覆盖乐昌一带；若产物请求的区域超出模板 bounds，栅格化会得到空/边缘结果 → 设计上先按模板过滤点集，若 0 个点落入则返回 `no_data_in_template` 错误，而不是产出空白图。
- **插值可造假**：默认关闭，开启时明确标注；不把插值图当作「实测分布」使用。
- **图片与结果表不同步**：结果表被覆盖写库后旧图不会自动失效；meta.json 记录生成时间与数据行数，由调用方按需重生成。
- **大区域性能**：全量 40100 点栅格化在 resolution_factor=4（约 908×788）下为秒级；再放大到 16 可能到数十秒，响应里返回耗时。

## Migration and Rollback

- 新增能力，无数据迁移。回滚 = 删除 `heavy_metal_cd_visualization.py`、路由端点、`data/cd_visualization/` 产物目录、模板资产与 pyproject 三条依赖；既有端点与结果表不受影响。

## Open Questions

1. `template.tif` 直接迁移原系统资产的授权/口径：当前按「项目内部迁移、manifest 标注 source」处理，若仓库不允许纳入二进制资产，需改为按区域 bbox 动态网格。
2. 有效态地图沿用原系统分位数 6 级是否可接受为展示口径？（不影响统计 API）
3. 产物保留策略：是否需要按时间/数量自动清理（当前不自动清理，由人工管理）。
