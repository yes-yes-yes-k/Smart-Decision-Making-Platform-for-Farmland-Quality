# add-acidification-rf-prediction 设计

## Context

当前 `farmland-acidification-improvement-model` 已定义 model-4 过程模型（四个 land/fertilizer 子模型、按需计算和标准化输出）。旧 `D:\work\suan\AcidificationModel\api` 的 Web `/predict` 是另一条在线 RF 计算链路：路由依据 `model_id` 查询 `Models.Data_type`，重命名请求特征，按本次请求批次执行 `SimpleImputer(strategy=mean).fit_transform`，再由 `app.model.predict` 通过 `load_model(session, model_id)` 读取 `Models.ModelFilePath` 的 pickle 模型。`reduce` 路由输出还经过 `predict_to_Q`、`Q_to_t_ha`、`t_ha_to_t_mu`，水田 `reflux` 取绝对值。

上述是旧代码路径层面的事实，但旧系统数据库中实际的 `ModelID`、`Data_type`、`Land_type`、`ModelFilePath` 及模型 metadata 尚未核验。因此不能以离线脚本 `calculate_soil_acidification_with_model.py` 的路径或 CSV 结果推断 Web 使用的同一模型。

## Goals / Non-Goals

**Goals:**

- 将旧 Web `/predict` 的在线 RF 语义核验后，迁移为当前系统的独立内部可调用能力。
- 保持模型选择、特征适配、请求批次缺失值处理、预测和 `reduce`/`reflux` 输出转换的可追溯性。
- 让模型 ID、文件路径、版本和特征顺序来自经核验的数据库/模型 metadata，而不是硬编码猜测。
- 当资产或在线语义无法核验时显式降级，禁止返回伪造的 RF 成功结果。

**Non-Goals:**

- 不通过 HTTP 调用旧服务或新增 HTTP 兼容代理。
- 不迁移离线 CSV 批处理/结果，也不把离线脚本作为在线实现依据。
- 不修改 model-4 过程模型，不设计 RF 与 model-4 的互补交互或自动组合。

## Decisions

### 1. RF 作为独立能力，不复用 model-4 过程计算

新增独立 RF domain/service 入口和结果来源标识。model-4 仍按现有请求契约执行；RF 调用不会隐式触发过程模型，过程模型也不会自动补齐 RF 结果。这样可以避免把统计学习预测与机理过程量混为同一结果。

### 2. 先核验旧数据库和在线路由，再冻结映射

实现前必须从旧系统可运行数据库/迁移快照核对至少：`ModelID`、`Data_type`、`Land_type`、`ModelFilePath`、模型文件 hash/metadata、特征顺序及输出单位。在线路由源码只用于确定控制流；离线脚本路径不能作为模型同一性的证据。核验结果应形成可审计清单和固定测试夹具，缺少证据的字段保持未知或降级。

### 3. 在入口显式完成特征适配和字段冲突检查

把旧路由的输入重命名规则集中在适配层，适配层输出规范化特征向量、实际模型 ID、土地类型及来源元数据。规范字段与旧别名同时出现且值冲突时拒绝请求；字段顺序必须由核验的 `Data_type`/模型 metadata 驱动，不能按字典迭代顺序猜测。

### 4. 保留“请求批次 fit_transform”的语义，但先明确其边界

旧 Web 路由的 `SimpleImputer(strategy=mean)` 是对当前请求批次执行 `fit_transform`，不是未经证实的训练集固定均值。迁移实现应先用在线路由和真实模型 metadata 复核这一行为及其适用范围；核验前不得改写为训练集均值，也不得静默用 0 填充。批次为空、全列缺失或特征无法转数值时返回可解释 rejected/degraded 结果。

### 5. 单独实现 reduce/reflux 转换并保留原始预测

RF 结果内部同时保留模型原始 prediction 与转换后的业务量。`reduce` 只有在在线路由和真实模型 metadata 核验转换关系、单位及精度后，才应用 `predict_to_Q → Q_to_t_ha → t_ha_to_t_mu`；水田 `reflux` 的绝对值语义同样必须由在线行为复核。证据不完整时结果应标记为未核验/降级，而非猜测单位或强行转换。

