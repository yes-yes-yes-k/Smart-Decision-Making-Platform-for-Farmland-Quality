# import-cd-ported-dataset Design

## Context

原系统数据（实测，`soilgd` 库）：

- `Farmland_data`：40100 行，列只有 `Farmland_ID / Sample_ID / lon / lan / Type / geom`，`Sample_ID` 全为 0，**没有行政区字段**
- `CropCd_input_data`：40100 行 × 17 列，14 个特征 + ID/Farmland_ID/Sample_ID，特征齐全
- `EffCd_input_data`：40100 行 × 24 列，21 个特征
- `MSM_output_data`：40100 行，含现成 `Cd.solution`
- `CropCd_output_data` / `EffCd_output_data`：各 40100 行，供回归比对

本项目现状：`parcel_info` 5488 行（`parcel_id` 纯数字 1..999），结果表 0 行，乡镇归属走 `farmland_region_parcel_area`（预计算面积），乡镇边界在 `spatial_region_catalog`（103 个）。

关键冲突：两边 `parcel_id` 都是纯数字，**直接写入会与自有地块混淆**（`Farmland_ID=1` 与 `parcel_id='1'` 是不同地块）。

## Goals / Non-Goals

**Goals:**

- 移植数据能被现有接口（统计/明细/CSV/乡镇/点位）直接消费，不需要为新数据写第二套查询
- 移植数据与自有地块数据在**任何响应里都可区分**
- 导入过程可重复执行（幂等），导入结果可与原系统输出回归比对

**Non-Goals:**

- 不做坐标匹配式的部分导入
- 不引入新依赖、不引入 MSM 求解
- 不改结果表结构、不改模型推理

## Decisions

### 1. 命名空间用 `SGD_` 前缀，写入现有表

- 结果表 `parcel_id`：`SGD_<Farmland_ID>`（如 `SGD_1`）
- `sample_id`：`SGD_<Farmland_ID>_<Sample_ID>`（原系统 `Sample_ID` 全为 0，即 `SGD_1_0`）
- `parcel_info` 插入同名 `parcel_id` 行，填 `centroid_lon/lat`（来自 `Farmland_data.lon/lan`），`geom` 留空，`legacy_parcel_code` 填 `soilgd:<Farmland_ID>` 便于追溯

理由：结果表结构不能加列（阶段 1 spec 锁定"只有 id/parcel_id/sample_id/ln_*"），唯一能在不改 schema 前提下区分来源的手段就是 ID 命名空间。`SGD_` 前缀与本项目纯数字 ID 不会碰撞。

### 2. 乡镇归属单独建表，不写 `farmland_region_parcel_area`

新表 `cd_ported_parcel_township`：

```text
parcel_id      VARCHAR(64) PK      -- SGD_<id>
township_id    VARCHAR(64)         -- spatial_region_catalog.object_id
township_name  VARCHAR(128)
distance_m     DOUBLE PRECISION     -- 点到乡镇边界的距离（0 表示在内部）
assigned_at    TIMESTAMP
```

归属规则：`ST_Contains(township.geom, point(lon,lat))`；若点不在任何乡镇内（可能有边界缝隙），回退到最近的乡镇并记录 `distance_m`。

理由：`farmland_region_parcel_area` 的语义是"区域 × 地块 × 面积亩"，点是零面积对象，塞进去会破坏该表语义与下游面积统计。

### 3. 统计接口加 `source` 维度，默认 `all` 但必须回显分解

- 参数：`source=native|ported|all`（默认 `all`）
- 判定：`parcel_id LIKE 'SGD\_%'` 为 ported，其余为 native
- 响应新增：`source`（生效值）、`source_breakdown`（`{native: n, ported: m}`）
- 分箱与 8 项统计口径不变

理由：不改变默认行为的向后兼容（默认 `all`），同时让人一眼看出"这些数字里有多少来自移植数据"。

### 4. 导入走现有 `run(rows=...)` 通道，不写第二套推理

