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
