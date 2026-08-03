---
change: fix-pre-existing-test-failures
design-doc: docs/superpowers/specs/2026-08-01-fix-pre-existing-test-failures-design.md
base-ref: 41526ef687d070d6819ca1b3b69e998e8e573b2e
archived-with: 2026-08-01-fix-pre-existing-test-failures
---

# 实施计划：修复 Pre-existing 测试失败

## 概述

修复项目中 80 failed / 4 collection errors 的 pre-existing 测试失败。基于 Design Doc 的 7 项修复方案，分 6 组任务执行。

## 任务 1：question type 路由修复（framework/agents/nodes.py）

### Step 1.1: 定义 TYPE_4/5 关键词
- 在 nodes.py 中定义 `QUESTION_TYPE_4_KEYWORDS`（有机质/有机肥/秸秆/肥力/SOC/Dose/有机碳/有机物质/腐殖质/有机质含量）
- 定义 `QUESTION_TYPE_5_KEYWORDS`（质量等级/综合指数/障碍度排序/等级评价/耕地质量/质量评价/等级评估）
- 验证：关键词不与 TYPE_1/2/3 交叉（参考 test_type_order_no_cross_collision）

### Step 1.2: 实现 _is_knowledge_question 函数
- 新增 `_is_knowledge_question(question: str) -> bool`
- 开头匹配：question.startswith(("什么是", "何为", "解释"))
- 包含匹配：any(p in question for p in ["是什么意思", "什么意思", "定义", "概念", "含义"])
- 验证：test_knowledge_question.py 的 16 个测试通过

### Step 1.3: 补充 _identify_question_type_keyword 路由
- 在现有 TYPE_1/3 检查之间补充 TYPE_2 检查
- 在 TYPE_3 后补充 TYPE_4/5 检查
- 验证：test_question_type_keywords.py 的 TYPE_1-5 路由测试通过

### Step 1.4: 在 identify_question_type 最前端执行知识性预检
- 在 identify_question_type 函数最前端调用 _is_knowledge_question
- 命中时返回 (0, 1.0) 走 RAG
- 验证：知识性问题路由到 TYPE_0，具体诊断问题不被误判

## 任务 2：parcel_id 透传修复（framework/agents/nodes.py）

### Step 2.1: 扩展 execute_models 的 context 透传列表
- 在透传列表中添加 "parcel_id" 和 "parcel_code"
- 验证：test_execute_models_pipeline.py 的 parcel_id 透传测试通过

## 任务 3：DataFile 模型补全（framework/models/data_file.py）

### Step 3.1: 创建 DataFile SQLAlchemy 模型
- 参考 framework/models/document.py 结构
- 表名 kb_data_file，字段 id/doc_name/file_path/file_type/file_size/category/treatment_type/status/create_by/create_time
- 提供 to_dict() 方法
- 验证：from framework.models.data_file import DataFile 成功

### Step 3.2: 验证 import 链恢复
- 验证 framework/api/routes/docs.py 的 import 成功
- 验证 test_docs_dedup.py collection 不再报错

## 任务 4：测试引用过时修复（tests/test_model_specs_sync.py）

### Step 4.1: 更新归档路径引用
- 将 openspec/changes/sync-model-specs-from-overview/specs/ 替换为 openspec/changes/archive/2026-07-24-sync-model-specs-from-overview/specs/
- 验证：test_model_specs_sync.py 的 12 个测试通过

## 任务 5：测试基础设施修复

### Step 5.1: 修复 fake.shp 缺失
- 为 test_stability_and_grade_integration.py 创建最小测试 shapefile
- 或在测试中 mock geopandas.read_file
- 验证：test_run_all_models_returns_nine_modules 通过

### Step 5.2: 修复 chroma_db 损坏
- 删除 chroma_db/ 目录重置损坏的元数据
- 验证：test_vector_store_operations 通过

### Step 5.3: 修复 langchain Tool import
- 将 test_function_calling.py 中的 from langchain.tools import Tool 改为 from langchain_core.tools import Tool
- 验证：test_function_calling.py collection 不再报错

## 任务 6：回归验证

### Step 6.1: 运行全量测试
- 运行 pytest tests/ --continue-on-collection-errors
- 确认无 collection error
- 对比修复前后失败列表

### Step 6.2: 确认零回归
- 确认不引入新的测试失败
- 确认 80 failed → 0 failed（或仅剩环境限制 skip）

## 验证标准

- 全量测试通过（80 failed → 0，4 errors → 0）
- question type 路由覆盖 TYPE_0-5
- 知识性问题正确识别
- parcel_id/parcel_code 透传到 context
- DataFile 模型可用，import 链恢复
- 测试引用路径正确
- 测试基础设施正常

