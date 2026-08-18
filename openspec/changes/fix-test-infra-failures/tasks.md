# Tasks: fix-test-infra-failures

## 1. geoalchemy2 stub 统一

- [x] 1.1 在 test_soil_data_models.py 顶部添加 geoalchemy2 stub 模式（与 test_agent_specialized.py 一致）
- [x] 1.2 运行 test_soil_data_models.py 验证全部通过

## 2. test_agent_manager.py 路由期望值修正

- [x] 2.1 修正 test_manager_register_five_agents 期望：包含 6 个 Agent（model-1 到 model-6，model-6 为占位）
- [x] 2.2 修正 9 个路由映射测试期望值：type N → model-N（非偏移映射）
- [x] 2.3 运行 test_agent_manager.py 验证全部通过

## 3. test_import_lechang_data.py 导入路径修复

- [x] 3.1 修改 framework/models/__init__.py：用 try/except 包裹 thematic_model 导入，geoalchemy2 缺失时容错跳过
- [x] 3.2 运行 test_import_lechang_data.py 验证全部通过

## 4. test_docs_dedup.py / test_observability_api.py fixture 表创建顺序

- [ ] 4.1 修复 _ensure_kb_message_columns：先检查表是否存在，不存在时先 CREATE TABLE 再 ALTER TABLE
- [ ] 4.2 运行 test_docs_dedup.py 和 test_observability_api.py 验证全部通过

## 5. chromadb 旧文件兼容

- [ ] 5.1 在 chroma_store.py 的 _init_client 中捕获 KeyError: '_type'，清理持久化目录后重试一次
- [ ] 5.2 运行 test_rag.py 验证通过

## 6. 完整测试套件回归验证

- [ ] 6.1 运行完整测试套件确认无新回归（对比修复前后 failed/error 数量）
