# add-heavy-metal-cd-statistics-api Design

## Context

阶段 1 交付了两张只存自然对数值的结果表，以及 `read_results()`（`exp` 还原为 mg/kg）。本阶段把它们暴露成可消费的统计与查询能力。

原系统口径（`app/services/cd_prediction_statistics_service.py`，逐行读过）：

- 8 项基础统计用**纯 Python 手算**：`mean = sum/count`、`std = sqrt(sum((x-mean)^2)/n)`（总体标准差）、`median` 按偶数取中间两数平均、`q25 = sorted[int(count*0.25)]`、`q75 = sorted[int(count*0.75)]`，全部 `round(…, 6)`
- 作物 Cd 分箱：`0.0 <= v < 0.2` 安全、`0.2 <= v < 0.3` 预警、`v >= 0.3` 超标、负值与异常值归入超标；占比 `round(x/total*100, 2)`
- 有效态统计只有 8 项基础统计
- 综合统计：`数据完整性` 三布尔 + 两模型 `数据点数量对比` / `平均浓度对比`
- 无数据时端点抛 404
- `get_crop_cd_statistics(area)` 的 `area` 参数**未参与查询**（缺陷）

本项目 HTTP 风格：`framework/api/routes/<domain>.py` 定义 Blueprint，`framework/api/app.py` 用 `url_prefix='/api/v1/<domain>'` 注册，端点用 `@jwt_required()`，服务层放 `framework/api/services/` 或 `framework/domain/`。

## Goals / Non-Goals

**Goals:**

- 前端/报告能直接取到与原系统可比的统计数字（口径一致、字段名一致）
- 区域过滤真正生效
- 空数据、单位待核、分布统计边界都在响应里说清楚，不给使用者留下误读空间

**Non-Goals:**

- 不做空间/乡镇统计（阶段 3）、不做图形（阶段 4）
- 不引入 SQL 窗口函数或 numpy 分位数（会改变与原系统的可比性）
- 不改阶段 1 的两张表结构

## Decisions

### 1. 统计算法照抄原系统，包括它的非标准分位数

`q25 = sorted[int(count*0.25)]`、`q75 = sorted[int(count*0.75)]` 是**下标直取**，与标准线性插值分位数不同（大样本差异小、小样本明显）。照抄的理由是与原系统历史结果可比；代价是它与 `numpy.percentile` 不等价。

因此 statistic 服务**不能**换成 pandas/numpy 的 `describe()`，必须手算，并在响应 `statistics_scope` 里写明算法（`population_std`、`index_based_quantile`）。

### 2. 分箱只属于作物 Cd，且必须自带"非安全判定"声明

`0.0~0.2 / 0.2~0.3 / ≥0.3` 三档只在作物 Cd 统计里出现，有效态 Cd **不提供**任何分箱。响应里固定带：

- `statistics_scope: "crop_cd_distribution"`（作物分布统计）
- `threshold_note: "分布区间仅用于描述预测值分布，不构成安全或超标判定"`

负值归入"超标区间"（与原系统一致），但同时在响应里给出 `invalid_count`，避免静默吞掉异常值。

### 3. 区域过滤用 `parcel_info.area_code` 真正过滤

结果表没有 `area_code` 列（用户口径：不追踪元数据），因此按区域统计时：

```sql
SELECT r.parcel_id, r.sample_id, r.ln_crop_cd
FROM cd_crop_prediction_result r
JOIN parcel_info p ON p.parcel_id = r.parcel_id
WHERE p.area_code = :area_code
```

不传 `area_code` 时统计全表。这样原系统"参数存在但无效"的缺陷被修正，且不新增列。

### 4. 空数据返回 200 + 结构化空态，不用 404

原系统无数据抛 404，前端无法区分"还没跑预测"与"接口出错"。本实现：

- `has_data: false`、`count: 0`、`basic_stats` 各字段为 `null`
- HTTP 200
- `message` 说明"该范围内暂无 Cd 预测结果"

### 5. 不返回"数据更新时间"

原系统的 `数据更新时间 = datetime.now()` 其实是**查询时间**，容易让人误读为"结果生成时间"。本实现返回 `queried_at`，并显式注明 `queried_at_is: "query_time"`；结果行没有生成时间可给（阶段 1 决策 3 明确不记录）。

### 6. CSV 导出带 BOM、列固定、有行数上限

- 编码 `utf-8-sig`（Excel 直接打开中文不乱码）
- 列：`parcel_id, sample_id, ln_value, value, unit, unit_status`
- 单次导出上限默认 100000 行，超过返回 413 并提示改用分页；分页参数 `limit`/`offset` 与明细接口共用
- 文件名 `<model>_cd_results_<UTC时间戳>.csv`

### 7. HTTP 端点全部需要 JWT

沿用项目现有认证，不做匿名只读；端点：

- `GET /api/v1/heavy-metal-cd/statistics/crop-cd?area_code=`
- `GET /api/v1/heavy-metal-cd/statistics/effective-cd?area_code=`
- `GET /api/v1/heavy-metal-cd/statistics/combined?area_code=`
- `GET /api/v1/heavy-metal-cd/results?model=&area_code=&limit=&offset=`
- `GET /api/v1/heavy-metal-cd/results.csv?model=&area_code=`
- `GET /api/v1/heavy-metal-cd/models`

## Risks / Trade-offs

- 照抄非标准分位数会让人用 numpy 校验时对不上，因此在响应里写明算法，文档也标注。
- `JOIN parcel_info` 在结果行数大时可能变慢；为 `parcel_info.parcel_id`（已有唯一约束）与结果表 `parcel_id` 索引做了支撑，超过百万行再考虑物化视图。
- CSV 上限 10 万行是经验值，超过走分页；若业务确实需要全量导出，另开 change。

## Migration and Rollback

- 无数据库变更，无需迁移。
- 回滚：删除蓝图注册与两个新文件即可；不影响阶段 1 的写入链路。

## Open Questions

1. **分位数算法**：照抄原系统下标法（可比但非标准），还是改标准线性插值（更规范但与历史结果有差异）？
2. **空数据语义**：200 + `has_data=false`（本提案默认），还是沿用原系统 404？
3. **区域过滤维度**：只按 `parcel_info.area_code`，还是也要支持按 `county`/`city` 文本匹配（原系统 `by_area` 用的是 `CropCd_input_data` 的行政区字段）？
4. **CSV 上限**：10 万行是否合适？
