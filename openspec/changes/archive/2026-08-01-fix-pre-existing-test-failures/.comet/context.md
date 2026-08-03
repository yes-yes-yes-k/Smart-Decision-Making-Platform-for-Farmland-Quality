# Comet Design Handoff

- Change: fix-pre-existing-test-failures
- Phase: design
- Mode: compact
- Context hash: 47077aa2bbf98c97091010c2562947cdb8c4b5ba95fea12196ad8d1a9fb823e4

Generated-by: comet-handoff.sh

OpenSpec remains the canonical capability spec. This handoff is a deterministic, source-traceable context pack, not an agent-authored summary.

## openspec/changes/fix-pre-existing-test-failures/proposal.md

- Source: openspec/changes/fix-pre-existing-test-failures/proposal.md
- Lines: 1-38
- SHA256: 6723c5f3f379c68c076cfa7d82bccbddb23168127734bff98bf5d478953412fc

```md
## Why

项目全量测试存在 80 failed / 4 collection errors 的 pre-existing 失败，涉及 question type 路由逻辑缺陷、缺失模块（framework/models/data_file.py）、parcel_id 透传 bug、测试引用过时路径和测试基础设施损坏（fake.shp 缺失、chroma_db 损坏、langchain import 变更）。这些失败降低了测试套件的可靠性，阻碍后续变更的验证工作。现在修复是因为刚完成酸化模型合并归档，需要干净的测试基线支撑后续开发。

## What Changes

### A. 代码缺陷修复（源代码）
- 在 `framework/agents/nodes.py` 补充 `QUESTION_TYPE_4_KEYWORDS`（肥力相关：有机质/有机肥/秸秆/肥力/SOC/Dose 等）和 `QUESTION_TYPE_5_KEYWORDS`（质量等级评价相关）定义
- 在 `_identify_question_type_keyword` 函数中补充 TYPE_2/4/5 的关键词路由逻辑（当前只覆盖 TYPE_1/3）
- 在 `framework/agents/nodes.py` 新增 `_is_knowledge_question` 函数，识别知识性问题模式（"什么是X"/"何为X"/"解释X"/"X是什么意思"/"X的定义"/"X的含义"/"X的概念"），路由到 TYPE_0（RAG）
- 在 `execute_models` 的 context 透传列表中添加 `parcel_id` 和 `parcel_code`，确保透传到 context top-level
- 新建 `framework/models/data_file.py`，实现 `DataFile` SQLAlchemy 模型（kb_data_file 表），字段包括 doc_name/file_path/file_type/file_size/category/treatment_type/status/create_by，提供 `.to_dict()` 方法

### B. 测试引用过时修复（测试代码）
- 更新 `tests/test_model_specs_sync.py` 中的路径引用，从 `openspec/changes/sync-model-specs-from-overview/specs/` 改为归档后路径 `openspec/changes/archive/2026-07-24-sync-model-specs-from-overview/specs/`

### C. 测试基础设施修复（测试环境/数据）
- 修复 `tests/test_stability_and_grade_integration.py` 的 fake.shp 缺失问题（创建最小测试数据或 mock geopandas 读取）
- 修复 `tests/test_rag.py` 的 chroma_db 损坏问题（重置 chroma_db 或修改测试容错）
- 修复 `tests/test_function_calling.py` 的 langchain Tool import 变更（适配 langchain 新版 import 路径）
- `tests/test_docs_dedup.py` 的 collection error 源于 data_file 缺失，修复 A5 后自动解决

## Capabilities

### New Capabilities
（无新增 capability — 全部在已有 capability 上修复实现）

### Modified Capabilities
- `database-models`: 新增 `DataFile` 模型（kb_data_file 表）的需求定义，补全缺失的数据文件存储模型
- 注：`role-based-routing`（TYPE_4/5 关键词、知识性问题识别）和 `multi-agent-orchestrator`（parcel_id 透传）的 spec 需求已存在，本次为**实现修复**以匹配已有 spec，无 spec-level 变更

## Impact

- **核心代码**：`framework/agents/nodes.py`（关键词定义、路由逻辑、知识性问题识别、parcel_id 透传）、`framework/models/data_file.py`（新建）
- **框架层**：`framework/api/routes/docs.py`（间接修复，data_file 模块可用后 import 链恢复）
- **测试**：`tests/test_model_specs_sync.py`（路径更新）、`tests/test_stability_and_grade_integration.py`（fake.shp）、`tests/test_rag.py`（chroma_db）、`tests/test_function_calling.py`（langchain import）
- **数据库**：DataFile 模型对应 kb_data_file 表（表结构应已存在，仅需模型定义）
- **无 API 契约变更**：修复透传逻辑和路由逻辑不影响外部 API 接口定义

```

