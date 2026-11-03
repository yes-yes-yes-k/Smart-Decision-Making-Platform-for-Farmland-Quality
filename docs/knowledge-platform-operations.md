# 增量知识图谱架构、审核与运行手册

## 标准抽取与分块哈希迁移进展

本次标准格式修复使用严格 JSON Schema 输出，再由本地验证器检查实体类型、
关系枚举、端点及方向，最后转换为 GraphRAG 记录。最多两次模型纠正，每次重新
通过同一校验；不能通过的结果仍拒绝。失败调用也记录 token 用量。
文本标准 867、扫描标准 563、含有效 OCR 页的混合标准 636 均通过真实影子回归，
问题数均为 0；三份最终报告位于 `artifacts/knowledge_platform/live-shadow-standard-*-v*.json`，
分别为 text-867-v3、scan-563-v4、mixed-636-v2。相关统一回归 116 项通过。

哈希迁移采用独立 SQLite 审计库保存写入前的元数据、正文指纹、原文件哈希和
不可变计划；迁移只更新 `content_sha256`。原件变化、正文/页码变化、计数不符、
已有哈希冲突、撤回或其他元数据变化均拒绝写入。真正补写前锁定并重读来源文档，
模型、embedding 和 BM25 不参与该迁移。

```powershell
# 只读盘点：分页扫描元数据，不读取正文到模型
python scripts/inventory_chunk_content_hashes.py --output artifacts/knowledge_platform/chunk-hash-inventory-v1.json

# 先生成已验证计划；dry-run 不修改向量数据
python scripts/migrate_chunk_content_hashes.py --journal .tools/kg-hash-migration/pilot-v1.sqlite --document-id 563 --report artifacts/knowledge_platform/hash-plan.json

# 按既有计划补写；重复执行为零额外写入
python scripts/migrate_chunk_content_hashes.py --apply --journal .tools/kg-hash-migration/pilot-v1.sqlite --document-id 563 --report artifacts/knowledge_platform/hash-apply.json

# 逐篇验证后补写；每篇独立提交，拒绝项保留在报告
python scripts/migrate_chunk_content_hashes.py --rollout --limit 2000 --journal .tools/kg-hash-migration/pilot-v1.sqlite --report artifacts/knowledge_platform/hash-rollout-live-v1.json

# 恢复已准备但未完成的写入；中断于验证阶段的文档可重跑 --rollout
python scripts/migrate_chunk_content_hashes.py --apply --resume --journal .tools/kg-hash-migration/pilot-v1.sqlite --report artifacts/knowledge_platform/hash-resume.json

# 回滚仅恢复该计划改过的哈希字段；其他字段、正文、向量保持不变
python scripts/migrate_chunk_content_hashes.py --rollback --journal .tools/kg-hash-migration/pilot-v1.sqlite --document-id 563 --report artifacts/knowledge_platform/hash-rollback.json
```

首批 4 篇、19 个分块已补写，幂等重放额外写入 0。
启动全量前的只读盘点为 1,144 篇合格公共文献、107,505 个分块，其中尚缺
哈希 107,486 个（1,140 篇）。其他 4,663 个公共分块不属于本次合格文献快照，
不纳入迁移。全量迁移及最终只读核验现已完成：1,144 篇全部绑定，匹配分块
107,505 个，缺失、冲突、计数差异和迁移失败均为 0。
最终报告为 `chunk-hash-final-inventory-v1.json`；监听已记录 `coverage_verified` 并退出。
审计库应保留至回滚窗口结束；不要用另一数据库或向量目录复用同一审计库。
来源内容版本变化时使用新的迁移审计库，旧计划不会被覆盖。

暂停后恢复可使用 `--continue-report <暂停报告的保留副本>` 和 `--rollout`。
脚本会从该报告最后一个完成的文档之后继续，并保留旧的已完成列表及累计计数。
暂停时若有 prepared 计划，须先按前述 `--apply --resume` 恢复；不要跳过未完成计划。
本次恢复使用 `hash-rollout-paused-before-resume-v1.json`，断点文档为 715。

