# Task 5 Report — AgentManager 集成与按需过滤

## Status

**DONE_WITH_CONCERNS**

brief 内部存在不可调和的测试断言矛盾（详见"Concerns"段），导致 GREEN 阶段 7 个新测试中 1 个（`test_topological_sort_model6_no_dep`）无法通过；既有 `test_manager_topological_sort_farmer` 反而未按 brief 预期 FAIL。已严格遵守 brief 的"按 5 处必改点逐一精准修改"原则，未做计划外修改，如实报告矛盾以供 coordinator 决策。

## Commits

- `175e7e3` — feat(manager): AgentManager 集成 FertilityMLAgent 并新增按需过滤
  - 2 files changed, 101 insertions(+), 4 deletions(-)
  - Files: `framework/agents/manager.py` (修改)、`tests/test_agent_manager.py` (修改)
  - 分支：`feature/20260718/add-model-6-fertility-ml`（BASE `af6fb2e`）
  - 注：按 brief Step 6 字面要求，仅 add 这两个文件；`task-5-report.md` 与 `task-5-brief.md` 不在本次 commit（与 Task 4 实现模式一致，留给 coordinator 后续 checkoff commit）

## 测试摘要

### RED 阶段（Step 1-2）

- 操作：在 `tests/test_agent_manager.py` 第 62 行（`if __name__ == "__main__":` 之前）按 brief 逐字插入 7 个测试函数
  - `test_should_execute_model6_fertility_question`
  - `test_should_skip_model6_non_fertility_question`
  - `test_should_execute_other_agents_always`
  - `test_model6_dependencies_empty`
  - `test_topological_sort_model6_no_dep`
  - `test_model6_skipped_in_details_for_non_fertility`
  - `test_manager_loads_fertility_ml_agent`
- 命令：`python -m pytest tests/test_agent_manager.py -v -k "should_execute or should_skip or dependencies_empty or topological_sort_model6 or skipped_in_details or loads_fertility"`
- 结果：**6 failed, 1 passed, 5 deselected**（与 brief Expected "FAIL" 一致；其中 `test_model6_skipped_in_details_for_non_fertility` 在 BASE 代码下因 `simulated is True` 已成立而 PASS，属偶然通过，但 RED 总体失败达到 TDD RED 阈值）

#### RED 实际输出

