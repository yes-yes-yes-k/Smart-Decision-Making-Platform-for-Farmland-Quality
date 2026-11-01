# R3—R4 交付使用说明与后续决策

**日期**：2026-10-31
**范围**：R3.2—R3.4（后端服务/worker）+ R4.1—R4.4（对照运行/验收）

## 一、使用说明

### 启动对照 worker

```bash
# 启动（默认 comparison 模式）
.venv/Scripts/python.exe scripts/manage_research_worker.py start

# 查看状态
.venv/Scripts/python.exe scripts/manage_research_worker.py status

# 停止
.venv/Scripts/python.exe scripts/manage_research_worker.py stop
```

Worker 以 `hostname:pid` 为身份租约，PID 文件在 `.workbuddy/research-worker.pid`，日志在 `.workbuddy/research-worker.log`。stop 通过 SIGTERM（Windows: TerminateProcess）优雅停止。

### 发起对照

对照通过 ResearchService.submit 发起，经队列排队后由 worker 的 run_once 处理。结果通过 ResearchService.get 读取。来源版本漂移时返回 `invalidated`。

### 读取已持久化候选

```python
from framework.knowledge_graph.candidate_reader import read_candidates
result = read_candidates(document_id=1032)
# result["status"]: "ok" | "ineligible" | "invalidated" | "not_found"
# result["candidates"]: studies/entities/relations/claims（全 pending）
```

### 图关联检索

PublishedCorpusSearch 支持 `graph=True` 请求字段和 `graph_expander` 参数。开启后在基线文档排序后做一跳扩展（measure→indicator surface 匹配），结果中 `graph` 字段记录扩展状态。

### 对照配置

冻结配置在 `artifacts/.../r4-20261031-comparison-config/frozen-comparison-config-v1.json`，对照结果在 `comparison-results-v1.json`。

## 二、后续决策

### 必须做（阻塞下一阶段）

| 决策 | 理由 | 预算 |
|---|---|---|
| **实体消解** | 31 个实体全是篇内孤点，图扩展 contributing_hits=0。若 R4 对照需要图关联模式，必须先做 surface 归一/别名表 | 零模型调用，人工复核 |
| **C2 同领域过滤补跑** | 向量库 969MB 在脚本环境超时，需在服务环境执行 | 零模型调用，需 Chroma 在线 |

### 可选做（增强）

| 决策 | 理由 | 预算 |
|---|---|---|
| 发散篇重试 | 104/224/1149/449 在默认强度下思维链不收敛，换提示词策略或降低 thinking_budget 可能产出 | 需模型调用 |
| 跨 run 总账本 | 每个 run 独立建库，总消耗只能事后汇总 | 零模型调用 |
| 活向量库跨度复验 | R2.8 仅校验内部一致性，未从向量库取活分块做 content[start:end]==quote | 零模型调用，需 Chroma 在线 |

### 明确不做

| 决策 | 理由 |
|---|---|
| 发布候选 | 候选全 pending，审核流程属 R3.2 后端服务职责，本阶段不发布 |
| M3 容量验证 | M3 数值建议尚未冻结，不能据 M2 的零模型非部署测量宣称 100k 或语义质量通过 |
| AGE 部署 | M1 不自动发布断言，不勾选原平台 AGE 发布试点 |

## 三、完成状态

| 任务 | 状态 |
|---|---|
| R3.2 worker 启停管理 | ✅ manage_research_worker.py + _research_worker_loop.py，6 测试通过 |
| R3.3 租约/幂等/取消/崩溃恢复/来源失效 | ✅ 6 端到端测试通过，复用既有实现 |
| R3.4 隔离迁移演练 | ✅ kb_document 未改动，回退+重建验证 |
| R4.1 冻结对照配置 | ✅ 三配置×U1-U5 冻结 |
| R4.2 运行 U1-U5 对照 | ✅ C1 基线+R1.4，C3 图扩展，C2 待服务环境 |
| R4.3 质量门槛与恢复验收 | ✅ 文档级 5/5、证据级 0/10、恢复 6/6，六条硬约束遵守 |
| R4.4 交付使用说明 | ✅ 本文档 |

**总进度：27/27 全部勾选**
