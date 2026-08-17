## 上下文

外部 `模型4_v2` 是韶关有机质培肥提升模型，包含旱地和水田两个 Dose RandomForestRegressor 子模型。当前仓库已经有训练数据、joblib、metadata 和可工作的底层推理逻辑，但实现文件命名为 `model_6.py`，正式 `model-5` 仍由规则型 `OrganicMatterAgent` 提供，`model-6` 又被能力目录定义为占位符，导致内部文件、公开模型编号和实际业务能力不一致。

本变更必须同时满足四个约束：

- 外部模型4_v2正式公开为 `model-5/organic-matter-improvement`；
- 完成正式 Agent、单模型 API 和聊天 API 的调用链；
- 不再保留 `framework/domain/other_models/model_6.py` 作为该模型入口，避免产生 model-6 混淆；
- `model-6/placeholder` 能力和占位 Agent 原样保留，不删除、不改名、不接入 RF 引擎。

## 目标 / 非目标

**目标：**

- 将真实肥力 ML 引擎文件和函数规范化为 `model_5.py` / `model_5_execution`。
- 保持全局 ETR SOC 预测、全局 Dose 预测和韶关旱地/水田 RF Dose 路由的现有算法行为。
- 增加外部 CSV 字段到当前 metadata 字段的显式适配，并在输入错误时返回可解释结果。
- 让 `OrganicMatterAgent` 通过统一的 `analyze(payload)`、`execute(task)` 和 `answer_question()` 调用同一个真实计算结果。
- 让 `/api/v1/models/run` 和 `/api/v1/chat/` 都可以传递区域、土地类型和源模型字段，并返回真实模型版本、置信度、降级和模拟状态。
- 增加 model-5 端到端验收，并证明 model-6 仍为占位符。

**非目标：**

- 不重新训练或改变外部提供的 RF 模型参数、训练集划分和 metadata 版本。
- 不改变酸化 `model-4`、质量等级 `model-2` 或障碍诊断 `model-3` 的业务边界。
- 不删除或重编号能力目录中的 `model-6/placeholder`。
- 不把非韶关区域伪装成韶关 RF 结果；非韶关路径只沿用现有通用模型或明确降级。

## 决策

### 1. 用 `model_5.py` 作为唯一底层入口

将现有 `framework/domain/other_models/model_6.py` 的真实肥力 ML 实现迁移到 `framework/domain/other_models/model_5.py`，把现有占位 `model_5.py` 替换为真实实现，并统一导出 `model_5_execution`。同步更新 `__init__.py`、Agent、脚本、测试和文档，仓库中不再存在该 RF 引擎的 `model_6.py` 或 `model_6_execution` 入口。

选择直接重命名而不是保留兼容别名，是因为用户明确要求消除 model-6 文件名造成的公开身份混淆；model-6 的公开占位能力仍由 Agent 层保留，不依赖底层文件名。

### 2. 保留 `OrganicMatterAgent` 作为 model-5 的正式 Agent 外观

不新增第七个 Agent。改造现有 `OrganicMatterAgent`，让其在具备结构化土壤特征时调用 `model_5_execution`，在 `area_code=lechang` 时选择韶关 RF，在其他区域使用通用模型或显式规则降级。Agent 的公开 `model_id` 保持 `model-5`，统一能力目录仍保留 6 项，其中 `model-6` 继续由 `_StubAgent` 占位。

### 3. 在输入边界设置单独的字段适配层

适配层将外部字段转换为模型 metadata 使用的字段：

```text
SJD → pH
YJZ → SOCbe
TD → TN
TL → TP
TJ → TK
YXL → AP
SXJ → AK
YJZTSZ → Gap
YJFLX → Fertilizer type
```

当前训练兼容的 `SOMbe→SOCbe` 仍保留。适配层在进入模型前统一完成 strip、数值转换、必需字段检查和肥料类型校验；底层模型只接收规范化字段，不在模型内部混入源文件命名规则。

### 4. 单模型 API 与聊天 API 复用同一个 Agent 分析结果

`/api/v1/models/run` 通过 `model_id=organic-matter-improvement` 调用 `OrganicMatterAgent.analyze()`；聊天链路 type 5 也调用同一个分析入口，再由现有编排器汇总。禁止 API 和聊天分别复制一套 RF 计算逻辑，避免结果和元数据不一致。

成功响应至少包含 `status=success`、`model_id=model-5`、`model_version`、`soc_prediction`、`dose_prediction`、`dose_confidence`、`simulated=false` 和实际区域/土地类型；均值填充、非韶关通用模型或模型文件缺失时必须显式标出 `imputation_applied`、`fallback` 或 `simulated`。

### 5. 保持 type 5/type 6 路由边界

统一能力目录和 `TYPE_AGENTS` 继续保持：

```text
question_type=5 → model-5/OrganicMatterAgent
question_type=6 → model-6/_StubAgent
```

只替换 type 5 实际执行实现，不修改 type 6 占位能力的名称、公开 ID、路由或返回行为。

## 风险 / 权衡

- **文件重命名造成旧内部导入失败** → 在同一变更中全量搜索 `model_6`、`model_6_execution`，同步修改源码、测试、脚本、文档，并以“仓库中不存在 RF 用途的 model_6.py”为验收条件。
- **外部字段与当前 metadata 字段含义被误配** → 使用源 README 的字段定义建立适配表；增加每个字段的单位、类型和转换测试，禁止仅按缩写字面替换。
- **非韶关区域误用 SG RF** → 只允许 `SHAOGUAN_AREA_CODES` 命中时选择 SG 子模型，并在响应中返回 `region`、`land_type` 和实际模型版本。
- **输入缺失时再次静默返回规则模拟值** → Agent 必须返回机器可读的 `fallback`/`need_input` 状态，并把 `simulated=true` 明确传到 API；完整真实特征调用必须断言 `simulated=false`。
- **model-6 占位能力被误改** → 增加注册表回归测试，断言 model-6 仍为 `_StubAgent`、公开能力为 `placeholder`，且 RF 只出现在 model-5。
- **预测值被误解为确定性处方** → 保留 metadata 中的 R²、warning 和“仅供参考”提示，文档明确要求农艺人员复核。

## 迁移计划

1. 先新增字段适配和 model-5 引擎测试，确认当前四个模型资产可加载。
2. 将真实引擎从 `model_6.py` 迁移为 `model_5.py`，更新导出和所有内部引用；此步骤完成后仓库中不保留旧文件。
3. 改造 `OrganicMatterAgent`，接入真实分析结果，更新能力目录描述中的运行前提和可靠性状态。
4. 更新模型 API、聊天节点和路由上下文，补充 `area_code`、`land_type` 以及外部字段透传。
5. 运行 model-5 专项测试、现有六模型测试和完整测试套件；确认 model-6 占位回归通过。
6. 部署时先运行模型资产健康检查，再灰度验证 type 5/API；如 RF 加载失败，只允许回退到明确标注的通用模型/规则结果，不恢复 `model_6.py` 旧入口。

## 开放问题

- 非韶关区域的最终降级策略需要在实现阶段确认是继续使用全局 ETR，还是使用现有规则型培肥结果；两者都必须在响应中显式标注。
- API 是否同时接受源字段和规范字段需要确认。设计默认两者均可接受，规范字段优先，冲突时返回输入冲突错误而不是静默覆盖。