## openspec/changes/fix-pre-existing-test-failures/design.md

- Source: openspec/changes/fix-pre-existing-test-failures/design.md
- Lines: 1-108
- SHA256: 1f132ef8c12a62a7f9a0b7f62078980d2b0a713c13f2822eb83620eaf4b94868

[TRUNCATED]

```md
## Context

项目全量测试存在 80 failed / 4 collection errors 的 pre-existing 失败。这些失败在 base-ref cee7265d 上就已存在，非近期变更引入，但一直未修复。失败原因分为三类：代码缺陷（nodes.py 路由逻辑不完整、模块缺失）、测试引用过时（归档后路径未更新）、测试基础设施损坏（fake.shp 缺失、chroma_db 损坏、langchain import 变更）。

当前状态：
- `framework/agents/nodes.py`：定义了 QUESTION_TYPE_1/2/3_KEYWORDS，但缺少 TYPE_4/5 关键词；`_identify_question_type_keyword` 只检查 TYPE_1/3；缺少 `_is_knowledge_question` 函数；`execute_models` 的 context 透传列表缺少 parcel_id/parcel_code
- `framework/models/data_file.py`：模块不存在，但 `framework/api/routes/docs.py:5` 引用 `from framework.models.data_file import DataFile`，导致整个 import 链断裂
- `tests/test_model_specs_sync.py`：引用已归档路径 `openspec/changes/sync-model-specs-from-overview/specs/`
- 测试基础设施：fake.shp 缺失、chroma_db 损坏、langchain.tools.Tool import 失败

约束：
- 不新增功能或 capability，仅修复现有实现以匹配已有 spec 和测试期望
- 不修改已归档的 change 产物内容
- TYPE_4/5 关键词需参考测试期望和 project_memory 中的定义
- DataFile 模型需匹配 docs.py 中的使用方式（构造参数、to_dict 方法、kb_data_file 表）

## Goals / Non-Goals

**Goals:**
- 修复所有代码缺陷，使 question type 路由覆盖 TYPE_0-5
- 补全缺失的 data_file 模块，恢复 import 链
- 修复 execute_models 的 parcel_id/parcel_code 透传
- 修复测试引用过时和测试基础设施问题
- 全量测试通过（或仅剩无法复现的环境限制 skip）

**Non-Goals:**
- 不新增功能或 capability
- 不修改 API 外部契约
- 不重构现有架构
- 不修改已归档 change 产物的内容
- 不优化性能或代码风格（仅修复 bug）

## Decisions

### D1: TYPE_4/5 关键词定义 — 参考测试期望 + project_memory

**选择**：
- TYPE_4（肥力）：有机质、有机肥、秸秆、肥力、SOC、Dose、有机碳、腐殖质 等
- TYPE_5（质量等级评价）：质量等级、综合指数、障碍度排序、等级评价 等

**理由**：
- 测试期望 TYPE_4 覆盖有机质含量、有机肥/秸秆施用量、农户肥力/SOC、县域有机质平均
- project_memory 记录 TYPE_5 需包含质量等级评价关键词
- 关键词匹配优先于向量相似度（keyword-first approach）

### D2: _is_knowledge_question 函数 — 模式匹配

**选择**：实现 `_is_knowledge_question(question: str) -> bool`，匹配以下模式：
- 前缀模式："什么是"/"何为"/"解释"/"什么是"
- 包含模式："是什么意思"/"什么意思"/"的定义"/"的含义"/"的概念"

**理由**：
- 测试期望覆盖这些知识性问题模式
- 知识性问题路由到 TYPE_0（RAG），与非知识性问题区分

### D3: parcel_id 透传 — 扩展 context 透传列表

**选择**：在 `execute_models` 的 context 透传循环中添加 `parcel_id` 和 `parcel_code`。

**理由**：
- 当前透传列表为 `("longitude", "latitude", "target_ph", "context", "land_type", "fertilizer_type")`，缺少 parcel_id/parcel_code
- project_memory 要求 parcel_id/parcel_code 作为 top-level context 字段

### D4: DataFile 模型 — 参考 Document 模型和 docs.py 使用方式

**选择**：新建 `framework/models/data_file.py`，实现 DataFile SQLAlchemy 模型：
- 表名：kb_data_file
- 字段：id（主键）、doc_name、file_path、file_type、file_size、category、treatment_type、status、create_by、create_time
- 方法：to_dict() 返回字段字典

**理由**：
- docs.py 中 DataFile 构造参数为 doc_name/file_path/file_type/file_size/category/treatment_type/status/create_by
- 参考 framework/models/document.py 的 Document 模型结构
- 表名 kb_data_file 来自 docs.py 注释

### D5: fake.shp — 创建最小测试数据

**选择**：为 test_stability_and_grade_integration.py 创建最小 fake.shp 测试数据文件。

**理由**：

```

