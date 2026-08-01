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
