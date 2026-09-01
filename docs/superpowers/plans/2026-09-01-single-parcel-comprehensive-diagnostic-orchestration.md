# 单地块综合诊断与改良报告 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (<code>- [ ]</code>) syntax for tracking.

**Goal:** 在不改变知识问答和单模型快路径的前提下，增加可持久恢复、受约束规划、两波模型执行、证据绑定和人工发布确认的单地块综合诊断工作流。

**Architecture:** 顶层 Coordinator 只输出严格枚举意图，确定性 TrafficGate 将知识问答和单模型请求留在现有图，将明确的单地块综合请求委派给独立 LangGraph 子图。子图使用 PostgreSQL checkpointer、Pydantic 契约、确定性 PlanValidator/InputResolver/ConfirmationPolicy/Scheduler/ResultValidator，以及受数值引用约束的 EvidenceResearcher 和 Reporter；所有 Agent 通过状态通信，不自由互相委派。

**Tech Stack:** Python 3.10+、Flask、Pydantic 2、LangGraph 1.2、langgraph-checkpoint-postgres 3.1、Psycopg 3、PostgreSQL、LangChain Tools、现有 RAG/Chroma、Pytest。

## Global Constraints

- 以 <code>docs/superpowers/specs/2026-09-01-single-parcel-comprehensive-diagnostic-orchestration-design.md</code> 为验收基线。
- 必须先完整执行并验证 <code>docs/superpowers/plans/2026-08-30-chat-analysis-object-context.md</code>；本计划依赖其中的 <code>AnalysisContext</code>、<code>AnalysisContextService</code>、<code>AnalysisRequirementGuard</code>、<code>ResultProvenanceBuilder</code> 和 <code>ChatRequestService</code>，不重复实现它们。
- 综合任务只接受 <code>calculation_mode=spatial</code> 且当前对象类型为 <code>parcel</code>；省、市、县、片区和 scenario 不进入综合子图。
- 快路径仍由现有 <code>QuestionTypeRouter</code> 执行一对一路由；未明确表达综合诊断/综合报告意图的请求不得升级到任务路径。
- Planner 只能选择 <code>model-1</code> 至 <code>model-5</code>；<code>model-6</code> 在综合任务中始终禁用。
- <code>model-2</code> 和 <code>model-3</code> 是核心任务；<code>model-1</code> 依历史数据，<code>model-4</code>/<code>model-5</code> 依用户意图或第一波证据。
- Planner、Coordinator、EvidenceResearcher、Reporter 的单次角色调用总尝试数固定为 2，不能形成无界修复循环。
- 单个模型初次调用后最多重试 2 次；只有明确的瞬时错误可重试，验证错误和业务输入错误不重试。
- 首稿不计入用户修订次数；用户最多请求 3 次报告修订。内部 schema/报告校验重生成不计入用户修订次数，但每个版本总生成次数仍最多 2 次。
- Function Calling 在任务路径只暴露已验证计划中的工具；调度器按 <code>agent_id</code> 精确调用，不让 LLM 在全部工具中二次选模。
- 生产 checkpointer 必须使用 PostgreSQL；<code>InMemorySaver</code> 只允许单元测试。
- 设置 <code>LANGGRAPH_STRICT_MSGPACK=true</code>；checkpoint 只保存 JSON 可序列化的普通类型，不保存 Flask 对象、DB session、Tool 或 Pydantic 类实例。
- 保留用户已有未提交修改；每次提交只暂存该任务列出的文件。

## Execution Prerequisite Gate

在 Task 1 前运行：

~~~powershell
python -m pytest tests/analysis_context -q
python -c "from framework.analysis_context.contracts import AnalysisContext; from framework.api.services.chat_service import ChatRequestService; print('analysis-context-ready')"
git status --short
~~~

Expected:

- 分析对象测试全部 PASS；
- 输出 <code>analysis-context-ready</code>；
- <code>git status --short</code> 中可以有用户原有修改，但不能有未完成的分析对象实施文件。

若任一前置检查失败，停止本计划并先执行 <code>2026-08-30-chat-analysis-object-context.md</code>。不要为绕过前置失败在本计划中复制简化版上下文服务。

## Official API Baseline

- LangGraph 生产持久化采用官方 <code>PostgresSaver</code>，首次部署显式调用 <code>setup()</code>：[LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence)。
- 人工中断使用 <code>interrupt()</code>，恢复使用同一 <code>thread_id</code> 和 <code>Command(resume=...)</code>；中断节点从头重跑，因此中断前操作必须幂等：[LangGraph interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts)。
- 版本范围以计划编写时稳定系列为准：<code>langgraph&gt;=1.2.11,&lt;2</code>、<code>langgraph-checkpoint-postgres&gt;=3.1.2,&lt;4</code>。

## File Map

| Path | Responsibility |
|---|---|
| <code>framework/agents/workflows/comprehensive/contracts.py</code> | 意图、计划、输入、任务结果、证据、报告和恢复动作契约 |
| <code>framework/agents/workflows/comprehensive/state.py</code> | 仅综合子图使用的 TypedDict 状态 |
| <code>framework/agents/workflows/comprehensive/checkpointing.py</code> | PostgreSQL checkpointer 生命周期和 thread config |
| <code>framework/agents/workflows/comprehensive/prompt_catalog.py</code> | 四个角色的版本化 Prompt |
| <code>framework/agents/workflows/comprehensive/structured_roles.py</code> | 最多两次的结构化 LLM 调用器 |
| <code>framework/agents/workflows/comprehensive/coordinator.py</code> | InteractionIntent 与 TrafficGate |
| <code>framework/agents/workflows/comprehensive/planner.py</code> | DiagnosticPlanner 与 PlanValidator |
| <code>framework/agents/workflows/comprehensive/confirmation.py</code> | 地块输入解析、默认值和智能确认策略 |
| <code>framework/agents/workflows/comprehensive/execution.py</code> | 受限工具调用、结果验证、触发器与两波调度 |
| <code>framework/agents/workflows/comprehensive/evidence.py</code> | 只检索本地知识库并绑定 claim/source |
| <code>framework/agents/workflows/comprehensive/reporting.py</code> | 报告生成、事实引用渲染、发布与修订约束 |
| <code>framework/agents/workflows/comprehensive/graph.py</code> | LangGraph 节点、边、中断和恢复 |
| <code>framework/agents/workflows/comprehensive/runtime.py</code> | 子图编译、初始运行、恢复和输出归一化 |
| <code>framework/agents/capabilities.py</code> | 综合任务能力、成本、超时、触发器和 tool_name |
| <code>framework/function_calling/specialized_tools.py</code> | 根据已验证 agent 集合返回精确工具映射 |
| <code>framework/agents/orchestrator.py</code> | 顶层快/任务路径分流，不承载综合内部节点 |
| <code>framework/api/services/chat_service.py</code> | initial/resume 请求归一化和统一响应 |
| <code>framework/api/routes/chat.py</code> | HTTP/SSE 适配，复用相同工作流结果 |
| <code>framework/observability/comprehensive_workflow.py</code> | 稳定事件名、计划/触发/降级指标 |
| <code>scripts/setup_langgraph_checkpoint.py</code> | 显式创建 checkpointer 表 |
| <code>scripts/benchmark_comprehensive_routing.py</code> | 快路径 P95 回归基准 |
| <code>tests/comprehensive_workflow/factories.py</code> | 跨任务复用的完整、确定性测试对象工厂 |

---

### Task 1: 固定运行时版本、Feature Flag 与持久 Checkpointer

**Files:**

- Modify: <code>pyproject.toml</code>
- Modify: <code>requirements.txt</code>
- Modify: <code>framework/config.py</code>
- Modify: <code>framework/api/app.py</code>
- Create: <code>framework/agents/workflows/__init__.py</code>
- Create: <code>framework/agents/workflows/comprehensive/__init__.py</code>
- Create: <code>framework/agents/workflows/comprehensive/checkpointing.py</code>
- Create: <code>scripts/setup_langgraph_checkpoint.py</code>
- Create: <code>tests/comprehensive_workflow/__init__.py</code>
- Create: <code>tests/comprehensive_workflow/test_checkpointing.py</code>
- Modify: <code>tests/test_config.py</code>

**Interfaces:**

- Consumes: <code>Config.SQLALCHEMY_DATABASE_URI</code>.
- Produces: <code>PostgresCheckpointerRuntime.start() -&gt; BaseCheckpointSaver</code>、<code>PostgresCheckpointerRuntime.close() -&gt; None</code>、<code>workflow_thread_config(conversation_id: int, run_id: str) -&gt; dict</code>.

- [ ] **Step 1: 写 Feature Flag、URI 和 thread_id 失败测试**

~~~python
from framework.agents.workflows.comprehensive.checkpointing import (
    normalize_postgres_uri,
    workflow_thread_config,
)
from framework.config import Config


def test_comprehensive_workflow_defaults_off():
    assert Config.COMPREHENSIVE_WORKFLOW_MODE == "off"


def test_psycopg2_sqlalchemy_uri_is_normalized_for_psycopg3():
    uri = "postgresql+psycopg2://u:p@db:5432/app"
    assert normalize_postgres_uri(uri) == "postgresql://u:p@db:5432/app"


def test_workflow_thread_config_is_run_scoped():
    assert workflow_thread_config(12, "run-7") == {
        "configurable": {
            "thread_id": "chat:12:comprehensive:run-7",
            "checkpoint_ns": "single-parcel-v1",
        }
    }
~~~

- [ ] **Step 2: 运行测试并确认模块/配置缺失**

Run: <code>python -m pytest tests/comprehensive_workflow/test_checkpointing.py tests/test_config.py -q</code>

Expected: FAIL，首次失败为 <code>ModuleNotFoundError</code> 或 <code>COMPREHENSIVE_WORKFLOW_MODE</code> 缬失。

- [ ] **Step 3: 固定依赖和配置**

在 <code>pyproject.toml</code> 的 dependencies 与 <code>requirements.txt</code> 增加相同范围：

~~~text
langgraph>=1.2.11,<2
langgraph-checkpoint-postgres>=3.1.2,<4
psycopg[binary,pool]>=3.2,<4
pydantic>=2.7,<3
~~~

在 <code>Config</code> 增加：

~~~python
COMPREHENSIVE_WORKFLOW_MODE = os.environ.get(
    "COMPREHENSIVE_WORKFLOW_MODE", "off"
).lower()
if COMPREHENSIVE_WORKFLOW_MODE not in {"off", "shadow", "enabled"}:
    raise ValueError(
        "COMPREHENSIVE_WORKFLOW_MODE must be off, shadow, or enabled"
    )
COMPREHENSIVE_ALLOWED_USER_IDS = tuple(
    int(value)
    for value in os.environ.get(
        "COMPREHENSIVE_ALLOWED_USER_IDS", ""
    ).split(",")
    if value.strip()
)
LANGGRAPH_CHECKPOINT_URI = os.environ.get(
    "LANGGRAPH_CHECKPOINT_URI", SQLALCHEMY_DATABASE_URI
)
LANGGRAPH_CHECKPOINT_AUTO_SETUP = (
    os.environ.get("LANGGRAPH_CHECKPOINT_AUTO_SETUP", "false").lower()
    == "true"
)
~~~

- [ ] **Step 4: 实现 checkpointer 生命周期**

~~~python
from __future__ import annotations

import os
from typing import Any

os.environ.setdefault("LANGGRAPH_STRICT_MSGPACK", "true")

from langgraph.checkpoint.postgres import PostgresSaver


CHECKPOINT_NAMESPACE = "single-parcel-v1"


def normalize_postgres_uri(uri: str) -> str:
    return (
        uri.replace("postgresql+psycopg2://", "postgresql://", 1)
        .replace("postgresql+psycopg://", "postgresql://", 1)
    )


def workflow_thread_config(
    conversation_id: int, run_id: str
) -> dict[str, dict[str, str]]:
    if conversation_id <= 0 or not run_id.strip():
        raise ValueError("conversation_id and run_id are required")
    return {
        "configurable": {
            "thread_id": (
                f"chat:{conversation_id}:comprehensive:{run_id}"
            ),
            "checkpoint_ns": CHECKPOINT_NAMESPACE,
        }
    }


class PostgresCheckpointerRuntime:
    def __init__(self, uri: str, *, auto_setup: bool = False):
        self._uri = normalize_postgres_uri(uri)
        self._auto_setup = auto_setup
        self._context_manager: Any = None
        self._saver: Any = None

    def start(self):
        if self._saver is not None:
            return self._saver
        self._context_manager = PostgresSaver.from_conn_string(self._uri)
        self._saver = self._context_manager.__enter__()
        if self._auto_setup:
            self._saver.setup()
        return self._saver

    def close(self) -> None:
        if self._context_manager is not None:
            self._context_manager.__exit__(None, None, None)
        self._context_manager = None
        self._saver = None
~~~

测试使用 fake context manager 断言重复 <code>start()</code> 只进入一次，<code>close()</code> 只退出一次，<code>auto_setup=False</code> 不执行 DDL。

在 <code>framework/api/app.py</code> 的 <code>create_app()</code> 完成配置与扩展初始化后调用：

~~~python
def init_comprehensive_checkpointer(app: Flask) -> None:
    if app.config["COMPREHENSIVE_WORKFLOW_MODE"] != "enabled":
        return
    runtime = PostgresCheckpointerRuntime(
        app.config["LANGGRAPH_CHECKPOINT_URI"],
        auto_setup=app.config["LANGGRAPH_CHECKPOINT_AUTO_SETUP"],
    )
    saver = runtime.start()
    app.extensions["comprehensive_checkpointer_runtime"] = runtime
    app.extensions["comprehensive_checkpointer"] = saver
    atexit.register(runtime.close)
~~~

<code>off</code>/<code>shadow</code> 不建立 checkpoint 连接；切换到 <code>enabled</code> 通过重启进程生效。测试直接从 <code>app.extensions</code> 取 runtime 并调用 <code>close()</code>，验证重复关闭安全。不得在 <code>teardown_appcontext</code> 中关闭，因为它会在每个请求后执行。

- [ ] **Step 5: 增加显式 setup 脚本**

~~~python
from framework.agents.workflows.comprehensive.checkpointing import (
    PostgresCheckpointerRuntime,
)
from framework.config import Config


def main() -> int:
    runtime = PostgresCheckpointerRuntime(
        Config.LANGGRAPH_CHECKPOINT_URI,
        auto_setup=True,
    )
    try:
        runtime.start()
    finally:
        runtime.close()
    print("LangGraph checkpoint schema is ready")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
~~~

- [ ] **Step 6: 运行测试并提交**

Run: <code>python -m pytest tests/comprehensive_workflow/test_checkpointing.py tests/test_config.py -q</code>

Expected: PASS。

~~~powershell
git add pyproject.toml requirements.txt framework/config.py framework/api/app.py framework/agents/workflows scripts/setup_langgraph_checkpoint.py tests/comprehensive_workflow tests/test_config.py
git commit -m "feat(workflow): add durable comprehensive checkpoint runtime"
~~~

---

### Task 2: 建立综合工作流契约并扩展能力目录

**Files:**

- Create: <code>framework/agents/workflows/comprehensive/contracts.py</code>
- Create: <code>framework/agents/workflows/comprehensive/state.py</code>
- Modify: <code>framework/agents/capabilities.py</code>
- Create: <code>tests/comprehensive_workflow/factories.py</code>
- Create: <code>tests/comprehensive_workflow/test_contracts.py</code>
- Modify: <code>tests/test_professional_capabilities.py</code>

**Interfaces:**

- Consumes: <code>AnalysisContext.to_dict()</code> from prerequisite plan.
- Produces: <code>InteractionIntent</code>、<code>DiagnosticPlan</code>、<code>DiagnosticTask</code>、<code>InputResolution</code>、<code>TaskResult</code>、<code>EvidenceBundle</code>、<code>ReportPayload</code>、<code>InteractionResponse</code>、<code>WorkflowOutput</code>、<code>ComprehensiveDiagnosticState</code>.

- [ ] **Step 1: 写严格枚举、额外字段拒绝和能力元数据测试**

~~~python
import pytest
from pydantic import ValidationError

