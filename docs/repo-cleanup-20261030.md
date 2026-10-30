# 工作区整理与分功能提交记录（2026-10-30）

范围：`D:/17417/Documents/agent_culti_demo`，基线 `7ec1d28`。
结果：**636 个文件、+62,394 / −556 行；`git status` 已清空。** 本批提交见 `git log 7ec1d28..HEAD`，下表按依赖顺序列出主体提交（本记录自身的后续修订未单列）。

## 一、提交清单（按依赖顺序）

| # | 提交 | 类型 | 文件数 | 增/删 | 内容 |
| --- | --- | --- | ---: | --- | --- |
| 1 | `0c1ea77` | chore | 9 | +235 / −1 | 忽略本地数据目录；部署模板补 AGE、CAJ、文献入库、抽取 worker 配置 |
| 2 | `80bb335` | feat(kg) | 32 | +6,591 / −2 | 图谱平台：持久模型、候选/Claim/证据生命周期、review、发布回滚、AGE 迁移、双读、适配器与 schema |
| 3 | `4ae0b48` | feat(kg) | 46 | +2,919 | 抽取基准与金标：选择协议、span/两阶段、参考编译、成员门禁、外部基准与 QA 打分、conformance |
| 4 | `6085250` | feat(kg) | 17 | +1,714 | 验收、容量、恢复测量：acceptance_*、capacity_*、job/operational/resilience probe |
| 5 | `badcc32` | feat(research) | 8 | +1,162 | 文献证据闭环：研究记录/来源/契约 v2/存储，已发布语料检索与条件分离，证据路由 |
| 6 | `1633ffa` | feat(retrieval) | 6 | +1,038 / −264 | 混合检索：持久化词法索引、BM25 重写、Chroma 同步、引用目录与格式化 |
| 7 | `1449f25` | feat(literature) | 9 | +2,554 / −93 | 文献批量入库、PDF 版式映射、CAJ 转换、worker 租约与重试、管理接口 |
| 8 | `63c6fed` | feat(models) | 16 | +1,161 / −101 | 版本化模型结果（数据/Agent 版本、参数）、计算修正、公共字段标签 |
| 9 | `d80ee80` | test | 130 | +9,140 / −35 | 平台、抽取、验收、容量、检索质量 R1.3、文献入库、版本化结果测试 |
| 10 | `ae58407` | docs | 61 | +4,608 / −19 | M0–M3 报告、检索质量 R0/R1.1/R1.2 结果、图谱评测与运维文档、ADR 0001–0004 |
| 11 | `d343866` | chore(openspec) | 61 | +4,037 / −24 | 归档 3 个已完成变更；新增 enable-literature-evidence-comparison、incremental KG、benchmark 重建；同步 4 份能力规格 |
| 12 | `63e0dda` | chore(scripts) | 235 | +24,196 / −17 | 入库、迁移、回填、基准、金标、外部 QA、验收、检索质量探针脚本；benchmark 目标与治理证据 |
| 13 | `c307546` | chore(kg) | 4 | +2,895 | 冻结抽取金标 v1/v2 及清单 |
| 14 | `ca8ea5a` | docs | 1 | +96 | 本整理记录 |
| 15 | `2a35605` | docs(research) | 2 | +48 / −1 | R1.3 结果文档与任务勾选（进度 12/27 → 13/27） |

> 第 1 条之前的基线为 `7ec1d28`；15 条提交合计 636 文件。

## 二、已删除（移入回收目录，可恢复）

回收位置：`D:/17417/Documents/_repo_trash_20261030/`（14 MB），确认无误后可整体删除。

| 文件 | 判断依据 |
| --- | --- |
| `tools/create_context_persistence_report.py` | 一次性 Word 报告生成器，输出路径硬编码为 `D:\...\outputs\上下文持久化问题解决方案汇报.docx`，全文无任何代码/文档引用 |
| `outputs/literature_execute_20261022.json` | 一次性文献批处理执行日志 |
| `outputs/literature_preflight_20261022.json` | 同上，preflight 首版 |
| `outputs/literature_preflight_20261022_v2.json` | 同上，被 `_final` 取代 |
| `outputs/literature_preflight_20261022_final.json` | 同上，最终版仍无引用 |
| `outputs/literature_resume_20261022.json` | 断点续跑日志 |
| `outputs/literature_resume_20261022_final.json` | 断点续跑日志 |
| `outputs/literature_resume_20261023_retry.json` | 重试日志 |
| `outputs/literature_resume_batch128_20261022.json` | 并发调参日志 |
| `outputs/literature_resume_concurrency_fix_20261022.json` | 并发修复日志 |
| `outputs/literature_resume_final_20261022.json` | 断点续跑日志 |
| `outputs/literature_manifest_with_standard_metadata_20261023.jsonl` | 一次性清单导出，正式清单已由 `generate_literature_manifest.py` + 批次表承接 |
| `outputs/literature_validation_20261023.json` | 一次性校验输出 |