```
============================= test session starts =============================
platform win32 -- Python 3.12.1, pytest-9.1.1, pluggy-1.6.0 -- D:\miniconda3\python.exe
cachedir: .pytest_cache
rootdir: D:\17417\Documents\agent_culti_demo
configfile: pyproject.toml
plugins: anyio-4.13.0, langsmith-0.10.2
collected 12 items / 5 deselected / 7 selected                                 

tests/test_agent_manager.py::test_should_execute_model6_fertility_question FAILED [ 14%]
tests/test_agent_manager.py::test_should_skip_model6_non_fertility_question FAILED [ 28%]
tests/test_agent_manager.py::test_should_execute_other_agents_always FAILED [ 42%]
tests/test_agent_manager.py::test_model6_dependencies_empty FAILED       [ 57%]
tests/test_agent_manager.py::test_topological_sort_model6_no_dep FAILED  [ 71%]
tests/test_agent_manager.py::test_model6_skipped_in_details_for_non_fertility PASSED [ 85%]
tests/test_agent_manager.py::test_manager_loads_fertility_ml_agent FAILED [100%]

================================== FAILURES =================================== 
________________ test_should_execute_model6_fertility_question ________________ 

    def test_should_execute_model6_fertility_question():
        """问'肥力' → _should_execute_agent('model-6', ...) = True"""
>       from framework.agents.manager import AgentManager, FERTILITY_KEYWORDS   
E       ImportError: cannot import name 'FERTILITY_KEYWORDS' from 'framework.agents.manager' (D:\17417\Documents\agent_culti_demo\framework\agents\manager.py)  

tests\test_agent_manager.py:65: ImportError
_______________ test_should_skip_model6_non_fertility_question ________________ 

    def test_should_skip_model6_non_fertility_question():
        """问'pH' → _should_execute_agent('model-6', ...) = False"""
        from framework.agents.manager import AgentManager
        mgr = AgentManager()
>       assert mgr._should_execute_agent("model-6", "我的田pH如何？") is False  
               ^^^^^^^^^^^^^^^^^^^^^^^^^
E       AttributeError: 'AgentManager' object has no attribute '_should_execute_agent'

tests\test_agent_manager.py:77: AttributeError
___________________ test_should_execute_other_agents_always ___________________ 

    def test_should_execute_other_agents_always():
        """非 model-6 的 agent 始终执行"""
        from framework.agents.manager import AgentManager
        mgr = AgentManager()
>       assert mgr._should_execute_agent("model-4", "任何问题") is True
               ^^^^^^^^^^^^^^^^^^^^^^^^^
E       AttributeError: 'AgentManager' object has no attribute '_should_execute_agent'

tests\test_agent_manager.py:86: AttributeError
_______________________ test_model6_dependencies_empty ________________________ 

    def test_model6_dependencies_empty():
        """model-6 dependencies=[]，不依赖 model-4/5"""
        from framework.agents.manager import AgentManager
        mgr = AgentManager()
>       assert mgr.agents["model-6"].dependencies == []
E       AssertionError: assert ['model-4', 'model-5'] == []
E
E         Left contains 2 more items, first extra item: 'model-4'
E
E         Full diff:
E         - []
E         + [
E         +     'model-4',
E         +     'model-5',
E         + ]

tests\test_agent_manager.py:95: AssertionError
_____________________ test_topological_sort_model6_no_dep _____________________ 

    def test_topological_sort_model6_no_dep():
        """model-6 dependencies=[]，拓扑排序不强制 model-6 在最后"""
        from framework.agents.manager import AgentManager
        mgr = AgentManager()
        ordered = mgr._topological_sort(["model-4", "model-5", "model-6"])
        assert set(ordered) == {"model-4", "model-5", "model-6"}
        # model-6 不再依赖 model-4/5，不强制排最后
>       assert ordered[-1] != "model-6" or len(ordered) == 1
E       AssertionError: assert ('model-6' != 'model-6' or 3 == 1)
E        +  where 3 = len(['model-4', 'model-5', 'model-6'])

tests\test_agent_manager.py:106: AssertionError
____________________ test_manager_loads_fertility_ml_agent ____________________ 

    def test_manager_loads_fertility_ml_agent():
        """_load_real_agents 加载 FertilityMLAgent"""
        from framework.agents.manager import AgentManager
        mgr = AgentManager()
        agent = mgr.agents["model-6"]
>       assert agent.__class__.__name__ == "FertilityMLAgent"
E       AssertionError: assert 'Comprehensiv...rovementAgent' == 'FertilityMLAgent'
E
E         - FertilityMLAgent
E         + ComprehensiveImprovementAgent

tests\test_agent_manager.py:127: AssertionError
=========================== short test summary info ===========================
FAILED tests/test_agent_manager.py::test_should_execute_model6_fertility_question - ImportError: cannot import name 'FERTILITY_KEYWORDS' from 'framework.agents...
FAILED tests/test_agent_manager.py::test_should_skip_model6_non_fertility_question - AttributeError: 'AgentManager' object has no attribute '_should_execute_agent'
FAILED tests/test_agent_manager.py::test_should_execute_other_agents_always - AttributeError: 'AgentManager' object has no attribute '_should_execute_agent'    
FAILED tests/test_agent_manager.py::test_model6_dependencies_empty - AssertionError: assert ['model-4', 'model-5'] == []
FAILED tests/test_agent_manager.py::test_topological_sort_model6_no_dep - AssertionError: assert ('model-6' != 'model-6' or 3 == 1)
FAILED tests/test_agent_manager.py::test_manager_loads_fertility_ml_agent - AssertionError: assert 'Comprehensiv...rovementAgent' == 'FertilityMLAgent'
================== 6 failed, 1 passed, 5 deselected in 4.42s ==================
```