from framework.agents.capabilities import CAPABILITY_BY_AGENT_ID
from framework.agents.workflows.comprehensive.contracts import (
    DiagnosticPlan,
    InteractionIntent,
)


def test_intent_rejects_unknown_kind_and_extra_fields():
    with pytest.raises(ValidationError):
        InteractionIntent.model_validate({
            "kind": "peer_chat",
            "confidence": 1,
            "reason_code": "UNKNOWN",
            "prompt_version": "coordinator-v1",
            "execute_now": True,
        })


def test_plan_rejects_more_than_five_tasks():
    payload = make_valid_plan_payload()
    payload["tasks"].append(payload["tasks"][0] | {"task_id": "six"})
    with pytest.raises(ValidationError):
        DiagnosticPlan.model_validate(payload)


def test_comprehensive_capability_metadata_is_complete():
    for agent_id in ("model-1", "model-2", "model-3", "model-4", "model-5"):
        cap = CAPABILITY_BY_AGENT_ID[agent_id]
        assert cap.tool_name
        assert cap.result_schema
        assert cap.timeout_seconds > 0
        assert cap.retry_limit == 2
    assert CAPABILITY_BY_AGENT_ID["model-6"].comprehensive_role == "disabled"
~~~

- [ ] **Step 2: 运行测试并确认契约不存在**

Run: <code>python -m pytest tests/comprehensive_workflow/test_contracts.py tests/test_professional_capabilities.py -q</code>

Expected: FAIL。

- [ ] **Step 3: 实现核心 Pydantic 契约**

~~~python
from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class InteractionKind(str, Enum):
    KNOWLEDGE = "knowledge"
    SINGLE_ANALYSIS = "single_analysis"
    COMPREHENSIVE_ANALYSIS = "comprehensive_analysis"
    UNSUPPORTED = "unsupported"


class InteractionIntent(StrictModel):
    kind: InteractionKind
    confidence: float = Field(ge=0, le=1)
    reason_code: Literal[
        "KNOWLEDGE_REQUEST",
        "SINGLE_MODEL_REQUEST",
        "EXPLICIT_COMPREHENSIVE_REPORT",
        "UNSUPPORTED_REQUEST",
        "DETERMINISTIC_FALLBACK",
    ]
    prompt_version: str


class TriggerRule(StrictModel):
    type: Literal["always", "all", "any"]
    predicates: tuple[str, ...] = ()


class DiagnosticTask(StrictModel):
    task_id: str = Field(min_length=1)
    agent_id: str
    required: bool
    depends_on: tuple[str, ...] = ()
    trigger: TriggerRule


class DiagnosticPlan(StrictModel):
    plan_version: Literal[1]
    analysis_mode: Literal["single_parcel_comprehensive"]
    planner_prompt_version: str
    tasks: tuple[DiagnosticTask, ...] = Field(min_length=2, max_length=5)
    planner_reason: str = Field(min_length=1, max_length=500)


class ResolvedValue(StrictModel):
    value: Any
    unit: str | None = None
    source: Literal["parcel_db", "user", "confirmed_default"]
    source_version: str


class InputResolution(StrictModel):
    task_arguments: dict[str, dict[str, Any]]
    resolved_values: dict[str, ResolvedValue]
    missing_inputs: tuple[str, ...] = ()
    proposed_defaults: dict[str, Any] = Field(default_factory=dict)
    object_version: int


class TaskResult(StrictModel):
    task_id: str
    agent_id: str
    status: Literal["succeeded", "failed", "degraded", "skipped"]
    payload: dict[str, Any]
    key_inputs: dict[str, Any]
    model_version: str
    data_as_of: str | None
    data_version: str | None
    calculated_at: str
    trace_id: str
    error_code: str | None = None


class EvidenceItem(StrictModel):
    source_id: str
    doc_name: str
    chunk_index: int | None
    page: int | None
    claim_ids: tuple[str, ...]
    score: float | None


class EvidenceBundle(StrictModel):
    items: tuple[EvidenceItem, ...]
    unsupported_claims: tuple[str, ...] = ()


class ReportSection(StrictModel):
    section_id: str
    title: str
    prose_template: str
    fact_refs: tuple[str, ...] = ()
    claim_ids: tuple[str, ...] = ()
    source_ids: tuple[str, ...] = ()


class ReportPayload(StrictModel):
    title: str
    sections: tuple[ReportSection, ...]
    degradations: tuple[str, ...]
    prompt_version: str


class InteractionResponse(StrictModel):
    run_id: str
    expected_checkpoint_version: int = Field(ge=1)
    action: Literal[
        "provide_input",
        "confirm_plan",
        "request_revision",
        "release_report",
        "cancel",
    ]
    values: dict[str, Any] = Field(default_factory=dict)
    comment: str = Field(default="", max_length=2000)


class WorkflowOutput(StrictModel):
    interaction_state: str
    run_id: str
    checkpoint_version: int = Field(ge=0)
    analysis_context: dict[str, Any]
    plan_summary: dict[str, Any] = Field(default_factory=dict)
    missing_inputs: tuple[str, ...] = ()
    proposed_defaults: dict[str, Any] = Field(default_factory=dict)
    report_draft: str | None = None
    answer: str | None = None
    degradations: tuple[str, ...] = ()
    provenance: dict[str, Any] = Field(default_factory=dict)
    trace_id: str
~~~

- [ ] **Step 4: 定义纯字典子图状态**

~~~python
from typing import Any, TypedDict


class ComprehensiveDiagnosticState(TypedDict, total=False):
    run_id: str
    trace_id: str
    conversation_id: int
    user_id: int
    checkpoint_version: int
    interaction_state: str
    normalized_request: dict[str, Any]
    interaction_intent: dict[str, Any]
    planning_facts: dict[str, Any]
    request_facts: dict[str, Any]
    analysis_context_snapshot: dict[str, Any]
    object_version: int
    diagnostic_plan: dict[str, Any]
    plan_hash: str
    resolved_inputs: dict[str, Any]
    missing_inputs: list[str]
    proposed_defaults: dict[str, Any]
    confirmation: dict[str, Any]
    task_results: dict[str, dict[str, Any]]
    task_attempts: dict[str, int]
    validation_issues: list[dict[str, Any]]
    degradations: list[str]
    evidence_items: list[dict[str, Any]]
    canonical_claims: list[dict[str, Any]]
    unsupported_claims: list[str]
    report_payload: dict[str, Any]
    report_draft: str
    report_revision_count: int
    report_validation_attempts: int
    revision_comment: str
    release_confirmation: dict[str, Any]
    provenance: dict[str, Any]
    error: dict[str, Any] | None
~~~

- [ ] **Step 5: 建立跨任务测试工厂**

在 <code>tests/comprehensive_workflow/factories.py</code> 中集中实现本计划测试片段引用的稳定对象。工厂只依赖 Task 2 契约，不访问数据库或外部服务：

~~~python
from __future__ import annotations

from copy import deepcopy
from typing import Any

from framework.agents.workflows.comprehensive.contracts import (
    DiagnosticPlan,
    EvidenceBundle,
    EvidenceItem,
    InputResolution,
    ReportPayload,
    ReportSection,
    ResolvedValue,
    TaskResult,
)


def make_valid_plan_payload(*, history: bool = False) -> dict[str, Any]:
    tasks = [
        {"task_id": "quality-evaluation", "agent_id": "model-2",
         "required": True, "depends_on": (),
         "trigger": {"type": "always", "predicates": ()}},
        {"task_id": "problem-diagnosis", "agent_id": "model-3",
         "required": True, "depends_on": (),
         "trigger": {"type": "always", "predicates": ()}},
        {"task_id": "acidification-remediation", "agent_id": "model-4",
         "required": False,
         "depends_on": ("problem-diagnosis",),
         "trigger": {"type": "any", "predicates": (
             "user_requested_acidification", "acidification_evidence")}},
        {"task_id": "organic-matter-improvement", "agent_id": "model-5",
         "required": False,
         "depends_on": ("problem-diagnosis",),
         "trigger": {"type": "any", "predicates": (
             "user_requested_organic_matter", "organic_matter_evidence")}},
    ]
    if history:
        tasks.insert(0, {
            "task_id": "stability-risk", "agent_id": "model-1",
            "required": False, "depends_on": (),
            "trigger": {"type": "all", "predicates": ("history_available",)},
        })
    return {
        "plan_version": 1,
        "analysis_mode": "single_parcel_comprehensive",
        "planner_prompt_version": "planner-v1",
        "tasks": tasks,
        "planner_reason": "固定综合诊断计划",
    }


def valid_plan(*, history: bool = False) -> DiagnosticPlan:
    return DiagnosticPlan.model_validate(make_valid_plan_payload(history=history))


def plan_without(agent_id: str) -> DiagnosticPlan:
    payload = make_valid_plan_payload(history=agent_id != "model-1")
    payload["tasks"] = [t for t in payload["tasks"] if t["agent_id"] != agent_id]
    return DiagnosticPlan.model_validate(payload)


def parcel_context(parcel_id: str = "P001", *, version: int = 4) -> dict[str, Any]:
    return {"object": {"type": "parcel", "id": parcel_id,
                       "display_name": "示例地块"},
            "version": version, "mode": "spatial"}


def verified_execution_context(parcel_id: str = "P001") -> dict[str, Any]:
    return {"analysis_context": parcel_context(parcel_id),
            "verified": True, "trace_id": "trace-1"}


def complete_resolution() -> InputResolution:
    values = {
        "parcel_id": ResolvedValue(value="P001", source="parcel_db",
                                   source_version="parcel:4"),
        "soil_ph": ResolvedValue(value=5.2, unit="pH", source="parcel_db",
                                 source_version="sample:9"),
    }
    return InputResolution(
        task_arguments={task.task_id: {"parcel_id": "P001", "soil_ph": 5.2}
                        for task in valid_plan().tasks},
        resolved_values=values, object_version=4,
    )


def successful_model2_result(*, composite_index: float = 0.734) -> TaskResult:
    return TaskResult(
        task_id="quality-evaluation", agent_id="model-2", status="succeeded",
        payload={"composite_index": composite_index, "quality_grade": "Ⅱ"},
        key_inputs={"parcel_id": "P001"}, model_version="model-2-v1",
        data_as_of="2026-08-31", data_version="sample:9",
        calculated_at="2026-09-01T00:00:00+00:00", trace_id="trace-1",
    )


def validated_results(*, composite_index: float = 0.734) -> dict[str, TaskResult]:
    return {"quality-evaluation": successful_model2_result(
        composite_index=composite_index)}


def valid_evidence() -> EvidenceBundle:
    return EvidenceBundle(items=(EvidenceItem(
        source_id="doc-1:0:1", doc_name="改良手册", chunk_index=0, page=1,
        claim_ids=("claim-1",), score=0.93,
    ),))


def report_payload(*, prose_template: str, fact_refs: tuple[str, ...]) -> ReportPayload:
    titles = {
        "object-summary": "分析对象",
        "execution-summary": "执行摘要",
        "quality": "质量评价",
        "obstacles": "障碍诊断",
        "conditional-specialty-results": "条件专项结果",
        "priority-remediation": "优先改良措施",
        "limitations": "限制与降级",
        "provenance": "数据与模型溯源",
    }
    return ReportPayload(
        title="单地块综合诊断与改良报告",
        sections=tuple(
            ReportSection(
                section_id=section_id,
                title=title,
                prose_template=(
                    prose_template if section_id == "quality" else "已验证内容。"
                ),
                fact_refs=fact_refs if section_id == "quality" else (),
                claim_ids=("claim-1",) if section_id == "quality" else (),
                source_ids=("doc-1:0:1",) if section_id == "quality" else (),
            )
            for section_id, title in titles.items()
        ),
        degradations=(), prompt_version="reporter-v1",
    )


def replace_agent(plan: DiagnosticPlan, old: str, new: str) -> DiagnosticPlan:
    payload = plan.model_dump(mode="python")
    for task in payload["tasks"]:
        if task["agent_id"] == old:
            task["agent_id"] = new
    return DiagnosticPlan.model_validate(payload)


def make_model4_always(plan: DiagnosticPlan) -> DiagnosticPlan:
    payload = deepcopy(plan.model_dump(mode="python"))
    for task in payload["tasks"]:
        if task["agent_id"] == "model-4":
            task["trigger"] = {"type": "always", "predicates": ()}
    return DiagnosticPlan.model_validate(payload)
~~~

其余只服务于单个测试文件的 fake（LLM、RAG、executor、runtime）在对应测试文件顶部显式定义；不要再引入未实现的共享 fixture 名称。

- [ ] **Step 6: 扩展能力目录**

给 <code>ProfessionalCapability</code> 增加：

~~~python
tool_name: str | None = None
result_schema: str | None = None
cost_class: Literal["standard", "high"] = "standard"
timeout_seconds: int = 90
retry_limit: int = 2
comprehensive_role: Literal["core", "optional", "disabled"] = "disabled"
allowed_triggers: tuple[str, ...] = ()
~~~

赋值固定为：

~~~python
COMPREHENSIVE_METADATA = {
    "model-1": {
        "tool_name": "model_1_stability_evaluation",
        "result_schema": "stability-v1",
        "comprehensive_role": "optional",
        "allowed_triggers": ("history_available",),
    },
    "model-2": {
        "tool_name": "model_2_quality_grade_evaluation",
        "result_schema": "quality-grade-v1",
        "comprehensive_role": "core",
        "allowed_triggers": ("always",),
    },
    "model-3": {
        "tool_name": "model_3_obstacle_diagnosis",
        "result_schema": "obstacle-v1",
        "comprehensive_role": "core",
        "allowed_triggers": ("always",),
    },
    "model-4": {
        "tool_name": "model_4_acidification_remediation",
        "result_schema": "acidification-v1",
        "comprehensive_role": "optional",
        "allowed_triggers": (
            "user_requested_acidification",
            "acidification_evidence",
        ),
    },
    "model-5": {
        "tool_name": "model_5_organic_matter_improvement",
        "result_schema": "organic-matter-v1",
        "comprehensive_role": "optional",
        "allowed_triggers": (
            "user_requested_organic_matter",
            "organic_matter_evidence",
        ),
    },
}
~~~

在构造五项能力时显式展开对应值；Model-6 显式写 <code>comprehensive_role="disabled"</code>。<code>public_capability_descriptor()</code> 返回这些只读字段，并增加：

~~~python
def public_comprehensive_capabilities() -> list[dict]:
    return [
        public_capability_descriptor(capability)
        for capability in PROFESSIONAL_CAPABILITIES
        if capability.comprehensive_role != "disabled"
    ]
~~~

- [ ] **Step 7: 运行测试并提交**

Run: <code>python -m pytest tests/comprehensive_workflow/test_contracts.py tests/test_professional_capabilities.py tests/test_question_type_router.py -q</code>

Expected: PASS，现有一对一路由测试不变。

~~~powershell
git add framework/agents/workflows/comprehensive/contracts.py framework/agents/workflows/comprehensive/state.py framework/agents/capabilities.py tests/comprehensive_workflow/factories.py tests/comprehensive_workflow/test_contracts.py tests/test_professional_capabilities.py
git commit -m "feat(workflow): define comprehensive contracts and capabilities"
~~~

---

### Task 3: 实现结构化角色调用、Coordinator 与 TrafficGate

**Files:**

- Create: <code>framework/agents/workflows/comprehensive/prompt_catalog.py</code>
- Create: <code>framework/agents/workflows/comprehensive/structured_roles.py</code>
- Create: <code>framework/agents/workflows/comprehensive/coordinator.py</code>
- Create: <code>tests/comprehensive_workflow/test_structured_roles.py</code>
- Create: <code>tests/comprehensive_workflow/test_coordinator.py</code>

**Interfaces:**

- Consumes: <code>llm_service.generate(prompt, messages) -&gt; dict</code> and <code>InteractionIntent</code>.
- Produces: <code>StructuredRoleRunner.generate(...)</code>、<code>Coordinator.classify(...)</code>、<code>TrafficGate.route(...)</code>.

- [ ] **Step 1: 写两次上限、无效 JSON 和保守回退测试**

