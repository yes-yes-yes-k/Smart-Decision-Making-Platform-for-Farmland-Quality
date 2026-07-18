# Task 6 Implementer Brief — ComprehensiveImprovementAgent 清理

## 身份与上下文

你是 Comet 工作流 `add-model-6-fertility-ml` 的 Task 6 implementer subagent。

- **Change**: add-model-6-fertility-ml
- **分支**: `feature/20260718/add-model-6-fertility-ml`（已 checkout，HEAD=`d1bbf8b`）
- **TDD 模式**: tdd（但本任务是删除/清理，无新增功能；TDD RED-GREEN 不强制——只需验证删除前后测试状态）
- **审查模式**: standard
- **当前 Task**: 6（ComprehensiveImprovementAgent 清理）
- **plan 路径**: `docs/superpowers/plans/2026-07-18-add-model-6-fertility-ml.md` 的 Task 6 章节（line 1498-1569）
- **语言**: 中文（代码注释、commit message 用中文；技术名词保持英文）

## 前置已完成产物（无需重做）

- Task 4: `framework/agents/specialized/fertility_ml_agent.py`（FertilityMLAgent）已创建并在 `__init__.py` 中导出
- Task 5: `framework/agents/manager.py` 已不再 import `ComprehensiveImprovementAgent`（改为 import `FertilityMLAgent`）

## 你的任务（来自 plan Task 6）

### 文件

- Delete: `framework/agents/specialized/comprehensive_agent.py`
- Modify: `framework/agents/specialized/__init__.py`（移除 comprehensive 导入）
- Modify: `tests/test_agent_specialized.py`（移除 comprehensive 测试）

### 必须完成的 6 个 Step（来自 plan）

#### Step 1: 修改 `framework/agents/specialized/__init__.py`

**当前内容**（17 行）：

```python
from .stability_risk_agent import StabilityRiskAgent
from .potential_agent import PotentialAssessmentAgent
from .problem_agent import ProblemIdentificationAgent
from .acidification_agent import AcidificationRemediationAgent
from .organic_matter_agent import OrganicMatterAgent
from .comprehensive_agent import ComprehensiveImprovementAgent
from .fertility_ml_agent import FertilityMLAgent

__all__ = [
    "StabilityRiskAgent",
    "PotentialAssessmentAgent",
    "ProblemIdentificationAgent",
    "AcidificationRemediationAgent",
    "OrganicMatterAgent",
    "ComprehensiveImprovementAgent",
    "FertilityMLAgent",
]
```

**目标内容**（14 行，删除 comprehensive 相关 2 行 + 1 个 `__all__` 条目）：

```python
from .stability_risk_agent import StabilityRiskAgent
from .potential_agent import PotentialAssessmentAgent
from .problem_agent import ProblemIdentificationAgent
from .acidification_agent import AcidificationRemediationAgent
from .organic_matter_agent import OrganicMatterAgent
from .fertility_ml_agent import FertilityMLAgent

__all__ = [
    "StabilityRiskAgent",
    "PotentialAssessmentAgent",
    "ProblemIdentificationAgent",
    "AcidificationRemediationAgent",
    "OrganicMatterAgent",
    "FertilityMLAgent",
]
```

使用 Edit 工具：
- 删除 `from .comprehensive_agent import ComprehensiveImprovementAgent` 这一行
- 删除 `__all__` 列表中的 `"ComprehensiveImprovementAgent",` 这一行（含逗号）

#### Step 2: 修改 `tests/test_agent_specialized.py`

需要删除 3 个测试函数：
- `test_comprehensive_agent_execute`（约 line 176-187）
- `test_comprehensive_agent_answer_question_farmer_plot`（约 line 190-196）
- `test_comprehensive_agent_consumes_upstream_results`（约 line 199-213）

同时从 `if __name__ == "__main__":` 块中移除对这 3 个函数的调用（约 line 393-395）：
```python
test_comprehensive_agent_execute()
test_comprehensive_agent_answer_question_farmer_plot()
test_comprehensive_agent_consumes_upstream_results()
```

请先用 Read 工具读取 `tests/test_agent_specialized.py` 完整内容，识别确切行号，再用 Edit 工具删除。**保留其他测试函数不动**（包括 Task 4 新增的 6 个 FertilityMLAgent 测试）。

#### Step 3: 删除 `framework/agents/specialized/comprehensive_agent.py`

使用 DeleteFile 工具：
```
d:\17417\Documents\agent_culti_demo\framework\agents\specialized\comprehensive_agent.py
```

#### Step 4: 搜索仓库确认无残留引用

使用 Grep 工具搜索 `ComprehensiveImprovement` 关键词（在整个项目范围）：

```
pattern: "ComprehensiveImprovement"
path: d:\17417\Documents\agent_culti_demo
output_mode: content
-n: true
```

