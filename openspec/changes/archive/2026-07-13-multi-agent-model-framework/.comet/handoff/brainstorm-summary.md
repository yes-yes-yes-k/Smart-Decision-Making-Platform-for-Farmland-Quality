# Brainstorm Summary

- Change: multi-agent-model-framework
- Date: 2026-07-13

## 确认的技术方案

采用方案 A：AgentManager 作为独立模块，在现有 LangGraph 的 `execute_models` 节点中被调用。

- BaseAgent 抽象基类：定义 `execute(task)` 和 `answer_question(question, context)` 两个核心方法
- AgentManager 中心化编排器：负责智能体注册、角色路由、依赖调度和结果汇总
- 6 个专业智能体：每个内置具体数值模拟数据（如 pH=5.5、有机质=25g/kg）和阈值规则
- Router 模块：基于关键词匹配识别省市/县域/农户三类角色

## 关键取舍与风险

- 模拟数据不真实 → 明确标注 `simulated: true`，后续可替换为真实计算
- 关键词路由精度有限 → 模拟环境可接受，后续可升级为 LLM 路由
- 智能体间依赖硬编码 → 模拟环境可接受，后续可改为配置驱动

## 测试策略

- 每个智能体独立测试：验证模拟计算输出和问题回答
- AgentManager 测试：验证依赖调度顺序和结果汇总格式
- API 集成测试：验证 `/api/v1/chat/` 端到端流程
- 三类角色路由测试：验证省市/县域/农户问题正确路由

## Spec Patch

无。Open 阶段的 delta spec 已包含充分的验收场景。