~~~python
def test_structured_runner_stops_after_two_attempts(fake_llm):
    fake_llm.responses = [
        {"success": True, "content": "not-json"},
        {"success": True, "content": "{\"kind\":\"peer_chat\"}"},
    ]
    with pytest.raises(StructuredRoleError):
        runner(fake_llm).generate(
            role="coordinator",
            schema=InteractionIntent,
            payload={"message": "综合诊断"},
        )
    assert fake_llm.call_count == 2


def test_invalid_coordinator_output_never_upgrades_to_comprehensive():
    intent = coordinator_with_broken_llm.classify(
        "这块地怎么样",
        deterministic_question_type=3,
    )
    assert intent.kind is InteractionKind.SINGLE_ANALYSIS
    assert intent.reason_code == "DETERMINISTIC_FALLBACK"


def test_gate_rejects_non_parcel_comprehensive():
    route = TrafficGate().route(
        explicit_comprehensive_intent(),
        calculation_mode="spatial",
        object_type="county",
    )
    assert route == "unsupported"
~~~

- [ ] **Step 2: 运行测试并确认模块缺失**

Run: <code>python -m pytest tests/comprehensive_workflow/test_structured_roles.py tests/comprehensive_workflow/test_coordinator.py -q</code>

Expected: FAIL。

- [ ] **Step 3: 建立版本化 Prompt 目录**

~~~python
from dataclasses import dataclass


@dataclass(frozen=True)
class RolePrompt:
    role: str
    version: str
    system: str


PROMPTS = {
    "coordinator": RolePrompt(
        role="coordinator",
        version="coordinator-v1",
        system=(
            "你只做意图分类。只输出 JSON，不调用工具，不回答问题。"
            "kind 只能是 knowledge、single_analysis、"
            "comprehensive_analysis、unsupported。"
            "只有用户明确要求单地块综合诊断、综合报告或完整改良方案，"
            "才能输出 comprehensive_analysis。"
        ),
    ),
    "planner": RolePrompt(
        role="planner",
        version="planner-v1",
        system=(
            "你只从给定能力目录生成 DiagnosticPlan JSON。"
            "不得创建未知 agent、工具、输入或依赖。"
        ),
    ),
    "researcher": RolePrompt(
        role="researcher",
        version="researcher-v1",
        system=(
            "你只为给定 claim_id 生成知识库检索短语。"
            "不得修改模型事实，不得生成新数值。"
        ),
    ),
    "reporter": RolePrompt(
        role="reporter",
        version="reporter-v1",
        system=(
            "你只生成固定报告结构和事实引用占位符。"
            "不得直接写阿拉伯数字，不得删除降级信息。"
        ),
    ),
}
~~~

- [ ] **Step 4: 实现统一最多两次结构化调用**

~~~python
from typing import Callable, TypeVar

from pydantic import BaseModel, ValidationError

from .prompt_catalog import PROMPTS

T = TypeVar("T", bound=BaseModel)


class StructuredRoleError(RuntimeError):
    def __init__(self, role: str, errors: list[str]):
        super().__init__(f"{role} structured output failed")
        self.role = role
        self.errors = tuple(errors)


class StructuredRoleRunner:
    def __init__(self, llm):
        self._llm = llm

    def generate(
        self,
        *,
        role: str,
        schema: type[T],
        payload: dict,
        semantic_validator: Callable[[T], object] | None = None,
    ) -> T:
        errors: list[str] = []
        prompt_spec = PROMPTS[role]
        for attempt in range(2):
            repair = (
                ""
                if not errors
                else "\n上次错误：" + errors[-1] + "\n只修复该错误。"
            )
            response = self._llm.generate(
                prompt_spec.system + repair + "\n输入：" + json.dumps(
                    payload, ensure_ascii=False, sort_keys=True
                )
            )
            try:
                result = schema.model_validate_json(
                    strip_json_fence(response.get("content", ""))
                )
                if semantic_validator is not None:
                    semantic_validator(result)
                return result
            except (ValidationError, ValueError) as exc:
                errors.append(str(exc))
        raise StructuredRoleError(role, errors)
~~~

<code>strip_json_fence()</code> 只删除首尾一个 Markdown JSON fence；不做正则猜测或截取正文中的花括号。

- [ ] **Step 5: 实现 Coordinator 与确定性 Gate**

~~~python
class Coordinator:
    def __init__(self, runner: StructuredRoleRunner):
        self._runner = runner

    def classify(
        self,
        message: str,
        *,
        deterministic_question_type: int | None,
    ) -> InteractionIntent:
        try:
            return self._runner.generate(
                role="coordinator",
                schema=InteractionIntent,
                payload={"message": message},
            )
        except StructuredRoleError:
            kind = (
                InteractionKind.KNOWLEDGE
                if deterministic_question_type == 0
                else InteractionKind.SINGLE_ANALYSIS
            )
            return InteractionIntent(
                kind=kind,
                confidence=0,
                reason_code="DETERMINISTIC_FALLBACK",
                prompt_version="coordinator-v1",
            )


class TrafficGate:
    def route(
        self,
        intent: InteractionIntent,
        *,
        calculation_mode: str | None,
        object_type: str | None,
    ) -> str:
        if intent.kind is InteractionKind.KNOWLEDGE:
            return "knowledge"
        if intent.kind is InteractionKind.SINGLE_ANALYSIS:
            return "single_analysis"
        if intent.kind is InteractionKind.UNSUPPORTED:
            return "unsupported"
        if calculation_mode == "spatial" and object_type == "parcel":
            return "comprehensive_analysis"
        return "unsupported"
~~~

- [ ] **Step 6: 运行测试并提交**

Run: <code>python -m pytest tests/comprehensive_workflow/test_structured_roles.py tests/comprehensive_workflow/test_coordinator.py tests/test_llm_routing.py tests/test_question_type_router.py -q</code>

Expected: PASS。

~~~powershell
git add framework/agents/workflows/comprehensive/prompt_catalog.py framework/agents/workflows/comprehensive/structured_roles.py framework/agents/workflows/comprehensive/coordinator.py tests/comprehensive_workflow
git commit -m "feat(workflow): add constrained coordinator and traffic gate"
~~~

---

### Task 4: 实现 DiagnosticPlanner 与确定性 PlanValidator

**Files:**

- Create: <code>framework/agents/workflows/comprehensive/planner.py</code>
- Create: <code>tests/comprehensive_workflow/test_planner.py</code>
- Create: <code>tests/comprehensive_workflow/test_plan_validator.py</code>
- Create: <code>tests/comprehensive_workflow/test_planning_facts.py</code>

**Interfaces:**

- Consumes: <code>StructuredRoleRunner</code>、<code>PROFESSIONAL_CAPABILITIES</code>.
- Produces: <code>PlanningFactsResolver.resolve(...)</code>、<code>PlanValidator.validate(plan, facts) -&gt; DiagnosticPlan</code>、<code>DiagnosticPlanner.create_plan(...) -&gt; DiagnosticPlan</code>.

- [ ] **Step 1: 写核心任务、模型 6、依赖和第二波触发失败测试**

~~~python
def test_plan_requires_model2_and_model3():
    plan = plan_without("model-2")
    with pytest.raises(PlanValidationError, match="core_task_missing"):
        validator.validate(plan, PlanningFacts(history_available=False))


def test_model6_is_never_allowed():
    with pytest.raises(PlanValidationError, match="agent_not_allowed"):
        validator.validate(
            replace_agent(valid_plan(), "model-4", "model-6"),
            PlanningFacts(history_available=False),
        )


def test_model4_and_model5_must_be_conditional_second_wave_tasks():
    invalid = make_model4_always(valid_plan())
    with pytest.raises(PlanValidationError, match="invalid_trigger"):
        validator.validate(invalid, PlanningFacts(history_available=False))


def test_history_controls_model1_presence():
    no_history = validator.validate(
        plan_without("model-1"),
        PlanningFacts(history_available=False),
    )
    assert "model-1" not in {task.agent_id for task in no_history.tasks}
    with pytest.raises(PlanValidationError, match="model1_required"):
        validator.validate(
            plan_without("model-1"),
            PlanningFacts(history_available=True),
        )


def test_task_id_is_fixed_per_agent():
    payload = make_valid_plan_payload()
    payload["tasks"][0]["task_id"] = "planner-invented-id"
    with pytest.raises(PlanValidationError, match="unexpected_task_id"):
        validator.validate(
            DiagnosticPlan.model_validate(payload),
            PlanningFacts(history_available=False),
        )
~~~

在 <code>test_planning_facts.py</code> 用无数据库 fake source 覆盖历史判定和确定性关键词：

~~~python
@dataclass
class FakePlanningFactSource:
    history_count: int
    has_result: bool

    def count_history_snapshots(self, parcel_id: str) -> int:
        assert parcel_id == "P001"
        return self.history_count

    def has_stability_result(self, parcel_id: str) -> bool:
        assert parcel_id == "P001"
        return self.has_result


@pytest.mark.parametrize(
    "history_count,has_result,expected",
    [(2, False, True), (0, True, True), (1, False, False)],
)
def test_history_fact_requires_two_snapshots_or_existing_result(
    history_count, has_result, expected
):
    source = FakePlanningFactSource(
        history_count=history_count,
        has_result=has_result,
    )
    facts = PlanningFactsResolver(source).resolve(
        parcel_id="P001",
        user_message="生成综合诊断报告",
    )
    assert facts.history_available is expected


def test_request_terms_are_derived_without_llm():
    facts = PlanningFactsResolver(
        FakePlanningFactSource(history_count=0, has_result=False)
    ).resolve(
        parcel_id="P001",
        user_message="请给出酸化治理和有机质培肥方案",
    )
    assert facts.user_requested_acidification is True
    assert facts.user_requested_organic_matter is True
~~~

- [ ] **Step 2: 运行测试并确认 Validator 缺失**

Run: <code>python -m pytest tests/comprehensive_workflow/test_plan_validator.py -q</code>

Expected: FAIL。

- [ ] **Step 3: 实现规划事实与严格校验**

~~~python
import dataclasses
from dataclasses import dataclass
from typing import Protocol

from framework.models.thematic_model import (
    ParcelHistorySnapshot,
    StabilityRiskResult,
)


@dataclass(frozen=True)
class PlanningFacts:
    history_available: bool
    user_requested_acidification: bool = False
    user_requested_organic_matter: bool = False


class PlanningFactSource(Protocol):
    def count_history_snapshots(self, parcel_id: str) -> int: ...
    def has_stability_result(self, parcel_id: str) -> bool: ...


class OrmPlanningFactSource:
    def count_history_snapshots(self, parcel_id: str) -> int:
        return ParcelHistorySnapshot.query.filter_by(parcel_id=parcel_id).count()

    def has_stability_result(self, parcel_id: str) -> bool:
        return (
            StabilityRiskResult.query.filter_by(parcel_id=parcel_id)
            .order_by(StabilityRiskResult.created_at.desc())
            .first()
            is not None
        )


class PlanningFactsResolver:
    ACIDIFICATION_TERMS = ("酸化", "酸性", "提高pH", "改良酸土")
    ORGANIC_MATTER_TERMS = ("有机质", "培肥", "增施有机肥", "肥力提升")

    def __init__(self, source: PlanningFactSource):
        self._source = source

    def resolve(self, *, parcel_id: str, user_message: str) -> PlanningFacts:
        message = user_message.casefold()
        return PlanningFacts(
            history_available=(
                self._source.count_history_snapshots(parcel_id) >= 2
                or self._source.has_stability_result(parcel_id)
            ),
            user_requested_acidification=any(
                term.casefold() in message for term in self.ACIDIFICATION_TERMS
            ),
            user_requested_organic_matter=any(
                term.casefold() in message for term in self.ORGANIC_MATTER_TERMS
            ),
        )


class PlanValidationError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class PlanValidator:
    ALLOWED = frozenset(
        {"model-1", "model-2", "model-3", "model-4", "model-5"}
    )
    SECOND_WAVE = {
        "model-4": frozenset({
            "user_requested_acidification",
            "acidification_evidence",
        }),
        "model-5": frozenset({
            "user_requested_organic_matter",
            "organic_matter_evidence",
        }),
    }
    EXPECTED_TASK_IDS = {
        "model-1": "stability-risk",
        "model-2": "quality-evaluation",
        "model-3": "problem-diagnosis",
        "model-4": "acidification-remediation",
        "model-5": "organic-matter-improvement",
    }

    def validate(
        self, plan: DiagnosticPlan, facts: PlanningFacts
    ) -> DiagnosticPlan:
        by_agent = {task.agent_id: task for task in plan.tasks}
        if len(by_agent) != len(plan.tasks):
            raise PlanValidationError("duplicate_agent")
        if not set(by_agent) <= self.ALLOWED:
            raise PlanValidationError("agent_not_allowed")
        if any(
            task.task_id != self.EXPECTED_TASK_IDS[task.agent_id]
            for task in plan.tasks
        ):
            raise PlanValidationError("unexpected_task_id")
        if not {"model-2", "model-3"} <= set(by_agent):
            raise PlanValidationError("core_task_missing")
        for agent_id in ("model-2", "model-3"):
            task = by_agent[agent_id]
            if not task.required or task.depends_on:
                raise PlanValidationError("invalid_core_task")
            if task.trigger.type != "always":
                raise PlanValidationError("invalid_core_trigger")
        for agent_id, predicates in self.SECOND_WAVE.items():
            task = by_agent.get(agent_id)
            if task is None:
                raise PlanValidationError(f"{agent_id}_conditional_missing")
            if task.required or task.trigger.type != "any":
                raise PlanValidationError("invalid_trigger")
            if frozenset(task.trigger.predicates) != predicates:
                raise PlanValidationError("invalid_trigger")
            if not {"quality-evaluation", "problem-diagnosis"} & set(
                task.depends_on
            ):
                raise PlanValidationError("invalid_second_wave_dependency")
        if facts.history_available != ("model-1" in by_agent):
            raise PlanValidationError(
                "model1_required"
                if facts.history_available
                else "model1_forbidden"
            )
        model1 = by_agent.get("model-1")
        if model1 is not None and (
            model1.required
            or model1.depends_on
            or model1.trigger.type != "all"
            or model1.trigger.predicates != ("history_available",)
        ):
            raise PlanValidationError("invalid_model1_task")
        validate_existing_dependencies(plan.tasks)
        validate_acyclic(plan.tasks)
        return plan
~~~

<code>validate_existing_dependencies()</code> 拒绝未知 task_id；<code>validate_acyclic()</code> 使用三色 DFS，发现回边抛 <code>dependency_cycle</code>。

- [ ] **Step 4: 实现 Planner 共用两次总尝试**

~~~python
class DiagnosticPlanner:
    def __init__(
        self,
        runner: StructuredRoleRunner,
        validator: PlanValidator,
    ):
        self._runner = runner
        self._validator = validator

    def create_plan(
        self,
        *,
        request: dict,
        capabilities: list[dict],
        facts: PlanningFacts,
    ) -> DiagnosticPlan:
        return self._runner.generate(
            role="planner",
            schema=DiagnosticPlan,
            payload={
                "request": request,
                "capabilities": capabilities,
                "facts": dataclasses.asdict(facts),
                "required_core": ["model-2", "model-3"],
                "required_conditional": ["model-4", "model-5"],
            },
            semantic_validator=lambda plan: self._validator.validate(
                plan, facts
            ),
        )
~~~

- [ ] **Step 5: 写“第二次语义失败即停止”测试**

让 fake LLM 连续返回两个 schema 合法但都含 <code>model-6</code> 的计划，断言：

~~~python
with pytest.raises(StructuredRoleError):
    planner.create_plan(
        request={"message": "生成综合报告"},
        capabilities=capability_descriptors,
        facts=PlanningFacts(history_available=False),
    )
assert fake_llm.call_count == 2
~~~

- [ ] **Step 6: 运行测试并提交**

Run: <code>python -m pytest tests/comprehensive_workflow/test_planner.py tests/comprehensive_workflow/test_plan_validator.py tests/comprehensive_workflow/test_planning_facts.py -q</code>

Expected: PASS。

~~~powershell
git add framework/agents/workflows/comprehensive/planner.py tests/comprehensive_workflow/test_planner.py tests/comprehensive_workflow/test_plan_validator.py tests/comprehensive_workflow/test_planning_facts.py
git commit -m "feat(workflow): validate constrained diagnostic plans"
~~~

---

