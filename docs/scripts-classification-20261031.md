# scripts/ 分类清理清单（2026-10-31）

**状态：仅盘点，未移动、未删除任何文件。** 本清单用于确认范围后再执行 `git mv`。

`scripts/` 当前 **273 个脚本、32,335 行**。按“同族旧版本 / 一次性修复迁移 / 纯审计报告”三类筛出 **55 个可归档或移出（54 归档 + 1 移出）**，其余 **218 个**建议保留原地；归档合计 5,194 行。

## 一、判定口径

- **引用数**：脚本名在 `docs/ openspec/ tests/ framework/ scripts/ deploy/ governance/ benchmarks/` 的出现次数，排除脚本自身、隐藏目录与 `.worktrees` 副本（这些副本会把计数放大十倍以上）。
- **同族**：去掉 `_v1/_v2/_r2/_r3/_r4/_r41/_r5/_final/_retry` 与日期后缀后同名。
- **基准入口**：同族中优先保留文档引用最多的版本；若同族各自产出过已发布产物（`build_minimal_kg_v03` 与 `v04` 分别对应 v0.3/v0.4 图谱），两者都保留。
- **零引用不等于无用**：不少审计脚本只被产物间接引用，故 C 类只归档、不删除。
- 判定仅依据文件名、修改时间、引用次数与产物依赖，**未运行任何脚本**。

## 二、汇总

| 分类 | 归档 | 移出仓库 | 保留 | 合计 |
|---|---:|---:|---:|---:|
| A 同族旧版本 | 10 | 1 | 1 | 12 |
| B 一次性修复/迁移 | 5 | 0 | 11 | 16 |
| C 纯审计/报告 | 39 | 0 | 40 | 79 |
| 其余（运行/构建/服务入口） | — | — | 166 | 166 |
| **合计** | **54** | **1** | **218** | **273** |

## 三、A 类：同族旧版本（12）

同族并存多版本，保留引用最多的基准入口，其余归档。`run_kg_benchmark_pilot_r5` 是同族最新一轮实验，暂不处理。

| 脚本 | 行数 | 最后修改 | 引用 | 建议 | 同族基准 / 依据 |
|---|---:|---|---:|---|---|
| `run_kg_external_qa_pilot.py` | 278 | 10-30 | 2 | 归档 | 同族基准入口为 run_kg_external_qa_pilot_v2.py，本文件为早期版本 |
| `run_kg_benchmark_pilot_r2.py` | 147 | 10-28 | 0 | 移出仓库 | 同族中间实验版本，零引用；基准入口为 run_kg_benchmark_pilot.py，git 历史可回溯 |
| `run_kg_benchmark_pilot_r5.py` | 136 | 10-29 | 2 | 保留 | 同族最新一轮实验，暂留；基准入口为 run_kg_benchmark_pilot.py |
| `run_kg_benchmark_pilot_r4.py` | 133 | 10-28 | 6 | 归档 | 同族基准入口为 run_kg_benchmark_pilot.py，本文件为早期版本 |
| `calibrate_kg_v4_r3.py` | 130 | 10-27 | 1 | 归档 | 同族基准入口为 calibrate_kg_v4_r4.py，本文件为早期版本 |
| `run_kg_benchmark_pilot_r3.py` | 119 | 10-28 | 8 | 归档 | 同族基准入口为 run_kg_benchmark_pilot.py，本文件为早期版本 |
| `report_kg_external_qa_pilot.py` | 103 | 10-30 | 1 | 归档 | 同族基准入口为 report_kg_external_qa_pilot_v2.py，本文件为早期版本 |
| `prepare_kg_external_qa_pilot.py` | 88 | 10-30 | 4 | 归档 | 同族基准入口为 prepare_kg_external_qa_pilot_v2.py，本文件为早期版本 |
| `review_kg_benchmark_metadata_v2.py` | 77 | 10-29 | 5 | 归档 | 同族基准入口为 review_kg_benchmark_metadata.py，本文件为早期版本 |
| `review_kg_benchmark_metadata_v4.py` | 61 | 10-29 | 2 | 归档 | 同族基准入口为 review_kg_benchmark_metadata.py，本文件为早期版本 |
| `freeze_kg_external_qa_pilot.py` | 46 | 10-30 | 1 | 归档 | 同族基准入口为 freeze_kg_external_qa_pilot_v2.py，本文件为早期版本 |
| `adjudicate_kg_benchmark_pilot_r4.py` | 30 | 10-28 | 0 | 归档 | 同族基准入口为 adjudicate_kg_benchmark_pilot.py，本文件为早期版本 |

