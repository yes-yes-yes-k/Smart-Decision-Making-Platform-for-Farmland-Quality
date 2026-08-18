## Why

测试套件存在 47 failed + 35 errors 的预先存在失败，全部是测试基础设施问题，不是生产代码缺陷。这些失败阻碍了 CI 信号的有效性，使真正的回归难以被发现（如本次 integrate-parcel-db-into-models 归档后补充测试时，只能通过单独运行相关测试文件来确认无回归，无法依赖完整套件）。

## What Changes

- 统一 `geoalchemy2` stub 策略到所有需要导入 `thematic_model` 的测试文件（test_soil_data_models.py 等），避免 `ModuleNotFoundError`
- 修正 `test_agent_manager.py` 中 9 个路由映射期望值：实际路由是 `type N → model-N`，测试错误地写成了偏移映射（type1→model-4 等）
- 修正 `test_manager_register_five_agents` 期望：model-6 已注册为占位 Agent，期望应包含 6 个 Agent
- 修复 `test_import_lechang_data.py` 的 `framework.models` 导入路径（`ImportError: cannot import name 'models' from 'framework'`）
- 修复 `test_docs_dedup.py` / `test_observability_api.py` 的 fixture 表创建顺序：`_ensure_kb_message_columns` 尝试 `ALTER TABLE kb_message` 但表未先创建
- 处理 chromadb 旧文件兼容问题（`KeyError: '_type'`）：清理旧 `chroma_db` 目录或添加初始化清理逻辑

## Capabilities

无 spec 级行为变更。此 change 是纯测试基础设施修复，不改变任何生产代码行为、API 契约或数据库 schema。将在 `.openspec.yaml` 中设置 `skip_specs: true`。

## Impact

- **测试文件**：test_agent_manager.py、test_import_lechang_data.py、test_docs_dedup.py、test_observability_api.py、test_soil_data_models.py
- **不影响生产代码**：所有修改限于 `tests/` 目录和测试 fixture
- **不影响 API、依赖或系统行为**