### Task 5: 实现地块输入解析与智能确认策略

**Files:**

- Create: <code>framework/agents/workflows/comprehensive/confirmation.py</code>
- Modify: <code>framework/domain/data/parcel_data_accessor.py</code>
- Create: <code>tests/comprehensive_workflow/test_input_resolver.py</code>
- Create: <code>tests/comprehensive_workflow/test_confirmation_policy.py</code>

**Interfaces:**

- Consumes: <code>DiagnosticPlan</code>、规范 parcel <code>AnalysisContext</code>、<code>ParcelInfo</code>.
- Produces: <code>ParcelInputResolver.resolve(...) -&gt; InputResolution</code>、<code>ConfirmationPolicy.decide(...) -&gt; ConfirmationDecision</code>、<code>confirmation_hash(...)</code>.

- [ ] **Step 1: 写数据库优先、缺输入和默认值确认测试**

~~~python
def test_resolver_reads_one_authoritative_parcel_snapshot(
    resolver, parcel_row
):
    result = resolver.resolve(
        valid_plan(),
        analysis_context=parcel_context("P001", version=4),
        user_values={},
    )
    assert result.object_version == 4
    assert result.task_arguments["quality-evaluation"]["parcel_id"] == "P001"
    assert result.resolved_values["soil_ph"].source == "parcel_db"
    assert resolver.accessor.snapshot_calls == ["P001"]


def test_missing_land_type_is_user_input_not_silent_upland_default(
    resolver, parcel_without_land_type
):
    result = resolver.resolve(
        valid_plan(),
        analysis_context=parcel_context("P001", version=4),
        user_values={},
    )
    assert "land_type" in result.missing_inputs


def test_result_affecting_default_requires_confirmation(policy):
    resolution = valid_resolution(
        proposed_defaults={"fertilizer_type": "compound"}
    )
    decision = policy.decide(
        plan=valid_plan(),
        resolution=resolution,
        previous_confirmation=None,
    )
    assert decision.interaction_state == "needs_confirmation"


def test_same_confirmed_hash_does_not_prompt_again(policy):
    resolution = valid_resolution(
        proposed_defaults={"fertilizer_type": "compound"}
    )
    digest = confirmation_hash(valid_plan(), resolution)
    decision = policy.decide(
        plan=valid_plan(),
        resolution=resolution,
        previous_confirmation={"confirmed": True, "hash": digest},
    )
    assert decision.interaction_state == "executing"
~~~

- [ ] **Step 2: 运行测试并确认失败**

Run: <code>python -m pytest tests/comprehensive_workflow/test_input_resolver.py tests/comprehensive_workflow/test_confirmation_policy.py -q</code>

Expected: FAIL。

- [ ] **Step 3: 给数据访问器增加一次性快照接口**

~~~python
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ParcelDataSnapshot:
    parcel_id: str
    area_code: str | None
    land_type: str | None
    fertilizer_type: str | None
    target_ph: float | None
    indicators: dict
    source_version: str


def get_parcel_snapshot(self, parcel_id: str) -> ParcelDataSnapshot | None:
    parcel = ParcelInfo.query.filter_by(parcel_id=parcel_id).first()
    if parcel is None:
        return None
    return ParcelDataSnapshot(
        parcel_id=parcel.parcel_id,
        area_code=parcel.area_code,
        land_type=parcel.land_type,
        fertilizer_type=parcel.fertilizer_type,
        target_ph=parcel.target_ph,
        indicators=dict(parcel.soil_indicators or {}),
        source_version=parcel.updated_at.isoformat(),
    )
~~~

该方法复用现有 app context 管理，但数据库异常必须抛可分类异常，不能与“未找到”一起返回 None。

- [ ] **Step 4: 实现 InputResolver**

~~~python
class ParcelInputResolver:
    def __init__(self, accessor: ParcelDataAccessor):
        self._accessor = accessor

    def resolve(
        self,
        plan: DiagnosticPlan,
        *,
        analysis_context: dict,
        user_values: dict[str, Any],
    ) -> InputResolution:
        obj = analysis_context["object"]
        if analysis_context["mode"] != "spatial" or obj["type"] != "parcel":
            raise ValueError("verified parcel context required")
        snapshot = self._accessor.get_parcel_snapshot(obj["id"])
        if snapshot is None:
            raise ValueError("parcel_snapshot_missing")
        values = build_resolved_value_map(snapshot, user_values)
        arguments = build_task_arguments(plan, snapshot, values)
        missing = tuple(sorted(find_missing_inputs(plan, arguments)))
        defaults = {}
        if "model-4" in {task.agent_id for task in plan.tasks}:
            if snapshot.fertilizer_type is None:
                defaults["fertilizer_type"] = "compound"
            if snapshot.target_ph is None:
                defaults["target_ph"] = 6.5
        return InputResolution(
            task_arguments=arguments,
            resolved_values=values,
            missing_inputs=missing,
            proposed_defaults=defaults,
            object_version=int(analysis_context["version"]),
        )
~~~

同时把 <code>ParcelDataAccessor.__init__</code> 改为接受显式 <code>app: Flask | None = None</code>；综合工作流必须传入当前应用，禁止在 worker 内递归调用 <code>create_app()</code>。保留无参数构造仅用于现有兼容路径，并为“显式 app 时不创建第二个 Flask app”增加回归测试。

<code>build_task_arguments()</code> 的固定映射：

- Model-1/2/3：规范 <code>parcel_id</code> 与权威 <code>area_code</code>；
- Model-4：<code>parcel_id</code>、<code>land_type</code>、<code>fertilizer_type</code>、<code>target_ph</code>；
- Model-5：<code>parcel_id</code>、<code>area_code</code>、<code>land_type</code>、完整 <code>indicators</code>。

用户只能补齐当前 <code>missing_inputs</code> 或确认 <code>proposed_defaults</code>；不能覆盖 <code>parcel_id</code>、<code>area_code</code>、对象版本或数据库已有指标。

- [ ] **Step 5: 实现确定性确认哈希和策略**

~~~python
@dataclass(frozen=True)
class ConfirmationDecision:
    interaction_state: str
    reason_codes: tuple[str, ...]
    confirmation_hash: str


def confirmation_hash(
    plan: DiagnosticPlan, resolution: InputResolution
) -> str:
    payload = {
        "plan": plan.model_dump(mode="json"),
        "object_version": resolution.object_version,
        "arguments": resolution.task_arguments,
        "defaults": resolution.proposed_defaults,
    }
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class ConfirmationPolicy:
    def decide(
        self,
        *,
        plan: DiagnosticPlan,
        resolution: InputResolution,
        previous_confirmation: dict | None,
    ) -> ConfirmationDecision:
        digest = confirmation_hash(plan, resolution)
        if resolution.missing_inputs:
            return ConfirmationDecision(
                "needs_input", ("MISSING_REQUIRED_INPUT",), digest
            )
        if (
            previous_confirmation
            and previous_confirmation.get("confirmed") is True
            and previous_confirmation.get("hash") == digest
        ):
            return ConfirmationDecision("executing", (), digest)
        reasons = []
        if resolution.proposed_defaults:
            reasons.append("RESULT_AFFECTING_DEFAULT")
        if any(task_cost(task.agent_id) == "high" for task in plan.tasks):
            reasons.append("HIGH_COST_TASK")
        if previous_confirmation and (
            previous_confirmation.get("hash") != digest
        ):
            reasons.append("CONFIRMED_CONTEXT_CHANGED")
        return ConfirmationDecision(
            "needs_confirmation" if reasons else "executing",
            tuple(reasons),
            digest,
        )
~~~

- [ ] **Step 6: 运行测试并提交**

Run: <code>python -m pytest tests/comprehensive_workflow/test_input_resolver.py tests/comprehensive_workflow/test_confirmation_policy.py tests/test_parcel_data_accessor.py -q</code>

Expected: PASS。

~~~powershell
git add framework/agents/workflows/comprehensive/confirmation.py framework/domain/data/parcel_data_accessor.py tests/comprehensive_workflow tests/test_parcel_data_accessor.py
git commit -m "feat(workflow): resolve parcel inputs and smart confirmation"
~~~

---

### Task 6: 建立受限工具执行与模型结果验证

**Files:**

- Modify: <code>framework/function_calling/specialized_tools.py</code>
- Create: <code>framework/agents/workflows/comprehensive/execution.py</code>
- Create: <code>tests/comprehensive_workflow/test_restricted_tools.py</code>
- Create: <code>tests/comprehensive_workflow/test_result_validator.py</code>
- Modify: <code>tests/test_specialized_tools.py</code>

**Interfaces:**

- Consumes: <code>DiagnosticTask</code>、<code>InputResolution.task_arguments</code>、现有 LangChain Tool.
- Produces: <code>get_specialized_tools_for(agent_ids) -&gt; dict[str, Tool]</code>、<code>ModelToolExecutor.invoke(...)</code>、<code>ResultValidator.validate(...) -&gt; TaskResult</code>.

- [ ] **Step 1: 写白名单、model-6 和对象冲突测试**

~~~python
def test_restricted_tool_map_contains_only_validated_agents():
    tools = get_specialized_tools_for({"model-2", "model-3"})
    assert set(tools) == {"model-2", "model-3"}


def test_restricted_tool_map_rejects_model6():
    with pytest.raises(ValueError, match="tool_not_registered"):
        get_specialized_tools_for({"model-6"})


def test_executor_rejects_argument_object_mismatch(executor):
    with pytest.raises(TaskExecutionError, match="analysis_object_conflict"):
        executor.invoke(
            quality_task(),
            arguments={"parcel_id": "P999"},
            execution_context=verified_execution_context("P001"),
        )
~~~

- [ ] **Step 2: 实现精确工具映射**

~~~python
AGENT_ID_TO_TOOL_NAME: Dict[str, str] = {
    agent_id: tool_name
    for tool_name, agent_id in TOOL_NAME_TO_AGENT_ID.items()
}


def get_specialized_tools_for(agent_ids: set[str]) -> Dict[str, Tool]:
    result: Dict[str, Tool] = {}
    for agent_id in sorted(agent_ids):
        tool_name = AGENT_ID_TO_TOOL_NAME.get(agent_id)
        tool = tool_registry.get(tool_name) if tool_name else None
        if tool is None:
            raise ValueError(f"tool_not_registered:{agent_id}")
        result[agent_id] = tool
    return result
~~~

不得在该函数中回退 <code>get_specialized_tools()</code> 全量列表。

- [ ] **Step 3: 实现直接工具执行器**

先修改五个 <code>_model_N_wrapper</code>：在现有公开参数末尾增加 keyword-only 的 <code>execution_context: dict[str, Any] | None = None</code>，但不把它加入任何 <code>args_schema</code>。wrapper 组装专业模型 payload 后，仅在值非空时执行 <code>payload["execution_context"] = execution_context</code>。这样现有快路径继续通过 <code>Tool.invoke()</code> 使用原 args schema；综合路径可以把后端验证的对象快照作为隐藏参数直接传入 wrapper。

~~~python
class TaskExecutionError(RuntimeError):
    def __init__(self, code: str, *, retryable: bool):
        super().__init__(code)
        self.code = code
        self.retryable = retryable


class ModelToolExecutor:
    LOCKED_KEYS = frozenset({"parcel_id", "parcel_code", "area_code"})

    def invoke(
        self,
        task: DiagnosticTask,
        *,
        arguments: dict[str, Any],
        execution_context: dict[str, Any],
    ) -> dict[str, Any]:
        obj = execution_context["analysis_context"]["object"]
        if arguments.get("parcel_id") != obj["id"]:
            raise TaskExecutionError(
                "analysis_object_conflict", retryable=False
            )
        tool = get_specialized_tools_for({task.agent_id})[task.agent_id]
        try:
            validated = tool.args_schema.model_validate(arguments)
            return tool.func(
                **validated.model_dump(),
                execution_context=execution_context,
            )
        except (TimeoutError, ConnectionError) as exc:
            raise TaskExecutionError(
                "transient_service_error", retryable=True
            ) from exc
        except Exception as exc:
            raise TaskExecutionError(
                "tool_execution_error", retryable=False
            ) from exc
~~~

不得把 <code>execution_context</code> 放进 Pydantic args schema、Prompt 或工具描述；LLM 永远看不到也不能生成该字段。综合路径在调用 <code>tool.func</code> 前使用原 <code>tool.args_schema</code> 校验，确保直接调用不会绕过公开参数校验。保留现有快路径 <code>Tool.invoke()</code> 行为。

- [ ] **Step 4: 写结果 schema 与溯源红灯测试**

~~~python
@pytest.mark.parametrize(
    "agent_id,payload,code",
    [
        ("model-2", {"quality_grade": "4"}, "missing_composite_index"),
        ("model-3", {"obstacle_type": "酸化"}, "missing_primary_factors"),
        ("model-4", {"ytk": 10.0}, "missing_unit"),
        ("model-5", {"dose": 20.0}, "missing_model_version"),
    ],
)
def test_result_validator_rejects_incomplete_payload(
    validator, agent_id, payload, code
):
    with pytest.raises(ResultValidationError, match=code):
        validator.validate(
            task_for(agent_id),
            raw_success(payload),
            execution_context=verified_execution_context("P001"),
        )
~~~

- [ ] **Step 5: 实现模型结果验证与统一 TaskResult**

~~~python
REQUIRED_PAYLOAD_KEYS = {
    "model-1": ("parcel_id", "stability_modules"),
    "model-2": ("parcel_id", "quality_grade", "composite_index"),
    "model-3": (
        "parcel_id",
        "obstacle_type",
        "primary_factors",
        "secondary_factors",
    ),
    "model-4": ("status", "result", "metadata"),
    "model-5": ("status", "result", "model_version"),
}


class ResultValidationError(ValueError):
    pass


class ResultValidator:
    def validate(
        self,
        task: DiagnosticTask,
        raw: dict[str, Any],
        *,
        execution_context: dict[str, Any],
    ) -> TaskResult:
        if raw.get("status") not in {"ok", "success"}:
            raise ResultValidationError(
                raw.get("reason") or "model_not_successful"
            )
        payload = dict(raw.get("result") or raw)
        for key in REQUIRED_PAYLOAD_KEYS[task.agent_id]:
            if payload.get(key) is None:
                raise ResultValidationError(f"missing_{key}")
        assert_result_object_matches(
            payload, execution_context["analysis_context"]["object"]["id"]
        )
        assert_numeric_units(task.agent_id, payload)
        provenance = extract_actual_provenance(raw, payload)
        if not provenance["model_version"]:
            raise ResultValidationError("missing_model_version")
        return TaskResult(
            task_id=task.task_id,
            agent_id=task.agent_id,
            status="succeeded",
            payload=payload,
            key_inputs=provenance["actual_inputs"],
            model_version=provenance["model_version"],
            data_as_of=provenance["data_as_of"],
            data_version=provenance["data_version"],
            calculated_at=provenance["calculated_at"],
            trace_id=execution_context["trace_id"],
        )
~~~

<code>assert_numeric_units()</code> 使用模型 schema 固定单位：Model-2 综合指数无量纲、Model-4 剂量 <code>kg/ha</code>、Model-5 剂量采用模型实际返回单位。它不得根据字段名猜测未知单位。

- [ ] **Step 6: 运行测试并提交**

Run: <code>python -m pytest tests/comprehensive_workflow/test_restricted_tools.py tests/comprehensive_workflow/test_result_validator.py tests/test_specialized_tools.py -q</code>

Expected: PASS。

~~~powershell
git add framework/function_calling/specialized_tools.py framework/agents/workflows/comprehensive/execution.py tests/comprehensive_workflow tests/test_specialized_tools.py
git commit -m "feat(workflow): restrict tools and validate model results"
~~~

---

### Task 7: 实现幂等两波调度、触发规则、重试和降级

**Files:**

- Modify: <code>framework/agents/workflows/comprehensive/execution.py</code>
- Create: <code>tests/comprehensive_workflow/test_trigger_evaluator.py</code>
- Create: <code>tests/comprehensive_workflow/test_scheduler.py</code>

**Interfaces:**

- Consumes: <code>ModelToolExecutor</code>、<code>ResultValidator</code>、validated <code>DiagnosticPlan</code>.
- Produces: <code>TriggerEvaluator.task_enabled(...)</code>、<code>ExecutionScheduler.execute(...) -&gt; ExecutionOutcome</code>.

