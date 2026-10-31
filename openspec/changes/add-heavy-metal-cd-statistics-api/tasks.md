## 1. 统计领域服务

- [ ] 1.1 新增 `framework/domain/other_models/heavy_metal_cd_statistics.py`，提供 `basic_statistics(values) -> dict`（8 项：数据点总数/均值/中位数/标准差/最小值/最大值/25%分位数/75%分位数，`round(…, 6)`）
- [ ] 1.2 统计算法严格对齐原系统：总体标准差（除以 n）、分位数按下标直取 `sorted[int(count*q)]`、偶数中位数取中间两数平均；不得改用 numpy/pandas 的 percentile
- [ ] 1.3 `crop_cd_distribution(values)`：三档计数与占比（`0.0~0.2` 安全 / `0.2~0.3` 预警 / `≥0.3` 超标），负值计入超标并单独给出 `invalid_count`
- [ ] 1.4 `collect_values(model_id, area_code=None)`：从结果表取 `exp(ln_*)`；传 `area_code` 时 JOIN `parcel_info` 真过滤（修正原系统 area 参数失效缺陷）
- [ ] 1.5 `crop_cd_statistics()` / `effective_cd_statistics()` / `combined_statistics()`：响应沿用原系统中文键名，新增 `has_data` / `unit` / `unit_status` / `statistics_scope` / `queried_at` / `queried_at_is`
- [ ] 1.6 空数据返回结构化空态（`has_data=false`、`count=0`、统计字段 `null`），不抛异常
- [ ] 1.7 有效态统计**不提供**任何分箱；作物分箱响应必须带 `threshold_note`（分布统计不构成安全判定）

## 2. 明细查询与 CSV 导出

- [ ] 2.1 `list_results(model_id, area_code=None, limit=100, offset=0)`：返回 `parcel_id/sample_id/ln_value/value/unit/unit_status`，按 `parcel_id, sample_id` 排序
- [ ] 2.2 `export_csv(model_id, area_code=None, max_rows=100000)`：UTF-8-BOM、固定列顺序、超过上限抛明确错误（由路由转 413）
- [ ] 2.3 分页参数校验：`limit` 上限（如 1000）、`offset` 非负，非法值返回 400

## 3. HTTP 蓝图

- [ ] 3.1 新增 `framework/api/routes/heavy_metal_cd.py`，Blueprint 注册到 `framework/api/app.py`，前缀 `/api/v1/heavy-metal-cd`
- [ ] 3.2 `GET /statistics/crop-cd`、`/statistics/effective-cd`、`/statistics/combined`，支持 `area_code` 查询参数，全部 `@jwt_required()`
- [ ] 3.3 `GET /results`（分页明细）与 `GET /results.csv`（附件下载，`Content-Disposition` 带文件名）
- [ ] 3.4 `GET /models`：返回 `available_models()` 的模型清单与输入契约（含 `unit` / `unit_basis` / `unit_status`）
- [ ] 3.5 错误处理：参数非法 400、CSV 超限 413、未认证 401、服务异常 500，响应体带稳定 `code`

## 4. 文档与验证

- [ ] 4.1 新增 `docs/heavy-metal-cd-statistics.md`：端点清单、响应字段、算法口径（总体标准差/下标分位数）、分箱边界与非安全判定声明
- [ ] 4.2 定向测试 `tests/test_heavy_metal_cd_statistics.py`：8 项统计与手算基准一致、下标分位数与原系统公式一致、三档计数与占比、负值计入超标且 invalid 计数、空态结构、area 过滤生效
- [ ] 4.3 HTTP 测试：三个统计端点 + 明细 + CSV + models 各一条，覆盖未认证 401 与参数非法 400
- [ ] 4.4 真实数据探针：当前库结果表为空时验证空态返回；插入 3 条探针行验证统计数值后清理（探针脚本用完删除）
- [ ] 4.5 `openspec validate add-heavy-metal-cd-statistics-api` 与 `git diff --check`

## 未完成（需人工确认后执行）

- **分位数算法**：照抄下标法（本提案默认，与原系统可比）还是改标准线性插值（Open Question 1）。
- **空数据语义**：200 + `has_data=false`（本提案默认）还是沿用原系统 404（Open Question 2）。
- **区域过滤维度**：仅 `parcel_info.area_code`，还是也要支持 `county`/`city` 文本匹配（Open Question 3）。
- **CSV 行数上限**：10 万行是否合适（Open Question 4）。
- **结果表无数据**：阶段 1 归档时表内为 0 行，统计接口当前只能验证空态；真实数值验证需要先有输入（依赖 MSM 或完整特征行供给）。
