# Design: fix-test-infra-failures

## 修复方案

### 1. geoalchemy2 stub 统一策略

**问题**：`test_soil_data_models.py` 直接 `from framework.models import soil_data`，触发 `thematic_model.py` 顶部 `from geoalchemy2 import Geometry`，测试环境未安装该包导致 `ModuleNotFoundError`。

**方案**：在 `test_soil_data_models.py` 顶部添加与 `test_agent_specialized.py` 相同的 geoalchemy2 stub 模式（在导入 thematic_model 之前 stub Geometry 类）。

### 2. test_agent_manager.py 路由期望值修正

**问题**：9 个测试的期望值写成偏移映射（type1→model-4、type2→model-5、type3→model-1、type4→model-2、type5→model-3），但实际路由是 `type N → model-N`（正确）。

**方案**：将期望值修正为 `type N → model-N`，并更新 `test_manager_register_five_agents` 期望包含 6 个 Agent（model-6 为占位 Agent）。

### 3. test_import_lechang_data.py 导入路径修复

**问题**：`scripts/import_lechang_data.py:37` 用 `import framework.models.soil_data` 触发注册，但 `framework/__init__.py` 未导出 `models` 子模块。

**方案**：将 `scripts/import_lechang_data.py` 中的导入改为 `from framework.models import soil_data`（显式子模块导入，不依赖 `framework/__init__.py` 导出）。

### 4. test_docs_dedup.py / test_observability_api.py fixture 表创建顺序

**问题**：`create_app('sqlite')` 调用 `_ensure_kb_message_columns` 尝试 `ALTER TABLE kb_message`，但 SQLite 内存数据库中该表尚未 `CREATE TABLE`。

**方案**：在 `_ensure_kb_message_columns` 中先检查表是否存在（`has_table`），不存在时先 `CREATE TABLE` 再 `ALTER TABLE`；或调整测试 fixture 确保 `create_all()` 在 `_ensure_kb_message_columns` 之前执行。

### 5. chromadb 旧文件兼容

**问题**：旧 `chroma_db` 目录中的 `chroma.sqlite3` 与 chromadb 0.5.11 不兼容，抛 `KeyError: '_type'`。

**方案**：在 `chroma_store.py` 的 `_init_client` 中捕获 `KeyError: '_type'`，自动清理持久化目录后重试一次（project memory 已记录此方案）。

## 不涉及

- 不修改生产代码的业务逻辑
- 不修改 API 契约或数据库 schema
- 不修改路由映射逻辑（路由是正确的，只是测试期望值错误）