- [ ] **Step 1: 写精确触发决策表**

~~~python
@pytest.mark.parametrize(
    "predicate,facts,expected",
    [
        ("history_available", {"history_available": True}, True),
        (
            "user_requested_acidification",
            {"user_requested_acidification": True},
            True,
        ),
        (
            "acidification_evidence",
            {
                "soil_ph": 5.2,
                "primary_factors": ["土壤酸化"],
            },
            True,
        ),
        (
            "acidification_evidence",
            {"soil_ph": 6.8, "primary_factors": []},
            False,
        ),
        (
            "organic_matter_evidence",
            {"primary_factors": ["有机质偏低"]},
            True,
        ),
    ],
)
def test_trigger_table(predicate, facts, expected):
    assert TriggerEvaluator().predicate(predicate, facts) is expected
~~~

- [ ] **Step 2: 写核心并行、第二波、重试和幂等测试**

~~~python
def test_core_wave_runs_model2_and_model3_before_optional(
    scheduler, recording_executor
):
    outcome = scheduler.execute(
        valid_plan(),
        resolution=complete_resolution(),
        existing_results={},
        execution_context=verified_execution_context("P001"),
        request_facts={"user_requested_acidification": False},
    )
    assert recording_executor.wave("model-2") == 1
    assert recording_executor.wave("model-3") == 1
    assert recording_executor.wave("model-4") == 2
    assert outcome.results["quality-evaluation"].status == "succeeded"


def test_resume_skips_existing_success(scheduler, recording_executor):
    existing = {"quality-evaluation": successful_model2_result()}
    scheduler.execute(
        valid_plan(),
        resolution=complete_resolution(),
        existing_results=existing,
        execution_context=verified_execution_context("P001"),
        request_facts={},
    )
    assert "model-2" not in recording_executor.calls


def test_transient_error_retries_twice_then_core_fails(
    scheduler, always_timeout_executor
):
    outcome = scheduler.execute(
        valid_plan(),
        resolution=complete_resolution(),
        existing_results={},
        execution_context=verified_execution_context("P001"),
        request_facts={},
    )
    assert always_timeout_executor.calls["model-2"] == 3
    assert outcome.final_state == "failed"
~~~

- [ ] **Step 3: 实现触发器**

~~~python
class TriggerEvaluator:
    def predicate(self, name: str, facts: dict[str, Any]) -> bool:
        if name == "history_available":
            return bool(facts.get("history_available"))
        if name == "user_requested_acidification":
            return bool(facts.get(name))
        if name == "user_requested_organic_matter":
            return bool(facts.get(name))
        factors = " ".join(
            str(value)
            for value in facts.get("primary_factors", [])
            + facts.get("secondary_factors", [])
        )
        if name == "acidification_evidence":
            ph = facts.get("soil_ph")
            return (
                any(token in factors for token in ("酸化", "酸性", "pH"))
                or isinstance(ph, (int, float)) and ph < 6.5
            )
        if name == "organic_matter_evidence":
            return any(
                token in factors for token in ("有机质", "培肥", "贫瘠")
            )
        raise ValueError(f"unknown_trigger:{name}")

    def task_enabled(
        self, task: DiagnosticTask, facts: dict[str, Any]
    ) -> bool:
        values = [
            self.predicate(name, facts)
            for name in task.trigger.predicates
        ]
        if task.trigger.type == "always":
            return True
        if task.trigger.type == "all":
            return all(values)
        return any(values)
~~~

- [ ] **Step 4: 实现并发分波和幂等重试**

~~~python
@dataclass(frozen=True)
class ExecutionOutcome:
    results: dict[str, TaskResult]
    attempts: dict[str, int]
    degradations: tuple[str, ...]
    final_state: str


def parse_existing_results(
    values: dict[str, dict[str, Any] | TaskResult],
) -> dict[str, TaskResult]:
    return {
        task_id: (
            value
            if isinstance(value, TaskResult)
            else TaskResult.model_validate(value)
        )
        for task_id, value in values.items()
    }


def failed_task_result(
    task: DiagnosticTask,
    *,
    trace_id: str,
    error_code: str,
) -> TaskResult:
    return TaskResult(
        task_id=task.task_id,
        agent_id=task.agent_id,
        status="failed",
        payload={},
        key_inputs={},
        model_version="unavailable",
        data_as_of=None,
        data_version=None,
        calculated_at=datetime.now(timezone.utc).isoformat(),
        trace_id=trace_id,
        error_code=error_code,
    )


def derive_trigger_facts(
    results: dict[str, TaskResult],
    resolution: InputResolution,
    request_facts: dict[str, Any],
) -> dict[str, Any]:
    facts = dict(request_facts)
    facts.update({
        key: value.value
        for key, value in resolution.resolved_values.items()
    })
    obstacle = results.get("problem-diagnosis")
    if obstacle is not None and obstacle.status == "succeeded":
        facts["primary_factors"] = list(
            obstacle.payload.get("primary_factors") or []
        )
        facts["secondary_factors"] = list(
            obstacle.payload.get("secondary_factors") or []
        )
    return facts


class ExecutionScheduler:
    def __init__(
        self,
        executor: ModelToolExecutor,
        validator: ResultValidator,
        trigger_evaluator: TriggerEvaluator,
        app,
        *,
        max_workers: int,
    ):
        self._executor = executor
        self._validator = validator
        self._triggers = trigger_evaluator
        self._app = app
        self._max_workers = max_workers

    def execute(
        self,
        plan: DiagnosticPlan,
        *,
        resolution: InputResolution,
        existing_results: dict[str, dict],
        execution_context: dict[str, Any],
        request_facts: dict[str, Any],
    ) -> ExecutionOutcome:
        results = parse_existing_results(existing_results)
        attempts: dict[str, int] = {}
        degradations: list[str] = []
        core = [
            task for task in plan.tasks
            if task.agent_id in {"model-2", "model-3", "model-1"}
            and self._triggers.task_enabled(task, request_facts)
        ]
        self._run_wave(
            core, results, attempts, degradations,
            resolution, execution_context,
        )
        if any(
            task.required
            and (
                task.task_id not in results
                or results[task.task_id].status != "succeeded"
            )
            for task in core
        ):
            return ExecutionOutcome(
                results, attempts, tuple(degradations), "failed"
            )
        derived = derive_trigger_facts(
            results, resolution, request_facts
        )
        optional = [
            task for task in plan.tasks
            if task.agent_id in {"model-4", "model-5"}
            and self._triggers.task_enabled(task, derived)
        ]
        self._run_wave(
            optional, results, attempts, degradations,
            resolution, execution_context,
        )
        return ExecutionOutcome(
            results,
            attempts,
            tuple(degradations),
            "validating",
        )

    def _run_wave(
        self,
        tasks: list[DiagnosticTask],
        results: dict[str, TaskResult],
        attempts: dict[str, int],
        degradations: list[str],
        resolution: InputResolution,
        execution_context: dict[str, Any],
    ) -> None:
        pending = [
            task for task in tasks
            if not (
                task.task_id in results
                and results[task.task_id].status == "succeeded"
            )
        ]
        if not pending:
            return
        workers = min(self._max_workers, len(pending))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(
                    self._run_one,
                    task,
                    resolution.task_arguments[task.task_id],
                    execution_context,
                ): task
                for task in pending
            }
            for future in as_completed(futures):
                task = futures[future]
                result, used_attempts = future.result()
                results[task.task_id] = result
                attempts[task.task_id] = used_attempts
                if not task.required and result.status != "succeeded":
                    degradations.append(
                        f"{task.agent_id}:{result.error_code}"
                    )

    def _run_one(
        self,
        task: DiagnosticTask,
        arguments: dict[str, Any],
        execution_context: dict[str, Any],
    ) -> tuple[TaskResult, int]:
        trace_id = execution_context["trace_id"]
        for attempt in range(1, 4):
            try:
                with self._app.app_context():
                    raw = self._executor.invoke(
                        task,
                        arguments=arguments,
                        execution_context=execution_context,
                    )
                return (
                    self._validator.validate(
                        task,
                        raw,
                        execution_context=execution_context,
                    ),
                    attempt,
                )
            except ResultValidationError as exc:
                return (
                    failed_task_result(
                        task,
                        trace_id=trace_id,
                        error_code=str(exc),
                    ),
                    attempt,
                )
            except TaskExecutionError as exc:
                if not exc.retryable or attempt == 3:
                    return (
                        failed_task_result(
                            task,
                            trace_id=trace_id,
                            error_code=exc.code,
                        ),
                        attempt,
                    )
        raise AssertionError("retry_loop_exhausted_without_result")
~~~

文件顶部导入 <code>ThreadPoolExecutor</code>、<code>as_completed</code>、<code>datetime</code> 和 <code>timezone</code>。只有主线程写 <code>results</code>/<code>attempts</code>/<code>degradations</code>；worker 只返回不可变结果。<code>_run_one()</code> 最多进行 3 次总尝试，只在 <code>TaskExecutionError.retryable=True</code> 时继续；结果验证错误不重试。可选任务失败写 <code>degradations</code>，核心任务失败由上层转 <code>failed</code>。

- [ ] **Step 5: 验证两个核心任务真正并行**

使用 <code>threading.Barrier(2)</code> fake executor；两个核心任务都必须进入 barrier 才能返回。测试设置 2 秒超时，串行实现会 FAIL，并行实现 PASS。不要用易抖动的毫秒耗时断言。

- [ ] **Step 6: 运行测试并提交**

Run: <code>python -m pytest tests/comprehensive_workflow/test_trigger_evaluator.py tests/comprehensive_workflow/test_scheduler.py -q</code>

Expected: PASS。

~~~powershell
git add framework/agents/workflows/comprehensive/execution.py tests/comprehensive_workflow/test_trigger_evaluator.py tests/comprehensive_workflow/test_scheduler.py
git commit -m "feat(workflow): schedule idempotent two-wave diagnostics"
~~~

---

### Task 8: 实现证据绑定和不可篡改数值的报告链

**Files:**

- Modify: <code>framework/rag/chain.py</code>
- Create: <code>framework/agents/workflows/comprehensive/evidence.py</code>
- Create: <code>framework/agents/workflows/comprehensive/reporting.py</code>
- Create: <code>tests/comprehensive_workflow/test_evidence.py</code>
- Create: <code>tests/comprehensive_workflow/test_reporting.py</code>
- Modify: <code>tests/test_rag.py</code>

**Interfaces:**

- Consumes: validated <code>TaskResult</code> only, <code>rag_chain.search_documents()</code>, <code>ResultProvenanceBuilder</code>.
- Produces: <code>canonical_claims_from_results(...)</code>、<code>EvidenceResearcher.research(...) -&gt; EvidenceBundle</code>、<code>Reporter.compose(...) -&gt; ReportPayload</code>、<code>ReportPolicyValidator.validate_and_render(...) -&gt; str</code>、<code>AggregateProvenanceBuilder.build(...) -&gt; dict</code>.

- [ ] **Step 1: 增加不调用通用 LLM 的检索接口**

测试：

~~~python
def test_search_documents_returns_raw_local_results_without_generation(
    rag_chain, monkeypatch
):
    monkeypatch.setattr(
        rag_chain.llm_service,
        "generate",
        lambda *args, **kwargs: pytest.fail("LLM must not run"),
    )
    results = rag_chain.search_documents("酸化改良依据")
    assert results[0]["metadata"]["source"] == "doc-1"
~~~

实现：

~~~python
def search_documents(
    self,
    query: str,
    *,
    valid_doc_names: set[str] | None = None,
) -> list[dict[str, Any]]:
    return list(
        self._retrieve_documents(query, valid_doc_names)["results"]
    )
~~~

- [ ] **Step 2: 写 evidence claim/source 绑定和 RAG 降级测试**

~~~python
def test_researcher_binds_only_declared_claim_ids(researcher):
    bundle = researcher.research(
        task_results=validated_results(),
        claims=canonical_claims(),
    )
    valid_claims = {claim["claim_id"] for claim in canonical_claims()}
    assert {
        claim_id
        for item in bundle.items
        for claim_id in item.claim_ids
    } <= valid_claims


def test_rag_failure_returns_degradation_not_general_knowledge(
    researcher_with_broken_rag,
):
    result = researcher_with_broken_rag.research_safe(
        task_results=validated_results(),
        claims=canonical_claims(),
    )
    assert result.bundle.items == ()
    assert result.degradation == "evidence_retrieval_unavailable"
~~~

- [ ] **Step 3: 实现 EvidenceResearcher**

~~~python
def canonical_claims_from_results(
    task_results: dict[str, TaskResult],
) -> list[dict[str, str]]:
    claims: list[dict[str, str]] = []
    obstacle = task_results.get("problem-diagnosis")
    if obstacle is not None and obstacle.status == "succeeded":
        factors = (
            list(obstacle.payload.get("primary_factors") or [])
            + list(obstacle.payload.get("secondary_factors") or [])
        )
        for index, factor in enumerate(factors):
            claims.append({
                "claim_id": f"obstacle-{index + 1}",
                "text": f"{factor}的成因与改良依据",
                "kind": "obstacle-explanation",
            })
    for task_id in (
        "acidification-remediation",
        "organic-matter-improvement",
    ):
        result = task_results.get(task_id)
        if result is not None and result.status == "succeeded":
            claims.append({
                "claim_id": f"{result.agent_id}-recommendation",
                "text": f"{result.agent_id}改良措施的适用依据",
                "kind": "recommendation-basis",
            })
    return claims


class EvidenceQuery(StrictModel):
    claim_id: str
    query: str = Field(min_length=2, max_length=120)


class EvidenceQueries(StrictModel):
    queries: tuple[EvidenceQuery, ...] = Field(max_length=12)


@dataclass(frozen=True)
class EvidenceResearchOutcome:
    bundle: EvidenceBundle
    degradation: str | None


class EvidenceUnavailable(RuntimeError):
    pass


class EvidenceResearcher:
    def __init__(self, runner: StructuredRoleRunner, rag):
        self._runner = runner
        self._rag = rag

    def research(
        self,
        *,
        task_results: dict[str, TaskResult],
        claims: list[dict[str, str]],
    ) -> EvidenceBundle:
        allowed = {claim["claim_id"] for claim in claims}
        queries = self._runner.generate(
            role="researcher",
            schema=EvidenceQueries,
            payload={"claims": claims},
            semantic_validator=lambda value: validate_claim_ids(
                value, allowed
            ),
        )
        items = []
        for query in queries.queries:
            try:
                hits = self._rag.search_documents(query.query)
            except (TimeoutError, ConnectionError) as exc:
                raise EvidenceUnavailable("rag_unavailable") from exc
            for hit in hits:
                metadata = hit.get("metadata") or {}
                source = str(metadata.get("source", "unknown"))
                chunk = metadata.get("chunk_index")
                page = metadata.get("page")
                items.append(EvidenceItem(
                    source_id=f"{source}:{chunk}:{page}",
                    doc_name=str(metadata.get("doc_name") or source),
                    chunk_index=chunk,
                    page=page,
                    claim_ids=(query.claim_id,),
                    score=hit.get("score"),
                ))
        return EvidenceBundle(items=tuple(dedupe_evidence(items)))

    def research_safe(
        self,
        *,
        task_results: dict[str, TaskResult],
        claims: list[dict[str, str]],
    ) -> EvidenceResearchOutcome:
        try:
            return EvidenceResearchOutcome(
                self.research(task_results=task_results, claims=claims),
                None,
            )
        except (EvidenceUnavailable, StructuredRoleError):
            return EvidenceResearchOutcome(
                EvidenceBundle(
                    items=(),
                    unsupported_claims=tuple(
                        claim["claim_id"] for claim in claims
                    ),
                ),
                "evidence_retrieval_unavailable",
            )
~~~

- [ ] **Step 4: 写 Reporter 数值防篡改和修订上限测试**

~~~python
def test_reporter_cannot_introduce_raw_numbers(validator):
    payload = report_payload(
        prose_template="建议施用 999 kg/ha",
        fact_refs=(),
    )
    with pytest.raises(ReportValidationError, match="raw_number_forbidden"):
        validator.validate_and_render(
            payload,
            task_results=validated_results(),
            evidence=valid_evidence(),
        )