### 6. 模型加载隔离且禁止不透明回退

通过受控模型仓库/加载器按已核验的 `ModelID` 定位 `ModelFilePath`，校验路径范围、文件 hash 和 metadata。加载失败、版本不匹配或 metadata 缺失时返回 model_unavailable/degraded；不得切换到 model-4、离线模型或伪造均值预测来冒充 RF 成功。

### 7. 随当前运行时重序列化已核验资产

实测旧 pickle 中的 estimator 记录 scikit-learn 1.3.0，而项目指定运行时为 1.9.0。三个模型在 1.9.0 加载后以其真实 `feature_names_in_` 构造 DataFrame 执行预测，使用当前版本 pickle round-trip 后预测逐值相等；因此将这三个已纳入项目的 RF pickle 在 1.9.0 重序列化，更新 manifest SHA-256、大小、pickle 协议和序列化 sklearn 版本。该操作不改模型结构/训练数据，不迁移或触碰 model-4；manifest hash 仍用于加载前完整性校验。若未来 sklearn 运行时变化，需重新进行 round-trip 预测等价探针，不能以屏蔽警告代替兼容性验证。

### 8. 当前系统只提供内部 callable 接入

第一阶段仅定义 domain/service callable 入口，供当前 agent 或其他内部流程显式调用；不新增 HTTP `/predict`，不访问旧服务。是否需要未来 HTTP API 由独立 change 讨论，且不能改变本提案的非目标。

## Migration and Rollback

1. 只读获取旧 Web 路由、数据库 schema/数据快照和真实模型 metadata，建立字段、模型 ID、路径、土地类型、输出单位核验记录；在项目指定 sklearn 运行时完成资产加载/预测对比后重序列化，随即更新 manifest hash/版本元数据。
2. 先实现适配器、加载器和转换单元测试，再接入独立 RF callable 入口。
3. 用固定小批量样本验证完整预测、缺失值、模型选择、reduce 与 paddy reflux；对照旧在线路径或同一模型的直接调用，不使用离线 CSV 结果作为等价证明。
4. 灰度启用独立 RF 能力，监控 model metadata、降级原因和输出来源；model-4 路径保持不变。
5. 若核验失败或结果不一致，关闭 RF 能力开关/移除注册，不回退到 model-4，不删除既有过程模型和数据。

## Risks / Trade-offs

- **数据库实例不可得或记录不完整** → 不猜测 `ModelID`/路径，能力保持未启用并记录阻塞证据。
- **离线脚本与 Web 模型不是同一资产** → 要求数据库 `ModelFilePath`、文件 hash 和 metadata 三者闭环确认；脚本路径只能作为线索。
- **请求批次均值填充导致输入分布随批次变化** → 保留旧在线语义以便兼容，但把批次策略和填充字段纳入审计；是否改训练集 imputer 另立决策。
- **reduce/reflux 单位或符号误读** → 先保留原始预测并在元数据中标记转换状态；未核验时不发布转换后的确定性结果。
- **RF 与 model-4 结果被误认为可互换** → 输出显式来源/模型类型，文档明确二者无预设互补关系。
- **pickle 跨版本仍有序列化安全/维护风险** → 当前只消除 1.3.0→1.9.0 加载警告并记录重序列化版本/hash；pickle 仍是可执行序列化格式，资产必须来自受控清单，升级 sklearn 时重新验证。

## Open Questions

- 真实旧路由源码版本快照、pickle 训练 metadata/特征名和目标运行时兼容性需发布前人工确认。
- 当前 `soil_indicators` 对 NO3/NH4/CEC 没有明确语义，parcel mapping 保持 `need_verification`；需人工确认后才能提供 parcel-level RF 成功调用。
- RF 未来是否暴露 HTTP API，或是否存在与 model-4 的业务编排，另立 change 决定。
