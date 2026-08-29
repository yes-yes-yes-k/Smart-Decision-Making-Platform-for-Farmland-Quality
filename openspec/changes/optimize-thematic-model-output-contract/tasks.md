## 1. 建立统一输出契约基础设施

- [x] 1.1 新增规范模型结果、评价对象、运行元数据、问题项和五种状态的类型定义与运行时校验器
- [x] 1.2 实现旧 `execute()` 状态、原因、模拟标记和数据来源到规范 `status/meta/issues` 的集中映射，覆盖成功、降级、拒绝、不可用和异常路径
- [x] 1.3 实现递归严格 JSON 清洗，统一将 `NaN`、`Infinity` 和 `-Infinity` 转为 `null`，并在需要时追加 `NON_FINITE_VALUE` 问题
- [x] 1.4 实现 `public_full`、`chat_compact`、`llm_context` 和 `audit` 四种纯投影函数，确保投影不重新执行模型且不复制完整结果
- [x] 1.5 为规范信封、状态约束、问题项、严格 JSON 和投影边界补充单元测试
- [x] 1.6 明确 Function Calling 与关键词回退共用同一规范结果转换器；保留现有回退触发条件，不在本变更中重做工具调用循环

## 2. 迁移六个专业模型

- [x] 2.1 重构 `BaseAgent.analyze()` 和聊天答复生成，使规范模型结果成为唯一业务事实来源，并删除默认的 `analysis/evidence/findings` 复制逻辑和硬编码通用置信度；兼容已有 Function Calling tool wrapper 的返回值
- [x] 2.2 迁移 Model-1 的预计算、数据库和降级路径到稳定性结果 Schema，将九模块收敛到 `result.modules` 并删除 `all_results` 重复项
- [x] 2.3 迁移 Model-2 的数据库与 CSV 路径到质量等级结果 Schema，统一指标和障碍度字段及数据来源元数据
- [x] 2.4 迁移 Model-3 的数据库与旧 SQLite 路径到障碍诊断结果 Schema，隔离原始 `evaluation/diagnosis` 存储层级
- [x] 2.5 迁移 Model-4 的数据库与 Legacy 路径到酸化改良结果 Schema，将来源缩写统一映射为有业务含义的 snake_case 字段
- [x] 2.6 迁移 Model-5 的数据库快速路径、全局 ETR 和韶关 RF 路径到有机质提升结果 Schema，保留两个真实置信度并对缺失预测返回明确降级
- [x] 2.7 将当前 `_StubAgent` 提供的 Model-6 占位调用改为 `unavailable`、`result=null` 和 `MODEL_NOT_IMPLEMENTED`，禁止返回成功桩结果
- [ ] 2.8 为六个模型分别补充成功、降级、拒绝、不可用和多数据源字段一致性测试
- [x] 2.9 验证 Function Calling、关键词回退两条路径对同一模型输出相同的规范字段集合和状态语义

## 3. 改造专题模型 API 与兼容层

- [x] 3.1 修改 `src/ai_culti_demo/thematic_models.py` 和 CoreEngine 调用边界，使正式能力直接传递规范模型结果且不再提升 Model-5 特例字段
- [x] 3.2 修改 `POST /api/v1/models/run`，默认返回带 `schema_version=2.0`、`trace_id` 和 `public_full` 数据的传输包络
- [x] 3.3 实现 `response_schema="1.0"` 兼容投影和弃用提示，确保旧响应完全由规范结果单向生成
- [ ] 3.4 为专题模型 API 补充 Schema 2.0、Schema 1.0 兼容、业务失败与 HTTP 参数错误的集成测试

## 4. 精简聊天编排与 LLM 上下文

- [x] 4.1 重构 AgentManager，使内部结果按模型保存规范信封，并从规范结果确定性生成汇总答复，不再构造 `data.details.analysis` 嵌套；保留关键词回退路由行为
- [x] 4.2 修改 Orchestrator 的 LLM prompt，只传递用户问题和 `llm_context` 投影；Function Calling 已生成答复时直接复用，并为最终 LLM 失败实现不重新执行模型的确定性答复
- [x] 4.3 提取聊天公共响应序列化器，统一生成 `message_id/answer/sources/recommendations/routing`，默认省略模型详情
- [x] 4.4 支持 `include_model_results=true` 时返回 `models` 的 `chat_compact` 投影，并移除可推导的 `agents_invoked` 及重复路由字段
- [x] 4.5 让 `/api/v1/chat/stream` 的 `done.data` 复用非流式响应序列化器，确保 RAG 和专业模型路径的字段省略规则一致
- [ ] 4.6 为 RAG、各专业模型、边界待确认、LLM 成功/失败、显式模型详情及流式/非流式一致性补充集成测试
- [ ] 4.7 覆盖 Function Calling 成功、无 tool call、工具失败和关键词回退场景，验证公共响应均不暴露 `data/details`

## 5. 持久化、可观测性与调用方迁移

- [x] 5.1 调整模型执行日志和结果持久化边界，将规范输出用于公共快照，将完整输入与内部诊断限制在 audit/trace 中
- [x] 5.2 增加 Schema 1.0 兼容调用计数和规范状态监控映射，确保弃用情况与 `ok/degraded/rejected/unavailable/error` 可观测
- [ ] 5.3 更新项目内前端和其他调用方，改用 `data.result`、`data.issues`、聊天 `data.routing` 及可选 `data.models`
- [x] 5.4 更新 OpenAPI、接口示例和迁移文档，列明旧字段到新字段的映射、兼容请求方式和计划下线条件

## 6. 回归与验收

- [x] 6.1 使用项目指定 Python 解释器运行专题模型、AgentManager、Orchestrator 和 API 全量相关测试并修复回归
- [x] 6.2 对六模型公共响应执行严格 JSON 解析、禁止旧重复字段和敏感审计字段的自动化检查
- [x] 6.3 使用现有实测 Model-1 样本比较 Schema 1.0 与 2.0 的响应体积和重复内容，记录压缩结果并确认九模块只保留一份
- [x] 6.4 验证 Schema 1.0 回滚开关不改变模型计算结果，并形成兼容层下线检查清单