def test_fact_reference_renders_exact_model_value(validator):
    payload = report_payload(
        prose_template="综合指数为 [[fact:model-2.composite_index]]。",
        fact_refs=("model-2.composite_index",),
    )
    rendered = validator.validate_and_render(
        payload,
        task_results=validated_results(composite_index=0.734),
        evidence=valid_evidence(),
    )
    assert "0.734" in rendered


def test_fourth_user_revision_is_rejected(report_service):
    with pytest.raises(ReportRevisionLimit):
        report_service.revise(
            existing_payload=valid_report(),
            user_comment="再改一次",
            current_revision_count=3,
        )
~~~

- [ ] **Step 5: 实现事实引用表和报告校验**

~~~python
FACT_TOKEN = re.compile(r"\[\[fact:([a-z0-9.-]+)\]\]")
RAW_NUMBER = re.compile(r"(?<![a-zA-Z])\d+(?:\.\d+)?")
REQUIRED_SECTION_IDS = (
    "object-summary",
    "execution-summary",
    "quality",
    "obstacles",
    "conditional-specialty-results",
    "priority-remediation",
    "limitations",
    "provenance",
)


def flatten_scalar_payload(
    value: Any,
    *,
    prefix: str = "",
) -> Iterator[tuple[str, str | int | float, str | None]]:
    if isinstance(value, dict):
        if (
            set(value) >= {"value", "unit"}
            and isinstance(value["value"], (str, int, float))
            and not isinstance(value["value"], bool)
        ):
            yield prefix, value["value"], str(value["unit"])
            return
        for key, child in value.items():
            child_path = f"{prefix}.{key}" if prefix else key
            yield from flatten_scalar_payload(child, prefix=child_path)
        return
    if isinstance(value, (str, int, float)) and not isinstance(value, bool):
        yield prefix, value, None


def format_fact(value: str | int | float, unit: str | None) -> str:
    if isinstance(value, float):
        rendered = format(value, ".15g")
    else:
        rendered = str(value)
    return f"{rendered} {unit}".rstrip() if unit else rendered


def build_fact_table(results: dict[str, TaskResult]) -> dict[str, str]:
    table: dict[str, str] = {}
    for result in results.values():
        if result.status != "succeeded":
            continue
        for path, value, unit in flatten_scalar_payload(result.payload):
            table[f"{result.agent_id}.{path}"] = format_fact(value, unit)
    return table


class ReportPolicyValidator:
    def validate_and_render(
        self,
        payload: ReportPayload,
        *,
        task_results: dict[str, TaskResult],
        evidence: EvidenceBundle,
        expected_degradations: tuple[str, ...] = (),
        expected_claim_ids: tuple[str, ...] = (),
    ) -> str:
        facts = build_fact_table(task_results)
        valid_sources = {item.source_id for item in evidence.items}
        section_ids = tuple(section.section_id for section in payload.sections)
        if section_ids != REQUIRED_SECTION_IDS:
            raise ReportValidationError("required_sections_mismatch")
        if payload.degradations != expected_degradations:
            raise ReportValidationError("degradations_mismatch")
        referenced_claim_ids: set[str] = set()
        rendered_sections = []
        for section in payload.sections:
            if RAW_NUMBER.search(FACT_TOKEN.sub("", section.prose_template)):
                raise ReportValidationError("raw_number_forbidden")
            if not set(section.fact_refs) <= set(facts):
                raise ReportValidationError("unknown_fact_reference")
            if not set(section.source_ids) <= valid_sources:
                raise ReportValidationError("unknown_source_reference")
            for claim_id in section.claim_ids:
                supporting_sources = {
                    item.source_id
                    for item in evidence.items
                    if claim_id in item.claim_ids
                }
                if not supporting_sources & set(section.source_ids):
                    raise ReportValidationError("claim_source_mismatch")
                referenced_claim_ids.add(claim_id)
            text = FACT_TOKEN.sub(
                lambda match: facts[match.group(1)],
                section.prose_template,
            )
            rendered_sections.append(f"## {section.title}\n\n{text}")
        if set(expected_claim_ids) - referenced_claim_ids:
            raise ReportValidationError("required_claim_unreferenced")
        return "# " + payload.title + "\n\n" + "\n\n".join(
            rendered_sections
        )
~~~

- [ ] **Step 6: 实现 Reporter 两次内部尝试和用户修订**

~~~python
class Reporter:
    def __init__(
        self,
        runner: StructuredRoleRunner,
        validator: ReportPolicyValidator,
    ):
        self._runner = runner
        self._validator = validator

    def compose(
        self,
        *,
        task_results: dict[str, TaskResult],
        claims: list[dict[str, str]],
        evidence: EvidenceBundle,
        degradations: tuple[str, ...],
        revision_comment: str = "",
    ) -> tuple[ReportPayload, str]:
        payload = self._runner.generate(
            role="reporter",
            schema=ReportPayload,
            payload=reporter_input(
                task_results,
                claims,
                evidence,
                degradations,
                revision_comment,
            ),
            semantic_validator=lambda value: (
                self._validator.validate_and_render(
                    value,
                    task_results=task_results,
                    evidence=evidence,
                    expected_degradations=degradations,
                    expected_claim_ids=tuple(
                        claim["claim_id"]
                        for claim in claims
                        if claim["claim_id"] not in evidence.unsupported_claims
                    ),
                )
            ),
        )
        rendered = self._validator.validate_and_render(
            payload,
            task_results=task_results,
            evidence=evidence,
            expected_degradations=degradations,
            expected_claim_ids=tuple(
                claim["claim_id"]
                for claim in claims
                if claim["claim_id"] not in evidence.unsupported_claims
            ),
        )
        return payload, rendered

    def revise(self, *, current_revision_count: int, **kwargs):
        if current_revision_count >= 3:
            raise ReportRevisionLimit("report_revision_limit")
        payload, rendered = self.compose(**kwargs)
        return payload, rendered, current_revision_count + 1
~~~

- [ ] **Step 7: 聚合前置计划的逐模型溯源**

~~~python
class AggregateProvenanceBuilder:
    def __init__(self, result_builder: ResultProvenanceBuilder):
        self._result_builder = result_builder

    def build(
        self,
        *,
        analysis_context: dict[str, Any],
        task_results: dict[str, TaskResult],
        evidence: EvidenceBundle,
        prompt_versions: dict[str, str],
        trace_id: str,
    ) -> dict[str, Any]:
        context = AnalysisContext.from_dict(analysis_context)
        model_runs = []
        for result in task_results.values():
            if result.status != "succeeded":
                continue
            capability = CAPABILITY_BY_AGENT_ID[result.agent_id]
            model_runs.append(self._result_builder.build(
                trace_id=trace_id,
                analysis_context=context,
                capability=capability,
                agent_result={
                    "model_version": result.model_version,
                    "data_as_of": result.data_as_of,
                    "data_version": result.data_version,
                    "actual_inputs": result.key_inputs,
                },
                calculated_at=datetime.fromisoformat(
                    result.calculated_at.replace("Z", "+00:00")
                ),
            ))
        return {
            "trace_id": trace_id,
            "analysis_context": analysis_context,
            "model_runs": model_runs,
            "prompt_versions": dict(prompt_versions),
            "source_ids": sorted(
                item.source_id for item in evidence.items
            ),
        }
~~~

- [ ] **Step 8: 运行测试并提交**

Run: <code>python -m pytest tests/comprehensive_workflow/test_evidence.py tests/comprehensive_workflow/test_reporting.py tests/test_rag.py -q</code>

Expected: PASS。

~~~powershell
git add framework/rag/chain.py framework/agents/workflows/comprehensive/evidence.py framework/agents/workflows/comprehensive/reporting.py tests/comprehensive_workflow tests/test_rag.py
git commit -m "feat(workflow): ground comprehensive reports in validated facts"
~~~

---

### Task 9: 组装可中断、可恢复的 LangGraph 综合子图

**Files:**

- Create: <code>framework/agents/workflows/comprehensive/graph.py</code>
- Create: <code>framework/agents/workflows/comprehensive/runtime.py</code>
- Modify: <code>framework/agents/workflows/comprehensive/state.py</code>
- Create: <code>tests/comprehensive_workflow/test_graph.py</code>
- Create: <code>tests/comprehensive_workflow/test_resume.py</code>

**Interfaces:**

- Consumes: Tasks 4—8 services and <code>BaseCheckpointSaver</code>.
- Produces: <code>build_default_comprehensive_services(app)</code>、<code>build_comprehensive_graph(services, checkpointer)</code>、<code>ComprehensiveWorkflowRuntime.run_initial(...)</code>、<code>resume(...)</code>、<code>WorkflowOutput</code>.

- [ ] **Step 1: 写缺输入 interrupt、同 thread resume 和版本冲突测试**

~~~python
def test_missing_input_interrupts_without_execution(runtime, services):
    output = runtime.run_initial(valid_initial_request_missing_land_type())
    assert output.interaction_state == "needs_input"
    assert output.checkpoint_version == 1
    assert services.executor.calls == []


def test_resume_uses_same_thread_and_executes_once(runtime, services):
    first = runtime.run_initial(valid_initial_request_missing_land_type())
    second = runtime.resume(
        conversation_id=12,
        response=InteractionResponse(
            run_id=first.run_id,
            expected_checkpoint_version=first.checkpoint_version,
            action="provide_input",
            values={"land_type": "upland"},
        ),
    )
    assert second.run_id == first.run_id
    assert services.executor.calls.count("model-2") == 1


def test_stale_checkpoint_version_is_409_domain_error(runtime):
    first = runtime.run_initial(valid_initial_request_missing_land_type())
    with pytest.raises(WorkflowConflict):
        runtime.resume(
            conversation_id=12,
            response=resume_response(
                first.run_id,
                expected_checkpoint_version=first.checkpoint_version - 1,
            ),
        )
~~~

- [ ] **Step 2: 定义节点服务容器和状态初始化**

~~~python
@dataclass(frozen=True)
class ComprehensiveServices:
    planning_facts_resolver: PlanningFactsResolver
    planner: DiagnosticPlanner
    input_resolver: ParcelInputResolver
    confirmation_policy: ConfirmationPolicy
    scheduler: ExecutionScheduler
    researcher: EvidenceResearcher
    reporter: Reporter
    provenance_builder: AggregateProvenanceBuilder


def build_default_comprehensive_services(app) -> ComprehensiveServices:
    runner = StructuredRoleRunner(llm_service)
    report_validator = ReportPolicyValidator()
    return ComprehensiveServices(
        planning_facts_resolver=PlanningFactsResolver(
            OrmPlanningFactSource()
        ),
        planner=DiagnosticPlanner(runner, PlanValidator()),
        input_resolver=ParcelInputResolver(ParcelDataAccessor(app=app)),
        confirmation_policy=ConfirmationPolicy(),
        scheduler=ExecutionScheduler(
            ModelToolExecutor(),
            ResultValidator(),
            TriggerEvaluator(),
            app,
            max_workers=3,
        ),
        researcher=EvidenceResearcher(runner, rag_chain),
        reporter=Reporter(runner, report_validator),
        provenance_builder=AggregateProvenanceBuilder(
            ResultProvenanceBuilder()
        ),
    )


def plan_node(
    state: ComprehensiveDiagnosticState,
    services: ComprehensiveServices,
) -> dict[str, Any]:
    request = state["normalized_request"]
    parcel_id = state["analysis_context_snapshot"]["object"]["id"]
    facts = services.planning_facts_resolver.resolve(
        parcel_id=parcel_id,
        user_message=request["question"],
    )
    plan = services.planner.create_plan(
        request=request,
        capabilities=public_comprehensive_capabilities(),
        facts=facts,
    )
    return {
        "planning_facts": dataclasses.asdict(facts),
        "request_facts": {
            "history_available": facts.history_available,
            "user_requested_acidification": (
                facts.user_requested_acidification
            ),
            "user_requested_organic_matter": (
                facts.user_requested_organic_matter
            ),
        },
        "diagnostic_plan": plan.model_dump(mode="json"),
        "interaction_state": "planned",
    }


def initial_state(request: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id": request["run_id"],
        "trace_id": request["trace_id"],
        "conversation_id": request["conversation_id"],
        "user_id": request["user_id"],
        "checkpoint_version": 0,
        "interaction_state": "received",
        "normalized_request": request,
        "analysis_context_snapshot": request["analysis_context"],
        "object_version": request["analysis_context"]["version"],
        "task_results": {},
        "task_attempts": {},
        "validation_issues": [],
        "degradations": [],
        "report_revision_count": 0,
        "report_validation_attempts": 0,
        "error": None,
    }
~~~

同一文件实现三个有副作用节点，并且只把 JSON 化结果写回状态：

~~~python
def execute_node(
    state: ComprehensiveDiagnosticState,
    services: ComprehensiveServices,
) -> dict[str, Any]:
    outcome = services.scheduler.execute(
        DiagnosticPlan.model_validate(state["diagnostic_plan"]),
        resolution=InputResolution.model_validate(state["resolved_inputs"]),
        existing_results=state.get("task_results", {}),
        execution_context={
            "analysis_context": state["analysis_context_snapshot"],
            "trace_id": state["trace_id"],
            "run_id": state["run_id"],
        },
        request_facts=state["request_facts"],
    )
    return {
        "task_results": {
            task_id: result.model_dump(mode="json")
            for task_id, result in outcome.results.items()
        },
        "task_attempts": outcome.attempts,
        "degradations": list(outcome.degradations),
        "interaction_state": outcome.final_state,
    }


def research_node(
    state: ComprehensiveDiagnosticState,
    services: ComprehensiveServices,
) -> dict[str, Any]:
    results = parse_existing_results(state["task_results"])
    claims = canonical_claims_from_results(results)
    outcome = services.researcher.research_safe(
        task_results=results,
        claims=claims,
    )
    degradations = list(state.get("degradations", []))
    if outcome.degradation and outcome.degradation not in degradations:
        degradations.append(outcome.degradation)
    return {
        "canonical_claims": claims,
        "evidence_items": [
            item.model_dump(mode="json") for item in outcome.bundle.items
        ],
        "unsupported_claims": list(
            outcome.bundle.unsupported_claims
        ),
        "degradations": degradations,
        "interaction_state": "reporting",
    }


def report_node(
    state: ComprehensiveDiagnosticState,
    services: ComprehensiveServices,
) -> dict[str, Any]:
    results = parse_existing_results(state["task_results"])
    evidence = EvidenceBundle(
        items=tuple(
            EvidenceItem.model_validate(item)
            for item in state.get("evidence_items", [])
        ),
        unsupported_claims=tuple(state.get("unsupported_claims", [])),
    )
    kwargs = {
        "task_results": results,
        "claims": state.get("canonical_claims", []),
        "evidence": evidence,
        "degradations": tuple(state.get("degradations", [])),
        "revision_comment": state.get("revision_comment", ""),
    }
    current_count = int(state.get("report_revision_count", 0))
    if state.get("revision_comment"):
        payload, rendered, next_count = services.reporter.revise(
            current_revision_count=current_count,
            **kwargs,
        )
    else:
        payload, rendered = services.reporter.compose(**kwargs)
        next_count = current_count
    provenance = services.provenance_builder.build(
        analysis_context=state["analysis_context_snapshot"],
        task_results=results,
        evidence=evidence,
        prompt_versions={
            "planner": state["diagnostic_plan"]["planner_prompt_version"],
            "reporter": payload.prompt_version,
        },
        trace_id=state["trace_id"],
    )
    return {
        "report_payload": payload.model_dump(mode="json"),
        "report_draft": rendered,
        "report_revision_count": next_count,
        "revision_comment": "",
        "provenance": provenance,
        "interaction_state": "awaiting_release",
    }
~~~

<code>execute_node</code> 只有在核心结果全部验证成功时才路由到 research；<code>failed</code> 直接结束且不生成正式报告。中断发生在后续确认/发布节点，因此正常 HITL 恢复读取已 checkpoint 的 <code>task_results</code>，不会重新进入模型节点。

- [ ] **Step 3: 实现输入/确认中断节点**

~~~python
from langgraph.types import interrupt


