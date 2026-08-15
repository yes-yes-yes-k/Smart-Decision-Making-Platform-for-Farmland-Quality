## 新增需求

### 需求: model-5 聊天路由使用真实肥力 ML

type 5 的聊天请求必须路由到 `model-5/OrganicMatterAgent`，并在提供区域和特征时执行真实肥力 ML；type 6 继续路由到 `model-6` 占位 Agent。

#### 场景: type 5 韶关请求
- **当** 用户问题被识别为 type 5，且上下文包含 `area_code=lechang`、`land_type` 和土壤特征
- **那么** `AgentManager.process` 只调用 model-5，并返回 SG RF 版本、Dose 和可靠性状态

#### 场景: type 6 占位请求
- **当** 用户问题被识别为 type 6
- **那么** 路由仍只调用 model-6 占位 Agent，不能转到 model-5

## 修改需求

### Requirement: 智能体组合执行

系统 SHALL 根据统一能力目录对 question_type 1 至 6 进行一对一专业路由：1→model-1，2→model-2，3→model-3，4→model-4，5→model-5（真实有机质培肥 ML Agent），6→model-6（占位符）。question_type=0 SHALL 继续走 RAG。路由 SHALL NOT 因底层文件名将 type 5 改派到 model-6。

#### Scenario: 有机质培肥问题调用 model-5
- **WHEN** 用户问题被识别为 type 5
- **THEN** AgentManager SHALL 仅调用 `model-5/OrganicMatterAgent`，并使用其真实分析结果或明确降级结果

#### Scenario: model-6 仍为占位
- **WHEN** 用户问题被识别为 type 6
- **THEN** AgentManager SHALL 仅调用 `model-6` 占位 Agent，行为保持不变

### Requirement: API 集成

系统 SHALL 通过现有 `/api/v1/chat/` 接口将 `area_code`、`land_type`、规范特征和外部源字段透传到 model-5 Agent，并返回包含 `question_type`、`agents_invoked`、`summary`、`recommendations` 和 model-5 真实/降级元数据的结构化结果；不得把 model-5 RF 结果放入 model-6。

#### Scenario: 聊天接口触发 model-5 RF
- **WHEN** 客户端提交有机质培肥问题并携带 `area_code=lechang` 和 `land_type`
- **THEN** API SHALL 返回 `question_type=5`、`agents_invoked=["model-5"]` 和实际 RF 模型版本

#### Scenario: 聊天请求缺少输入
- **WHEN** type 5 请求没有足够特征
- **THEN** API SHALL 返回 model-5 的 `need_input` 或 `fallback` 状态，不能返回未标记的模拟成功结果
