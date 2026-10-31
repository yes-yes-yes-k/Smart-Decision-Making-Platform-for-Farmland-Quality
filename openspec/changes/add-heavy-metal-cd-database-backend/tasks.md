## 1. 结果表结构与 ORM 模型

- [ ] 1.1 在 `framework/models/` 新增 `CdCropPredictionResult`（表 `cd_crop_prediction_result`）与 `CdEffectivePredictionResult`（表 `cd_effective_prediction_result`），列与原系统同构：`id` / `parcel_id` / `sample_id` / `ln_crop_cd` 或 `ln_eff_cd`，注释沿用原系统措辞并标注 `[ln(mg/kg)]`
- [ ] 1.2 两表加 `UniqueConstraint(parcel_id, sample_id)`，并加 `parcel_id` 单列索引
- [ ] 1.3 确认不添加 `execution_id` / `model_version` / `created_at`（design 决策 3），在模型文件里写明这一取舍
- [ ] 1.4 在 `framework/models/__init__.py` 注册新模型，使 `db.create_all()` 能发现新表

## 2. 数据库输入适配

- [ ] 2.1 新增 `framework/domain/other_models/heavy_metal_cd_db.py`，提供 `build_inputs(parcel_id, model_id) -> {data, missing_fields, provenance}`
- [ ] 2.2 按 design 决策 5 实现已确认映射（有效钾、有效磷、全氮、黏粒、砂粒），其余字段一律进 `missing_fields`
- [x] 2.3 编写映射覆盖率实测脚本，针对当前库真实数据统计：每个模型有多少地块能凑齐全部特征、各字段的非空率；结果已写入 `docs/cd-input-coverage-report.md`，实测两模型可凑齐地块数均为 0
- [ ] 2.4 逐字段核实待定映射（质地三组分、元素总量、`cec`/`exchangeable_base_sum`、`total_cadmium` 取自 `cd`），确认一个启用一个，未确认的保持 `missing_fields`
- [ ] 2.7 增加"完整特征行"输入通道：接受外部提供的 `parcel_id`/`sample_id` + 全部特征 + `solution`，供当前库无映射时使用（design 决策 10）
- [ ] 2.5 明确禁止：不得把 `exchangeable_ca/mg/na/k` 当作 `total_calcium/total_magnesium/total_potassium`，不得填零或区域均值
- [ ] 2.6 批量入口显式接受上游提供的 `solution` / `cdsolution`（MSM 输出经 `LN(POR_Layer/bd020_90*112000*Cd.solution)` 转换）；该值缺失的地块进 `rejected`，不以降级值入库

## 3. 批量预测与地块级覆盖写库

- [ ] 3.1 实现 `predict_and_store(model_id, parcel_ids)`：预检 → 推理 → 删除同地块旧行 → 分批（5000/批）`bulk_insert_mappings` → 单事务 commit，异常 rollback
- [ ] 3.2 预检有任何地块缺输入时整批拒绝，返回 `rejected` 明细（`parcel_id` + `missing_fields`），不写库、不写半截
- [ ] 3.3 重跑同一批次验证幂等：第二次执行后表内行数不变、`ln_*` 值被替换为最新结果
- [ ] 3.4 验证"地块级"语义：一个 `parcel_id` 下多个 `sample_id` 时，重算后该地块所有样例行都被本次结果替换

## 4. 结果读取与单位口径

- [ ] 4.1 提供 `read_results(model_id, parcel_ids)`，返回 `exp(ln_*)` 还原后的 mg/kg 值与原始 ln 值
- [ ] 4.2 `available_models()` 与 `predict()` 增加 `unit="mg/kg"` 与 `unit_basis`（引用原系统模型类文档与列注释），**`unit_status` 保持 `unverified`**
- [ ] 4.3 同提交内更新 `data/model_artifacts/heavy_metal_cd/manifest.json`：新增 `unit=mg/kg` 与 `unit_basis`，`unit_status` 保持 `unverified` 并写明"量级待核"的理由
- [ ] 4.4 补一条断言：`unit == "mg/kg"` 且 `unit_basis` 非空；既有的两处 `unverified` 断言保持不改

## 5. 迁移脚本与批处理入口

- [ ] 5.1 新增 `scripts/migrate_add_cd_result_tables.py`：`db.create_all()` + 打印两张表的列与约束校验结果，幂等可重跑
- [ ] 5.2 新增 `scripts/run_cd_prediction.py`：接受 `--model` 与 `--parcel-ids`/`--all`，默认 dry-run（只打印预检与预测值），`--apply` 才写库
- [ ] 5.3 文档中给出覆盖前备份命令（`pg_dump -t`）与回滚命令（`DROP TABLE`）

## 6. 文档与验证

- [ ] 6.1 在 `docs/` 增加 Cd 数据库后端说明：表结构、覆盖语义、映射表、单位依据
- [ ] 6.2 定向测试：新增 `tests/test_heavy_metal_cd_db.py`，覆盖"缺输入拒绝"、"整批不写"、"重跑幂等"、"多样例地块替换"四条
- [ ] 6.3 真实数据探针：对当前库真实地块跑一次 dry-run，打印可算/不可算地块数与原因分布（脚本用完删除）
- [ ] 6.4 `openspec validate add-heavy-metal-cd-database-backend` 与 `git diff --check`
- [ ] 6.5 归档时回填 `docs/cd-migration-roadmap.md` 中阶段 1 的状态与归档日期（与归档动作同一提交）

## 未完成（需人工确认后执行）

- **`solution`/`cdsolution` 的供给依赖上游 MSM**：原系统链路是 `MSM_output_data.Cd.solution` → `solution = LN(POR_Layer/bd020_90 * 112000 * Cd.solution)` → `CropCd_input_data.solution`，本仓库没有 MSM。阶段 1 假设该输入由上游提供，缺失即整批拒绝、不入库降级值；MSM 集成与新地块处置留后续 change。
- **输入量口径未定（IDW 插值面 vs 样点实测值）**：原系统特征是 IDW 插值列，本系统只有实测点值，需先拍板再决定能否宣称"与原系统同源"。
- **质地拆分**：`texture` 字符串能否稳定拆成 `silt/sand/gravel` 三组分，需拿到数据字典或来源说明（Open Question 2）。
- **`total_cadmium` 来源**：是否直接取 `third_survey_topsoils.cd`（Open Question 3）。
- **地块-样点口径**：结果表按样点出行还是按地块聚合一行（Open Question 4）。
- **映射未确认的字段**：在确认前一律保持 `missing_fields`，不得为了让覆盖率好看而放宽。