Full source: openspec/changes/fix-pre-existing-test-failures/design.md

## openspec/changes/fix-pre-existing-test-failures/tasks.md

- Source: openspec/changes/fix-pre-existing-test-failures/tasks.md
- Lines: 1-31
- SHA256: ce2d8e4c93fe947a79b27804602476de48e09748a9eb015867d0b784b6bccaf7

```md
## 1. question type 路由修复（framework/agents/nodes.py）

- [ ] 1.1 定义 `QUESTION_TYPE_4_KEYWORDS`（肥力相关：有机质/有机肥/秸秆/肥力/SOC/Dose/有机碳/腐殖质等），参考 test_question_type_keywords.py 期望
- [ ] 1.2 定义 `QUESTION_TYPE_5_KEYWORDS`（质量等级评价相关：质量等级/综合指数/障碍度排序/等级评价等），参考 project_memory 中 QUESTION_TYPE_5_KEYWORDS 定义
- [ ] 1.3 在 `_identify_question_type_keyword` 中补充 TYPE_2/4/5 的关键词路由逻辑（当前只覆盖 TYPE_1/3），确保关键词优先于向量匹配
- [ ] 1.4 实现 `_is_knowledge_question(question: str) -> bool` 函数，匹配开头模式（"什么是"/"何为"/"解释"）和包含模式（"是什么意思"/"什么意思"/"定义"/"概念"/"含义"），不匹配具体诊断/评价问题
- [ ] 1.5 在 `identify_question_type` 最前端执行知识性问题预检，命中时返回 `(0, 1.0)` 走 RAG

## 2. parcel_id 透传修复（framework/agents/nodes.py）

- [ ] 2.1 在 `execute_models` 的 context 透传列表中添加 `parcel_id` 和 `parcel_code`，确保传递到 context top-level

## 3. DataFile 模型补全（framework/models/data_file.py）

- [ ] 3.1 创建 `framework/models/data_file.py`，实现 `DataFile` SQLAlchemy 模型（表名 kb_data_file），字段：id/doc_name/file_path/file_type/file_size/category/treatment_type/status/create_by/create_time，提供 `to_dict()` 方法，参考 framework/models/document.py 结构
- [ ] 3.2 验证 `framework/api/routes/docs.py` 的 `from framework.models.data_file import DataFile` import 成功，docs_bp 正常加载

## 4. 测试引用过时修复

- [ ] 4.1 更新 `tests/test_model_specs_sync.py` 中的路径引用，从 `openspec/changes/sync-model-specs-from-overview/specs/` 改为 `openspec/changes/archive/2026-07-24-sync-model-specs-from-overview/specs/`

## 5. 测试基础设施修复

- [ ] 5.1 修复 `tests/test_stability_and_grade_integration.py` 的 fake.shp 缺失问题（创建最小测试 shapefile 或 mock geopandas 读取）
- [ ] 5.2 修复 `tests/test_rag.py` 的 chroma_db 损坏问题（重置 chroma_db 目录或修改测试容错）
- [ ] 5.3 修复 `tests/test_function_calling.py` 的 langchain Tool import 变更（适配新版 import 路径，如 `from langchain_core.tools import Tool`）

## 6. 回归验证

- [ ] 6.1 运行全量测试，确认所有修复生效且无 collection error
- [ ] 6.2 确认零回归（不引入新的测试失败），对比修复前的失败列表

```

