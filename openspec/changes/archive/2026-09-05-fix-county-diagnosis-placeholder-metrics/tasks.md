## 1. 安全响应契约

- [x] 1.1 在县域诊断模块中定义定量字段可用性元数据构造与校验规则，覆盖 `status`、`reason`、`unit`、`source`、`method`、`model_version`、`calculated_at` 和 `scope`
- [x] 1.2 增加统一响应安全校验，递归检查 `problems`、`measures`、`treatments`、`regions`、`base_data` 中的非空定量值及其字段级依据
- [x] 1.3 为模板化诊断定义 `status=degraded`、`result_kind=advisory_only` 和顶层非预测可靠性字段

## 2. 县域诊断实现

- [x] 2.1 移除 `diagnosis.py` 中固定的治理周期、提升率、效果、成本和问题占比，并将需兼容保留的旧字段改为 `null`
- [x] 2.2 为保留的定性问题、治理方向和推荐图层增加 `advisory_only` 与 `template_guidance` 依据说明，并删除预测性措辞
- [x] 2.3 停止返回没有真实空间统计依据的重点区域、权重和效果排序；无可靠结果时返回空列表及机器可读不可用原因
- [x] 2.4 确保 `measures`、`treatments`、`regions` 和 `base_data` 只从通过安全校验的结构生成，不在兼容别名中恢复旧值
- [x] 2.5 保持非法区域和非法主题的现有错误码与 HTTP 行为不变

## 3. 下游兼容与摘要传播

- [x] 3.1 更新核心引擎和 `build_report_summary`，接受结构完整的安全降级诊断并传播 `result_kind`、`reliability` 和定量不可用状态
- [x] 3.2 确保诊断摘要、关键发现、治理建议和行动项不根据 `null` 字段补造周期、提升率、效果、成本或占比
- [x] 3.3 检查县域诊断 API 的序列化与调用适配层，确保 HTTP 200 的 `degraded/advisory_only` 语义不会被改写为 `ok`

## 4. API 文档与迁移说明

- [x] 4.1 更新县域诊断 OpenAPI schema，使相关定量字段可空，并补充 `metric_meta`、`result_kind` 和可靠性字段定义
- [x] 4.2 更新 API 请求/响应示例，展示模板建议、真实定量结果最低溯源要求和错误响应的差异
- [x] 4.3 增加旧客户端迁移说明，要求前端处理 `null`、`degraded` 和空重点区域列表，并显示“暂无可靠估计”而不是本地默认数字

## 5. 自动化验证

- [x] 5.1 更新现有县域诊断与接口测试，使合法模板请求期望 `degraded/advisory_only`，同时保留主题、建议和推荐图层断言
- [x] 5.2 新增负向契约测试，递归确认活动响应中不存在旧固定周期和固定提升率、效果、成本、占比
- [x] 5.3 新增字段级依据测试，验证 `unavailable` 字段只能为 `null`，非空定量值缺少完整来源时被拒绝
- [x] 5.4 新增兼容别名测试，验证 `measures`、`treatments`、`regions` 和 `base_data` 不会复制无依据值
- [x] 5.5 新增诊断摘要回归测试，验证安全降级状态被保留且摘要不会恢复已清空的数字
- [x] 5.6 使用项目指定 Python 解释器运行县域诊断、核心引擎、摘要与 API 契约定向测试
- [x] 5.7 使用 `rg` 和完整测试集检查旧占位常量、预测性措辞及跨模块行为回归，并记录无法在本地执行的外部依赖测试
