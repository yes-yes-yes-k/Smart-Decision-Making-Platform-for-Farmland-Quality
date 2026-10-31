## 1. 统计领域服务

- [x] 1.1 新增 `framework/domain/other_models/heavy_metal_cd_statistics.py`，提供 `basic_statistics(values)`（8 项，`round(…, 6)`）
- [x] 1.2 统计算法严格对齐原系统：总体标准差（除以 n）、分位数下标直取 `sorted[int(count*q)]`、偶数中位数取中间两数平均；未使用 numpy/pandas 分位数
- [x] 1.3 `crop_cd_distribution(values)`：三档计数与占比，负值计入超标并单独给出 `invalid_count`，`threshold_note` 固定返回
- [x] 1.4 `collect_values(model_id, area_code)`：从结果表取 `exp(ln)`；传 `area_code` 时 JOIN `parcel_info` 真过滤（修正原系统 area 失效）
- [x] 1.5 `crop_cd_statistics()` / `effective_cd_statistics()` / `combined_statistics()`：沿用原系统中文键名，新增 `has_data` / `unit` / `unit_status` / `statistics_scope` / `queried_at` / `queried_at_is`
- [x] 1.6 空数据返回结构化空态（`has_data=false`、统计字段 `null`），HTTP 200，不抛异常
- [x] 1.7 有效态统计不含任何分箱；作物分箱响应固定带非安全判定声明

## 2. 明细查询与 CSV 导出

- [x] 2.1 `list_results(model_id, area_code, limit, offset)`：返回 `parcel_id/sample_id/ln_value/value/unit/unit_status`，按 `parcel_id, sample_id` 排序
- [x] 2.2 `export_csv(model_id, area_code, max_rows=100000)`：UTF-8-BOM、固定列序，超限抛 `export_exceeds_limit`
- [x] 2.3 分页参数校验：`limit` 1–1000、`offset` ≥ 0，非法返回 400

## 3. HTTP 蓝图

- [x] 3.1 新增 `framework/api/routes/heavy_metal_cd.py`，注册为 `/api/v1/heavy-metal-cd`（`framework/api/app.py`）
- [x] 3.2 `GET /statistics/crop-cd`、`/statistics/effective-cd`、`/statistics/combined`，支持 `area_code`，全部 `@jwt_required()`
- [x] 3.3 `GET /results`（分页）与 `GET /results.csv`（`Content-Disposition` + `X-Row-Count`）
- [x] 3.4 `GET /models`：返回模型清单与输入契约（含 `unit` / `unit_basis` / `unit_status`）
- [x] 3.5 错误处理：400（参数非法）、413（导出超限，带回 count/max_rows）、401（框架）、500（服务异常）

## 4. 文档与验证

- [x] 4.1 新增 `docs/heavy-metal-cd-statistics.md`：端点、响应字段、算法口径、分箱边界与非安全判定声明
- [x] 4.2 `tests/test_heavy_metal_cd_statistics.py` 22 passed：手算基准、总体标准差、下标分位数（与 numpy 差异）、三档边界、负值、空态、exp 还原、有效态无分箱、综合缺失标记、分页、CSV、超限、area 过滤
- [x] 4.3 HTTP 测试：认证 401、统计 200、参数非法 400、CSV 超限 413、CSV 响应头、模型契约字段
- [x] 4.4 真实库探针（真实 PG + Flask test_client + JWT）：空表 `has_data=false`；插入 3 行后均值 0.233333、总体标准差 0.10274、三档各 1；有效态无分箱；综合统计标出缺失侧；明细分页；CSV BOM + 4 行（1 表头 + 3 数据）；models 单位正确；非法 limit 400；未认证 401；探针行已清理（表回 0 行）
- [x] 4.5 `openspec validate add-heavy-metal-cd-statistics-api` = valid；`git diff --check` 通过
- [x] 4.6 归档时回填 `docs/cd-migration-roadmap.md` 中阶段 2 的状态与归档日期（已完成：2026-10-31 归档）

## 未完成（需人工确认后执行）

- **四个口径已拍板（2026-10-31 用户确认）**：1A 照抄下标分位数、2A 空数据 200 + `has_data=false`、3A 区域过滤仅 `parcel_info.area_code`、CSV 上限 10 万行。design 的 Open Questions 保持为决策记录。
- **结果表当前为空**：统计接口的真实数值验证依赖输入到位（MSM 输出或完整特征行供给），目前只能用探针行证明算法与链路正确。
- **分位数算法非标准**：与 numpy 线性插值结果不同，已在响应 `statistics_scope` 与文档中声明；若将来要与外部标准口径对齐，需新建 change。
