## 1. 移植数据集导入

- [x] 1.1 新增 `framework/domain/other_models/heavy_metal_cd_ported.py`：源表读取（`Farmland_data`/`CropCd_input_data`/`EffCd_input_data`）、特征行组装、`SGD_` 命名空间生成
- [x] 1.2 列映射按 ORM 语义硬编码（`CropCd_input_data` 的 `AvaP`/`AvaK` 交叉）：`available_phosphorus ← AvaK_IDW`、`available_potassium ← AvaP_IDW`；有效态不交叉
- [x] 1.3 新增 `scripts/import_ported_cd_dataset.py`：`--model` / `--limit` / `--apply` / `--rollback` / `--assign-townships` / `--compare`，默认 dry-run
- [x] 1.4 导入走现有 `run(rows=..., apply=True)`，复用覆盖写与单事务；不写第二套推理
- [x] 1.5 `parcel_info` 插入 `SGD_` 行：`centroid_lon/lat` 取自 `lon/lan`，`geom` 与 `area_code` 留空，`legacy_parcel_code=soilgd:<id>`

## 2. 乡镇归属

- [x] 2.1 新增表 `cd_ported_parcel_township`（`parcel_id` PK、`township_id`、`township_name`、`distance_m`、`assigned_at`）
- [x] 2.2 归属实现：`ST_Contains(township.geom, point(lon,lat))`；未命中时回退最近乡镇并记录距离（已归属的点跳过计算）
- [x] 2.3 新增 `scripts/migrate_add_ported_dataset_tables.py`（幂等 `create_all` + 结构校验）
- [x] 2.4 覆盖率实测：40100 点中 39831 落在乡镇多边形内、74 走回退（0.18%），已写入 `docs/cd-ported-dataset.md`

## 3. 数据来源维度（含既有实现改造）

- [x] 3.1 统计服务增加 `source` 参数（`native|ported|all`，默认 `all`）与 `source_breakdown`
- [x] 3.2 明细与 CSV 导出同样支持 `source`
- [x] 3.3 **改造阶段 3 空间服务**：`township_statistics` / `region_statistics` 按来源切换归属依据（自有→面积表，移植→`cd_ported_parcel_township`），响应返回 `assignment_sources` 与 `ported_fallback_count`
- [x] 3.4 `points_geojson` 支持 `source` 过滤并在响应返回来源条数
- [x] 3.5 **改造阶段 1 读取入口**：`read_results` 增加可选 `source`（缺省不过滤，向后兼容）
- [x] 3.6 路由参数校验：非法 `source` 返回 400

## 4. 回归验收

- [x] 4.1 导入后比对：作物 Cd `local ln` vs `LnCropCd`，最大绝对差 **2.79e-06** < 1e-4
- [x] 4.2 有效态 Cd：`local 浓度` vs `LnEffCd` 列值（该列实为浓度），最大相对差 **1.03e-06** < 1e-4
- [x] 4.3 不达标时脚本非零退出并打印差异分布（中位/最大/超差样本数）

## 5. 既有功能影响验证

- [x] 5.1 **`parcel_info` 污染核查**：`geom IS NOT NULL` 导入后仍为 5488（= 导入前），`area_code IS NOT NULL` 亦为 5488；`farmland_statistics` 统计 SQL 带 `data.geom IS NOT NULL`，移植点被自然排除
- [x] 5.2 核对 `parcel_info` 总数 5488 → 45588，`geom IS NULL` 行数 40100 = 移植行数
- [x] 5.3 核对阶段 2/3 在 `source=native` 时行为与导入前完全一致（`has_data=false` 空态）

## 6. 文档与验证

- [x] 6.1 新增 `docs/cd-ported-dataset.md`：命名空间规则、导入/回滚命令、来源维度说明、并存策略、实测记录
- [x] 6.2 更新既有文档：`docs/heavy-metal-cd-statistics.md` / `-spatial.md` / `-database-backend.md` 增补 `source` 与 `SGD_` 说明
- [x] 6.3 `docs/cd-migration-roadmap.md` 增加 D1 数据通道条目
- [x] 6.4 测试 `tests/test_heavy_metal_cd_ported.py`（9 个）：命名空间隔离、列映射交叉、`source` 过滤、乡镇归属回退、回滚只删 `SGD_`
- [x] 6.5 真实导入：先 `--limit 200` 验证链路，再全量 40100；两模型行数、`source_breakdown`、归属覆盖率已核对
- [x] 6.6 `openspec validate import-cd-ported-dataset` 与 `git diff --check`
- [x] 6.7 归档时回填 roadmap（D1 状态与归档日期）

## 未完成（需人工确认后执行）

- **四个口径已拍板（2026-10-31 用户确认"按推荐"）**：`SGD_` 前缀、写入 `parcel_info`（geom/area_code 留空）、统计默认 `all`、CSV 上限 10 万行沿用。
- **业务方数据到位后的处置**：并存 / 替换 / 清理移植数据，另开 change。
- **移植数据无合法行政区属性**：`area_code` 留空意味着区县粒度统计不会包含移植数据（刻意为之），乡镇粒度走点面归属。
- **回退归属 74 个点**（0.18%）：落在乡镇边界缝隙，取最近乡镇并记 `distance_m`，前端可按 `distance_m > 0` 标识。
