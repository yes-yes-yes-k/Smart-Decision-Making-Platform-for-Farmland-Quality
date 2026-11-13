## ADDED Requirements

### Requirement: Owned conversational artifacts

系统 SHALL 将对话生成的地图、直方图、CSV 和可选预测 GeoTIFF 绑定到用户、会话及消息/结果 revision，保存筛选条件和生成状态。列表、预览、下载及历史入口 MUST 校验归属；路径白名单和登录校验 MUST NOT 替代对象授权。附件 MUST 使用服务端生成的不透明 ID，不返回绝对路径或 URL 内令牌。

#### Scenario: Authorized preview and download
- **WHEN** 会话所有者请求已完成附件
- **THEN** 系统 MUST 返回约定 MIME 的文件，预览/下载契约包含标题、大小、种类与元信息

#### Scenario: Cross-user or legacy endpoint bypass
- **WHEN** 其他用户尝试通过新接口或原有全局产物接口访问该附件
- **THEN** 系统 MUST 拒绝访问且不泄露文件；历史无归属产物不得默认向所有登录用户开放

#### Scenario: Conversation deleted
- **WHEN** 会话已删除但物理文件尚未清理
- **THEN** 系统 MUST 立即撤销附件访问，并允许幂等文件清理

### Requirement: Faithful visual presentation

系统 SHALL 提供已有预测和通量结果的地图/直方图，默认不插值。仅在服务支持且用户明确请求时启用插值，并披露实际方法及降级。产物 MUST 显示年度或时期未知、来源、指标、单位状态、边界来源、覆盖和截断信息，区别像元统计与记录统计；分级 MUST NOT 被描述为污染安全结论。

#### Scenario: Default map
- **WHEN** 用户请求 Cd 分布图且没有要求插值
- **THEN** 系统 MUST 默认不插值，展示真实来源、覆盖及空白区域含义

#### Scenario: Unsupported flux interpolation
- **WHEN** 用户要求当前通量制图服务不支持的插值
- **THEN** 系统 MUST 明确说明不支持，不忽略参数或谎称已插值

### Requirement: Bounded and recoverable artifact generation

系统 SHALL 校验制图参数、点数和导出行数；CSV 超过 10 万行 MUST 报错，地图截断 MUST 明示。生成失败 MUST NOT 发布半成品附件；重试 MUST 关联同一请求 revision，状态不得错配到新结果。下载 MUST 限制受控路径和文件类型。

#### Scenario: Retry after failed generation
- **WHEN** 文件生成失败后用户重试
- **THEN** 系统 MUST 清理或隔离失败产物，提供可追溯完成状态且不引用零字节或未完成文件

#### Scenario: Invalid path or oversized export
- **WHEN** 请求使用非法产物 ID/文件类型/越界路径，或 CSV 超过上限
- **THEN** 系统 MUST 拒绝请求并返回可读错误，不返回其他文件或静默截断

### Requirement: Frontend preview acceptance

系统 SHALL 定义 HTTP/SSE 共用的附件结构及携带登录凭据获取文件的方式。真实聊天预览、下载和历史消息显示 MUST 由前端消费方联调验证，后端仅返回附件 ID 或通过替身测试 MUST NOT 被记录为完整界面验收。

#### Scenario: Frontend not yet connected
- **WHEN** 后端附件契约通过但尚未完成真实聊天预览联调
- **THEN** 验收记录 MUST 分别标明后端已完成和前端未完成，保留对应实施任务未勾选
