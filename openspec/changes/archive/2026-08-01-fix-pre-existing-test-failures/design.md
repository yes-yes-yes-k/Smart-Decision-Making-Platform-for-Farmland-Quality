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
- 测试期望读取 shapefile 进行稳定性预计算
- mock geopandas 读取会过度复杂化测试
- 创建最小有效 shapefile 更直接

### D6: chroma_db 损坏 — 重置 vector store

**选择**：重置 chroma_db 目录，清除损坏的元数据。

**理由**：
- project_memory 记录 chroma_db 可能出现元数据段压缩损坏（Rust u64/SQL BLOB 类型不匹配）
- 重置 chroma_db 可解决 test_vector_store_operations 失败
- 索引文档可通过 reindex_documents.py 重新索引

### D7: langchain Tool import — 适配新版 import 路径

**选择**：检查 langchain 版本，更新 test_function_calling.py 的 import 路径（如 `from langchain.tools import Tool` → `from langchain_core.tools import Tool`）。

**理由**：
- langchain 新版本将 Tool 移到 langchain_core.tools
- 适配 import 路径比降级 langchain 更安全

## Risks / Trade-offs

- **[风险] TYPE_4/5 关键词可能与现有 TYPE_1/2/3 关键词冲突** → 缓解：参考 test_question_type_keywords.py 中的 test_type_order_no_cross_collision 测试，确保关键词不交叉
- **[风险] 重置 chroma_db 丢失已索引文档** → 缓解：可通过 reindex_documents.py 重新索引；测试环境数据可重建
- **[风险] DataFile 模型字段与实际 kb_data_file 表结构不匹配** → 缓解：参考 Document 模型和 docs.py 使用方式；如有差异在 build 阶段通过测试发现
- **[权衡] fake.shp 创建可能需要 geopandas 依赖** → 缓解：使用 geopandas 创建最小 shapefile，或使用 pyshp 库
- **[风险] langchain import 适配可能影响其他使用 Tool 的代码** → 缓解：仅修改测试文件 import，不影响生产代码
