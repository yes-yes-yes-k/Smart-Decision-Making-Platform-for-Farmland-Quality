# Task 8 Implementer Brief — 端到端集成验证

## 上下文

- **Change**: `add-model-6-fertility-ml`
- **Phase**: build (subagent-driven-development, tdd_mode=tdd, review_mode=standard)
- **Branch**: `feature/20260718/add-model-6-fertility-ml`
- **BASE（HEAD）**: `00ef255`（Task 7 checkoff）
- **Plan**: `docs/superpowers/plans/2026-07-18-add-model-6-fertility-ml.md` Task 8（line 1658-1775）
- **Tasks.md**: `openspec/changes/add-model-6-fertility-ml/tasks.md` 8.1-8.6

## TDD 硬约束

Task 8 是纯验证任务，无代码变更。TDD 在此任务的体现为：**每个验证步骤必须留下输出证据**（命令输出片段），不能仅口头声明 PASS。

## 任务目标

通过端到端集成验证，确认 Task 1-7 的实现产物在生产环境配置下正常工作。无代码变更，仅运行验证命令并记录输出。

## 实施步骤（来自 plan Task 8）

### Step 1: 验证 AgentManager 正常初始化

```bash
python -c "from framework.agents.manager import agent_manager; print(agent_manager.agents['model-6'].__class__.__name__)"
```

Expected: 输出 `FertilityMLAgent`，无 ImportError。

### Step 2: 验证 model_6_execution 真实预测

```bash
python -c "
from framework.domain.other_models.model_6 import model_6_execution
result = model_6_execution({'pH': 6.5, 'SOCbe': 15.0, 'TN': 1.2, 'TP': 0.8, 'TK': 25.0, 'AP': 30.0, 'AK': 80.0, 'Gap': 5.0, 'Dose': 200.0, 'Fertilizer type': 1})
print('status:', result['status'])
print('soc_prediction:', result['soc_prediction'])
print('dose_prediction:', result['dose_prediction'])
print('soc_confidence:', result['soc_confidence'])
print('dose_confidence:', result['dose_confidence'])
"
```

Expected: `status: success`，soc_prediction 与 dose_prediction 为 float 值，confidences 分别为 0.91 和 0.47（dose_confidence 可能略有差异但应接近 0.47）。

### Step 3: 验证非肥力问题跳过 model-6

```bash
python -c "
from framework.agents.manager import AgentManager
mgr = AgentManager()
result = mgr.process('我的田pH如何？', {})
m6 = result['data']['details']['model-6']
print('model-6 status:', m6.get('status'))
print('model-6 reason:', m6.get('reason'))
"
```

Expected: `model-6 status: skipped`，`model-6 reason: question_not_related`。

### Step 4: 验证肥力问题触发 model-6 ML 预测

```bash
python -c "
from framework.agents.manager import AgentManager
mgr = AgentManager()
result = mgr.process('我的田肥力怎么样？', {'data': {'pH': 6.5, 'SOCbe': 15.0, 'TN': 1.2, 'TP': 0.8, 'TK': 25.0, 'AP': 30.0, 'AK': 80.0, 'Gap': 5.0, 'Dose': 200.0, 'Fertilizer type': 1}})
m6 = result['data']['details']['model-6']
print('answer:', m6.get('answer', '')[:100])
print('has evidence:', len(m6.get('evidence', [])) > 0)
"
```

Expected: answer 包含 "SOC" 和 "Dose" 预测值，evidence 非空。

### Step 5: 验证 fallback 降级（临时重命名模型文件）

```powershell
Rename-Item data\fertility\models\soc_etr_model.joblib soc_etr_model.joblib.bak
```

```bash
python -c "
from framework.domain.other_models import model_6
model_6._SOC_LOAD_FAILED = False
model_6._DOSE_LOAD_FAILED = False
model_6._SOC_MODEL = None
model_6._DOSE_MODEL = None
result = model_6.model_6_execution({'pH': 6.5})
print('status:', result['status'])
print('fallback_reason:', result.get('fallback_reason'))
print('soc_confidence:', result['soc_confidence'])
"
```

Expected: `status: fallback`，`fallback_reason: model_file_missing`，`soc_confidence: 0.3`。

**重要**：验证完成后必须恢复文件：
```powershell
Rename-Item data\fertility\models\soc_etr_model.joblib.bak soc_etr_model.joblib
```

并在恢复后重新运行 Step 2 确认模型恢复正常。

### Step 6: 启动开发服务器验证 /api/chat 接口（可选）

如服务器可用，启动开发服务器并验证 `/api/chat` 接口：

```bash
python start_http_server.py
```

在另一个终端：
```bash
curl -X POST http://localhost:5000/api/auth/login -H "Content-Type: application/json" -d "{\"username\":\"admin\",\"password\":\"admin\"}"
```

用返回的 token 调用：
```bash
curl -X POST http://localhost:5000/api/chat -H "Content-Type: application/json" -H "Authorization: Bearer <token>" -d "{\"message\":\"我的田肥力怎么样？\"}"
```

Expected: 响应 `data.details["model-6"]` 包含 ML 预测结果（非 `diagnosis`/`zoning_suggestions` 旧结构）。

**如果服务器启动失败或环境限制无法启动**，在报告中标注 Step 6 SKIP 并说明原因，不阻塞任务完成。

### Step 7: 最终全量测试确认

```bash
python -m pytest tests/ -v
```

Expected: 所有测试 PASS 或 SKIP（集成测试），无 FAIL。

注意：Task 7 implementer 已运行过全量测试套件，105 PASS / 0 FAIL（排除 2 个 pre-existing 集合错误：test_interfaces.py、test_thematic_models.py 缺 ai_culti_demo 顶级包）。本步骤重新运行确认。

## 边界与约束

- **禁止代码变更**：Task 8 是纯验证任务。如发现 bug 需要修改代码，报告 DONE_WITH_CONCERNS 并说明问题，不直接修复。
- **允许的文件操作**：仅 Step 5 的临时重命名 `.joblib` 文件（必须恢复）
- **服务器启动失败处理**：Step 6 是可选步骤，如环境限制无法启动服务器，标注 SKIP 并继续后续步骤

## 风险信号自报（implementer 必须在报告中回答）

1. 跨模块/跨子系统协调改动？
2. 安全敏感面（认证/授权/加解密/SQL/外部输入/密钥）？
3. 并发/锁/共享可变状态？
4. 数据或 schema 迁移？
5. 公共 API 契约或对外接口变更？
6. 是否返回 DONE_WITH_CONCERNS？
7. 单任务 diff 超过 200 行？

（纯验证任务，预期全部"否"。如发现需要代码修改，第 6 项应为"是"。）

## 完成标准

- Step 1-5 全部 PASS（有输出证据）
- Step 6 PASS 或 SKIP（如 SKIP 需说明原因）
- Step 7 全量测试 PASS（0 FAIL，允许 SKIP）
- 风险信号自报全部"否"或第 6 项"是"（如发现 bug）
- **不创建新 commit**（纯验证任务，无代码变更）

## 报告格式

完成后写入 `openspec/changes/add-model-6-fertility-ml/.comet/task-8-report.md`，包含：
- 每个步骤的命令输出片段（关键输出，不需要全部输出）
- 验证结果（PASS/FAIL/SKIP）
- 风险信号自报（7 项）
- 任何 Minor finding 或 concern
- Step 5 文件恢复确认
