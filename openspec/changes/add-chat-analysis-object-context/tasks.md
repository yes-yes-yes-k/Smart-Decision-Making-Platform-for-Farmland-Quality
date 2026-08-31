## 1. 数据库迁移与 ORM

- [x] 1.1 为 `kb_conversation` 增加 `analysis_object`、`context_version`、`analysis_object_updated_at`
- [x] 1.2 为 `kb_message` 增加 `analysis_context_snapshot`
- [x] 1.3 新增 `spatial_region_catalog` ORM、唯一约束、父级字段与索引
- [x] 1.4 为 `model_execution_log` 增加对象、上下文版本、模型版本和数据时间字段及索引
- [x] 1.5 提供向前迁移和回滚脚本，并验证现有数据默认值
- [x] 1.6 从已启用 `area_code_region_map` 精确导入首批区域目录，不导入默认回退

## 2. 分析对象领域层

- [x] 2.1 定义 `AnalysisObject`、`AnalysisContext`、`CalculationMode` 数据结构和校验规则
- [x] 2.2 实现地块解析器，精确查询 `parcel_info` 并生成规范父级路径
- [x] 2.3 实现区域解析器，精确查询 `spatial_region_catalog`
- [x] 2.4 实现解析器注册表与对象访问权限校验接口
- [x] 2.5 实现 `AnalysisContextService` 的 set/inherit/clear 和版本条件更新
- [x] 2.6 实现旧版 parcel_id/parcel_code/area_code 到新对象的兼容适配器与弃用提示
- [x] 2.7 为双旧版地块 ID 增加权威一致性校验；缺少映射时拒绝而非猜测

## 3. 聊天 API 集成

- [x] 3.1 为非流式聊天接入统一上下文解析、消息快照和错误映射
- [x] 3.2 为 SSE 聊天复用同一服务，并保持应用上下文内的持久化安全
- [x] 3.3 实现 HTTP 200 可恢复状态、HTTP 409/422/503 错误包络
- [x] 3.4 在会话列表/详情响应中返回当前对象和上下文版本
- [x] 3.5 确保非法对象请求不修改会话对象或保存误导性助手结果

## 4. 编排与模型前置守卫

- [x] 4.1 在专业能力目录增加 supported_object_types/requires_spatial_object/supports_scenario/required_scenario_inputs
- [x] 4.2 实现 `AnalysisRequirementGuard`
- [x] 4.3 在问题类型识别后、Function Calling 与 AgentManager 之前接入守卫
- [x] 4.4 为 needs_analysis_object 和 needs_scenario_inputs 增加确定性响应节点
- [x] 4.5 确保知识问答与不要求空间对象的问题不受影响

## 5. 专业 Agent 安全收敛

- [x] 5.1 移除生产聊天酸化模型缺地块时自动补 MOCK_INPUTS 的数值输出路径
- [x] 5.2 统一 Model-1 至 Model-5 在对象验证失败时的拒绝/输入不足语义
- [x] 5.3 为支持的模型接入显式 scenario 模式和必需输入校验
- [x] 5.4 保留测试或显式演示入口的 MOCK 能力，并确保生产聊天不可到达
- [x] 5.5 确保数据库异常不会被解释为对象不存在或触发默认区域回退

## 6. 溯源与持久化

- [x] 6.1 实现 `ResultProvenanceBuilder`
- [x] 6.2 在最终回答前生成固定对象标题与情景试算标签
- [x] 6.3 将编排器 trace_id、用户、会话和对象版本传入每次模型执行
- [x] 6.4 写入实际关键输入、模型版本、data_as_of、data_version 和 calculated_at
- [x] 6.5 确保消息快照、响应溯源和执行日志内容一致
- [x] 6.6 确保最终 LLM 只能润色正文，不覆盖结构化对象与溯源字段

## 7. API 文档与兼容说明

- [x] 7.1 更新 `docs/openapi.json` 的请求、成功响应、可恢复状态和错误 schema
- [x] 7.2 增加 set/inherit/clear、scenario、版本冲突和旧字段兼容示例
- [x] 7.3 更新 README/API 文档中的对象继承、弃用字段和错误语义

## 8. 测试

- [x] 8.1 单元测试对象解析、父级路径、权限、上下文动作与版本冲突
- [x] 8.2 单元测试模型空间要求守卫和 scenario 输入校验
- [x] 8.3 集成测试地块级问题缺对象时不调用工具、Agent 或 LLM
- [x] 8.4 集成测试县域统计问题允许县级对象通过
- [x] 8.5 集成测试 Function Calling 与关键词回退均不能绕过守卫
- [x] 8.6 集成测试非流式与 SSE 返回相同上下文和溯源字段
- [x] 8.7 集成测试消息与执行日志共享对象版本和 trace_id
- [x] 8.8 测试旧字段合法归一化与非法标识拒绝，不返回 MOCK 数值
- [x] 8.9 运行完整测试套件并记录回归结果（846 passed，22 skipped）

## 9. 发布与观测

- [x] 9.1 先部署可空迁移与兼容读取，再启用中央守卫
- [x] 9.2 增加 needs_analysis_object、422、409、503 和旧字段使用量指标
- [x] 9.3 验证可按对象类型、区域、模型和时间聚合执行日志
- [x] 9.4 编写回滚与客户端迁移说明
