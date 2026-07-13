## Why

当前新框架 `framework/` 的专业模型模块（`framework/domain/other_models/`）使用占位实现，缺少完整的县域数据目录、诊断规则引擎和专题模型框架。原始项目 `src/ai_culti_demo` 包含完整的数据目录系统、县域概览、诊断规则和6个专题模型定义，应作为底层核心引擎被新框架调用，而非完全抛弃。

## What Changes

- 将 `src/ai_culti_demo` 重构为核心引擎模块，提供数据目录、县域概览、诊断规则和专题模型服务
- 修改 `framework/api/routes/county.py`，调用底层引擎获取县域概览和诊断分析
- 修改 `framework/api/routes/models.py`，调用底层引擎获取模型列表
- 修改 `framework/agents/nodes.py`，调用底层引擎执行专题模型
- 创建 `framework/core_engine/` 适配器层，统一调用底层引擎接口
- 保留原始 HTTP Server 和 CLI 功能，确保向后兼容

## Capabilities

### New Capabilities

- `core-engine-adapter`: 核心引擎适配器，统一调用 `src/ai_culti_demo` 的数据目录、概览、诊断和模型服务
- `diagnosis-rule-engine`: 诊断规则引擎，支持酸化诊断、质量总览、治理提升三种诊断主题
- `thematic-model-framework`: 专题模型框架，支持6个专题模型的定义和执行

### Modified Capabilities

- `unified-api-layer`: 修改县域诊断接口实现，从底层引擎获取数据
- `multi-agent-orchestrator`: 修改专业模型执行逻辑，调用底层引擎的专题模型

## Impact

- **代码**: 修改 `framework/api/routes/county.py`、`framework/api/routes/models.py`、`framework/agents/nodes.py`
- **新增**: `framework/core_engine/` 适配器层
- **保留**: `src/ai_culti_demo/` 原始代码保持不变
- **API**: 接口保持向后兼容，实现细节变更