```powershell
python scripts/migrate_chunk_content_hashes.py --rollout --limit 2000 --continue-report artifacts/knowledge_platform/hash-rollout-paused-before-resume-v1.json --journal .tools/kg-hash-migration/pilot-v1.sqlite --report artifacts/knowledge_platform/hash-rollout-live-v1.json
python scripts/watch_chunk_hash_migration.py --report artifacts/knowledge_platform/hash-rollout-live-v1.json --events artifacts/knowledge_platform/hash-migration-monitor-v1.jsonl --final-inventory artifacts/knowledge_platform/chunk-hash-final-inventory-v1.json --poll-seconds 10
```

监听器每 10 秒检查进程及文档检查点，只在进度变化、异常、暂停或完成时写事件。
进程异常退出会记录 `process_exited_before_completion`；正常结束后自动分页核验
全量哈希覆盖。仅当 remaining_documents=0、哈希冲突=0 且计数差异为空时，
才记录 `coverage_verified`；否则记录 `coverage_requires_attention`，不提前宣称完成。

## 常驻抽取 worker（2026-10-25）

`scripts/run_knowledge_graph_worker.py` 是独立进程入口，支持持续轮询、
`--once` 单步消费和 `--check` 配置/运行时检查。启动不会自动迁移数据库；
先按现有迁移流程准备关系表。不要在每个 WSGI 进程中启动它。

```powershell
python -m venv .tools/graphrag-runtime
.tools/graphrag-runtime/Scripts/python.exe -m pip install -r deploy/graphrag-requirements.txt
$env:KG_GRAPHRAG_PYTHON = (Resolve-Path .tools/graphrag-runtime/Scripts/python.exe).Path
$env:KG_EXTRACTION_BASE_URL = 'http://127.0.0.1:8001/v1'
$env:KG_EXTRACTION_MODEL = '本机服务实际提供的模型名'
python scripts/run_knowledge_graph_worker.py --check
python scripts/run_knowledge_graph_worker.py --once --shadow
python scripts/run_knowledge_graph_worker.py --shadow
```

后端使用真正的 GraphRAG 3.3.0 `GraphExtractor` 和 OpenAI 兼容模型接口，
每个已发布分块独立抽取，保留原分块、页码和哈希，不重新切分正文。
模型必须输出显式关系类型，未知类型或错误方向不能降级为猜测关系。
默认仅允许 loopback 模型端点，禁用环境代理和 HTTP 重定向。
2026-10-25 用户已明确授权使用项目现有硅基流动模型抽取已审核公共文献。
部署时可设置 `KG_EXTRACTION_ALLOW_SILICONFLOW=true`、
`KG_EXTRACTION_BASE_URL=https://api.siliconflow.cn/v1` 和
`KG_EXTRACTION_MODEL=deepseek-ai/DeepSeek-V4-Flash`；该地址复用
`SILICONFLOW_API_KEY`，也可单独设置 `KG_EXTRACTION_API_KEY`。
其他外部目的地仍不允许。
本机服务未启动时不能宣称真实模型验收通过；mock 协议测试也不等同于金标质量评测。

API 与 worker 必须使用相同的 `KG_EXTRACTION_MODEL`、端点、token 上限和 Schema。
上传、管理员重跑和历史回填共用配置指纹；已有旧指纹任务会以
`backend_config_mismatch` 终止，避免用另一套模型结果冒充原任务。
无候选的旧任务可经管理员文档重跑接口更新指纹；已有候选的任务禁止改写指纹。

worker 先提交 outbox 到任务的转换，再一次领取一个任务；后台线程使用独立数据库
会话续租。worker 使用 Chroma 公共 API 按文档/哈希/公开状态有界读取，
不加载问答服务的全量 BM25 索引。模型调用期间不持有数据库事务，落库前重新锁定任务、验证租约并检查
文档当前发布状态和内容哈希。候选落库与任务完成同事务提交，异常全部回滚。
模型超时和临时运行失败指数退避，来源失效、配置不符、非法产物进入死信。
所有产物保持人工待审，不创建 release，不改变活动图。

