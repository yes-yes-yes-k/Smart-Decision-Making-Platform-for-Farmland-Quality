# add-acidification-rf-prediction 提案

## Why

旧 `AcidificationModel` 系统的 Web `/predict` 路由包含一条独立的随机森林（RF）在线酸化预测链路：按 `model_id` 查询模型元数据，按 `Data_type`/土地类型重命名输入，在当前请求批次上执行 `SimpleImputer(strategy=mean).fit_transform`，加载数据库 `ModelFilePath` 指向的 pickle 模型并预测；`reduce` 结果还经过 `predict_to_Q`、`Q_to_t_ha`、`t_ha_to_t_mu` 转换，水田 `reflux` 使用绝对值处理。当前系统已有 model-4 过程酸化模型，但没有将这条独立的 Web RF 计算能力纳入正式能力边界。

本提案只定义如何把旧在线语义核验后移植为当前系统的独立 RF 能力，避免把离线批处理脚本或未经证实的模型资产关系当成在线事实。旧系统数据库中的真实 `ModelID`、`Data_type`、`Land_type`、`ModelFilePath` 尚未核对，不能依据 `calculate_soil_acidification_with_model.py` 的路径断言 Web 使用了同一模型。

## What Changes

- 新增独立的酸化 RF 预测能力，与既有 model-4 过程模型并列，不修改 model-4 的公式、输入和输出。
- 按旧 Web `/predict` 的实际在线调用链建立特征适配、模型选择、缺失值处理和预测输出语义；具体字段与转换在核验真实路由、数据库元数据和模型 metadata 后固化。
- 保留 `reduce` 的单位/量纲转换链和水田 `reflux=abs(...)` 语义，但在证据不足时显式降级，不猜测字段含义。
- 通过当前系统的内部可调用入口接入，不新增对外 HTTP 代理或依赖旧系统 HTTP 服务。
- 增加模型资产、元数据、缺失值、土地类型及输出转换的可验证契约和回归验收要求。

## Capabilities

### New Capabilities

- `farmland-acidification-rf-prediction`: 基于经核验旧 Web 在线语义的独立酸化 RF 预测能力。

### Modified Capabilities

- `farmland-acidification-improvement-model`：仅新增独立 RF 能力要求；既有 model-4 过程模型仍保持原有能力边界，不预设二者互补或自动串联。

## Impact

- 运行时：新增 RF 领域入口、特征适配与模型加载/预测适配层；不改变现有 model-4 路由。
- 模型资产与数据：需核验旧数据库实际 `ModelID`、`Data_type`、`Land_type`、`ModelFilePath` 及真实 pickle/joblib metadata；在核验完成前不得发布具体模型 ID、路径或版本断言。
- 输出：内部结果需区分 RF 与 process_v2 来源，并保留缺失值处理、模型元数据和 `reduce`/`reflux` 转换证据；无法核验时返回明确降级状态。
- 接口：不新增 HTTP `/predict` 兼容代理；当前系统使用内部 callable/domain 入口，具体公开 API 是否暴露另行决策。
- 测试：新增基于固定模型夹具/真实核验资产的在线语义测试；不运行旧离线 CSV 批处理作为本 change 的实现验证。

## Non-Goals

- 不走 HTTP，不把旧系统 `/predict` 作为运行时依赖，也不新增 HTTP 转发/兼容端点。
- 不迁移 `offline calculate_soil_acidification_with_model.py` 的 CSV 批处理流程、输出 CSV 或其结果数据。
- 不删除、替换或修改已有 model-4 过程模型。
- 不预设 RF 与 model-4 的互补交互、串联、择优或结果合并规则；是否存在业务协同需另行提出并验证。
- 不凭离线脚本路径、文件名或推测重建旧数据库中的 `ModelID`/`FilePath` 关系。