导入脚本只做"读源表 → 组装完整特征行 → 调 `run()`"，推理与写库复用阶段 1 的实现（覆盖写、单事务、预检拒绝）。这样移植数据的产生路径与自有数据完全一致，不会出现"两套算法"。

列映射必须按已核实的 ORM 语义（**`CropCd_input_data` 的 `AvaP`/`AvaK` 是交叉的**）：

```text
crop_cd:    available_phosphorus ← AvaK_IDW ；available_potassium ← AvaP_IDW
effective:  available_potassium ← AvaK_IDW ；available_phosphorus ← AvaP_IDW
```

按列名直觉取数会让作物 Cd 稳定偏 +0.38（ln），已在一致性报告里记录。

### 5. 回归比对作为导入的验收门

导入完成后必须比对：

- 作物 Cd：`local ln` vs 原系统 `LnCropCd`，要求最大绝对差 < 1e-4
- 有效态 Cd：`local 浓度` vs 原系统 `LnEffCd` 列值（该列存的是浓度），要求最大相对差 < 1e-4

不达标则不提交导入结果（脚本以非零退出并打印差异分布）。

### 6. 移植数据写入 `parcel_info` 时 `geom` 与 `area_code` 留空，既有地块统计不受污染

移植点只有经纬度、没有地块多边形，因此写入 `parcel_info` 时：

- `centroid_lon/lat` 填原系统 `lon/lan`
- `geom` **留空**
- `area_code` **留空**
- `legacy_parcel_code` 填 `soilgd:<Farmland_ID>`（唯一约束满足）

实测依据：`framework/api/services/farmland_statistics.py` 的统计 SQL 全部带 `data.geom IS NOT NULL`（`_live_statistics_sql` 第 800 行附近），所以 `geom` 为空的行不会进入既有的地块面积/质量统计。`area_code` 为空则阶段 2 的 `area_code` 过滤、阶段 3 的区县粒度统计都会自然排除移植数据——这正是期望行为（移植数据没有合法行政区属性）。

实现后必须实测：对同一行政区调用 `farmland_statistics.aggregate_statistics()`，导入前后返回的数值必须一致。

### 7. 乡镇归属按来源切换，两套依据并存

- 自有地块：`farmland_region_parcel_area`（面积最大归属，已归档的阶段 3 语义，**不改**）
- 移植地块：`cd_ported_parcel_township`（点面判断 + 最近回退）

`source=all` 时两套并存，响应给出 `source_breakdown` 与两类归属的样本数；`source=native|ported` 时只用对应依据。这样既不改阶段 3 已归档的归属语义，也让移植数据能做乡镇统计。

## Risks / Trade-offs

- **`parcel_info` 被灌入 40100 行**：会让"地块总数"从 5488 跳到 45588，任何不区分来源的 UI/统计都会失真。缓解：接口默认返回 `source_breakdown`；文档显著标注。
- **移植数据的乡镇归属是点面判断**（原系统点可能落在边界缝隙），存在 `distance_m > 0` 的回退归属，需在响应里暴露该计数。
- **原系统行没有行政区码**，区域统计只能靠乡镇归属表推导，不能给出 `area_code` 级别的准确归属。
- 若将来业务方数据到位，需要决定"并存 / 替换 / 清理移植数据"，届时另开 change。

## Migration and Rollback

- 建表：新增 `scripts/migrate_add_ported_dataset_tables.py`（幂等 `create_all`）
- 导入：`scripts/import_ported_cd_dataset.py --apply`；`--rollback` 删除 `SGD_%` 的 `parcel_info`、结果表与归属表行（不动自有数据）
- 不涉及既有表结构变更

## Open Questions

1. **`SGD_` 前缀是否接受**，还是希望换成别的标识（如 `PORTED_`）？
2. **是否把 40100 个移植点写进 `parcel_info`**（本提案默认写，好处是点位/明细可直接 join；代价是地块总数从 5488 变成 45588，需要所有页面都认 `source` 维度）？替代方案是不写 `parcel_info`，只给移植数据单独一套点位表，但那样点位接口要分叉。
3. **统计默认值**：`all`（本提案默认，能看到数据）还是 `native`（更安全，但默认仍为空态）？