## 四、B 类：一次性修复与迁移（16）

执行完毕的修复/迁移可归档；**部署或升级流程仍要跑的迁移必须留在原地**，否则新环境无法按文档初始化。

| 脚本 | 行数 | 最后修改 | 引用 | 建议 | 同族基准 / 依据 |
|---|---:|---|---:|---|---|
| `migrate_analysis_context.py` | 394 | 09-13 | 7 | 保留 | 部署或数据导入仍需执行 |
| `import_lechang_data.py` | 351 | 08-24 | 51 | 保留 | 部署或数据导入仍需执行 |
| `import_lechang_boundaries.py` | 337 | 09-21 | 0 | 保留 | 部署或数据导入仍需执行 |
| `backfill_versioned_model_results.py` | 279 | 10-13 | 0 | 归档 | 一次性修复/迁移，已执行完毕 |
| `migrate_canonical_parcel_management_fields.py` | 213 | 10-24 | 0 | 保留 | 部署或数据导入仍需执行 |
| `migrate_knowledge_graph_platform.py` | 203 | 10-24 | 8 | 保留 | 部署或数据导入仍需执行 |
| `migrate_kb_taxonomy.py` | 195 | 10-03 | 1 | 保留 | 部署或数据导入仍需执行 |
| `import_soil_data.py` | 146 | 08-24 | 2 | 保留 | 部署或数据导入仍需执行 |
| `migrate_chroma.py` | 122 | 07-13 | 1 | 归档 | 一次性修复/迁移，已执行完毕 |
| `migrate_chunk_content_hashes.py` | 121 | 10-26 | 6 | 保留 | 部署或数据导入仍需执行 |
| `migrate_literature_ingestion.py` | 101 | 10-22 | 2 | 保留 | 部署或数据导入仍需执行 |
| `migrate_add_model45_fields.py` | 95 | 08-24 | 2 | 归档 | 一次性修复/迁移，已执行完毕 |
| `migrate_add_message_agents.py` | 74 | 08-17 | 1 | 归档 | 一次性修复/迁移，已执行完毕 |
| `migrate_v04_to_age.py` | 53 | 10-24 | 1 | 保留 | 部署或数据导入仍需执行 |
| `backfill_knowledge_graph.py` | 48 | 10-24 | 1 | 归档 | 一次性修复/迁移，已执行完毕 |
| `migrate_research_evidence.py` | 41 | 10-30 | 3 | 保留 | 部署或数据导入仍需执行 |

## 五、C 类：纯审计与报告生成（79）

只读分析并生成 JSON/Markdown/HTML 报告，不写业务库。零引用 39 个归档；被文档当作证据入口引用的 40 个保留。

