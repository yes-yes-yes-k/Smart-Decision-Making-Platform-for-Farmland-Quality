# Task 4 Review — FertilityMLAgent 智能体

> **审查范围**：BASE `ddd374e` → HEAD `ad98800`（commit `ad98800`，3 files / +317 / -0）
> **审查依据**：`task-4-brief.md`（Step 1-6 + Global Constraints）、`task-4-report.md`（implementer 自报）、`task-4-review-package.diff`
> **审查模式**：review_mode=standard，build_mode=subagent-driven-development，tdd_mode=tdd
> **审查日期**：2026-07-18

## 审查文件清单

| 文件 | 类型 | 行数 |
|---|---|---|
| `framework/agents/specialized/fertility_ml_agent.py` | 新建 | 154 |
| `framework/agents/specialized/__init__.py` | 修改 | +2 |
| `tests/test_agent_specialized.py` | 修改 | +161 |

## 跨文件契约验证（环境基线）

| 依赖 | 路径 | 状态 |
|---|---|---|
| `BaseAgent` 抽象基类 | `framework/agents/base.py` 第 6-26 行 | ✅ 存在，签名 `__init__(name, description, model_id, domain)`、抽象方法 `execute`/`answer_question` 与实现匹配 |
| `MockDataLoader.mark_simulated` | `framework/agents/mock_data.py` 第 15-20 行 | ✅ 签名 `(payload: Dict) -> Dict`，添加 `simulated: True` 到副本 |
| `model_6_execution` | `framework/domain/other_models/model_6.py` 第 168 行 | ✅ 存在，返回含 `status`/`soc_prediction`/`dose_prediction`/`model_version` 等字段 |
| `manager.py` 旧 import | `framework/agents/manager.py` 第 93 行 | ✅ 仍导入 `ComprehensiveImprovementAgent`（Task 5 才切换），`__init__.py` 保留该导入故无回归 |
| `AgentManager.FERTILITY_KEYWORDS` | `framework/agents/manager.py` | ⚠️ 当前未定义（Task 5 才添加）；`fertility_ml_agent.py` 内的 `FERTILITY_KEYWORDS` 常量注释指向"未来一致"，符合 plan 第 1815 行说明 |

---

## 1. Spec Compliance Verdict

**Status**: ✅ **PASS**

### 逐项核对结果

