# add-heavy-metal-cd-database-backend Design

## Context

阶段 0（`add-heavy-metal-cd-prediction`，已在 `zsj_1024` 归档）交付了两件事：

- `framework/domain/other_models/heavy_metal_cd.py`：本地 torch 推理，固定特征序（作物 14 维、有效态 21 维），`solution` 索引 13 / `cdsolution` 索引 20，缺特殊输入时按训练集中位数 -2.1266 降级并强制 `degraded`；
- `data/model_artifacts/heavy_metal_cd/`：`.pth` + mean/scale npy + `manifest.json`（含 SHA-256）。
- `prefill_from_parcel()`：只把 `parcel_info.soil_indicators` 里 5 个语义明确的键（有效钾、有效磷、全氮、黏粒、砂粒）映射成模型字段，其余进 `missing_fields`。

原 AcidMap 的持久化实现（实测 `app/services/cd_prediction_database_service.py`）：

```python
delete_count = db.query(EffCdOutputData).filter(
    EffCdOutputData.farmland_id.in_(farmland_ids)
).delete(synchronize_session=False)
# ... 组装 batch_data ...
for i in range(0, len(batch_data), 5000):
    db.bulk_insert_mappings(EffCdOutputData, batch_data[i:i+5000])
db.commit()   # except: db.rollback()
```

方法注释写的是 "UPSERT"，实现其实是 **delete + insert**；删除粒度是 `farmland_id`（地块级），一个地块的多个样点行会一起被替换。

当前系统的数据底座：`third_survey_topsoils` 有 pH/CEC/SOM/TN/TP/TK/AP/AK/SAK、交换性盐基与 Ca/Mg/Na/K、电导率、S/Si/Fe/Mn/Cu/Zn/B/**Cd**/Cr/Ni、质地、经纬度；`parcel_info` 有 `parcel_id` 唯一约束、PostGIS 几何、`area_code`、`soil_indicators(JSON)`。

## Goals / Non-Goals

**Goals:**

- 用当前系统数据库的地块数据跑出 Cd 双模型预测并落库，语义与原系统一致。
- 覆盖语义明确、可重跑、不产生重复行。
- 输入映射逐字段可核查，不允许静默填值。
- 单位口径落到 mg/kg 并留下依据。

**Non-Goals:**

- 不做批次/历史/版本追踪（用户已明确不需要"哪个模型算的"）。
- 不做 HTTP 接口、统计、空间、地图、通量、未来情景。
- 不改动 Model-1..6 的既有结果表或发布层。

## Decisions

### 1. 结果表与原系统同构，只存自然对数值

两张表：

```text
cd_crop_prediction_result
  id            INTEGER PK autoincrement
  parcel_id     VARCHAR(64) NOT NULL     -- 对应原系统 Farmland_ID
  sample_id     VARCHAR(64) NOT NULL     -- 对应原系统 Sample_ID
  ln_crop_cd    FLOAT NOT NULL           -- 籽粒镉浓度的自然对数值[ln(mg/kg)]

cd_effective_prediction_result
  id            INTEGER PK autoincrement
  parcel_id     VARCHAR(64) NOT NULL
  sample_id     VARCHAR(64) NOT NULL
  ln_eff_cd     FLOAT NOT NULL           -- 有效态镉浓度的自然对数值[ln(mg/kg)]
```

理由：原系统对外契约就是"存 ln、查询时 exp 还原"，消费方（统计、地图）都按这个口径写。存还原值会让后续阶段 2/3 的数值与原系统不可比。列注释直接沿用原系统措辞，单位信息写在注释里，不额外加 `unit` 列。

**偏差一处（有意为之）**：原系统主键只有自增 `ID`，没有唯一约束，一旦某次 `DELETE` 范围未覆盖到就会重复累积行。本 change 给 `(parcel_id, sample_id)` 加唯一约束。对调用方透明（可见数据语义不变），只是把隐患堵住。

### 2. 覆盖语义 = 地块级覆盖，单事务提交

服务函数签名：

```text
predict_and_store(model_id: str, parcel_ids: list[str]) -> dict
```

流程：

1. 预检：读取每个地块的输入，构建 `missing_fields`；有缺失的地块进入 `rejected`，**整批不写库**（与原系统"一个事务全成或全败"一致）。
2. 推理：逐地块调用 `heavy_metal_cd.predict()`。
3. 写库：`DELETE FROM <table> WHERE parcel_id IN (...)`，再 `bulk_insert_mappings` 分批 5000 条，单事务 `commit()`，异常 `rollback()`。
4. 返回：`{model_id, requested, stored, rejected: [{parcel_id, missing_fields}], status}`。

理由：与原系统行为一致，重跑幂等，一个地块不会出现两份结果。

### 3. 不写 execution_id / model_version / computed_at

用户口径：与原系统保持一致，不做"哪个模型算的"追踪。因此结果表不加现有 `xxx_result` 表通用的 `execution_id`、`model_version`、`created_at`。

后果（已知取舍，写在此处备查）：