def input_node(
    state: ComprehensiveDiagnosticState,
    services: ComprehensiveServices,
) -> dict[str, Any]:
    resolution = services.input_resolver.resolve(
        DiagnosticPlan.model_validate(state["diagnostic_plan"]),
        analysis_context=state["analysis_context_snapshot"],
        user_values=state["normalized_request"].get("user_values", {}),
    )
    return {
        "resolved_inputs": resolution.model_dump(mode="json"),
        "missing_inputs": list(resolution.missing_inputs),
        "proposed_defaults": dict(resolution.proposed_defaults),
        "object_version": resolution.object_version,
        "interaction_state": "resolving",
    }


def confirmation_node(
    state: ComprehensiveDiagnosticState,
    services: ComprehensiveServices,
):
    decision = services.confirmation_policy.decide(
        plan=DiagnosticPlan.model_validate(state["diagnostic_plan"]),
        resolution=InputResolution.model_validate(
            state["resolved_inputs"]
        ),
        previous_confirmation=state.get("confirmation"),
    )
    if decision.interaction_state == "executing":
        return {
            "interaction_state": "executing",
            "plan_hash": decision.confirmation_hash,
        }
    version = state.get("checkpoint_version", 0) + 1
    response = interrupt({
        "interaction_state": decision.interaction_state,
        "run_id": state["run_id"],
        "checkpoint_version": version,
        "reason_codes": list(decision.reason_codes),
        "missing_inputs": state.get("missing_inputs", []),
        "proposed_defaults": state.get("proposed_defaults", {}),
    })
    validated = InteractionResponse.model_validate(response)
    return apply_confirmation_response(
        state,
        validated,
        expected_version=version,
        confirmation_hash=decision.confirmation_hash,
    )
~~~

中断前只执行纯计算和数据库读取。<code>apply_confirmation_response()</code>：

- 先校验 <code>run_id</code> 与 <code>expected_checkpoint_version</code> 等于当前中断载荷，否则抛 <code>WorkflowConflict</code>；
- <code>cancel</code> -&gt; <code>canceled</code>；
- <code>provide_input</code> 只接受当前缺失键，把值合并到 <code>normalized_request["user_values"]</code> 并返回 <code>planned</code>，保证重新规划/解析仍能读到用户补参；
- <code>confirm_plan</code> 将 <code>proposed_defaults</code> 转成 <code>ResolvedValue(source="confirmed_default")</code> 后重建 <code>task_arguments</code>，再固化 hash/defaults 并返回 <code>executing</code>；
- 其他 action 抛 <code>InvalidWorkflowAction</code>。

- [ ] **Step 4: 实现报告发布中断**

~~~python
def release_node(state: ComprehensiveDiagnosticState):
    version = state.get("checkpoint_version", 0) + 1
    response = interrupt({
        "interaction_state": "awaiting_release",
        "run_id": state["run_id"],
        "checkpoint_version": version,
        "report_draft": state["report_draft"],
        "revision_count": state["report_revision_count"],
        "max_revisions": 3,
        "degradations": state["degradations"],
    })
    validated = InteractionResponse.model_validate(response)
    if (
        validated.run_id != state["run_id"]
        or validated.expected_checkpoint_version != version
    ):
        raise WorkflowConflict("checkpoint_version_conflict")
    if validated.action == "release_report":
        return {
            "checkpoint_version": version,
            "release_confirmation": {"released": True},
            "interaction_state": (
                "partial_complete"
                if state["degradations"]
                else "completed"
            ),
        }
    if validated.action == "request_revision":
        if state["report_revision_count"] >= 3:
            raise ReportRevisionLimit("report_revision_limit")
        return {
            "checkpoint_version": version,
            "revision_comment": validated.comment,
            "interaction_state": "reporting",
        }
    if validated.action == "cancel":
        return {"checkpoint_version": version, "interaction_state": "canceled"}
    raise InvalidWorkflowAction("invalid_release_action")
~~~

<code>release_node</code> 只返回状态更新；<code>route_after_release()</code> 在 <code>interaction_state=="reporting"</code> 时返回 <code>"report"</code>，其余终态返回 <code>"end"</code>。不要在同时配置静态/条件边的节点返回带 <code>goto</code> 的 <code>Command</code>，避免同一恢复触发两条路径。

- [ ] **Step 5: 组装图边和终态**

~~~python
def build_comprehensive_graph(
    services: ComprehensiveServices,
    checkpointer,
):
    graph = StateGraph(ComprehensiveDiagnosticState)
    graph.add_node("plan", partial(plan_node, services=services))
    graph.add_node("resolve_inputs", partial(input_node, services=services))
    graph.add_node(
        "confirm", partial(confirmation_node, services=services)
    )
    graph.add_node("execute", partial(execute_node, services=services))
    graph.add_node("research", partial(research_node, services=services))
    graph.add_node("report", partial(report_node, services=services))
    graph.add_node("release", release_node)
    graph.add_edge(START, "plan")
    graph.add_edge("plan", "resolve_inputs")
    graph.add_edge("resolve_inputs", "confirm")
    graph.add_conditional_edges(
        "confirm",
        route_after_confirmation,
        {
            "plan": "plan",
            "execute": "execute",
            "end": END,
        },
    )
    graph.add_conditional_edges(
        "execute",
        route_after_execution,
        {"research": "research", "end": END},
    )
    graph.add_edge("research", "report")
    graph.add_edge("report", "release")
    graph.add_conditional_edges(
        "release",
        route_after_release,
        {"report": "report", "end": END},
    )
    return graph.compile(checkpointer=checkpointer)
~~~

文件顶部显式导入 <code>dataclasses</code> 与 <code>functools.partial</code>；所有 node callable 都由 <code>partial(..., services=services)</code> 注入普通服务对象，服务对象本身不写入 checkpoint。

- [ ] **Step 6: 实现 Runtime 的 initial/resume**

~~~python
class WorkflowConflict(RuntimeError):
    http_status = 409


class WorkflowNotFound(RuntimeError):
    http_status = 404


def plan_summary(state: dict[str, Any]) -> dict[str, Any]:
    plan = state.get("diagnostic_plan") or {}
    return {
        "plan_version": plan.get("plan_version"),
        "analysis_mode": plan.get("analysis_mode"),
        "tasks": [
            {
                "task_id": task["task_id"],
                "agent_id": task["agent_id"],
                "required": task["required"],
            }
            for task in plan.get("tasks", [])
        ],
        "plan_hash": state.get("plan_hash"),
    } if plan else {}


def normalize_graph_output(result: dict[str, Any]) -> WorkflowOutput:
    interrupts = result.get("__interrupt__") or ()
    interaction = {}
    if interrupts:
        first = interrupts[0]
        interaction = getattr(first, "value", first)
    state_name = interaction.get(
        "interaction_state",
        result.get("interaction_state", "failed"),
    )
    released = state_name in {"completed", "partial_complete"}
    return WorkflowOutput(
        interaction_state=state_name,
        run_id=result["run_id"],
        checkpoint_version=int(interaction.get(
            "checkpoint_version",
            result.get("checkpoint_version", 0),
        )),
        analysis_context=result["analysis_context_snapshot"],
        plan_summary=plan_summary(result),
        missing_inputs=tuple(interaction.get(
            "missing_inputs",
            result.get("missing_inputs", []),
        )),
        proposed_defaults=dict(interaction.get(
            "proposed_defaults",
            result.get("proposed_defaults", {}),
        )),
        report_draft=interaction.get(
            "report_draft",
            result.get("report_draft"),
        ),
        answer=result.get("report_draft") if released else None,
        degradations=tuple(result.get("degradations", [])),
        provenance=dict(result.get("provenance", {})),
        trace_id=result["trace_id"],
    )


class ComprehensiveWorkflowRuntime:
    def __init__(self, graph):
        self._graph = graph

    def run_initial(self, request: dict[str, Any]) -> WorkflowOutput:
        config = workflow_thread_config(
            request["conversation_id"], request["run_id"]
        )
        result = self._graph.invoke(initial_state(request), config=config)
        return normalize_graph_output(result)

    def resume(
        self,
        *,
        conversation_id: int,
        response: InteractionResponse,
    ) -> WorkflowOutput:
        config = workflow_thread_config(conversation_id, response.run_id)
        snapshot = self._graph.get_state(config)
        if snapshot is None or not snapshot.values:
            raise WorkflowNotFound("workflow_checkpoint_not_found")
        current = int(snapshot.values.get("checkpoint_version", 0)) + 1
        if response.expected_checkpoint_version != current:
            raise WorkflowConflict("checkpoint_version_conflict")
        result = self._graph.invoke(
            Command(resume=response.model_dump(mode="json")),
            config=config,
        )
        return normalize_graph_output(result)
~~~

- [ ] **Step 7: 测试恢复不重复副作用**

让执行完成后在发布确认暂停；关闭并重新创建 Runtime（共享同一测试 saver），再恢复发布。断言每个模型调用计数仍为 1，报告无需重跑。另测用户请求 revision 时只重跑 Reporter，不重跑模型和 RAG。

- [ ] **Step 8: 运行测试并提交**

Run: <code>python -m pytest tests/comprehensive_workflow/test_graph.py tests/comprehensive_workflow/test_resume.py -q</code>

Expected: PASS。

~~~powershell
git add framework/agents/workflows/comprehensive/graph.py framework/agents/workflows/comprehensive/runtime.py framework/agents/workflows/comprehensive/state.py tests/comprehensive_workflow/test_graph.py tests/comprehensive_workflow/test_resume.py
git commit -m "feat(workflow): persist and resume comprehensive diagnostics"
~~~

---

### Task 10: 接入顶层编排器并实现 off/shadow/enabled 三态

**Files:**

- Modify: <code>framework/api/app.py</code>
- Modify: <code>framework/agents/orchestrator.py</code>
- Modify: <code>framework/agents/nodes.py</code>
- Create: <code>tests/comprehensive_workflow/test_orchestrator_gate.py</code>
- Modify: <code>tests/test_multi_agent.py</code>
- Modify: <code>tests/test_agent_integration.py</code>

**Interfaces:**

- Consumes: <code>Coordinator</code>、<code>TrafficGate</code>、Flask <code>app.extensions["comprehensive_checkpointer"]</code>.
- Produces: 顶层 <code>run()</code>/<code>run_stream()</code> 对快路径兼容并可委派综合任务。

- [ ] **Step 1: 写三种模式和快路径不变测试**

~~~python
@pytest.mark.parametrize("mode", ["off", "shadow"])
def test_comprehensive_request_keeps_existing_path_when_not_enabled(
    orchestrator, monkeypatch, mode
):
    monkeypatch.setattr(Config, "COMPREHENSIVE_WORKFLOW_MODE", mode)
    result = orchestrator.run(explicit_comprehensive_request())
    assert result["routing_path"] == "fast"
    assert orchestrator.comprehensive_runtime.execution_calls == 0


def test_enabled_explicit_comprehensive_request_uses_task_path(
    orchestrator, monkeypatch
):
    monkeypatch.setattr(Config, "COMPREHENSIVE_WORKFLOW_MODE", "enabled")
    result = orchestrator.run(explicit_comprehensive_request())
    assert result["routing_path"] == "comprehensive"


def test_enabled_single_model_request_still_uses_one_agent(
    orchestrator, monkeypatch
):
    monkeypatch.setattr(Config, "COMPREHENSIVE_WORKFLOW_MODE", "enabled")
    result = orchestrator.run(single_model_request(question_type=4))
    assert result["agents_invoked"] == ["model-4"]
~~~

- [ ] **Step 2: 实现用户 allowlist 与三态选择**

~~~python
def comprehensive_mode_for_user(user_id: int | None) -> str:
    mode = Config.COMPREHENSIVE_WORKFLOW_MODE
    allowed = Config.COMPREHENSIVE_ALLOWED_USER_IDS
    if mode == "enabled" and allowed and user_id not in allowed:
        return "shadow"
    return mode


def runtime_from_current_app() -> ComprehensiveWorkflowRuntime:
    runtime = current_app.extensions.get("comprehensive_runtime")
    if runtime is None:
        raise CheckpointerUnavailable("comprehensive_runtime_not_initialized")
    return runtime
~~~

Task 1 的 <code>init_comprehensive_checkpointer()</code> 之后，在 <code>create_app()</code> 中增加 <code>init_comprehensive_workflow(app)</code>：shadow/enabled 都构造并保存 <code>comprehensive_services</code>；enabled 再读取 <code>comprehensive_checkpointer</code>，编译一次图并保存 <code>comprehensive_runtime</code>。若 enabled 缺 saver，应用启动失败，不延迟到首个用户请求。

~~~python
def init_comprehensive_workflow(app: Flask) -> None:
    mode = app.config["COMPREHENSIVE_WORKFLOW_MODE"]
    if mode == "off":
        return
    services = build_default_comprehensive_services(app)
    app.extensions["comprehensive_services"] = services
    if mode == "shadow":
        return
    saver = app.extensions.get("comprehensive_checkpointer")
    if saver is None:
        raise CheckpointerUnavailable("checkpointer_not_initialized")
    graph = build_comprehensive_graph(services, saver)
    app.extensions["comprehensive_runtime"] = (
        ComprehensiveWorkflowRuntime(graph)
    )
~~~

工作流模块在 <code>init_comprehensive_workflow()</code> 函数体内延迟导入，避免 <code>app -&gt; routes.chat -&gt; orchestrator -&gt; app</code> 循环；初始化函数本身不从 <code>routes</code> 导入对象。

<code>MultiAgentOrchestrator</code> 构造函数接收可替换的 <code>runtime_provider</code> 和 <code>services_provider</code>，默认从 <code>current_app.extensions</code> 读取；只有已确认进入 comprehensive path 时才调用 runtime provider。<code>off</code> 不调用 Coordinator；<code>shadow</code> 调 Coordinator 和 Planner，记录计划但返回现有快路径结果；<code>enabled</code> 仅在 Gate 返回 <code>comprehensive_analysis</code> 时执行子图。

- [ ] **Step 3: 抽取 run/run_stream 共用顶层决策**

~~~python
@dataclass(frozen=True)
class RoutedRequest:
    path: str
    intent: dict[str, Any] | None
    request: dict[str, Any]


def prepare_top_level_route(
    self,
    request: dict[str, Any],
    history: list[dict] | None,
) -> RoutedRequest:
    mode = comprehensive_mode_for_user(request.get("user_id"))
    if mode == "off":
        return RoutedRequest("fast", None, request)
    base_state, _ = prepare_routed_state(request, history)
    intent = self._coordinator.classify(
        request["question"],
        deterministic_question_type=base_state.get("question_type"),
    )
    analysis_context = request.get("analysis_context") or {}
    object_type = (analysis_context.get("object") or {}).get("type")
    calculation_mode = (
        analysis_context.get("mode")
        or request.get("calculation_mode")
    )
    route = self._traffic_gate.route(
        intent,
        calculation_mode=calculation_mode,
        object_type=object_type,
    )
    if mode == "shadow":
        self._record_shadow_plan(request, intent, route)
        return RoutedRequest("fast", intent.model_dump(mode="json"), request)
    return RoutedRequest(
        "comprehensive" if route == "comprehensive_analysis" else "fast",
        intent.model_dump(mode="json"),
        request,
    )
~~~

<code>run()</code> 与 <code>run_stream()</code> 都先调用该函数。快路径继续调用现有图/流式逻辑；综合路径调用 Runtime。不得把综合字段塞进现有 <code>MultiAgentState</code>。

- [ ] **Step 4: 让 shadow 模式绝不执行模型**

<code>_record_shadow_plan()</code> 只在 <code>route=="comprehensive_analysis"</code> 且对象合法时，先调用与 enabled 路径相同的 <code>PlanningFactsResolver.resolve(parcel_id, user_message)</code>，再把这些事实交给 Planner；它只把 intent、事实摘要、计划或失败码写观测事件。注入的 scheduler/executor 在 shadow 测试中设置为 pytest.fail。Planner 失败不影响用户收到的快路径响应。

- [ ] **Step 5: 运行回归并提交**

Run: <code>python -m pytest tests/comprehensive_workflow/test_orchestrator_gate.py tests/test_multi_agent.py tests/test_agent_integration.py tests/test_question_type_router.py tests/test_knowledge_question.py -q</code>