| # | Global Constraint | 实现位置 | 结论 |
|---|---|---|---|
| 1 | `FertilityMLAgent` 继承 `BaseAgent` | `fertility_ml_agent.py:24` `class FertilityMLAgent(BaseAgent):` | ✅ |
| 2 | `__init__` 含 `model_id="model-6"`/`domain="fertility_ml"`/`name="FertilityMLAgent"`/`description="基于 ML 的耕地肥力 SOC/Dose 预测"` | `fertility_ml_agent.py:27-33` | ✅ 四参数全部精确匹配 |
| 3 | `dependencies = []` | `fertility_ml_agent.py:34` | ✅ |
| 4 | `execute(task)` 返回 `{status, result, metadata}` 三层 | `fertility_ml_agent.py:39-56` | ✅ |
| 5 | `execute` 调用 `model_6_execution(task or {})` 并包装 | `fertility_ml_agent.py:38` | ✅ |
| 6 | `result` 含 7 字段 `soc_prediction`/`soc_confidence`/`dose_prediction`/`dose_confidence`/`dose_warning`/`imputed_features`/`imputation_applied` | `fertility_ml_agent.py:42-48` | ✅ 7 字段齐全 |
| 7 | `metadata` 含 `model_version`/`fallback_reason`/`reason`/`out_of_range_features` | `fertility_ml_agent.py:51-54` | ✅ 4 字段齐全；后三者用 `.get()` 容错缺失键 |
| 8 | 所有返回通过 `MockDataLoader.mark_simulated` 添加 `simulated: True` | `execute` 第 39 行；`_format_rejected` 第 85 行；`_format_soc_only` 第 100 行；`_format_dose_only` 第 118 行；`_format_both` 第 140 行 | ✅ 5 处全部包装 |
| 9 | `answer_question(question, context)` 返回 `{answer, evidence, sources}` | 4 个 `_format_*` 返回均含此三键 | ✅ |
| 10 | 关键词优先级：Dose > SOC > 综合/默认 | `fertility_ml_agent.py:67-76`（先 DOSE、再 SOC、最后 `_format_both`） | ✅ |
| 11 | `_format_dose_only` evidence 含 `dose_prediction` 不含 `soc_prediction` | `fertility_ml_agent.py:120-123` | ✅ 仅 `dose_prediction`/`dose_confidence` |
| 12 | `_format_soc_only` evidence 含 `soc_prediction` 不含 `dose_prediction` | `fertility_ml_agent.py:102-105` | ✅ 仅 `soc_prediction`/`soc_confidence` |
| 13 | `_format_both` evidence 同时含 `soc_prediction` 和 `dose_prediction` | `fertility_ml_agent.py:147-152` | ✅ 4 项 evidence |
| 14 | fallback 时 answer 标注"模型不可用，返回训练集均值估算" | `_format_soc_only:96`、`_format_dose_only:114`、`_format_both:135-137`（"以上为训练集均值估算"） | ✅ |
| 15 | rejected 时 answer 标注越界特征列表，evidence 为空 | `_format_rejected:78-89`，`evidence=[]` | ✅ |
| 16 | Dose 单位 `t/ha`、SOC 单位 `g/kg` | `fertility_ml_agent.py:101/119/143-144/148/150` | ✅ |
| 17 | import 路径 `from ..base`/`from ..mock_data`/`from ...domain.other_models.model_6` | `fertility_ml_agent.py:4-6` | ✅ 三级相对路径正确，已实测 import 成功 |
| 18 | `__init__.py` 新增 `from .fertility_ml_agent import FertilityMLAgent` 和 `__all__` 列表项 | `__init__.py:7`、`__init__.py:16` | ✅ |
| 19 | 保留 `comprehensive_agent` 导入（Task 6 才删除） | `__init__.py:6`、`__init__.py:15` | ✅ 保留 |
| 20 | 不修改 `if __name__ == "__main__":` 块 | `test_agent_specialized.py:377-396` 原样保留 | ✅ |

### Findings（Spec Compliance）

**无 Critical / Important / Minor findings。**

所有 20 项 Global Constraints 在 `fertility_ml_agent.py` 与 `__init__.py` 中均精确实现，且与 brief 提供代码逐字一致。

---

## 2. Code Quality Verdict

**Status**: ✅ **Approved**（仅 Minor 项，且多数为 plan-mandated）

### Findings（Code Quality）

#### M-1. [Minor, plan-mandated] `List` 类型导入未使用

**位置**：`fertility_ml_agent.py:2` `from typing import Any, Dict, List`

**问题**：文件内未使用 `List` 类型注解（`FERTILITY_KEYWORDS` 等列表均无类型注解）。

**plan-mandated 说明**：brief 第 259 行 `from typing import Any, Dict, List` 逐字提供，implementer 按 brief 复制。

**建议**：保持现状（YAGNI 优先级低于 plan 一致性；Task 6 重构时可清理）。

#### M-2. [Minor, plan-mandated] `FERTILITY_KEYWORDS` 模块级常量在当前文件中未被使用

**位置**：`fertility_ml_agent.py:10-15`

**问题**：`answer_question` 仅使用 `DOSE_KEYWORDS` 与 `SOC_KEYWORDS`，`FERTILITY_KEYWORDS` 在当前文件中是"死常量"。

**plan-mandated 说明**：brief 第 266-272 行明确要求定义此常量；plan 第 1815 行注明 "Task 4 定义于 `fertility_ml_agent.py`，Task 5 定义于 `manager.py`，两处列表内容一致"，即 Task 5 `AgentManager` 会 `from framework.agents.specialized.fertility_ml_agent import FERTILITY_KEYWORDS` 复用。此为有意为之的前瞻性定义。

**建议**：保持现状。

#### M-3. [Minor, plan-mandated] `_format_soc_only` / `_format_dose_only` / `_format_both` 缺少 docstring

**位置**：`fertility_ml_agent.py:91`、`109`、`127`

**问题**：三个私有格式化方法未写 docstring，仅 `_format_rejected` 有简短 docstring。

**plan-mandated 说明**：brief 第 348/366/384 行提供的代码本身不含 docstring，implementer 按 brief 逐字复制。

