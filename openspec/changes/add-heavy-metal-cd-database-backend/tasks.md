## 1. 结果表结构与 ORM 模型

- [x] 1.1 新增 `framework/models/cd_prediction.py`：`CdCropPredictionResult`（表 `cd_crop_prediction_result`）与 `CdEffectivePredictionResult`（表 `cd_effective_prediction_result`），列与原系统同构：`id` / `parcel_id` / `sample_id` / `ln_crop_cd` 或 `ln_eff_cd`，注释标注 `[ln(mg/kg)]`
- [x] 1.2 两表加 `UniqueConstraint(parcel_id, sample_id)`，并加 `parcel_id` 单列索引（真实 PG 已核对约束与索引）
- [x] 1.3 确认不添加 `execution_id` / `model_version` / `created_at`（design 决策 3），模型文件 docstring 已写明取舍
- [x] 1.4 在 `framework/models/__init__.py` 注册新模型，`db.create_all()` 能发现新表（实测建表成功）

## 2. 数据库输入适配

- [x] 2.1 新增 `framework/domain/other_models/heavy_metal_cd_db.py`，提供 `map_indicators()`（纯函数）/ `build_inputs(parcel_id, model_id)` / `build_inputs_from_row(row, model_id)`
- [x] 2.2 实现已确认映射（有效钾、有效磷、全氮）；实测 `soil_indicators` 无 `silt_content`/`sand_content`，黏粒/砂粒映射未启用，其余字段一律进 `missing_fields`
- [x] 2.3 编写映射覆盖率实测脚本，针对当前库真实数据统计：每个模型有多少地块能凑齐全部特征、各字段的非空率；结果已写入 `docs/cd-input-coverage-report.md`，实测两模型可凑齐地块数均为 0
- [ ] 2.4 逐字段核实待定映射（质地三组分、元素总量、`cec`/`exchangeable_base_sum`、`total_cadmium` 取自 `cd`），确认一个启用一个，未确认的保持 `missing_fields`
- [x] 2.7 增加"完整特征行"输入通道：`run(rows=[{parcel_id, sample_id, **features}])`，供当前库无映射时使用（design 决策 10，真实 PG 已跑通）
- [x] 2.5 明确禁止：不得把 `exchangeable_ca/mg/na/k` 当作 `total_calcium/total_magnesium/total_potassium`，不得填零或区域均值（`FORBIDDEN_SOURCES` + 单测覆盖）
- [x] 2.6 批量入口显式接受上游提供的 `solution` / `cdsolution`；该值缺失的地块进 `rejected`，不以降级值入库（单测 `test_incomplete_batch_writes_nothing`）

## 3. 批量预测与地块级覆盖写库

- [x] 3.1 实现 `run(model_id, rows=…/parcel_ids=…, apply=…)`：预检 → 推理 → 按 parcel_id 删除旧行 → 分批（5000/批）`bulk_insert_mappings` → 单事务 commit，异常 rollback
- [x] 3.2 预检有任何地块缺输入时整批拒绝，返回 `rejected` 明细（`parcel_id` + `missing_fields`），不写库、不写半截
- [x] 3.3 重跑同一批次验证幂等：第二次执行后表内行数不变、`ln_*` 值被替换为最新结果（真实 PG + 单测双证）
- [x] 3.4 验证"地块级"语义：一个 `parcel_id` 下多个 `sample_id` 时，重算后该地块所有样例行都被本次结果替换（单测 `test_parcel_level_replacement`）

## 4. 结果读取与单位口径

- [x] 4.1 提供 `read_results(model_id, parcel_ids=None)`，返回 `exp(ln_*)` 还原后的 mg/kg 值与原始 ln 值
- [x] 4.2 `available_models()` 与 `predict()` 增加 `unit="mg/kg"` 与 `unit_basis`（引用原系统模型类文档与列注释），**`unit_status` 保持 `unverified`**
- [x] 4.3 `manifest.json` 新增 `unit` / `unit_basis` / `unit_status` / `unit_status_note`（写明"量级待核"理由）
- [x] 4.4 新增断言：`unit == "mg/kg"` 且 `unit_basis` 非空；既有两处 `unverified` 断言保持不变（15 passed）

## 5. 迁移脚本与批处理入口

- [x] 5.1 新增 `scripts/migrate_add_cd_result_tables.py`：`db.create_all()` + 打印两张表的列/注释/约束/索引并校验，幂等可重跑；`--drop` 回滚
- [x] 5.2 新增 `scripts/run_cd_prediction.py`：`--model` + `--rows-file`/`--parcel-ids`/`--all`，默认 dry-run，`--apply` 才写库
- [x] 5.3 文档给出覆盖前备份命令（`pg_dump -t`）与回滚命令（`--drop`）：`docs/heavy-metal-cd-database-backend.md`

## 6. 文档与验证

- [x] 6.1 在 `docs/heavy-metal-cd-database-backend.md` 说明表结构、覆盖语义、输入通道与映射表、单位依据、命令
- [x] 6.2 定向测试 `tests/test_heavy_metal_cd_db.py` 11 passed：缺输入拒绝、整批不写、重跑幂等、多样点替换、dry-run 不写、读取还原、映射禁止项、单位标注
- [x] 6.3 真实数据探针：`--all --limit 5` dry-run 全部 rejected（缺 11 个特征含 solution），整批零写入；探针脚本与 JSON 已删除
- [x] 6.4 `openspec validate add-heavy-metal-cd-database-backend` = valid；`git diff --check` 通过
- [ ] 6.5 归档时回填 `docs/cd-migration-roadmap.md` 中阶段 1 的状态与归档日期（与归档动作同一提交）

## 未完成（需人工确认后执行）

- **`solution`/`cdsolution` 的供给依赖上游 MSM**：原系统链路是 `MSM_output_data.Cd.solution` → `solution = LN(POR_Layer/bd020_90 * 112000 * Cd.solution)` → `CropCd_input_data.solution`，本仓库没有 MSM。阶段 1 假设该输入由上游提供，缺失即整批拒绝、不入库降级值；MSM 集成与新地块处置留后续 change。
- **输入量口径未定（IDW 插值面 vs 样点实测值）**：原系统特征是 IDW 插值列，本系统只有实测点值，需先拍板再决定能否宣称"与原系统同源"。
- **质地拆分**：`texture` 字符串能否稳定拆成 `silt/sand/gravel` 三组分，需拿到数据字典或来源说明（Open Question 2）。
- **`total_cadmium` 来源**：是否直接取 `third_survey_topsoils.cd`（Open Question 3）。
- **地块-样点口径**：结果表按样点出行还是按地块聚合一行（Open Question 4）。
- **映射未确认的字段**：在确认前一律保持 `missing_fields`，不得为了让覆盖率好看而放宽。
- **PG 测试库缺失**：本机不存在 `db_enterprise_qa_20261013_test`，PG 集成测试会自动跳过；本 change 的写库测试已改为 PG 缺失时退到内存 SQLite 真实执行。是否创建测试库需单独决定（会影响其他既有 PG 测试的跳过状态）。
