# 重金属 Cd 数据库后端（阶段 1）

对应 OpenSpec change：`add-heavy-metal-cd-database-backend`（路线图阶段 1 / 7，见 `docs/cd-migration-roadmap.md`）。

## 一、范围

把 `add-heavy-metal-cd-prediction`（阶段 0）的参数级 callable 接成"批量预测 + 结果落库 + 读取还原"的链路，语义对齐 AcidMap 原系统 `CropCd_output_data` / `EffCd_output_data`。

- 本阶段**不**做 HTTP 接口、统计、空间、地图、通量。
- 因当前库输入覆盖率为 0（`docs/cd-input-coverage-report.md`），主通道是调用方提供**完整特征行**。

## 二、表结构

两张表，与原系统同构（只存自然对数值），差异只有唯一约束：

**`cd_crop_prediction_result`**

- `id` INTEGER PK autoincrement — 主键
- `parcel_id` VARCHAR(64) NOT NULL — 地块唯一编号（对应原系统 Farmland_ID）
- `sample_id` VARCHAR(64) NOT NULL — 样点编号（地块级口径时等于 parcel_id）
- `ln_crop_cd` FLOAT NOT NULL — 籽粒镉浓度的自然对数值[ln(mg/kg)]
- 约束：`UNIQUE (parcel_id, sample_id)`；索引：`parcel_id`

**`cd_effective_prediction_result`**

- `id` / `parcel_id` / `sample_id` 同上
- `ln_eff_cd` FLOAT NOT NULL — 有效态镉浓度的自然对数值[ln(mg/kg)]
- 约束：`UNIQUE (parcel_id, sample_id)`；索引：`parcel_id`

**有意不加**的列（design 决策 3）：`execution_id`、`model_version`、`computed_at`、批次号。用户口径是与原系统一致、不追踪"哪个模型算的"。

## 三、覆盖语义

- **地块级覆盖**：写入前 `DELETE FROM <表> WHERE parcel_id IN (本次涉及的地块)`，再 `bulk_insert_mappings`（5000 条/批）。
- **单事务**：任一步失败整体 `rollback`，不留部分写入。
- **重跑幂等**：同一批次重跑后行数不变，值替换为最新结果。
- **预检整批拒绝**：只要有一个地块缺必需输入，整批不写库，返回逐地块 `missing_fields`。

## 四、输入通道

**通道 A（主）｜完整特征行**：`run(model_id, rows=[{parcel_id, sample_id, **14/21 个特征}])`

**通道 B（可选）｜当前库映射**：`run(model_id, parcel_ids=[...])`，从 `parcel_info.soil_indicators` 取值。

已启用的映射（`CONFIRMED_INDICATOR_MAP`）：

- `available_potassium` ← `available_potassium`
- `available_phosphorus` ← `available_phosphorus`
- `total_nitrogen` ← `total_n`

实测发现：`soil_indicators` 里**没有** `silt_content` / `sand_content`，因此原计划中的黏粒/砂粒映射未启用；`soil_texture` 是类别描述，无法拆成三组分。

**明确禁止**：不得把 `exchangeable_ca / exchangeable_mg / exchangeable_k / exchangeable_na` 当作 `total_calcium / total_magnesium / total_potassium`。不得填零、区域均值或训练集统计量。

**`solution` / `cdsolution`**：由上游 MSM 提供（原系统链路 `MSM_output_data.Cd.solution` → `solution = LN(POR_Layer/bd020_90 * 112000 * Cd.solution)`）。批量场景缺失即整批拒绝，**不以中位数降级值入库**；单点 `predict()` 的降级路径保留供调试。

## 五、单位口径

- 输出单位标注 `mg/kg`，`unit_basis` 指向原系统模型类文档与建表迁移列注释。
- `unit_status` **保持 `unverified`**：`exp(LnEffCd)` 实测落在 1.004–2.295 mg/kg，量级高于常规有效态 Cd，单位/标度待核（design 决策 6）。
- 不提供任何阈值分箱、安全等级或法规结论。

## 六、命令

建表（幂等）：

```bash
python scripts/migrate_add_cd_result_tables.py
```

覆盖前备份：

```bash
pg_dump -h 127.0.0.1 -p 5432 -U postgres -d db_enterprise_qa_20261013 \
  -t cd_crop_prediction_result -t cd_effective_prediction_result \
  -f D:/temp/cd_tables_backup.sql
```

回滚（删除两张表，不触碰其他表）：

```bash
python scripts/migrate_add_cd_result_tables.py --drop
```

批处理（默认 dry-run，`--apply` 才写库）：

```bash
# 主通道：完整特征行
python scripts/run_cd_prediction.py --model crop_cd --rows-file D:/temp/cd_rows.json
python scripts/run_cd_prediction.py --model crop_cd --rows-file D:/temp/cd_rows.json --apply

# 可选通道：当前库映射（当前覆盖率 0，会整批拒绝并列出缺口）
python scripts/run_cd_prediction.py --model effective_cd --parcel-ids P0001,P0002
python scripts/run_cd_prediction.py --model crop_cd --all --limit 5
```

## 七、实测验证记录（2026-10-31）

- 建表：`db.create_all()` 新建 2 表；列、注释、`UNIQUE (parcel_id, sample_id)`、`parcel_id` 索引全部核对通过
- 真实 PG 写库：2 条探针地块（输入=训练均值）→ `value=0.266523`、`ln=-1.3222964`，与原系统审计基准一致
- 幂等：连跑两次 `--apply`，表内仍 2 行，值相同；查询确认后清理，表回到 0 行
- 回读：`value = exp(ln) = 0.26652256`，`unit=mg/kg`，`unit_status=unverified`
- 真实库 dry-run（`--all --limit 5`）：5 个地块全部 `rejected`，缺失 11 个特征（含 `solution`），**整批零写入**
- 测试：`tests/test_heavy_metal_cd_db.py` 11 passed（写库路径在内存 SQLite 真实执行，因本机 `*_test` 库不存在，未建库）；`tests/test_heavy_metal_cd.py` 15 passed（未被破坏）

## 八、边界与未完成

- 输入口径（IDW 插值面 vs 样点实测值）未拍板，因此**不能宣称"与原系统同源"**。
- MSM 未集成，`solution`/`cdsolution` 依赖上游供给。
- 按样点出行还是按地块聚合一行（Open Question 4）暂定"调用方给什么就存什么"，映射通道用 `sample_id = parcel_id`。
- `total_cadmium`、质地三组分等映射仍待数据字典确认。