`--lease-seconds` 默认 120，`--heartbeat-seconds` 默认 30，必须小于租约；
`--timeout` 默认 900 秒，是单文档抽取进程总时限。
SIGINT/SIGTERM/SIGBREAK 停止领取新任务，当前任务结束后退出。
日志及数据库失败字段仅保存稳定错误码，不保存模型异常原文。

Linux 可使用 `deploy/knowledge-graph-worker.service`，调整绝对目录后安装。
Windows 可用项目已有 NSSM 单独注册服务（先创建 `logs` 目录）：

```powershell
deploy/nssm.exe install AgentCultiGraphWorker "$PWD/.venv/Scripts/python.exe" "$PWD/scripts/run_knowledge_graph_worker.py" --shadow
deploy/nssm.exe set AgentCultiGraphWorker AppDirectory "$PWD"
deploy/nssm.exe set AgentCultiGraphWorker AppExit Default Restart
deploy/nssm.exe set AgentCultiGraphWorker AppRestartDelay 10000
deploy/nssm.exe set AgentCultiGraphWorker AppStdout "$PWD/logs/kg-worker.log"
deploy/nssm.exe set AgentCultiGraphWorker AppStderr "$PWD/logs/kg-worker-error.log"
deploy/nssm.exe start AgentCultiGraphWorker
```

环境变量放入项目 `.env`（不要在命令行传密钥）。多个进程使用不同 worker ID，
PostgreSQL `SKIP LOCKED` 领取任务；SQLite 只用于单 worker 的功能测试。
正式启用仍需完成真实金标、conformance、试点和既有生产门禁。
CLI 默认重新计算后端资格门禁，未通过时拒绝启动；`--shadow` 是显式的
候选抽取试点模式。服务模板暂带 `--shadow`，通过门禁后再移除。
`--check` 只报告运行时/配置可用和生产资格，不消费任务，也不保证远程模型在线。

真实模型影子试点可运行：

```powershell
python scripts/run_kg_live_shadow.py --list-sources
python scripts/run_kg_live_shadow.py --siliconflow --verify-legacy-chunks --document-id 1171 --output artifacts/knowledge_platform/live-shadow-v1.json
```

该工具只读正式文档及其公共分块，在 `.tools/kg-shadow/<run-id>/shadow.db`
中创建独立任务和候选，报告记录真实模型、版本、token 用量及计数。
它不修改正式关系数据库或活动图，也不代替 94 条金标评测。
部分历史分块尚无 `content_sha256`。`--verify-legacy-chunks` 仅用于影子试点：
先验证原文件 SHA-256，再重新解析并逐分块比对正文、页码和索引，全部一致后
才在内存中补足来源绑定。任何差异均拒绝，不回写正式向量库。
正常 worker 继续严格要求持久化分块哈希；正式历史回填前需重新索引或独立迁移。
更换模型配置后，历史回填须使用新的 `run_key`，避免混用不同配置的断点。

2026-10-25 验证结果：论文 1171（4 分块）真实影子试点完成，产生 5 个实体候选、
2 个关系候选和 2 条证据，问题数 0；token 用量 1,952。
报告为 `artifacts/knowledge_platform/live-shadow-paper-1171-v4.json`。
同次标准 563 试点仍被模型输出格式校验拒绝，不能视为标准语料验收通过。
相关回归 98 项通过，GraphRAG 隔离运行时检查和 pip check 通过。
当前未注册/启动系统常驻服务，未消费正式队列；生产资格继续为 false。

## 架构决策

关系数据库是治理事实源，保存任务、候选、证据状态、审核决定、release change、活动版本镜像与回滚审计。Apache AGE 只保存版本化活动知识视图；JSON 图保留为只读回退。抽取后端只能产生候选，不能直写 AGE。生产变更必须依次通过证据校验、人工审核、发布门禁和原子活动版本切换。

文献完成事务只写 outbox，图谱失败不得回滚文献和向量索引。图查询只返回证据定位符，正文必须回到 Chroma 并使用普通 RAG 的公开/所有者/领域过滤。