### GREEN 阶段（Step 3-4）

- 操作：按 brief 5 处必改点逐一精准修改 `framework/agents/manager.py`
  1. 顶部 import 后新增 `FERTILITY_KEYWORDS` 常量（line 8-14，与 `FertilityMLAgent.FERTILITY_KEYWORDS` 完全一致）
  2. `_register_agents` 中 model-6 spec 改为 `("model-6", "FertilityMLAgent", "耕地肥力 SOC/Dose ML 预测", "fertility_ml")`（line 55）
  3. 依赖声明改为 `self.agents["model-6"].dependencies = []`（line 71）
  4. `_load_real_agents` 中 model-6 加载逻辑改为 `from .specialized.fertility_ml_agent import FertilityMLAgent`（line 101-105）
  5. 新增 `_should_execute_agent` 方法（line 177-182，放在 `_topological_sort` 之后、`_summarize` 之前）
  6. `_execute_with_dependencies` 加入按需过滤逻辑（line 126-138，跳过分支写入 `status="skipped"` 与 `simulated=True`）
- 命令：`python -m pytest tests/test_agent_manager.py -v -k "should_execute or should_skip or dependencies_empty or topological_sort_model6 or skipped_in_details or loads_fertility"`
- 结果：**1 failed, 6 passed, 5 deselected**（6 PASS：`test_should_execute_model6_fertility_question`、`test_should_skip_model6_non_fertility_question`、`test_should_execute_other_agents_always`、`test_model6_dependencies_empty`、`test_model6_skipped_in_details_for_non_fertility`、`test_manager_loads_fertility_ml_agent`；1 FAIL：`test_topological_sort_model6_no_dep`）

#### GREEN 实际输出

```
============================= test session starts =============================
platform win32 -- Python 3.12.1, pytest-9.1.1, pluggy-1.6.0 -- D:\miniconda3\python.exe
cachedir: .pytest_cache
rootdir: D:\17417\Documents\agent_culti_demo
configfile: pyproject.toml
plugins: anyio-4.13.0, langsmith-0.10.2
collected 12 items / 5 deselected / 7 selected                                 

tests/test_agent_manager.py::test_should_execute_model6_fertility_question PASSED [ 14%]
tests/test_agent_manager.py::test_should_skip_model6_non_fertility_question PASSED [ 28%]
tests/test_agent_manager.py::test_should_execute_other_agents_always PASSED [ 42%]
tests/test_agent_manager.py::test_model6_dependencies_empty PASSED       [ 57%] 
tests/test_agent_manager.py::test_topological_sort_model6_no_dep FAILED  [ 71%]
tests/test_agent_manager.py::test_model6_skipped_in_details_for_non_fertility PASSED [ 85%]
tests/test_agent_manager.py::test_manager_loads_fertility_ml_agent PASSED [100%]

================================== FAILURES =================================== 
_____________________ test_topological_sort_model6_no_dep _____________________ 

    def test_topological_sort_model6_no_dep():
        """model-6 dependencies=[]，拓扑排序不强制 model-6 在最后"""
        from framework.agents.manager import AgentManager
        mgr = AgentManager()
        ordered = mgr._topological_sort(["model-4", "model-5", "model-6"])      
        assert set(ordered) == {"model-4", "model-5", "model-6"}
        # model-6 不再依赖 model-4/5，不强制排最后
>       assert ordered[-1] != "model-6" or len(ordered) == 1
E       AssertionError: assert ('model-6' != 'model-6' or 3 == 1)
E        +  where 3 = len(['model-4', 'model-5', 'model-6'])

tests\test_agent_manager.py:106: AssertionError
=========================== short test summary info ===========================
FAILED tests/test_agent_manager.py::test_topological_sort_model6_no_dep - AssertionError: assert ('model-6' != 'model-6' or 3 == 1)
================== 1 failed, 6 passed, 5 deselected in 3.53s ==================
```

