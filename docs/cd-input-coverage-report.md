# Cd 双模型输入覆盖率实测报告（2026-10-31）

数据库：`db_enterprise_qa_20261013` @ 127.0.0.1:5432
方式：只读连接（`set_session(readonly=True)`），仅执行 SELECT；探针脚本跑完即删。
用途：判断"当前系统数据库能否直接支撑 Cd 双模型批量预测"。

## 一、数据规模

- `parcel_info`：**5488 行**，全部有 PostGIS 几何，全部有 `soil_indicators` JSON
- `third_survey_topsoils`：**649 行**（注意：不是原库 `soilgd` 的 40100 行，本库只导入了一个县/区的表层土点位）

## 二、`parcel_info.soil_indicators` 现有键（每个键 5488 个地块都有）

`available_phosphorus`、`available_potassium`、`bulk_density`、`cation_exchange_capacity`、`composite_index`、`drainage_capacity`、`effective_soil_depth`、`exchangeable_acid_total`、`exchangeable_aluminum`、`exchangeable_hydrogen`、`fertilizer_type`、`hydrolytic_total_acidity`、`indicator_provenance`、`irrigation_condition`、`organic_matter`、`plow_layer_thickness`、`provenance`、`quality_grade`、`soil_ph`、`soil_structure`、`soil_texture`、`target_ph`、`terrain_position`、`topsoil_thickness`、`total_n`

注意：这些值大多是区域回填（`provenance` 中有标注），不是地块实测。

## 三、`third_survey_topsoils` 列非空率（共 649 行）

- `ph`、`cec`、`som`、`tn`、`tk`、`ak`、`sak`、`exchangeable_ca`、`exchangeable_mg`、`conductivity`、`s`、`fe`、`mn`、`cu`、`zn`、`b`、`ni`、`lon`、`lat`：100%
- `tp`、`exchangeable_k`：99.7%
- `ap`：98.6%
- `exchangeable_base_sum`：97.5%
- `cr`：97.4%
- `cd`：97.2%
- `exchangeable_na`：65.9%
- `texture`：50.5%（只有 328 行，且是字符串描述）
- `si`：43.1%

## 四、模型特征可映射情况（实测）

**作物 Cd（crop_cd，14 个特征）**

- 严格可映射 **4/14**：`available_phosphorus`、`available_potassium`、`slowly_available_potassium`、`total_nitrogen`
- 严格缺口（10 个）：`silt_fraction`、`sand_fraction`、`gravel_fraction`、`total_aluminum`、`total_calcium`、`total_iron`、`total_magnesium`、`total_manganese`、`total_sulfur`、`solution`
- 乐观可映射（额外接受 fe/mn/s 作全铁/全锰/全硫）**7/14**
- 乐观缺口（7 个）：`silt_fraction`、`sand_fraction`、`gravel_fraction`、`total_aluminum`、`total_calcium`、`total_magnesium`、`solution`
- **能凑齐全部 14 个特征的样点数：0**

**有效态 Cd（effective_cd，21 个特征）**

- 严格可映射 **7/21**：`available_phosphorus`、`available_potassium`、`electrical_conductivity`、`exchangeable_hydrogen`、`slowly_available_potassium`、`total_nitrogen`、`total_phosphorus`
- 乐观可映射（额外接受 fe/mn/s/tk/cd/exchangeable_base_sum）**13/21**
- 乐观缺口（8 个）：`oc_fe_0_30`、`silt_fraction`、`sand_fraction`、`gravel_fraction`、`total_aluminum`、`total_calcium`、`total_magnesium`、`cdsolution`
- **能凑齐全部 21 个特征的样点数：0**

## 五、硬缺口（现有库完全没有数据来源）

- **质地三组分**（`silt/sand/gravel`）：只有 `texture` 字符串（50.5%）与 `soil_texture` 类别描述，无法得出三个质量占比百分数
- **全铝**（`total_aluminum`）：库内无 Al 字段（`si` 是硅，且只有 43.1%）
- **全钙 / 全镁**（`total_calcium` / `total_magnesium`）：只有交换性钙镁，语义不同，不可替代
- **有机碳-铁结合态**（`oc_fe_0_30`，有效态模型）：无对应字段
- **`solution` / `cdsolution`**：依赖上游 MSM 络合模型，本仓库未集成

## 六、结论

1. **按"从当前库直接取数"的路线，阶段 1 无法产出任何一条真实预测**（覆盖率 0，模型不接受缺特征）。
2. 缺口不是"数据缺失需要补几个字段"，而是**整类输入不存在**：质地三组分、全铝、全钙、全镁、OC-Fe、MSM 输出。
3. 原系统之所以能跑，是因为它喂给模型的是 **IDW 空间插值面**（列名带 `_IDW`），数据来源是其上游的插值数据集，而不是本库这 649 个采样点。

## 七、可选路线（供决策）

- **A｜输入外部供给（推荐）**：阶段 1 只做"结果表 + 地块级覆盖写库 + 读取 + 批量入口"，批量入口接受完整 14/21 特征行。验证用原系统已有的 `CropCd_input_data` / `EffCd_input_data`（离线导入，不建成运行时依赖）。这样阶段 1 能真正跑通、结果可核对，同时不假装"数据库适配已完成"。
- **B｜先补 IDW 插值**：把阶段 3/4 的空间插值提前。但本库只有 649 个点去插 5488 个地块，代表性弱，且缺口（全铝、全钙、全镁、OC-Fe）插值也变不出来——插值只能补已有字段的空间分布，不能生成不存在的指标。
- **C｜缩减模型特征**：不可行，两个模型都是固定 14/21 维输入，缺一个即拒绝。
