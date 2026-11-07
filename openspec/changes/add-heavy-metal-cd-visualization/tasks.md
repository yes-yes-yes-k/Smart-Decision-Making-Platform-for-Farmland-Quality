# add-heavy-metal-cd-visualization Tasks

## 1. 资产与依赖

- [ ] 1.1 复制原系统 `template.tif` 到 `data/model_artifacts/heavy_metal_cd/visualization/`，写 `manifest.json`（source path、大小、SHA-256、CRS、尺寸、bounds、nodata）
- [ ] 1.2 `pyproject.toml` 增补 `rasterio>=1.4,<2`、`seaborn>=0.13,<1`、`matplotlib>=3.8,<4`
- [ ] 1.3 conda 环境安装上述依赖并验证导入（numpy 2.x 组合）

## 2. 可视化服务

- [ ] 2.1 新增 `heavy_metal_cd_visualization.py`：加载模板网格与 manifest
- [ ] 2.2 结果表 → 点位数据集（复用 `points_geojson` 的 join/source 过滤语义，含 `value=exp(ln)`）
- [ ] 2.3 区域过滤（`region_type`/`region_id` → 地块集合，复用阶段 3 归属依据）与模板范围过滤
- [ ] 2.4 栅格化：`rasterize(fill=nan)` + 边界掩膜（多 feature）+ 凸包兜底 + 可选 `griddata` 插值 + 掩膜回扣
- [ ] 2.5 分级地图：作物三档 / 有效态分位数 6 级 + 边界描边 + JPG 输出
- [ ] 2.6 直方图：有效像元 `histplot + kdeplot`，单值场景特殊绘制
- [ ] 2.7 产物目录与 `meta.json`（参数、口径、统计摘要、文件清单、边界来源、插值标记）

## 3. HTTP 端点

- [ ] 3.1 `POST /api/v1/heavy-metal-cd/visualization`（生成）
- [ ] 3.2 `GET /api/v1/heavy-metal-cd/visualization/artifacts`（列表）
- [ ] 3.3 `GET /api/v1/heavy-metal-cd/visualization/artifacts/<artifact_id>/<kind>`（下载，路径校验）
- [ ] 3.4 错误语义：`unknown_model` / `no_data` / `no_data_in_template` / `invalid_*` 与既有包络一致

## 4. 文档与验证

- [ ] 4.1 `docs/cd-migration-roadmap.md` 阶段 4 状态回填（归档时）
- [ ] 4.2 定向测试：栅格化/插值/分级/直方图/产物目录/下载校验
- [ ] 4.3 真实数据探针：真实库结果表生成一张图 + 直方图，校验文件存在、尺寸、统计与 meta 一致
- [ ] 4.4 `openspec validate add-heavy-metal-cd-visualization` 通过

## 未完成（需人工确认后执行）

- [ ] A. `template.tif` 纳入仓库的授权/口径确认（不确认则回退为动态网格方案）
- [ ] B. 有效态分位数 6 级作为展示口径的确认
- [ ] C. 产物保留/清理策略确认