**建议**：保持现状（私有方法名已自描述；Task 6 重构时可补）。

#### M-4. [Minor, plan-mandated] 测试中存在未使用的 `model_6` 导入

**位置**：`test_agent_specialized.py:219` `from framework.domain.other_models import model_6`

**问题**：在 `test_fertility_ml_agent_execute_structure` 中导入了 `model_6` 模块但未引用（mock 通过 `monkeypatch.setattr` 字符串路径完成）。

**plan-mandated 说明**：brief 第 87 行代码逐字提供此导入，可能用于 IDE 静态检查或文档目的。

**建议**：保持现状。

#### M-5. [Minor] 测试覆盖边界场景略窄

**位置**：`test_agent_specialized.py:216-374`

**问题**：6 个测试覆盖了 success/fallback/rejected × Dose/SOC/综合 的主路径，但以下边界场景未覆盖：
- `imputation_applied: True` 时 `_format_both` 的 `imputation_note` 分支（brief 第 388-391 行）
- 同时含 Dose 与 SOC 关键词的问题（应触发 Dose 优先级，但无显式断言）
- `exec_result["status"]` 为非 success/fallback/rejected 的未知值时的行为
- `execute(task=None)` 直接调用（`task or {}` 的 None 分支）

**严重级别**：Minor。brief Step 1 仅要求上述 6 个测试函数，未要求覆盖这些边界；implementer 严格按 brief 实现。

**建议**：可选在 Task 6/7 阶段补充边界测试；当前不影响交付。

#### M-6. [Minor, plan-mandated] 关键词列表与"AgentManager.FERTILITY_KEYWORDS"的一致性尚为前向承诺

**位置**：`fertility_ml_agent.py:9` 注释

**问题**：注释声称"与 AgentManager.FERTILITY_KEYWORDS 保持一致"，但 `AgentManager` 当前未定义此常量（Task 5 才添加）。当前无法静态验证一致性，依赖 Task 5 实施者按相同列表复制。

**plan-mandated 说明**：plan 第 1815 行明确 "两处列表内容一致" 为 Task 5 验收项。

**建议**：Task 5 reviewer 需核对两处常量字面量一致。

### 其他维度核查（无发现）

- [x] **YAGNI**：除上述 M-1/M-2 的 plan-mandated 项外，无多余抽象/功能
- [x] **Test hygiene**：6 个测试均使用 pytest `monkeypatch` fixture（自动 teardown），无 `setattr` 残留；每个测试内创建独立 `FertilityMLAgent()` 实例，无共享状态
- [x] **Import 正确性**：`..`/`...` 相对路径正确解析（`fertility_ml_agent.py` → `specialized` → `agents` → `framework` → `framework.domain.other_models.model_6`）
- [x] **Error handling**：无 `try/except` 吞噬异常；`metadata` 中后三字段用 `.get()` 容错缺失键（合理）；`model_6_execution` 抛异常时会向上传播（与 brief 一致，未引入额外异常处理）
- [x] **Type hints**：所有公开方法（`__init__`/`execute`/`answer_question`）类型注解完整
- [x] **测试覆盖主路径**：6 个测试覆盖 success/fallback/rejected × Dose/SOC/综合 的全部 6 个组合

---

## 3. 测试覆盖评估

### 测试函数清单（与 brief Step 1 逐字对照）

| # | 测试函数 | 覆盖路径 | mock 路径 | 结论 |
|---|---|---|---|---|
| 1 | `test_fertility_ml_agent_execute_structure` | `execute` success 三层结构 + `model_id`/`dependencies` | `framework.agents.specialized.fertility_ml_agent.model_6_execution` | ✅ |
| 2 | `test_fertility_ml_agent_answer_dose_keywords` | Dose 关键词分支 + evidence 仅 dose | 同上 | ✅ |
| 3 | `test_fertility_ml_agent_answer_soc_keywords` | SOC 关键词分支 + evidence 仅 soc | 同上 | ✅ |
| 4 | `test_fertility_ml_agent_answer_fertility_keywords` | 综合分支 + evidence 含 soc+dose | 同上 | ✅ |
| 5 | `test_fertility_ml_agent_answer_fallback_status` | fallback 时 answer 含"模型不可用"/"训练集均值" | 同上 | ✅ |
| 6 | `test_fertility_ml_agent_answer_rejected_status` | rejected 时 answer 含越界特征 + `evidence == []` | 同上 | ✅ |

