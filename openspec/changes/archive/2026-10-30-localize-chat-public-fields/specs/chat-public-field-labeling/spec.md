# chat-public-field-labeling Specification (Delta)

## ADDED Requirements

### Requirement: 用户可见专业字段统一使用中文标准名称

系统 SHALL 在所有用户可见的专业分析文本中，将已登记的模型内部字段码转换为中文标准名称。该转换 SHALL 适用于普通聊天答复、确定性降级答复、综合报告正文、`report_draft`、文本型 `recommendations` 和助手历史消息正文。

首批标准映射 SHALL 至少包括：

| 内部字段 | 中文标准名称 |
|---|---|
| `SJD` / `pH` | 土壤酸碱度 |
| `YJZ` | 有机质 |
| `YXL` / `AP` | 有效磷 |
| `SXJ` / `AK` | 速效钾 |
| `TRRZ` | 土壤容重 |
| `GCZD` | 耕层质地 |
| `GGNL` | 灌溉能力 |
| `PSNL` | 排水能力 |
| `DXBW` | 地形部位 |
| `ZDGX` | 质地构型 |
| `YXTCHD` | 有效土层厚度 |
| `GCHD` | 耕层厚度 |
| `JHX` | 交换性氢 |
| `JLA` | 交换性铝 |
| `YTK` | 土壤调理剂（亿土康） |
| `MBNT` | 木本泥炭 |
| `SOCbe` | 初始土壤有机碳 |
| `SOMbe` | 初始土壤有机质 |
| `SOC` | 土壤有机碳 |
| `TN` / `TD` | 全氮 |
| `TP` / `TL` | 全磷 |
| `TK` / `TJ` | 全钾 |
| `Gap` / `YJZTSZ` | 有机质提升目标 |
| `Dose` | 建议施用量 |
| `Fertilizer type` / `YJFLX` | 肥料类型 |

#### Scenario: 障碍诊断答复包含内部字段码

- **WHEN** Model-2 或 Model-3 的自然语言答复候选包含 `GGNL`、`DXBW` 或 `SXJ`
- **THEN** 最终用户答复 SHALL 分别显示“灌溉能力”、“地形部位”和“速效钾”
- **AND** 最终用户答复 SHALL NOT 同时保留这些内部字段码

#### Scenario: 酸化和培肥答复包含内部字段码

- **WHEN** Model-4 或 Model-5 的自然语言答复候选包含 `JHX`、`JLA`、`SOCbe` 或 `Dose`
- **THEN** 最终用户答复 SHALL 使用对应中文标准名称

#### Scenario: 综合报告复用公共字典

- **WHEN** 综合诊断报告或确定性摘要渲染专业字段
- **THEN** 系统 SHALL 使用与普通聊天相同的公共字段字典
- **AND** SHALL NOT 维护语义冲突的独立展示映射

### Requirement: 机器可读字段与计算结果保持不变

中文字段转换 SHALL 只作用于用户可见自然语言文本。系统 SHALL NOT 因展示转换而重命名 `public_full`、`chat_compact`、`models`、规范 `result`、模型输入、审计快照或版本化计算结果中的 JSON 键，也 SHALL NOT 重新执行模型或修改计算值。

#### Scenario: 聊天请求显式包含模型结果

- **WHEN** 客户端设置 `include_model_results=true`
- **THEN** `answer` SHALL 使用中文标准字段名称
- **AND** `data.models` SHALL 继续遵循现有结构化模型结果契约
- **AND** 展示转换 SHALL NOT 改变模型状态、数值、版本、输入哈希或计算时间

#### Scenario: 专题模型 API 返回结构化结果

- **WHEN** 调用方直接请求专题模型的机器可读结果
- **THEN** 系统 SHALL 保持现有 Schema 和字段命名
- **AND** SHALL NOT 把结构化 JSON 键替换为中文

### Requirement: 非流式与流式聊天使用相同字段转换语义

`POST /api/v1/chat/` 的 `answer`、`POST /api/v1/chat/stream` 的 token 文本和 `done.data.answer` SHALL 使用同一公共字段字典。SSE 转换 SHALL 支持字段码跨任意 token 边界拆分，不得向客户端提前发送无法撤回的字段码片段。

#### Scenario: 完整字段码位于单个 token

- **WHEN** SSE token 包含完整的 `GGNL`
- **THEN** 客户端 SHALL 接收到“灌溉能力”而不是 `GGNL`

#### Scenario: 字段码跨多个 token

- **WHEN** SSE 依次生成 `G`、`GN`、`L`
- **THEN** 流式转换器 SHALL 缓冲未决前缀并最终输出“灌溉能力”
- **AND** 客户端 SHALL NOT 接收到残留的 `G`、`GN` 或 `GGNL`

#### Scenario: 流式完成事件保持一致

- **WHEN** SSE 输出完成
- **THEN** 系统 SHALL 在 `done` 事件前刷新待判定文本
- **AND** 所有 token 拼接后的文本与 `done.data.answer` SHALL 使用相同中文字段名称

### Requirement: 字段转换遵守独立词边界

系统 SHALL 只转换作为独立专业字段出现的已登记字段码，匹配大小写不敏感；系统 SHALL NOT 修改更长机器标识、版本字符串或普通单词中的同形字符序列。

#### Scenario: 独立字段码被转换

- **WHEN** 用户可见文本包含 `GGNL（重度障碍）`
- **THEN** 系统 SHALL 输出“灌溉能力（重度障碍）”

#### Scenario: 字段码嵌入更长标识

- **WHEN** 文本包含 `GGNLcode` 或 `XGGNL`
- **THEN** 系统 SHALL 保持该标识原样

### Requirement: 历史助手消息向后兼容中文展示

新助手消息 SHALL 在持久化前完成字段转换。对已经保存且仍包含内部字段码的助手消息，系统 SHALL 在消息列表返回和重新构造 LLM 会话历史时转换为中文标准名称；用户原始消息 SHALL 保持不变。

#### Scenario: 读取旧助手消息

- **WHEN** 数据库中的旧助手消息包含 `GGNL`、`DXBW` 或其他已登记字段码
- **THEN** 消息查询接口 SHALL 返回中文标准名称
- **AND** 系统 SHALL NOT 要求先执行历史数据批量迁移

#### Scenario: 旧消息进入后续 LLM 上下文

- **WHEN** 包含内部字段码的旧助手消息被用于下一轮对话历史
- **THEN** 提供给 LLM 的助手历史文本 SHALL 已转换为中文标准名称

#### Scenario: 用户消息包含字段码

- **WHEN** 用户主动输入 `GGNL` 等字段码进行询问
- **THEN** 系统 SHALL 保留用户消息原文
- **AND** 助手的最终解释 SHALL 使用中文标准名称

### Requirement: LLM 不得作为唯一字段转换机制

最终 LLM prompt SHALL 指示模型使用中文标准字段名称且不得展示内部字段码；无论 LLM 是否遵循提示、是否不可用或是否走 Function Calling，最终用户文本出口仍 SHALL 执行确定性字段转换。

#### Scenario: LLM 原样复制内部字段码

- **WHEN** LLM 候选答复仍包含 `GGNL` 或其他已登记字段码
- **THEN** 输出边界 SHALL 在返回和持久化前转换该文本

#### Scenario: LLM 总结不可用

- **WHEN** 系统使用确定性摘要作为降级答复
- **THEN** 确定性摘要 SHALL 使用相同公共字段字典
