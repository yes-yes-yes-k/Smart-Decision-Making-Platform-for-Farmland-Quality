# 重金属 Cd 统计 API（阶段 2）

对应 OpenSpec change：`add-heavy-metal-cd-statistics-api`（路线图阶段 2 / 7）。

## 一、端点（前缀 `/api/v1/heavy-metal-cd`，全部要求 JWT）

- `GET /statistics/crop-cd?area_code=` — 作物 Cd：8 项基础统计 + 三档分布
- `GET /statistics/effective-cd?area_code=` — 有效态 Cd：8 项基础统计（**无分箱**）
- `GET /statistics/combined?area_code=` — 双模型综合统计 + 数据完整性 + 对比
- `GET /results?model=&area_code=&limit=&offset=` — 分页明细（`limit` 1–1000，默认 100）
- `GET /results.csv?model=&area_code=` — CSV 导出（UTF-8 BOM，单次上限 10 万行）
- `GET /models` — 模型清单与输入契约（含 `unit` / `unit_basis` / `unit_status`）

错误约定：未认证 401（框架）、参数非法 400、导出超限 413、服务异常 500；响应体固定带 `status` 与 `reason`。

## 二、统计口径（与原系统逐项对齐）

**8 项基础统计**：数据点总数、均值、中位数、标准差、最小值、最大值、25% 分位数、75% 分位数，全部 `round(…, 6)`。

两处容易踩的非标准算法：

- **标准差是总体标准差**（除以 n），不是样本标准差（除以 n−1）
- **分位数按下标直取** `sorted[int(count*q)]`，不是线性插值。例如 1..10 的 25% 分位数是 `sorted[2] = 3`，numpy 线性插值会给 3.25

因此本实现**不能**改用 `numpy.percentile` / `pandas.describe()`；响应里用 `statistics_scope` 声明算法来源。

**作物 Cd 三档分布**（仅作物 Cd）：

- `0.0 ~ 0.2` 安全区间
- `0.2 ~ 0.3` 预警区间
- `≥ 0.3` 超标区间
- 负值计入超标区间，并单独计入 `invalid_count`
- 响应固定带 `threshold_note`：分布区间仅用于描述预测值分布，**不构成安全或超标判定**

**有效态 Cd**：只有 8 项基础统计，任何分箱都不提供。

## 三、几个已定的行为

- **空数据**：HTTP 200 + `has_data=false` + 统计字段 `null`（不沿用原系统 404），便于前端区分"还没跑预测"与"接口出错"
- **区域过滤**：按 `parcel_info.area_code` JOIN 结果表真正过滤（原系统 `get_crop_cd_statistics(area)` 的 `area` 参数未参与查询，是失效的）
- **不返回"数据更新时间"**：结果表没有生成时间（阶段 1 决策 3），只返回 `queried_at` 且标注 `queried_at_is: "query_time"`

## 四、响应示例（作物 Cd，有数据）

```json
{
  "status": "ok",
  "data": {
    "模型类型": "作物Cd预测模型",
    "数据单位": "mg/kg",
    "unit_status": "unverified",
    "has_data": true,
    "statistics_scope": "crop_cd_distribution",
    "queried_at": "2026-10-31T18:12:03+08:00",
    "queried_at_is": "query_time",
    "基础统计": {"数据点总数": 3, "均值": 0.2333, "中位数": 0.25, "...": "..."},
    "数据来源": "cd_crop_prediction_result表",
    "分布统计表格": {
      "标题": "水稻镉含量预测统计",
      "总数据点数": 3,
      "表格数据": [
        {"序号": 1, "分布区间": "0.0 ~ 0.2", "区间说明": "安全区间", "数据点数量": 1, "占比": 33.33},
        {"序号": 2, "分布区间": "0.2 ~ 0.3", "区间说明": "预警区间", "数据点数量": 1, "占比": 33.33},
        {"序号": 3, "分布区间": "≥ 0.3", "区间说明": "超标区间", "数据点数量": 1, "占比": 33.33}
      ],
      "invalid_count": 0,
      "threshold_note": "分布区间仅用于描述预测值分布，不构成安全或超标判定"
    }
  }
}
```

## 五、CSV 格式

- 编码：UTF-8 BOM（Excel 直接打开不乱码）
- 列：`parcel_id, sample_id, ln_value, value, unit, unit_status`
- 响应头带 `X-Row-Count` 与 `Content-Disposition` 文件名 `<model>_cd_results_<UTC时间戳>.csv`

## 六、当前数据状态

结果表在阶段 1 归档时为 0 行，因此**统计接口目前只能验证空态**。真实数值依赖输入到位（MSM 输出或完整特征行供给）。

## 七、测试

`tests/test_heavy_metal_cd_statistics.py` 共 22 项：

- 算法：手算对比、总体标准差、下标分位数（与 numpy 差异）、空值、三档边界（0.2/0.3/0.1999）、负值计入超标
- 服务（内存 SQLite 真实查询）：空态、exp 还原、有效态无分箱、综合统计缺失标记、分页排序、参数校验、CSV BOM/列序、超限拒绝、area 过滤生效
- HTTP：认证 401、统计 200 结构、参数非法 400、CSV 超限 413、CSV 响应头、模型契约字段