## 审核运行

`domain_reviewer` 可消歧并审核实体、关系、claim 与证据；只有 `admin` 可重试任务、发布和回滚。每个决定必须包含理由和唯一幂等键。关系批准顺序为端点实体、有效证据、关系。抽取置信度不能替代审核决定。

发布前检查 schema 兼容、端点、方向、有效证据、重复、孤点、审核覆盖、代表性查询和变更校验和。发布预览不改变生产状态。JSON/Parquet 审计导出由独立 worker 处理。

## 容量规划与基准

容量目标在 `benchmarks/knowledge_platform/target-v1.json`：100k 文档、100k 实体、1m 证据、100k 任务。使用隔离命名空间生成：

```powershell
python scripts/generate_kg_synthetic.py --output-root benchmarks/runs `
  --namespace synthetic-capacity-v1
```

清理只允许 marker 和命名空间均匹配的直接子目录：

```powershell
python scripts/generate_kg_synthetic.py --output-root benchmarks/runs `
  --namespace synthetic-capacity-v1 --cleanup
```

完整基准必须记录硬件、操作系统、PostgreSQL/AGE 版本、schema、索引、worker 并发、数据分布和起止时间。不得用 SQLite 或缩小数据量代替 AGE 容量验收。

完整执行顺序如下。所有 DSN 必须指向可清理的隔离 benchmark 数据库；任务基准还会强制校验数据库名包含 `benchmark`。

```powershell
# 1. 生成文档、规范实体、合法方向关系、完整证据与任务数据
python scripts/generate_kg_synthetic.py --output-root benchmarks/runs `
  --namespace synthetic-capacity-v1

# 2. 流式装载 AGE；证据按关系分组，不在内存保留 1m 行
python scripts/load_kg_synthetic_age.py --dsn $env:KG_BENCHMARK_DSN `
  --dataset benchmarks/runs/synthetic-capacity-v1 `
  --release-id synthetic-capacity-release-1 --release-sequence 1 `
  --rollback-release-id synthetic-capacity-release-0 --activate `
  --report artifacts/knowledge_platform/capacity-load-v1.json

# 3. 实测 1/2 跳 top-100 P95，并执行显式激活和回滚
python scripts/benchmark_kg_age_runtime.py --dsn $env:KG_BENCHMARK_DSN `
  --entity-id synthetic-capacity-v1:entity:0 `
  --entity-id synthetic-capacity-v1:entity:1 --rounds 25 `
  --target-release synthetic-capacity-release-1 `
  --rollback-release synthetic-capacity-release-0 --apply-release-switch `
  --output artifacts/knowledge_platform/capacity-runtime-v1.json

# 4. 在独立关系数据库跑 100k 任务、全量重复投递及 worker 重启
python scripts/benchmark_kg_jobs.py --dsn $env:KG_JOB_BENCHMARK_DSN `
  --namespace synthetic-capacity-jobs-v1 --apply `
  --output artifacts/knowledge_platform/capacity-jobs-v1.json

# 5. 主动注入图故障，验证当前 Chroma 仍返回证据
python scripts/probe_kg_vector_resilience.py `
  --query "土壤酸化改良措施" --query "耕地有机质不足如何治理" `
  --output artifacts/knowledge_platform/vector-resilience-v1.json
```

备份必须恢复到另一隔离数据库，并通过活动 release、实体/关系/证据计数和校验和验证：

```powershell
python scripts/age_backup_restore.py backup `
  --dsn $env:KG_BENCHMARK_DSN --database-name kg_capacity_benchmark `
  --graph-name cultivated_land_kg_capacity `
  --output backups/database/kg-capacity.dump

python scripts/age_backup_restore.py restore `
  --dsn $env:KG_RESTORE_BENCHMARK_DSN `
  --dump backups/database/kg-capacity.dump `
  --manifest backups/database/kg-capacity.dump.manifest.json `
  --graph-name cultivated_land_kg_capacity --apply `
  --report artifacts/knowledge_platform/backup-restore-v1.json
```