- 结果行无法与 `model_execution_log` 关联，也无法回答"这条值是哪次执行产生的"；
- 与 Model-1..6 结果表的结构惯例不一致，阶段 2 的查询 API 需要单独适配这两张表。

### 4. 不接入 VersionedModelResult 统一发布层

`framework/domain/assessment/versioned_results.py` 的 `VersionedModelResult` 用 `agent_id + subject_id + model_version + input_hash` 做不可变发布、`is_current` 标记当前行。接入它必然引入模型版本与输入指纹，与决策 3 冲突。

后果：Cd 结果不进 `get_current_result()` 的统一消费路径，地图/报告/Agent 若要用 Cd 结果，需在阶段 2 直接读这两张表（或在其上做一层读取函数）。

### 5. 输入适配只允许已确认映射，不填默认值

沿用 `prefill_from_parcel()` 的保守原则，扩展候选映射如下（**需在实现时逐字段核实语义与单位后才允许启用**）：

- 已确认（现有映射表）：`available_potassium`、`available_phosphorus`、`total_nitrogen`（来自 `total_n`）、`silt_fraction`、`sand_fraction`
- 语义可能对应、待核实：质地字段 → `silt/sand/gravel` 三组分；`third_survey_topsoils.fe/mn/s/cd` 等元素总量 → `total_iron`/`total_manganese`/`total_sulfur`/`total_cadmium`；`cec`/`exchangeable_base_sum` → `exchangeable_base`
- 明确不可映射（交换态 ≠ 全量）：`exchangeable_ca/mg/na/k` **不得**当作 `total_calcium/total_magnesium/total_potassium`
- 无法映射：`solution` / `cdsolution`（上游 MSM 络合模型不在本仓库）→ 走既有降级路径（中位数假设 + `degraded`），或整地块拒绝，取决于批次口径（见 Open Questions）

不填零、不填区域均值；缺失即拒绝，并回显 `missing_fields`。

### 6. 单位口径：标注 `mg/kg`，但核验状态保留 `unverified`

依据（原系统源码，可复核）：

- `app/models/EffCd_output.py` 类文档：`EffCd = exp(LnEffCd) [单位：mg/kg]`；`effective_cadmium()` docstring：`计算实际有效态镉浓度(单位：mg/kg)`
- `app/models/CropCd_output.py`：`实际籽粒镉浓度 = exp(LnCropCd) [单位：mg/kg]`
- 建表迁移 `migrations/versions/95832ecc0bdc_add_effcd_ouput_table.py` 列注释：`有效态镉浓度的自然对数值[ln(mg/kg)]`

因此输出单位**标注为 `mg/kg`**，并返回 `unit_basis` 指向上述引用。但 `unit_status` **保持 `unverified`**：`docs/cd-system-migration-plan-1031.md` 记录原系统 40100 条数据的 `exp(LnEffCd)` 实测落在 **1.004–2.295 mg/kg**，高于土壤有效态 Cd 的常规量级，单位或标度本身仍需核对。核验通过前不得把该值表述为可直接对外引用的浓度。

**阈值分箱仍然不做**，`0.2/0.3 mg/kg` 之类的分档留给阶段 2 且必须显式标注为作物 Cd 分布统计。

### 7. 迁移沿用现有手写脚本，不引入 Alembic

两条新表通过 `db.create_all()` 创建（模型注册后即可建出），新脚本 `scripts/migrate_add_cd_result_tables.py` 只做"创建缺失表 + 打印校验结果"，保持与 `migrate_add_model45_fields.py` 相同的幂等形态。不引入 Alembic（用户口径：现有系统没有就沿用现有路线）。

### 8. 部分地块输入缺失时整批拒绝

预检失败不进入写入阶段，避免"部分地块更新、部分保留旧值"的中间态。若后续需要"能算的先算"，应作为独立 change 明确写入语义。

### 9. `solution` / `cdsolution` 由上游 MSM 提供，批量场景不做缺失降级

原系统的链路是有明确定义的（`app/api/cascade_update.py` 的 `data_chain` 定义，可直接复核）：

- 阶段 1：MSM 络合模型，表 `MSM_input_data` → `MSM_output_data`，输出 `Cd.solution`（土壤溶液镉离子浓度）
- 阶段 2：`solution = LN(POR_Layer/bd020_90 * 112000 * Cd.solution)`，写入 `CropCd_input_data.solution`，该列注释就是这条公式
- 阶段 3：作物 Cd 预测读取 `CropCd_input_data`，`solution` 是 14 个特征之一（索引 13）

也就是说 `solution`/`cdsolution` **不是 Cd 模型自己算的**，是上游 MSM 模型的输出经公式转换而来。本仓库目前没有 MSM——`heavy_metal_cd.py` 文件头已写明 "solution/Cdsolution come from the upstream MSM complexation model which is NOT in this repository"。

结论（用户口径）：本系统集成 MSM 后即具备该输入，因此批量预测场景**不存在"solution 缺失"这一常规分支**：

