# Brainstorm Summary

- Change: fix-pre-existing-test-failures
- Date: 2026-08-01

## 确认的技术方案

7 项修复，分 A/B/C 三类：

### A. 代码缺陷修复
1. **TYPE_4/5 关键词定义**（nodes.py）：TYPE_4 肥力相关（有机质/有机肥/秸秆/肥力/SOC/Dose/有机碳），TYPE_5 质量等级评价相关（质量等级/综合指数/障碍度排序/等级评价）
2. **_is_knowledge_question 函数**（nodes.py）：开头匹配（"什么是"/"何为"/"解释"）+ 包含匹配（"是什么意思"/"什么意思"/"定义"/"概念"/"含义"），在 identify_question_type 最前端执行
3. **_identify_question_type_keyword 路由**（nodes.py）：补充 TYPE_2/4/5 关键词路由（当前只覆盖 TYPE_1/3）
4. **parcel_id/parcel_code 透传**（nodes.py execute_models）：在 context 透传列表中添加 parcel_id 和 parcel_code
5. **DataFile 模型**（新建 framework/models/data_file.py）：参考 Document 模型结构，表名 kb_data_file，字段 doc_name/file_path/file_type/file_size/category/treatment_type/status/create_by/create_time，提供 to_dict()

### B. 测试引用过时修复
6. **test_model_specs_sync.py 路径更新**：从 openspec/changes/sync-model-specs-from-overview/specs/ 改为 openspec/changes/archive/2026-07-24-sync-model-specs-from-overview/specs/

### C. 测试基础设施修复
7. **fake.shp**：创建最小测试 shapefile（geopandas）
8. **chroma_db**：重置 chroma_db/ 目录（索引可通过 reindex_documents.py 重建）
9. **langchain import**：适配为 `from langchain_core.tools import Tool`（langchain 1.3.14 已验证）

## 关键取舍与风险

- TYPE_4/5 关键词需避免与 TYPE_1/2/3 冲突（参考 test_type_order_no_cross_collision）
- 重置 chroma_db 丢失已索引文档（可重建）
- kb_data_file 表由 SQLAlchemy db.create_all() 自动创建（无需手动建表）
- langchain 1.3.14 的 Tool 在 langchain_core.tools 路径

## 测试策略

- 现有测试验证：test_question_type_keywords.py（TYPE_4/5 路由）、test_knowledge_question.py（知识性问题识别）、test_execute_models_pipeline.py（parcel_id 透传）、test_docs_dedup.py（import 链恢复）、test_model_specs_sync.py（路径更新）
- 全量回归对比：修复前后失败列表对比，确认零回归
- 目标：80 failed → 0 failed，4 errors → 0 errors

## Spec Patch

- database-models delta spec 已创建（ADDED DataFile 模型需求，3 个 scenario）
- 无需额外 Spec Patch（role-based-routing 和 multi-agent-orchestrator 的 spec 需求已存在，本次为实现修复）