## openspec/changes/fix-pre-existing-test-failures/specs/database-models/spec.md

- Source: openspec/changes/fix-pre-existing-test-failures/specs/database-models/spec.md
- Lines: 1-33
- SHA256: 5201a41d6c95205b6b6642a7220216677f5951a55c81b834a977cb7bbfaed23f

```md
## ADDED Requirements

### Requirement: DataFile 数据文件模型
系统 SHALL 提供 `DataFile` SQLAlchemy 模型（位于 `framework/models/data_file.py`），对应数据库表 `kb_data_file`，用于存储用户上传的数据文件（raw_data/improved_data 分类）的元数据。`DataFile` 模型 SHALL 被 `framework/api/routes/docs.py` 导入，支持数据文件上传接口的存储和查询功能。

`DataFile` 模型 SHALL 包含以下字段：
- `id`：主键，自增整数
- `doc_name`：原始文件名（字符串）
- `file_path`：存储路径/新文件名（字符串）
- `file_type`：文件类型（字符串）
- `file_size`：文件大小，字节（整数）
- `category`：文件分类（字符串，如 raw_data/improved_data）
- `treatment_type`：治理类型（字符串，可选）
- `status`：状态标志（整数，如 1=有效）
- `create_by`：创建者用户 ID（整数）
- `create_time`：创建时间（datetime，默认当前时间）

`DataFile` 模型 SHALL 提供 `to_dict()` 方法，返回包含上述字段的字典。

#### Scenario: 数据文件上传存储
- **WHEN** 用户上传一个分类为 `raw_data` 的数据文件，且文件通过查重检查
- **THEN** 系统 SHALL 创建 `DataFile` 实例，填充 doc_name/file_path/file_type/file_size/category/treatment_type/status/create_by 字段
- **AND** 系统 SHALL 将实例添加到数据库会话并提交
- **AND** 系统 SHALL 返回包含 `data_file.to_dict()` 的成功响应

#### Scenario: DataFile 模型导入可用
- **WHEN** `framework/api/routes/docs.py` 执行 `from framework.models.data_file import DataFile`
- **THEN** 导入 SHALL 成功，不抛出 ModuleNotFoundError
- **AND** `DataFile` SHALL 可用于构造数据文件实例

#### Scenario: to_dict 方法返回完整字段
- **WHEN** 调用 `DataFile` 实例的 `to_dict()` 方法
- **THEN** 返回的字典 SHALL 包含 id/doc_name/file_path/file_type/file_size/category/treatment_type/status/create_by/create_time 字段

```