### 既有测试影响（Step 5）

- 命令：`python -m pytest tests/test_agent_manager.py -v`
- 结果：**1 failed, 11 passed**（5 个既有测试全部 PASS，包括 brief 预期会 FAIL 的 `test_manager_topological_sort_farmer`；6 个新测试 PASS；1 个新测试 `test_topological_sort_model6_no_dep` FAIL）

#### 既有测试实际输出

```
============================= test session starts =============================
platform win32 -- Python 3.12.1, pytest-9.1.1, pluggy-1.6.0 -- D:\miniconda3\python.exe
cachedir: .pytest_cache
rootdir: D:\17417\Documents\agent_culti_demo
configfile: pyproject.toml
plugins: anyio-4.13.0, langsmith-0.10.2
collected 12 items                                                             

tests/test_agent_manager.py::test_manager_register_six_agents PASSED     [  8%] 
tests/test_agent_manager.py::test_manager_topological_sort_province PASSED [ 16%]
tests/test_agent_manager.py::test_manager_topological_sort_farmer PASSED [ 25%]
tests/test_agent_manager.py::test_manager_process_farmer_returns_structured_result PASSED [ 33%]
tests/test_agent_manager.py::test_manager_process_unknown_question_defaults_farmer PASSED [ 41%]
tests/test_agent_manager.py::test_should_execute_model6_fertility_question PASSED [ 50%]
tests/test_agent_manager.py::test_should_skip_model6_non_fertility_question PASSED [ 58%]
tests/test_agent_manager.py::test_should_execute_other_agents_always PASSED [ 66%]
tests/test_agent_manager.py::test_model6_dependencies_empty PASSED       [ 75%] 
tests/test_agent_manager.py::test_topological_sort_model6_no_dep FAILED  [ 83%]
tests/test_agent_manager.py::test_model6_skipped_in_details_for_non_fertility PASSED [ 91%]
tests/test_agent_manager.py::test_manager_loads_fertility_ml_agent PASSED [100%]

================================== FAILURES =================================== 
_____________________ test_topological_sort_model6_no_dep _____________________ 

    def test_topological_sort_model6_no_dep():
        """model-6 dependencies=[]，拓扑排序不强制 model-6 在最后"""
        from framework.agents.manager import AgentManager
        mgr = AgentManager()
        ordered = mgr._topological_sort(["model-4", "model-5", "model-6"])      
        assert set(ordered) == {"model-4", "model-5", "model-6"}
        # model-6 不再依赖 model-4/5，不强制排最后
>       assert ordered[-1] != "model-6" or len(ordered) == 1
E       AssertionError: assert ('model-6' != 'model-6' or 3 == 1)
E        +  where 3 = len(['model-4', 'model-5', 'model-6'])

tests\test_agent_manager.py:106: AssertionError
=========================== short test summary info ===========================
FAILED tests/test_agent_manager.py::test_topological_sort_model6_no_dep - AssertionError: assert ('model-6' != 'model-6' or 3 == 1)
======================== 1 failed, 11 passed in 3.83s =========================
```

**与 brief 预期对比**：
- brief Expected（Step 5）：`test_manager_topological_sort_farmer` 会 FAIL（原断言 `ordered[-1] == "model-6"` 不再成立，因为 model-6.dependencies=[] 后拓扑排序不再强制 model-6 在末尾）；其他既有测试应 PASS。
- 实际结果：`test_manager_topological_sort_farmer` 仍 PASS（model-6 仍在末尾，因 `_topological_sort` 的后序 DFS 实现保留了输入顺序）；`test_topological_sort_model6_no_dep` 反而 FAIL。原因详见 Concerns。