Expected: 输出"无匹配"或仅在 `openspec/changes/`、`docs/superpowers/`、`.comet/` 归档/规划文档中出现（这些文档不需修改）。

**如果发现代码或测试中有残留，逐一修复**。归档文档（`openspec/changes/add-model-6-fertility-ml/` 下的 proposal/design/tasks 等）的引用不需修改。

把 Grep 实际输出贴到 task-6-report.md 的"残留引用搜索"区。

#### Step 5: 验证模块导入正常

```bash
python -c "from framework.agents.specialized import FertilityMLAgent; print('OK')"
python -c "from framework.agents.manager import AgentManager; m=AgentManager(); print(m.agents['model-6'].__class__.__name__)"
```

Expected: 第一行输出 `OK`；第二行输出 `FertilityMLAgent`。

同时运行 AgentManager 测试套件确认无回归：

```bash
python -m pytest tests/test_agent_manager.py tests/test_agent_specialized.py -v
```

Expected: 所有测试 PASS（test_agent_manager.py 12 个 + test_agent_specialized.py 既有 5 个 agent 测试 + Task 4 新增 6 个 FertilityMLAgent 测试）。

把实际输出贴到 task-6-report.md。

#### Step 6: 提交

```bash
git add framework/agents/specialized/__init__.py framework/agents/specialized/comprehensive_agent.py tests/test_agent_specialized.py
git commit -m "refactor(agent): 删除 ComprehensiveImprovementAgent 占位实现，清理残留引用"
```

**注意**：`comprehensive_agent.py` 是被删除的文件，git 会自动检测删除。如果 `git add framework/agents/specialized/comprehensive_agent.py` 报错"file not found"，改用 `git add -A framework/agents/specialized/` 或 `git rm framework/agents/specialized/comprehensive_agent.py`。

## 关键约束

1. **不要修改其他文件**——本任务范围严格限定为：`__init__.py`、`test_agent_specialized.py`、删除 `comprehensive_agent.py`。
2. **不要修改 `manager.py`**——Task 5 已完成，不再触碰。
3. **不要修改归档/规划文档**（`openspec/changes/add-model-6-fertility-ml/` 下的 proposal/design/tasks 等）——这些是历史记录，残留引用是预期。
4. **不要新增任何文件或功能**——本任务是纯删除/清理。
5. **保留 `tests/test_agent_specialized.py` 中的其他测试**——尤其是 Task 4 新增的 6 个 FertilityMLAgent 测试。
6. **commit message 必须使用 plan 提供的原话**：`refactor(agent): 删除 ComprehensiveImprovementAgent 占位实现，清理残留引用`。

## 风险信号自报（implementer 完成后必须填写到 task-6-report.md）

请在 task-6-report.md 末尾填写下列自报（每项写"是/否 + 简短说明"）：

- 跨模块/跨子系统协调改动？
- 安全敏感面（认证、授权、加解密、SQL、外部输入处理、密钥/凭证）？
- 并发、锁、共享可变状态？
- 数据或 schema 迁移？
- 公共 API 契约或对外接口变更？
- 是否返回 DONE_WITH_CONCERNS？
- 单任务 diff 超过 200 行？

如任一为"是"，coordinator 将派发 reviewer subagent。

**预期风险信号**：
- 全部"否"（这是纯清理任务，删除占位实现，无新功能/API/并发/数据迁移）
- diff < 200 行（纯删除，预计 -100 行左右）

如果实际与预期不符，请在自报中说明。

## 交付物

1. 修改后的 `framework/agents/specialized/__init__.py`（移除 comprehensive 导入）
2. 修改后的 `tests/test_agent_specialized.py`（移除 3 个 comprehensive 测试 + 调用）
3. 删除的 `framework/agents/specialized/comprehensive_agent.py`
4. `openspec/changes/add-model-6-fertility-ml/.comet/task-6-report.md`（包含残留引用搜索、模块导入验证、测试结果、风险信号自报、commit hash）
5. Git commit `refactor(agent): 删除 ComprehensiveImprovementAgent 占位实现，清理残留引用`

## 验收标准

- [ ] `__init__.py` 移除了 comprehensive 导入和 `__all__` 条目
- [ ] `test_agent_specialized.py` 移除了 3 个 comprehensive 测试函数和 `if __name__` 调用
- [ ] `comprehensive_agent.py` 已删除
- [ ] Grep 搜索确认代码/测试中无残留引用（归档文档除外）
- [ ] 模块导入验证通过（输出 `OK` 和 `FertilityMLAgent`）
- [ ] AgentManager + specialized 测试套件全部 PASS
- [ ] commit 已创建（hash 记录到 report）
- [ ] 风险信号自报已填写
