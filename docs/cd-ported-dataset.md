# 移植数据集（原系统 Cd 数据，阶段 D1）

对应 OpenSpec change：`import-cd-ported-dataset`。

## 一、为什么有这套数据

Cd 业务链路（阶段 0–3）代码已跑通，但本项目自有地块缺模型输入（覆盖率 0），原系统数据又无法按坐标对应（匹配率 8.7%，中位距离 57km）。为**先把业务跑通**，把原系统整套 Cd 数据集移植进本项目数据库，与自有数据并存。

两条数据线并行：

- **A 线**：`docs/cd-data-requirements.md` 已交业务方，等真实地块数据
- **B 线（本条）**：先用移植数据把统计、明细、导出、乡镇、点位全部验证起来

## 二、命名空间：`SGD_` 前缀

- 结果表 `parcel_id`：`SGD_<Farmland_ID>`（如 `SGD_1`）
- `sample_id`：`SGD_<Farmland_ID>_<Sample_ID>`（原系统 `Sample_ID` 全为 0，即 `SGD_1_0`）
- `parcel_info` 同名插入：`centroid_lon/lat` 取自原系统 `lon/lan`，**`geom` 与 `area_code` 留空**，`legacy_parcel_code = soilgd:<id>`

与自有 `parcel_id`（纯数字 1..999）永不冲突。

`geom` / `area_code` 留空的意义：

- 既有地块面积/质量统计的 SQL 带 `data.geom IS NOT NULL`，自动排除移植点
- 按 `area_code` 过滤的统计自动排除移植数据（它们没有合法行政区属性）

## 三、命令

```bash
# 建表（幂等）
python scripts/migrate_add_ported_dataset_tables.py

# dry-run（看源表规模与前 5 行预测）
python scripts/import_ported_cd_dataset.py --model crop_cd --limit 200

# 正式导入（all = 两个模型）
python scripts/import_ported_cd_dataset.py --model all --apply

# 只重算乡镇归属
python scripts/import_ported_cd_dataset.py --assign-townships

# 回归比对（导入验收）
python scripts/import_ported_cd_dataset.py --compare --model all

# 回滚（只删 SGD_ 前缀，不动自有数据）
python scripts/import_ported_cd_dataset.py --rollback
```

## 四、导入链路

1. 从 `soilgd` 读 `Farmland_data` + `CropCd_input_data` / `EffCd_input_data`
2. 按**已核实的 ORM 列映射**组装 14/21 特征行（`CropCd_input_data` 的 `AvaP`/`AvaK` 是交叉的：`available_phosphorus ← AvaK_IDW`、`available_potassium ← AvaP_IDW`）
3. `parcel_info` 插入 `SGD_` 行
4. 乡镇归属：`ST_Contains(township.geom, point)` → 未命中取最近乡镇并记 `distance_m`
5. 走既有 `run(rows=..., apply=True)` 写结果表（复用覆盖写与单事务）
6. 回归比对：作物 Cd 比 `ln` 绝对差；有效态比**浓度**相对差（原系统 `LnEffCd` 列实际存的是浓度）

任一步失败：脚本非零退出，不留下"看起来成功"的结果。

## 五、数据来源维度

所有统计/明细/导出/空间接口新增 `source` 参数：

- `native`：只看自有地块
- `ported`：只看移植数据
- `all`（默认）：两者都看，响应带 `source_breakdown` 给出各自样本数

乡镇统计的归属按来源切换：

- 自有 → `farmland_region_parcel_area`（面积最大归属）
- 移植 → `cd_ported_parcel_township`（点面判断 + 最近回退）
- `assignment_rule` 会反映实际用到的依据（单套时为 `max_area` / `point_in_polygon`，两套都有数据时为 `per_source`）

## 六、与业务方数据的关系

- 现在：移植数据供演示与链路验证，自有数据为空
- 业务方数据到位后：默认 `source=native` 即只看真实地块；移植数据保留作为对照或清空（`--rollback`）
- 两者永不混入同一口径而不加标注

## 七、实测记录（2026-10-31，开发库 `db_enterprise_qa_20261013`）

**导入规模**

- 源表可导入：两个模型各 40100 行
- `parcel_info` 新增 40100 行（试点 200 + 全量 39900），总数 5488 → 45588
- `cd_ported_parcel_township` 40100 行：点面包含 39831、回退最近乡镇 74（0.18%）
- 结果表各 40100 行

**回归比对（容差 1e-4）**

- 作物 Cd：比对 40100 行，最大差 2.79e-06、中位 1.77e-07、超差 0 → 通过
- 有效态 Cd：比对 40100 行，最大差 1.03e-06、中位 7.48e-08、超差 0 → 通过

**作物 Cd 分布（`source=ported`，mg/kg）**

- 均值 0.112495、中位 0.098645、标准差 0.082643
- 最小 0.004774、最大 0.437994、P25 0.049215、P75 0.144102

**乡镇粒度（`min_count=100`）**

- 17 个乡镇达标，最大 440281106（4628 点，均值 0.0701），次之 440281108（4407 点，0.0478）、440281104（4169 点，0.1467）
- `assignment_rule = point_in_polygon`，`ported_fallback_count = 74`

**既有功能未受污染**

- `parcel_info`：`geom IS NOT NULL` 仍为 **5488**（= 导入前），`area_code IS NOT NULL` 仍为 5488
- `source=native` 时统计仍是空态（`has_data=false`），与业务方数据未到位的事实一致

