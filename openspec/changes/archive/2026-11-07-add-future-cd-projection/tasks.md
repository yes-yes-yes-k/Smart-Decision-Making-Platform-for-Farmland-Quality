# add-future-cd-projection Tasks

## 1. 预测服务

- [x] 1.1 新增 `framework/domain/other_models/cd_projection.py`：`Future_Cd=(Initial+Net×years)/(2000×bd020_90)`
- [x] 1.2 回退规则与计数（bd020_90→1.0、initial_cd→0、soil_mass<=0→0）
- [x] 1.3 多年份：`years` 单个或列表（1–100），按年份分组返回
- [x] 1.4 区域/来源过滤复用阶段 3 归属

## 2. 统计与空间

- [x] 2.1 单年份统计：8 项基础统计（阶段 2 口径）+ GB15618 三档分布
- [x] 2.2 点位 GeoJSON（地块质心）
- [x] 2.3 地图/直方图（复用阶段 4 引擎，产物目录 `projection_<years>`）
- [x] 2.4 CSV 导出（10 万行上限）

## 3. HTTP 端点

- [x] 3.1 `POST /cd-flux/projection`
- [x] 3.2 `GET /projection/statistics`、`/points`、`/export.csv`
- [x] 3.3 `POST /projection/visualization`
- [x] 3.4 错误语义与阶段 5/6 一致

## 4. 文档与验证

- [x] 4.1 `docs/cd-migration-roadmap.md` 阶段 7 状态回填（归档时）
- [x] 4.2 定向测试：公式数值、多年份、回退计数、区域过滤、空数据
- [x] 4.3 真实库探针：真实输入行 → 预测 → 统计 → 导出 → 清理
- [x] 4.4 `openspec validate add-future-cd-projection` 通过

## 未完成（需人工确认后执行）

- [ ] A. 未来年份上限（当前 100，照抄原系统）是否调整
- [ ] B. 净通量为负导致负浓度是否截断到 0
- [ ] C. 多年份对比结果是否需要落库/缓存