| 脚本 | 行数 | 最后修改 | 引用 | 建议 |
|---|---:|---|---:|---|
| `verify_thematic_models_db.py` | 496 | 08-19 | 13 | 保留 |
| `evaluate_minimal_kg_v03.py` | 495 | 10-15 | 0 | 归档 |
| `verify_agent_capabilities.py` | 289 | 09-05 | 20 | 保留 |
| `verify_model_data.py` | 262 | 08-16 | 0 | 归档 |
| `render_minimal_kg_html.py` | 221 | 10-17 | 0 | 归档 |
| `verify_dialogue.py` | 192 | 09-05 | 2 | 保留 |
| `check_knowledge_platform_components.py` | 185 | 10-23 | 2 | 保留 |
| `evaluate_kg_extraction_backend.py` | 177 | 10-26 | 7 | 保留 |
| `score_kg_corpus.py` | 173 | 10-27 | 11 | 保留 |
| `verify_live_e2e_database.py` | 160 | 09-05 | 0 | 归档 |
| `report_kg_benchmark_progress.py` | 151 | 10-29 | 1 | 保留 |
| `score_kg_external_relation_pilot.py` | 148 | 10-29 | 3 | 保留 |
| `verify_real_parcels.py` | 130 | 08-19 | 0 | 归档 |
| `report_kg_external_benchmarks.py` | 116 | 10-30 | 0 | 归档 |
| `report_kg_benchmark_metadata.py` | 112 | 10-29 | 2 | 保留 |
| `evaluate_v04_role_semantics.py` | 111 | 10-18 | 0 | 归档 |
| `verify_kg_annotator_controls.py` | 109 | 10-27 | 3 | 保留 |
| `report_kg_benchmark_pilot.py` | 105 | 10-29 | 6 | 保留 |
| `audit_quality_grade_consistency.py` | 105 | 10-11 | 0 | 归档 |
| `evaluate_kg_candidate_retention.py` | 103 | 10-27 | 1 | 保留 |
| `report_kg_external_qa_pilot_v2.py` | 103 | 10-30 | 2 | 保留 |
| `audit_kg_evaluation_dataset.py` | 103 | 10-27 | 0 | 归档 |
| `verify_kg_annotation_load.py` | 102 | 10-27 | 3 | 保留 |
| `render_kg_acceptance_inspection.py` | 98 | 10-28 | 0 | 归档 |
| `audit_kg_benchmark_identity.py` | 97 | 10-28 | 2 | 保留 |
| `verify_pg_init.py` | 94 | 08-17 | 25 | 保留 |
| `audit_kg_gold_sources.py` | 93 | 10-26 | 3 | 保留 |
| `audit_kg_external_qa_evidence.py` | 91 | 10-30 | 3 | 保留 |
| `inspect_kg_acceptance_review.py` | 91 | 10-28 | 2 | 保留 |
| `audit_minimal_kg_orphans.py` | 91 | 10-15 | 0 | 归档 |
| `evaluate_kg_candidate_pilot.py` | 91 | 10-27 | 0 | 归档 |
| `evaluate_kg_production_acceptance.py` | 88 | 10-18 | 0 | 归档 |
| `score_kg_external_calibration.py` | 85 | 10-30 | 3 | 保留 |
| `audit_knowledge_m2_integrity.py` | 83 | 10-30 | 1 | 保留 |
| `audit_kg_benchmark_reference_construction.py` | 82 | 10-29 | 2 | 保留 |
| `audit_kg_external_isolation.py` | 82 | 10-29 | 0 | 归档 |
| `report_kg_acceptance_v1.py` | 79 | 10-28 | 1 | 保留 |
| `score_kg_two_stage.py` | 79 | 10-27 | 0 | 归档 |
| `render_kg_benchmark_dataset_review.py` | 78 | 10-29 | 1 | 保留 |
| `score_kg_external_qa.py` | 78 | 10-30 | 8 | 保留 |
| `check_kg_corpus_conformance.py` | 76 | 10-27 | 0 | 归档 |
| `report_kg_quoted_selection_pilot.py` | 76 | 10-29 | 0 | 归档 |
| `summarize_kg_benchmark_arbitration.py` | 76 | 10-28 | 0 | 归档 |
| `score_kg_acceptance_v1.py` | 75 | 10-28 | 2 | 保留 |
| `compare_kg_source_gold.py` | 74 | 10-27 | 0 | 归档 |
| `score_kg_span_experiment.py` | 74 | 10-27 | 0 | 归档 |
| `diagnose_kg_model_capability.py` | 73 | 10-27 | 0 | 归档 |
| `report_kg_benchmark_dual_selector.py` | 71 | 10-29 | 0 | 归档 |
| `verify_kg_annotation_neutral_prompt.py` | 65 | 10-27 | 0 | 归档 |
| `report_kg_benchmark_reference_coverage.py` | 64 | 10-29 | 2 | 保留 |
| `verify_graph_store_dual_read.py` | 62 | 10-24 | 2 | 保留 |
| `verify_context_enhanced_routing.py` | 61 | 08-24 | 4 | 保留 |
| `summarize_kg_v4_r4_diagnostics.py` | 60 | 10-27 | 0 | 归档 |
| `report_kg_external_pilot_errors.py` | 57 | 10-29 | 0 | 归档 |
| `summarize_kg_v4_calibration.py` | 57 | 10-27 | 0 | 归档 |
| `audit_kg_verbatim_quote_counterfactual.py` | 56 | 10-29 | 0 | 归档 |
| `diagnose_kg_v4_r4_original_pilot.py` | 56 | 10-27 | 0 | 归档 |
| `verify_kg_corpus_artifacts.py` | 56 | 10-27 | 0 | 归档 |
| `audit_kg_reference_correlated_errors.py` | 53 | 10-29 | 2 | 保留 |
| `render_kg_external_qa_review.py` | 53 | 10-30 | 2 | 保留 |
| `score_kg_silver100.py` | 50 | 10-27 | 5 | 保留 |
| `audit_kg_external_qa_source_inputs.py` | 48 | 10-30 | 0 | 归档 |
| `audit_kg_external_qa_judge_stability.py` | 46 | 10-30 | 1 | 保留 |
| `summarize_kg_v4_r3.py` | 46 | 10-27 | 0 | 归档 |
| `verify_kg_benchmark_budget_v2.py` | 45 | 10-29 | 1 | 保留 |
| `verify_kg_silver100.py` | 45 | 10-27 | 1 | 保留 |
| `render_codex_kg_review.py` | 45 | 10-27 | 0 | 归档 |
| `evaluate_kg_capacity_run.py` | 43 | 10-24 | 1 | 保留 |
| `evaluate_kg_adapter_policy.py` | 42 | 10-24 | 1 | 保留 |
| `render_research_m1_review.py` | 40 | 10-30 | 0 | 归档 |
| `audit_kg_acceptance_isolation.py` | 39 | 10-27 | 1 | 保留 |
| `audit_kg_annotator_verification.py` | 38 | 10-27 | 0 | 归档 |
| `audit_kg_r4_fragment_failures.py` | 35 | 10-27 | 0 | 归档 |
| `inspect_postgres_parcels.py` | 28 | 09-05 | 0 | 归档 |
| `render_kg_benchmark_semantic_audit.py` | 27 | 10-29 | 0 | 归档 |
| `render_kg_silver100.py` | 25 | 10-27 | 0 | 归档 |
| `check_kg_v4_release_gates.py` | 23 | 10-27 | 1 | 保留 |
| `verify_kg_benchmark_membership.py` | 23 | 10-29 | 1 | 保留 |
| `verify_postgres_workflow_fix.py` | 20 | 09-05 | 0 | 归档 |

