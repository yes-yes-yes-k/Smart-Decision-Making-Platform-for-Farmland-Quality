## 为什么

外部目录 `模型4_v2` 实际交付的是韶关旱地/水田有机质培肥 Dose 随机森林模型。当前仓库虽然已经保存训练数据、joblib、metadata，并且底层函数可以直接预测，但正式 `model-5` 仍调用规则型 `OrganicMatterAgent`，聊天和单模型 API 不能获得该 RF 结果。

现在需要统一公开身份和内部文件命名：将该能力正式归入 `model-5/organic-matter-improvement`，完成字段适配、Agent 注册、单模型 API 和聊天路由，同时保留现有 `model-6` 占位能力不变，避免“模型已部署但正式入口仍是模拟结果”。

## 变更内容

- **BREAKING**：将真实肥力 ML 引擎从 `framework/domain/other_models/model_6.py` 重命名并归属到 `framework/domain/other_models/model_5.py`，同步更新所有内部导入、测试和文档；不再保留 `model_6.py` 作为该引擎入口。
- 将 `model-5` 的正式 Agent 改为调用韶关 RF Dose 模型；`area_code=lechang` 时按 `land_type` 选择旱地或水田模型，SOC 继续使用全局 ETR 模型。
- 增加外部字段到当前模型字段的明确输入适配：`SJD/YJZ/TD/TL/TJ/YXL/SXJ/YJZTSZ/YJFLX` 映射为 `pH/SOCbe/TN/TP/TK/AP/AK/Gap/Fertilizer type`，并保留 `SOMbe→SOCbe` 兼容。
- 在 `AgentManager`、统一能力目录、`/api/v1/models/run` 和 `/api/v1/chat/` 中完成 `model-5` 的正式调用链，返回真实模型版本、置信度、降级状态和输入校验结果。
- 保留 `model-6/placeholder` 能力、占位 Agent、question type 6 路由及其对外描述，不删除、不改名、不将 RF 模型注册为 model-6。
- 对非韶关区域明确使用现有通用肥力模型或规则降级，并在响应中标注实际模型来源，禁止静默伪装为韶关 RF 结果。

## 功能 (Capabilities)

### 新增功能

无。该变更将已有肥力 ML 能力正式接入现有 `model-5` 能力，不新增公开模型编号。

### 修改功能

- `fertility-ml-prediction`：真实引擎公开入口从 `model_6.py/model_6_execution` 改为 `model_5.py/model_5_execution`，并增加源字段适配和正式 `model-5` 调用契约。
- `professional-model-agents`：`model-5` 从规则型 `OrganicMatterAgent` 改为可调用真实 RF 的有机质培肥 Agent；`model-6/placeholder` 保持不变。
- `role-based-routing`：type 5/model-5 的 Agent 执行结果必须来自真实 RF 或明确的非韶关降级路径；type 6/model-6 占位路由保持不变。
- `api-documentation-examples`：更新 model-5 请求示例、字段要求、模型版本和可靠性/降级说明。

## 影响

- 代码：`framework/domain/other_models`、`framework/agents/specialized`、`framework/agents/manager.py`、`framework/agents/capabilities.py`、路由及模型 API 适配层。
- API：`POST /api/v1/models/run` 和 `POST /api/v1/chat/` 的 model-5 输入和响应字段增加真实 ML 元数据；model-6 占位接口行为不变。
- 数据：继续使用 `data/fertility/` 下的全局/韶关训练数据、joblib 和 metadata；不重新训练模型，除非回归验证发现资产不一致。
- 依赖：运行时需要 scikit-learn 与 joblib；部署检查需要验证四个 RF/ETR 模型文件及 metadata 可加载。
- 测试：增加字段映射、model-5 单模型 API、model-5 聊天路由、旱地/水田选择、非韶关降级、版本/置信度和 model-6 保持占位的回归测试。