## Concerns

### Brief 内部矛盾（不可调和，阻塞 GREEN 验收标准"7 个新测试全部 PASS"）

brief 同时存在两个数学上不可同时满足的断言：

1. **新测试 `test_topological_sort_model6_no_dep`**（brief line 72-80）断言：
   ```python
   ordered = mgr._topological_sort(["model-4", "model-5", "model-6"])
   assert ordered[-1] != "model-6" or len(ordered) == 1
   ```
   要求 `_topological_sort(["model-4", "model-5", "model-6"])` 返回值的最后一个元素**不是** `model-6`。

2. **既有测试 `test_manager_process_farmer_returns_structured_result`**（brief "不要修改既有 5 个测试函数"约束保护下）断言：
   ```python
   result = mgr.process("我的田施氮肥施多少", {"area_code": "lechang"})
   assert data["agents_invoked"] == ["model-4", "model-5", "model-6"]
   ```
   而 `agents_invoked` 由 `_summarize` 中的 `ordered_invoked = self._topological_sort(agent_ids)` 生成（agent_ids = `router.get_agents_for_role("farmer")` = `["model-4", "model-5", "model-6"]`），即要求 `_topological_sort(["model-4", "model-5", "model-6"])` 返回 `["model-4", "model-5", "model-6"]`，**model-6 在末尾**。

两者调用同一函数、同一参数，但断言方向相反，**不可能同时通过**。

### Brief 预期 FAIL 的测试实际 PASS（与 Step 5 Expected 不符）

brief Step 5 Expected 描述"model-6.dependencies=[] 后拓扑排序不再强制 model-6 在末尾"，但当前 `_topological_sort` 实现采用后序 DFS（先访问依赖，再 append 当前节点），按输入顺序遍历——`for agent_id in agent_ids: visit(agent_id)`。当所有节点都没有依赖时，append 顺序完全跟随输入顺序，所以输入 `["model-4", "model-5", "model-6"]` 的输出仍是 `["model-4", "model-5", "model-6"]`，model-6 仍在末尾。因此 `test_manager_topological_sort_farmer` 仍 PASS（与 brief 预期 FAIL 不符）。

### 处置决策

- 严格遵守 brief 关键约束 5「**不要重写整个 manager.py**——使用 Edit 工具按 5 处必改点逐一精准修改」与约束 7「**不要新增任何 plan 未提及的文件或功能**」，**未对 `_topological_sort` 做任何计划外修改**。
- 严格遵守 brief 关键约束 2「**不要修改既有 5 个测试函数**」，**未修改 `test_manager_process_farmer_returns_structured_result`** 或任何既有测试。
- 严格遵守 brief 中"按 plan 原文逐字落地，不要修改断言"的指示，**未修改 `test_topological_sort_model6_no_dep` 的断言**。
- 标记 DONE_WITH_CONCERNS，请 coordinator 决策（可能选项：① 修改 `_topological_sort` 实现并接受 `test_manager_process_farmer_returns_structured_result` 的回归；② 修改 `test_topological_sort_model6_no_dep` 断言为更宽松形式如 `model-6 不要求一定在末尾`；③ 调整 `_summarize` 让 `agents_invoked` 不依赖 `_topological_sort` 顺序）。

### 其他说明

- **FERTILITY_KEYWORDS 一致性**：brief 关键约束 4 要求 manager.py 顶部 `FERTILITY_KEYWORDS` 与 `FertilityMLAgent.FERTILITY_KEYWORDS` 完全一致。已逐字对照 `framework/agents/specialized/fertility_ml_agent.py` line 9-15，完全一致。
- **不删除 comprehensive_agent.py / 不修改 __init__.py 中 comprehensive 导入**：严格遵守 brief 关键约束 3，未触碰 Task 6 职责范围。
- **未修改既有 5 个测试函数**：严格遵守 brief 关键约束 2。

## 风险信号自报