Expected: PASS。

~~~powershell
git add framework/api/app.py framework/agents/orchestrator.py framework/agents/nodes.py tests/comprehensive_workflow/test_orchestrator_gate.py tests/test_multi_agent.py tests/test_agent_integration.py
git commit -m "feat(orchestrator): route explicit comprehensive diagnostics"
~~~

---

### Task 11: 扩展聊天 API 的恢复动作并统一 HTTP/SSE

**Files:**

- Modify: <code>framework/api/services/chat_service.py</code>
- Modify: <code>framework/api/routes/chat.py</code>
- Create: <code>tests/comprehensive_workflow/test_chat_api.py</code>
- Create: <code>tests/comprehensive_workflow/test_chat_sse.py</code>

**Interfaces:**

- Consumes: prerequisite <code>PreparedChat</code>/<code>ChatRequestService</code> and <code>InteractionResponse</code>.
- Produces: 初始请求、补参、确认、修订、发布、取消的统一 HTTP/SSE 契约。

- [ ] **Step 1: 写 action/status 矩阵测试**

~~~python
@pytest.mark.parametrize(
    "state,action,expected_http",
    [
        ("needs_input", "provide_input", 200),
        ("needs_confirmation", "confirm_plan", 200),
        ("awaiting_release", "request_revision", 200),
        ("awaiting_release", "release_report", 200),
        ("needs_input", "release_report", 422),
    ],
)
def test_interaction_action_matrix(
    client, auth_header, seeded_run, state, action, expected_http
):
    seeded_run.set_state(state)
    response = client.post(
        "/api/v1/chat/",
        headers=auth_header,
        json={
            "conversation_id": seeded_run.conversation_id,
            "interaction_response": {
                "run_id": seeded_run.run_id,
                "expected_checkpoint_version": seeded_run.version,
                "action": action,
                "values": {},
                "comment": "",
            },
        },
    )
    assert response.status_code == expected_http
~~~

- [ ] **Step 2: 在 ChatRequestService 区分 initial 与 resume**

~~~python
@dataclass
class PreparedChat:
    conversation: Conversation
    user_message: Message | None
    history: list[dict[str, str]]
    orchestrator_request: dict[str, Any]
    context_snapshot: dict[str, Any]
    interaction_response: InteractionResponse | None


def prepare(self, *, user_id: int, body: Mapping[str, Any]) -> PreparedChat:
    response_payload = body.get("interaction_response")
    if response_payload is not None:
        response = InteractionResponse.model_validate(response_payload)
        conversation = self._get_owned_conversation(
            user_id, int(body["conversation_id"])
        )
        return self._prepare_resume(conversation, response)
    return self._prepare_initial(user_id=user_id, body=body)
~~~

Resume 不允许携带新的 <code>analysis_context</code>；对象切换必须作为新任务发起。<code>_prepare_resume()</code> 不重复保存原始综合问题，只在 <code>comment</code> 或 <code>values</code> 非空时保存一条用户交互消息。

- [ ] **Step 3: 实现统一结果序列化**

~~~python
def serialize_workflow_output(output: WorkflowOutput) -> dict[str, Any]:
    return {
        "interaction_state": output.interaction_state,
        "run_id": output.run_id,
        "checkpoint_version": output.checkpoint_version,
        "analysis_context": output.analysis_context,
        "plan_summary": output.plan_summary,
        "missing_inputs": output.missing_inputs,
        "proposed_defaults": output.proposed_defaults,
        "report_draft": output.report_draft,
        "answer": output.answer,
        "degradations": output.degradations,
        "provenance": output.provenance,
        "trace_id": output.trace_id,
    }
~~~

所有键始终存在，不适用时为 null、空 list 或空 object。<code>failed*</code> 状态使用现有 error envelope；404（run/checkpoint 不存在）、409（版本冲突）、422（动作或输入非法）、503（持久化/核心依赖不可用）由领域错误映射。

- [ ] **Step 4: 让 SSE 只流式发送已验证内容**

综合路径事件顺序：

~~~text
data: {"event":"meta","data":{"routing_path":"comprehensive","run_id":"run-7"}}
data: {"event":"progress","data":{"stage":"executing","completed_tasks":2}}
data: {"event":"interaction","data":{"interaction_state":"awaiting_release","report_draft":"已验证的报告草稿"}}
data: {"event":"done","data":{"interaction_state":"awaiting_release","run_id":"run-7"}}
~~~

在 <code>completed</code>/<code>partial_complete</code> 时，只有 <code>ReportPolicyValidator</code> 通过后的 <code>answer</code> 可以分 token 发送。needs 状态不发送 token。HTTP 和 SSE 的 <code>done.data</code> 使用同一 <code>serialize_workflow_output()</code>。

- [ ] **Step 5: 写流式/非流式字段一致测试**

固定 Coordinator、Planner、模型、RAG 和 Reporter，分别执行 HTTP 与 SSE；从 SSE 取 <code>done.data</code>，逐键比较：

~~~python
for key in (
    "interaction_state",
    "run_id",
    "checkpoint_version",
    "analysis_context",
    "missing_inputs",
    "proposed_defaults",
    "report_draft",
    "degradations",
    "provenance",
):
    assert sse_done[key] == http_payload["data"][key]
~~~

- [ ] **Step 6: 运行测试并提交**

Run: <code>python -m pytest tests/comprehensive_workflow/test_chat_api.py tests/comprehensive_workflow/test_chat_sse.py tests/analysis_context/test_chat_api.py tests/analysis_context/test_chat_sse.py -q</code>

Expected: PASS。

~~~powershell
git add framework/api/services/chat_service.py framework/api/routes/chat.py tests/comprehensive_workflow/test_chat_api.py tests/comprehensive_workflow/test_chat_sse.py
git commit -m "feat(api): resume comprehensive workflow over HTTP and SSE"
~~~

---

### Task 12: 增加观测、文档、金标 E2E 和快路径基准

**Files:**

- Create: <code>framework/observability/comprehensive_workflow.py</code>
- Modify: <code>framework/api/routes/observability.py</code>
- Create: <code>tests/comprehensive_workflow/test_observability.py</code>
- Create: <code>tests/comprehensive_workflow/test_e2e_golden.py</code>
- Create: <code>tests/fixtures/comprehensive_diagnostic_cases.yaml</code>
- Create: <code>scripts/benchmark_comprehensive_routing.py</code>
- Modify: <code>docs/openapi.json</code>
- Modify: <code>docs/api.md</code>
- Modify: <code>docs/chat-routing-keywords.md</code>
- Create: <code>docs/deployment/comprehensive-diagnostic-rollout.md</code>

**Interfaces:**

- Consumes: workflow outputs and existing observability storage.
- Produces: stable workflow events, dashboard aggregates, OpenAPI examples, rollout/runbook, 15-scenario golden suite and P95 comparison.

- [ ] **Step 1: 写稳定事件和敏感字段过滤测试**

~~~python
def test_workflow_event_contains_versions_without_prompt_body(recorder):
    recorder.record(
        "plan_validated",
        run_id="run-1",
        trace_id="trace-1",
        object_id="P001",
        prompt_version="planner-v1",
        plan={"tasks": [{"agent_id": "model-2"}]},
        system_prompt="secret prompt",
    )
    event = recorder.last()
    assert event["event"] == "comprehensive.plan_validated"
    assert event["prompt_version"] == "planner-v1"
    assert "system_prompt" not in event
~~~

实现稳定事件：

~~~python
EVENTS = frozenset({
    "comprehensive.intent_classified",
    "comprehensive.plan_validated",
    "comprehensive.interrupted",
    "comprehensive.task_started",
    "comprehensive.task_retried",
    "comprehensive.task_completed",
    "comprehensive.task_skipped",
    "comprehensive.degraded",
    "comprehensive.report_drafted",
    "comprehensive.report_revised",
    "comprehensive.report_released",
    "comprehensive.failed",
})
~~~

所有事件带 <code>run_id</code>、<code>trace_id</code>、对象 ID、节点、Prompt/plan 版本和耗时；不得包含完整 Prompt、权限令牌、数据库 URI 或未脱敏输入。

- [ ] **Step 2: 建立 15 个金标场景**

<code>tests/fixtures/comprehensive_diagnostic_cases.yaml</code> 固定：

~~~yaml
- id: complete-parcel
  expected_state: completed
  expected_agents: [model-2, model-3]
  forbidden_agents: [model-6]
- id: missing-object
  expected_state: needs_analysis_object
  expected_tool_calls: 0
- id: missing-land-type
  expected_state: needs_input
- id: default-needs-confirmation
  expected_state: needs_confirmation
- id: trigger-acidification
  expected_agents: [model-2, model-3, model-4]
- id: skip-acidification
  forbidden_agents: [model-4]
- id: trigger-organic-matter
  expected_agents: [model-2, model-3, model-5]
- id: skip-organic-matter
  forbidden_agents: [model-5]
- id: optional-model-fails
  expected_state: partial_complete
- id: core-model-fails
  expected_state: failed
  report_forbidden: true
- id: rag-unavailable
  expected_state: partial_complete
  unreferenced_claims_in_report: 0
- id: fourth-revision
  expected_error: report_revision_limit
- id: duplicate-confirmation
  expected_model_call_count: 2
- id: knowledge-fast-path
  expected_routing_path: fast
  expected_agents: [rag]
- id: single-model-fast-path
  expected_routing_path: fast
  expected_agents: [model-4]
~~~

测试为每个场景注入 deterministic fake services，断言状态、Agent、调用数、数值引用、source_id、降级和报告权限。

- [ ] **Step 3: 增加快路径 P95 基准脚本**

~~~python
def percentile(values: list[float], p: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, math.ceil(len(ordered) * p) - 1)
    return ordered[index]


def benchmark(orchestrator, requests, *, mode: str, rounds: int = 100):
    Config.COMPREHENSIVE_WORKFLOW_MODE = mode
    for request in requests:
        orchestrator.run(request)
    samples = []
    for index in range(rounds):
        started = time.perf_counter()
        orchestrator.run(requests[index % len(requests)])
        samples.append(time.perf_counter() - started)
    return percentile(samples, 0.95)


def main() -> int:
    requests = load_fast_path_fixture()
    baseline = benchmark(build_fake_orchestrator(), requests, mode="off")
    enabled = benchmark(build_fake_orchestrator(), requests, mode="enabled")
    ratio = enabled / baseline if baseline else 1
    print(json.dumps({
        "baseline_p95": baseline,
        "enabled_p95": enabled,
        "ratio": ratio,
    }))
    return 0 if ratio <= 1.10 else 1
~~~

基准固定同一机器、fake LLM/RAG/模型、预热一轮、100 次和固定请求集；只测新增路由开销，不把外部网络抖动混入验收。

- [ ] **Step 4: 更新 OpenAPI 与 API 文档**

增加：

- <code>InteractionIntent</code>、<code>DiagnosticPlanSummary</code>、<code>InteractionResponse</code>、<code>ComprehensiveWorkflowResponse</code>；
- needs_input、needs_confirmation、awaiting_release、completed、partial_complete、canceled 示例；
- 404 workflow/checkpoint 不存在、409 checkpoint 冲突、422 action/state 不匹配、503 checkpointer/核心依赖不可用；RAG 不可用按设计降级为 <code>partial_complete</code>，不映射为 503；
- SSE <code>meta</code>/<code>progress</code>/<code>interaction</code>/<code>token</code>/<code>done</code>；
- Model-6 不参与综合任务的明确说明。

Run: <code>python -m json.tool docs/openapi.json</code>

Expected: 成功输出 JSON。

- [ ] **Step 5: 编写发布与回滚 runbook**

<code>docs/deployment/comprehensive-diagnostic-rollout.md</code> 固定顺序：

1. 完成分析对象计划并运行其完整验证；
2. 安装锁定依赖；
3. 设置 <code>LANGGRAPH_STRICT_MSGPACK=true</code>；
4. 运行 <code>python scripts/setup_langgraph_checkpoint.py</code>；
5. 以 <code>off</code> 部署；
6. 切换 <code>shadow</code>，观察 intent/plan 差异；
7. 配置内部 <code>COMPREHENSIVE_ALLOWED_USER_IDS</code> 并启用；
8. 小流量启用，观察失败率、重试、降级和 P95；
9. 默认启用；
10. 回滚只需切回 <code>off</code>，不删除 checkpoint 表，现有快路径继续工作。

- [ ] **Step 6: 运行聚焦测试、完整回归和基准**

Run: <code>python -m pytest tests/comprehensive_workflow tests/analysis_context tests/test_multi_agent.py tests/test_agent_integration.py tests/test_function_calling.py tests/test_specialized_tools.py tests/test_rag.py -q</code>

Expected: PASS。

Run: <code>python -m pytest -q</code>

Expected: PASS；只接受仓库已有且有明确 marker 的 SKIP，不接受本变更新增 XFAIL。

Run: <code>python scripts/benchmark_comprehensive_routing.py</code>

Expected: exit 0，JSON 中 <code>ratio &lt;= 1.10</code>。

- [ ] **Step 7: 做最终安全与一致性扫描**

~~~powershell
rg -n "model-6" framework/agents/workflows/comprehensive
rg -n "get_specialized_tools\(\)" framework/agents/workflows/comprehensive
rg -n "MOCK|默认地块|general knowledge" framework/agents/workflows/comprehensive
rg -n "TBD|TODO|FIXME|implement later" framework/agents/workflows/comprehensive tests/comprehensive_workflow docs/deployment/comprehensive-diagnostic-rollout.md
git diff --check
git status --short
~~~

Expected:

- Model-6 只出现在显式拒绝常量或测试；
- 综合路径不调用全量 <code>get_specialized_tools()</code>；
- 无 MOCK、默认地块或 RAG 通用知识回退；
- 无占位符；
- <code>git diff --check</code> 无输出；
- 状态只包含用户原有未提交文件；本计划各任务文件均已按任务提交。

- [ ] **Step 8: 提交观测、文档与最终验收**

~~~powershell
git add framework/observability/comprehensive_workflow.py framework/api/routes/observability.py tests/comprehensive_workflow/test_observability.py tests/comprehensive_workflow/test_e2e_golden.py tests/fixtures/comprehensive_diagnostic_cases.yaml scripts/benchmark_comprehensive_routing.py docs/openapi.json docs/api.md docs/chat-routing-keywords.md docs/deployment/comprehensive-diagnostic-rollout.md
git commit -m "docs(workflow): publish comprehensive rollout and acceptance"
~~~

---

## Completion Checklist

- [ ] 前置分析对象计划完整通过；综合子图只消费后端验证的 parcel 快照。
- [ ] off/shadow/enabled 三态生效；shadow 不执行任何专业模型。
- [ ] 知识问答和单模型回归集路由/响应契约 100% 保持。
- [ ] 快路径固定基准的 P95 开销不超过 10%。
- [ ] Coordinator/Planner/Researcher/Reporter 每个角色最多调用 2 次。
- [ ] 非法 Agent、Model-6、重复任务、非法依赖、未知触发器和超 5 个任务全部被拒绝。
- [ ] Model-2/3 核心并行；Model-1/4/5 只按已批准触发器执行。
- [ ] 任务路径只绑定计划白名单工具，LLM 不能二次选模或覆盖对象参数。
- [ ] 初次调用加最多 2 次瞬时重试；验证/输入错误不重试。
- [ ] 缺对象、缺输入、计划确认和报告发布均可持久恢复。
- [ ] 相同 <code>task_id</code> 恢复不重复执行；报告修订不重跑模型/RAG。
- [ ] 可选模型或 RAG 失败发布后为 <code>partial_complete</code>；核心模型失败不生成正式报告。
- [ ] 报告所有阿拉伯数字来自经过验证的 fact reference；所有关键解释性主张有 source_id。
- [ ] 用户报告修订最多 3 次；第 4 次不调用 Reporter。
- [ ] HTTP 与 SSE 使用相同状态、错误码、checkpoint 版本和最终包络。
- [ ] PostgreSQL checkpointer 首次 setup、严格 msgpack 和关闭生命周期均有测试。
- [ ] 15 个金标 E2E、聚焦测试、完整测试、OpenAPI JSON 和安全扫描全部通过。
- [ ] 没有修改或暂存用户原有无关变更。