复制 `benchmarks/knowledge_platform/run-metadata-template-v1.json`，填写真实硬件、版本、索引、并发和起止时间；模板中的 `null` 不会通过门禁。最后组合五份独立证据：

```powershell
python scripts/assemble_kg_capacity_report.py --run-id synthetic-full-v1 `
  --metadata artifacts/knowledge_platform/run-metadata-v1.json `
  --load-report artifacts/knowledge_platform/capacity-load-v1.json `
  --runtime-report artifacts/knowledge_platform/capacity-runtime-v1.json `
  --job-report artifacts/knowledge_platform/capacity-jobs-v1.json `
  --vector-report artifacts/knowledge_platform/vector-resilience-v1.json `
  --backup-report artifacts/knowledge_platform/backup-restore-v1.json `
  --output artifacts/knowledge_platform/capacity-run-v1.json
```

基准执行器产出的 JSON 报告必须再经过机器门禁；只有退出码为 0 且 `eligible_for_age_primary=true` 才能进入 AGE 主读变更审批：

```powershell
python scripts/evaluate_kg_capacity_run.py `
  --run benchmarks/runs/synthetic-capacity-v1/run-report.json `
  --output artifacts/knowledge_platform/capacity-acceptance-v1.json
```

门禁会同时验证完整规模、必填运行元数据、1–2 跳 top-100 P95、激活/回滚时限、向量持续可用、单文档无全图扫描、重复投递与 worker 重启下的任务计数守恒、零重复业务生效和备份恢复。缺失字段按失败处理。

## 指标与告警

`GET /api/v1/observability/knowledge-graph/metrics` 返回脱敏的任务吞吐/失败率、过期租约、待审风险、最老待审时长、无证据关系、活动 release、发布差异与最近回滚。告警码为 `pending_jobs_high`、`job_failure_rate_high`、`expired_leases_present`、`review_backlog_high`、`evidence_free_relations_present`。不得包含正文、路径、模型错误原文或用户身份。

## 事故处置与回滚

1. 暂停 outbox/抽取 worker，保持文献与向量检索运行。
2. 设置 `KG_ROLLOUT_MODE=off` 关闭图增强；AGE 异常时设置 `KG_GRAPH_STORE=json`。
3. 调用 `/api/v1/knowledge-graph/releases/{release_id}/rollback`，提交原因和幂等键；目标必须兼容且已验证。
4. 验证活动 release、1–2 跳查询和向量回退，目标为 60 秒内切换。
5. 保留失败 release、候选、审核和回滚审计。健康检查失败时服务会尝试恢复先前活动 release。
6. AGE 恢复后先做 JSON/AGE 双读与备份恢复验证，再恢复 canary，禁止直接全量切主读。

## 环境门禁

GraphRAG/OpenSPG 生产启用必须具备精确版本、相同 94 条金标报告、conformance 通过、质量/吞吐/成本记录和 shadow 结果。缺运行时或模型凭据时报告 `environment_blocked`，不得用金标回放冒充真实抽取评测。

当前策略在 `governance/knowledge-platform/adapter-policy-v1.json`，状态保持 `pending_evaluation`。真实预测评测和 conformance 报告齐备并经人工批准后，运行：

```powershell
python scripts/evaluate_kg_adapter_policy.py `
  --policy governance/knowledge-platform/adapter-policy-v1.json `
  --evaluation artifacts/knowledge_platform/graphrag-evaluation-v1.json `
  --evaluation artifacts/knowledge_platform/openspg-evaluation-v1.json `
  --conformance artifacts/knowledge_platform/graphrag-conformance-v1.json `
  --conformance artifacts/knowledge_platform/openspg-conformance-v1.json `
  --output artifacts/knowledge_platform/adapter-policy-status-v1.json
```

只有退出码为 0 且 `production_ready=true` 才允许写入首选/回退运行配置。金标自身回放、版本不匹配、缺 conformance 或仅有自动分数但无人审批都会被拒绝。