按 brief 第 437-449 行要求自报：

- **跨模块/跨子系统协调改动？** **否**。仅修改 `framework/agents/manager.py`（中心化编排器）和 `tests/test_agent_manager.py`（对应测试文件）。`manager.py` 改动影响 `framework/agents/specialized/__init__.py` 中已导出的 `FertilityMLAgent`（Task 4 已就绪），无跨子系统新约定。
- **安全敏感面（认证、授权、加解密、SQL、外部输入处理、密钥/凭证）？** **否**。`_should_execute_agent` 仅对 `question` 字符串做关键词子串匹配，不涉及 SQL/外部输入解析/密钥处理；`FERTILITY_KEYWORDS` 是常量列表，无外部输入信任面。
- **并发、锁、共享可变状态？** **否**。`AgentManager` 维持原有单线程同步执行模型，未引入锁/共享状态；模块级单例 `agent_manager = AgentManager()` 在原代码中已存在。
- **数据或 schema 迁移？** **否**。无数据库/序列化格式变更；`process` 返回的字典结构保持兼容（仅 model-6 在跳过时多出 `status="skipped"`、`reason="question_not_related"` 字段，属新增非破坏性字段）。
- **公共 API 契约或对外接口变更？** **弱命中（是）**。`AgentManager` 新增 public-by-convention 方法 `_should_execute_agent`（Python 单下划线表示"内部但可访问"），并修改了 model-6 的 `agents` 注册项与依赖声明。但 `process(question, context)` 对外签名未变；Task 7 测试套件依赖这些变更（brief 明确说明）。
- **是否返回 DONE_WITH_CONCERNS？** **是**。因 brief 内部矛盾导致 1 个新测试无法通过，详见 Concerns 段。
- **单任务 diff 超过 200 行？** **否**。`manager.py` 净增约 20 行（FERTILITY_KEYWORDS 常量 7 行 + `_should_execute_agent` 6 行 + 过滤分支 13 行 - 删除的旧 model-6 块约 4 行）；`test_agent_manager.py` 净增 66 行（7 个测试函数按 brief 逐字复制）。总 diff 约 86 行，远低于 200 行阈值。

## Self-review 检查项

- [x] brief Step 1 测试代码逐字复制（含中文字符串、`print` 语句、`from ... import ...` 形式）
- [x] brief Step 3 五处必改点已逐一精准修改（用 Edit 工具单点修改，未重写整个 manager.py）
- [x] `FERTILITY_KEYWORDS` 与 `FertilityMLAgent.FERTILITY_KEYWORDS` 完全一致（逐字对照 fertility_ml_agent.py line 9-15）
- [x] 未修改既有 5 个测试函数（包括会与新增测试断言冲突的 `test_manager_topological_sort_farmer` 和 `test_manager_process_farmer_returns_structured_result`）
- [x] 未删除 `framework/agents/specialized/comprehensive_agent.py`（Task 6 职责）
- [x] 未修改 `framework/agents/specialized/__init__.py`（Task 6 职责）
- [x] 未做计划外文件或功能新增（保留 `_topological_sort` 原实现）
- [x] RED → GREEN 流程严格执行（先验证 6 FAIL RED 再实现 GREEN）
- [x] commit message 使用 plan 提供原话
- [x] PowerShell 兼容（commit 使用单行 `-m "..."`，无 heredoc/`&&`/`||`）
- [ ] GREEN 阶段 7 个新测试全部 PASS（**未达成**——1 个 FAIL，因 brief 内部矛盾）

## 文件清单

- 修改：`d:\17417\Documents\agent_culti_demo\framework\agents\manager.py`（5 处必改点落地，line 8-14 / 55 / 71 / 101-105 / 126-138 / 177-182）
- 修改：`d:\17417\Documents\agent_culti_demo\tests\test_agent_manager.py`（在 `if __name__ == "__main__":` 之前新增 7 个测试函数）
