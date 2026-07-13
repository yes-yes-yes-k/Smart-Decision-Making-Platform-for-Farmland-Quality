## Why

现有框架已集成底层核心引擎（`src/ai_culti_demo`），但缺少面向专业模型的智能体层。Excel「专业模型总览表」定义了 6 个耕地质量专业模型和 3 类用户角色（省市管理端、县域执行端、农户种植端）的问题库，需要将这些模型能力封装为独立智能体，通过中心化编排实现多智能体协作，为不同角色用户提供精准的专业问答和模型计算服务。

## What Changes

- 新增智能体基类 `BaseAgent`，定义统一接口：接收任务、执行模拟计算、返回结构化结果
- 新增 6 个专业智能体，每个对应一个专业模型：
  - `StabilityRiskAgent` — 耕地质量等级稳定性与退化风险识别
  - `PotentialAssessmentAgent` — 耕地质量提升潜力评估
  - `ProblemIdentificationAgent` — 耕地质量主要问题精准识别
  - `AcidificationRemediationAgent` — 耕地土壤酸化改良
  - `OrganicMatterAgent` — 耕地土壤有机质培肥提升
  - `ComprehensiveImprovementAgent` — 耕地综合地力改良提升
- 新增 `AgentManager` 中心化编排器，负责任务分配、智能体调度和结果汇总
- 新增模拟数据层，为每个智能体提供领域内的模拟输入输出数据
- 新增用户角色路由逻辑，根据省市/县域/农户角色将问题路由到正确的智能体组合
- 修改现有 `framework/agents/orchestrator.py`，集成新的多智能体框架
- 修改现有 `framework/api/routes/chat.py`，支持通过聊天接口触发多智能体协作

## Capabilities

### New Capabilities

- `agent-base-framework`: 智能体基类框架，定义 BaseAgent 抽象类、AgentManager 编排器、模拟数据层和通信机制
- `professional-model-agents`: 6 个专业模型智能体实现，每个智能体包含领域知识、模拟计算逻辑和问题回答能力
- `role-based-routing`: 用户角色路由机制，根据省市管理端/县域执行端/农户种植端的问题特征路由到正确的智能体组合

### Modified Capabilities

（无现有 spec 需要修改）

## Impact

- **代码影响**: `framework/agents/` 目录新增多个文件，`framework/api/routes/chat.py` 修改调用逻辑
- **API 影响**: `/api/v1/chat/` 接口增强，支持多智能体协作返回结构化结果
- **依赖影响**: 无新增外部依赖，复用现有 LangGraph 框架
- **数据影响**: 使用模拟数据，不依赖真实数据源