保留未动：`outputs/repaired_validation_candidate.pdf`、`outputs/region_audits/`。

## 三、保留在本地但不入库（新增忽略规则）

| 目录 | 体积 | 说明 |
| --- | ---: | --- |
| `artifacts/knowledge_platform/` | 4.8 GB | 运行证据（chroma 克隆 2.1 GB、检索对照 1.9 GB、外部基准 460 MB、抽取基准 303 MB 等）。目录内 9,049 个文件，含 3 个近 1 GB 的 `chroma.sqlite3`，不适合入库 |
| `backups/` | 1.0 GB | 数据库与知识库备份 |
| `outputs/` | 1.5 MB | 一次性运行输出（已清理 12 个文献日志） |

结论：证据留在开发机，文档（`docs/knowledge-platform-operations.md` 等）记录结论与产物路径；如需长期留存，应走对象存储或制品库，不再进 Git。

## 四、未删除、待确认的候选

以下脚本在 `docs/ openspec/ tests/ framework/ scripts/` 内无任何引用，但可能用于复现已冻结产物，故保留待确认：

| 脚本 | 用途推断 | 风险 |
| --- | --- | --- |
| `scripts/build_minimal_knowledge_graph.py` | 早期 v0.1/v0.2 图谱构建，已被 `build_minimal_kg_v03/v04.py` 取代 | 删除后无法复现 v0.2 图谱 |
| `scripts/apply_minimal_kg_review.py` | 一次性把人工复核结果写回图谱 | 复核流程已由 review 平台承接 |
| `scripts/evaluate_graph_vs_vector.py` | 早期图/向量对比实验 | 已被 R1.2 对照取代 |
| `scripts/debug_llm_routing.py` | 路由调试脚本 | 已有路由测试套件 |
| `scripts/clean_discrete_values.py` | 一次性离散值清洗 | 已执行完毕 |
| `scripts/correct_parcel_area_codes.py` | 一次性地块面积编码修正 | 已执行完毕 |
| `scripts/fix_postgres_workflow_data.py` | 一次性 PG 工作流数据修复 | 已由迁移脚本承接 |
| `scripts/check_age_graph.py` | AGE 连通性探针 | 已被 `verify_graph_store_dual_read.py` 与健康接口承接 |

如需进一步精简，确认后可按上表批量移入回收目录。

## 五、验证

| 项目 | 命令/方式 | 结果 |
| --- | --- | --- |
| 工作区状态 | `git status --porcelain` | 0 条 |
| 检索质量 R1.3 | `pytest tests/test_retrieval_quality_r13.py tests/test_retrieval_quality_policy.py` | 20 通过 |
| 证据闭环 + 图谱任务 + 版本化结果 | `pytest tests/test_research_evidence.py tests/test_knowledge_graph_jobs.py tests/test_versioned_model_results.py` | 61 通过（含前两项） |
| 基线对照 | `git diff 7ec1d28 --stat` | 636 files, +62,394 / −556 |

未执行：全量 1,147 项回归（需数据库与外部服务），以及 R1.4 真实接口基线。

## 六、注意事项

1. 本次提交位于 `D:/17417/Documents/agent_culti_demo`，分支 `codex/parcel-field-canonicalization-source`；`C:/Users/17417/WorkBuddy/Worktrees/...` 那个 worktree 仍停在 `7ec1d28`，需要合并或重新检出才能看到这些提交。
2. `.git` 体积已达 3.6 GB，来自更早历史中的大文件，本次未处理；若要瘦身需单独做 `filter-repo` 并全体重新克隆。
3. `artifacts/knowledge_platform/` 虽已忽略，但仍是本机唯一证据副本，清理磁盘前请先归档。
