# add-cd-flux-accounting Tasks

## 1. 表与迁移

- [x] 1.1 新增 `framework/models/cd_flux.py`：`CdFluxInput`、`CdFluxOutput`（含 `(parcel_id, sample_id)` 唯一约束）
- [x] 1.2 新增 `scripts/migrate_cd_flux_tables.py`（幂等建表，`db.create_all()` 路线）
- [x] 1.3 真实库执行建表并验证两表存在、唯一约束生效

## 2. 输入导入

- [x] 2.1 CSV 导入服务：字段契约校验（必需 10 列、可选 `bd020_90`）、数值校验、同键覆盖
- [x] 2.2 导入结果计数（inserted/updated/skipped）与错误行报告

## 3. 通量计算

- [x] 3.1 计算服务：`In = DQCJ+GGS+NCP`、`Out = DX+DB+ZL+JG`、`Net = In−Out`、`End = (Initial+Net)/(2000×bd020_90)`
- [x] 3.2 缺失回退：`bd020_90→1.0`、`initial_cd→0`、`soil_mass<=0→0`，回退计数进响应
- [x] 3.3 覆盖写库（唯一键 upsert），区域/来源过滤重算

## 4. 统计与分布

- [x] 4.1 8 项基础统计复用 `heavy_metal_cd_statistics.basic_statistics`
- [x] 4.2 分布：`end_cd` 三档（GB15618）、`net_cd` 互斥三档（<-5 / -5~5 / >5）、`in/out` 相对三档
- [x] 4.3 区域/乡镇聚合复用阶段 3 归属依据；`region_type`/`region_id`/`source` 过滤

## 5. 空间结果与导出

- [x] 5.1 点位 GeoJSON（结果表 + 地块质心，四类字段）
- [x] 5.2 分级地图/直方图：复用阶段 4 栅格化/渲染函数（net 三档互斥、end GB15618 三档、in/out 分位数 6 级）
- [x] 5.3 明细分页 + CSV 导出（上限 10 万行）

## 6. HTTP 端点

- [x] 6.1 `POST /inputs/import`（CSV 上传）
- [x] 6.2 `POST /calculate`
- [x] 6.3 `GET /statistics`、`GET /results`、`GET /export.csv`、`POST /visualization`
- [x] 6.4 错误语义：`unknown_field`/`invalid_region*`/`invalid_source` 400，`region_not_found` 404，空数据 200 + `has_data=false`

## 7. 文档与验证

- [x] 7.1 `docs/cd-migration-roadmap.md` 阶段 5 状态回填（归档时）
- [x] 7.2 定向测试：导入校验、公式与回退、分箱互斥（占比和 ≤100%）、统计口径、导出
- [x] 7.3 真实库探针：建表 → 导入样例输入行 → 计算 → 统计 → 导出 → 清理
- [x] 7.4 `openspec validate add-cd-flux-accounting` 通过

## 人工确认结论（2026-11-07 用户拍板）

- [x] A. `bd020_90`：**先与原系统一致**（输入行自带，缺失回退 1.0 + 回退计数），迁移完成后再评估是否导入容重数据
- [x] B. `net_cd` 平衡区间：**保留 ±5 g/ha/a**（原系统口径），迁移完成后再按真实分布评估
- [x] C. `end_cd` 三档阈值：**保留 0.3/0.6 mg/kg 统一阈值**（原系统口径），迁移完成后再评估是否按 pH 细分

> 总原则：迁移期以「与原系统一致」为准；缺陷类问题（如 net 分箱重叠）已在迁移中修正并记录。