- 批量入口接受由上游提供的 `solution`/`cdsolution`；
- 若某地块确实没有该值（例如新地块尚无 MSM 结果），该地块进入 `rejected`，**不写库、不以降级值入库**；
- 单点 `predict()` 的"训练集中位数假设 + `degraded`"保留不变（那是参数级调试路径）；
- MSM 本体的集成、以及新地块的处置，留到后续 change 讨论。

### 10. 阶段 1 的输入由外部供给（建议，待用户确认）

2026-10-31 对当前库做了只读实测（完整数据见 `docs/cd-input-coverage-report.md`）：

- `parcel_info` 5488 行（全部有几何与 `soil_indicators`），`third_survey_topsoils` **只有 649 行**；
- crop_cd：严格可映射 **4/14**、乐观 7/14；
- effective_cd：严格可映射 **7/21**、乐观 13/21；
- **两个模型"能凑齐全部特征"的地块数均为 0**；
- 硬缺口：质地三组分（`silt/sand/gravel`，库内只有 `texture` 字符串，50.5% 非空）、全铝（无 Al 字段）、全钙/全镁（只有交换态）、`oc_fe_0_30`（无）、`solution`/`cdsolution`（依赖未集成的 MSM）。

这不是"缺几个字段"，而是整类输入不存在；IDW 插值也变不出不存在的指标（插值只能补已有字段的空间分布）。

因此建议阶段 1 改为：

- 批量入口接受**完整特征行**（`parcel_id` / `sample_id` + 14 或 21 个特征 + `solution`），不绑定当前库字段；
- 当前库字段映射保留为**可选**能力：能凑齐的地块才进入预测，否则进 `rejected` 并报告 `missing_fields`；
- 验证通道使用原系统输入表（`CropCd_input_data` / `EffCd_input_data`）里离线抽取的样本行，仅用于验证，不建成运行时依赖、运行时不读 `soilgd`；
- 真实输入的补齐（IDW 插值面、MSM 输出、缺失指标的数据来源）作为后续 change，阶段 1 不承诺全库可跑。

## Risks / Trade-offs

- **映射覆盖率可能很低**：有效态 Cd 有 21 个特征，当前库能确认映射的可能只有 5–8 个，且 `cdsolution` 依赖尚未集成的上游 MSM，阶段 1 实际可跑的地块数量可能远小于全库。实现的第一步必须先做"映射覆盖率实测"并如实报告，而不是假设能跑全量。
- **`total_cadmium` 的来源要澄清**：`third_survey_topsoils.cd` 是土壤 Cd 实测值，可用于有效态模型的 `total_cadmium`；但有效态 Cd 本身就是 `cd` 的另一种形态，若 `cd` 与有效态 Cd 语义混淆会影响结论。实现时要在文档里写清取值来源。
- **无历史留痕**：覆盖后旧值不可恢复，重算前需要备份（`scripts/migrate_*.py` 之外另给备份命令）。
- **契约变化**：`unit_status` 从 `unverified` 变 `verified`，仓库内有两处测试断言，同提交更新；若外部前端硬编码该值需通知。

## Migration and Rollback

- 建表：`python scripts/migrate_add_cd_result_tables.py`（幂等，`create_all` 只建缺失表）。
- 回滚：`DROP TABLE cd_crop_prediction_result, cd_effective_prediction_result;`（不涉及既有表，无级联影响）。
- 数据回滚：覆盖写之前用 `pg_dump -t` 备份两张表；本 change 不提供自动恢复。

## Open Questions

1. **输入量口径：IDW 插值面还是样点实测值**（本阶段最关键的一个）。原系统 `CropCd_input_data` 的 13 个特征全部是 IDW 插值列——`TAl_IDW`、`TCa_IDW`、`TFe_IDW`、`TMg_IDW`、`TMn_IDW`、`TN_IDW`、`TS_IDW`、`AvaK_IDW`、`AvaP_IDW`、`SAvaK_IDW`、`002_0002IDW`/`02_002IDW`/`2_02IDW`，即"插值面在样点处的取值"，不是样点实测值。本系统 `third_survey_topsoils` 存的是实测点值。两种做法的预测结果不可直接比较：阶段 1 是接受"用地块实测值近似"，还是必须先补齐 IDW 插值（插值属空间能力，本在阶段 3/4 范围）？
2. **质地三组分**：原系统同样是插值列（粉粒 `002_0002IDW`、砂粒 `02_002IDW`、石砾 `2_02IDW`），本系统 `texture` 是字符串描述，无法可靠拆成三组分。
3. **`total_cadmium`**：原系统用 `TCd_IDW`（插值全镉），本系统 `third_survey_topsoils.cd` 是实测点值，能否直接替代需确认。
4. **地块与样点的关联规则**：原系统靠 `Farmland_data(Farmland_ID, Sample_ID)` 复合外键，一个地块多行样点；本系统 `parcel_info` 与 `third_survey_topsoils` **没有外键**，只有经纬度，需要先用空间关系（点在多边形内）定义关联规则，才能决定结果表是"按样点出行"还是"按地块聚合一行"。