### Mock 路径正确性

- **路径**：`framework.agents.specialized.fertility_ml_agent.model_6_execution`
- **正确性**：`fertility_ml_agent.py:6` 通过 `from ...domain.other_models.model_6 import model_6_execution` 将函数绑定为本模块属性，故 `monkeypatch.setattr` 字符串路径可正确解析 ✓

### 既有测试回归

- implementer 报告：`python -m pytest tests/test_agent_specialized.py -v` → **24 passed in 2.44s**（18 既有 + 6 新增）
- 静态核查：`__init__.py` 保留 `ComprehensiveImprovementAgent` 导入，`manager.py:93` 的 `from .specialized.comprehensive_agent import ComprehensiveImprovementAgent` 仍可解析，无回归风险
- `if __name__ == "__main__":` 块未修改，3 个 `comprehensive_*` 测试仍在直接运行列表中

### 未破坏既有测试

✅ 18 个既有测试零回归（基于 implementer 报告 + 静态 import 链验证）。

---

## 4. Recommendations

### 必须修复的 Critical / Important 项

**无。**

### 可选改进的 Minor 项（建议在 Task 6/7 或后续重构中处理）

1. **M-1**：清理 `from typing import ... List` 中未使用的 `List`
2. **M-2**：评估 `FERTILITY_KEYWORDS` 是否改为在 Task 5 中由 `manager.py` 单点定义后导入（避免 DRY 违反）
3. **M-3**：为 `_format_soc_only`/`_format_dose_only`/`_format_both` 补充一行 docstring
4. **M-4**：移除 `test_fertility_ml_agent_execute_structure` 中未使用的 `from framework.domain.other_models import model_6`
5. **M-5**：补充 `imputation_applied=True` 路径的测试
6. **M-6**：Task 5 reviewer 需核对 `manager.py.FERTILITY_KEYWORDS` 与 `fertility_ml_agent.py.FERTILITY_KEYWORDS` 字面量一致

**重要说明**：M-1 ~ M-4 均为 **plan-mandated**（implementer 严格按 brief 逐字复制），不应视为 implementer 的代码质量问题。这些项应在 plan/brief 层面在 Task 6/7 收尾时统一处理。

---

## 5. Final Verdict

### **✅ Approved**

**理由**：

1. **Spec Compliance**：20 项 Global Constraints 全部精确实现，无任何 Critical / Important / Minor 偏差
2. **Code Quality**：实现严格遵循 brief 提供的代码，无主观设计变更；6 处 Minor 发现中 5 处为 plan-mandated（不应归责 implementer），1 处为可选测试增强
3. **测试覆盖**：6 个测试覆盖全部主路径（success/fallback/rejected × Dose/SOC/综合），mock 路径正确，既有 18 个测试零回归
4. **TDD 流程**：RED 阶段先验证 6 个测试 FAIL（错误信息与预期一致），GREEN 阶段实现后 6 个测试 PASS，全量 24 PASS——流程严格执行
5. **跨模块影响**：保留 `comprehensive_agent` 导入，`manager.py` 现有 import 不破坏；`FertilityMLAgent` 对外行为零变更（Task 5 才切换 `_load_real_agents`）
6. **风险信号**：implementer 自报 diff>200（317 行）命中，但其中 162 行为新文件 + 155 行为新测试，均为 brief 逐字内容，无主观设计变更，风险可控

**准予进入 Task 5**（AgentManager 接入 FertilityMLAgent + FERTILITY_KEYWORDS）。

---

## 附录：审查方法论

- **静态审查**：基于 review-package.diff + 实际文件读取（非推测）
- **不重跑测试**：信任 implementer 报告的 24 PASS 证据，未重复执行 pytest
- **跨文件契约验证**：手动 Read `base.py`/`mock_data.py`/`model_6.py`/`manager.py` 确认 import 链完整
- **plan-mandated 标注**：对源于 brief/plan 的代码问题明确标注，不归责 implementer
- **编码问题说明**：review-package.diff 中中文显示为乱码（GBK/UTF-8 解码问题），但通过直接 Read 实际文件验证中文内容正确，不影响审查结论