## 六、保留的 166 个（按前缀汇总）

完整清单见 `docs/scripts-classification-20261031.csv`：

| 前缀 | 数量 | 行数 |
|---|---:|---:|
| `run_*` | 23 | 3740 |
| `prepare_*` | 15 | 1429 |
| `validate_*` | 9 | 741 |
| `build_*` | 8 | 1444 |
| `export_*` | 7 | 909 |
| `adjudicate_*` | 7 | 681 |
| `rebuild_*` | 4 | 636 |
| `benchmark_*` | 4 | 356 |
| `review_*` | 4 | 333 |
| `measure_*` | 4 | 425 |
| `freeze_*` | 4 | 268 |
| `import_*` | 3 | 968 |
| `generate_*` | 3 | 307 |
| `annotate_*` | 3 | 335 |
| `graphrag_*` | 3 | 464 |
| `probe_*` | 3 | 245 |

## 七、执行归档前必须处理的三个问题

1. **根目录定位会失效**：273 个脚本中 **233 个**用 `Path(__file__).resolve().parents[1]` 定位仓库根目录。移入 `scripts/archive/` 后 `parents[1]` 会变成 `scripts/`，`sys.path` 与产物路径全部错位。归档必须同步改为 `parents[2]`，并抽样跑 `--help` 验证。
2. **文档路径引用**：A 类中 `run_kg_benchmark_pilot_r3/r4`（8/6 处）、`review_kg_benchmark_metadata_v2`（5 处）等仍被文档引用，归档会让命令示例失效，需同批更新；否则宁可保留。
3. **证据链可追溯性**：C 类脚本是冻结产物（`artifacts/knowledge_platform/**`）的生成入口，归档后要在对应结果文档补一行“生成脚本已移至 scripts/archive/”。

## 八、建议执行顺序（尚未执行）

1. 先归档 **B 类 5 个**：零业务影响、不涉及文档路径。
2. 再归档 **C 类 39 个**，同时加 `scripts/archive/README.md` 说明归档规则与根目录定位变更。
3. A 类 10 个先改文档引用再归档；`run_kg_benchmark_pilot_r2` 执行 `git rm`（历史可回溯）。
4. 每批单独提交，提交后跑 `py -3.12 -m pytest tests/test_retrieval_quality_r13.py -q`，并对任一归档脚本执行 `--help` 验证 `parents` 修正。

## 九、附件

- `docs/scripts-classification-20261031.csv`：273 行全量分类（行数、最后修改、引用次数、分类、建议、同族基准），可直接驱动批量 `git mv`。
