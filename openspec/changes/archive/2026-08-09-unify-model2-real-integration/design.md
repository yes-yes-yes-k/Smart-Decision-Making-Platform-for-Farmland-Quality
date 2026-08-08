## Context

当前能力目录把 `model-2` 定义为提升潜力评估，但其 `PotentialAssessmentAgent` 只计算固定 `MOCK_INDICATORS`；真实的 Python 质量评价和潜力算法则由另一个 `model-7/FarmlandGradeAgent` 暴露。底层 `src/ai_culti_demo/farmland_grade_eval` 已具备质量等级、障碍度、单地块潜力和县域潜力函数，默认数据为项目内 CSV。详见本 change 的 proposal 和 delta specs。

## Goals / Non-Goals

**Goals:**

- 将 `model-2` 变成唯一的真实耕地质量评价/提升潜力专题 Agent。
- 让质量等级问题和提升潜力问题都通过 `model-2` 进入真实 Python 引擎，并正确透传 `parcel_code`、县域编码和 CSV 路径。
- 从能力目录、Agent 注册、路由、公开能力描述、验证报告和测试中移除独立 `model-7`，最终注册 6 个专题 Agent。
- 保持底层 `farmland_grade_eval` 包的模块路径和函数兼容，降低已有内部调用的迁移成本。
- 从运行时、API 能力描述和模型标识别名中彻底删除 `quality-grade-evaluation` / `model-7` 的历史记录。

**Non-Goals:**

- 不重新实现或改写 `farmland_grade_eval` 的评价公式、权重、等级阈值和潜力情景算法。
- 不把 `D:\work\2026\0801\模型2` 目录作为线上运行时依赖；项目继续使用仓库内置或上传部署的 CSV。
- 不新增 HTTP 批量潜力端点，不迁移其他专题模型的业务边界。
- 不在本 change 中解决 `model-5`、`model-6` 等其他 Agent 的模拟/真实状态问题。

## Decisions

### 1. 以 model-2 作为唯一规范身份

能力目录保留 `agent_id="model-2"` 和 `model_id="improvement-potential-assessment"`，将 `FarmlandGradeAgent` 的真实引擎调用并入新的模型2执行路径。`model-7` 从 `PROFESSIONAL_CAPABILITIES` 和 `AgentManager` 注册表移除。选择统一身份而不是保留双注册，是为了使“只有 6 个专题模型”在 API 和运行时都可验证；底层 Python 包名不需要改名。

### 2. 模型2按问题类型选择真实计算分支

保留 `question_type=6` 作为提升潜力主类型，并为 `question_type=5` 增加到同一 `model-2` 的路由别名。模型2根据上下文选择：

- type 5 或明确质量等级/障碍度问题：调用 `run_grade_evaluation(parcel_code)`；
- type 6 的单地块问题：调用 `run_potential_analysis(parcel_code)`；
- type 6 的县域问题：调用 `run_county_potential(xqmc_code, scenario)`；
- 没有 `parcel_code`：返回 `status: "error"`、`error.code: "MISSING_PARCEL_CODE"`；其他数据问题返回对应部署或数据错误，不调用固定模拟指标。

路由器不再要求每个问题类型只能对应不同 Agent，而是允许多个问题类型映射到同一个 Agent。能力目录增加问题类型别名或等价映射，公开 descriptor 仍以规范能力为准。

### 3. 不保留 model-7 兼容层

删除 `quality-grade-evaluation` 和 `model-7` 的输入别名、公开描述、注册项和独立 Agent 入口。旧标识不再被解析为模型2，调用方必须改用规范的 `improvement-potential-assessment` 或模型2对应的路由入口。选择彻底删除是为了避免第七个模型的历史记录继续影响能力统计、接口语义和后续维护。

### 4. 真实结果与模拟回退分离

模型2的真实分支必须直接使用 `farmland_grade_eval` 返回的状态和明细，并显式标记 `simulated=false`。如果 CSV 缺失、地块不存在、编码越界或输入不足，返回机器可读错误/提示；不再把固定 `MOCK_INDICATORS` 当作成功结果。只有在已有框架明确允许的非生产演示入口中，才可保留模拟回退，并且必须保留 `simulated=true`。

### 5. 删除验证优先于兼容测试

旧的 `model-7` 路由和 7 模型数量断言改为 6 模型断言；新增 type 5/type 6 均调用 model-2、真实 A0001 结果、缺少 parcel_code、CSV 缺失和旧标识不存在测试。底层 `farmland_grade_eval` 既有回归测试继续保留，确保归并只改变归属和入口，不改变公式数值。

## Risks / Trade-offs

- [Risk] type 5 与 type 6 共享一个 Agent，若路由上下文缺少问题类型可能选错计算分支 → 强制透传 `question_type`，并在模型2入口对缺失类型返回输入不足。
- [Risk] 旧客户端仍发送 `model-7` → 该调用将不再被识别；通过 API 文档和发布说明明确模型2的新唯一入口。
- [Risk] CSV 未部署时真实模型不可用 → 返回 `DEPLOYMENT_ERROR` 或 `need_input`，禁止静默返回演示数值。
- [Trade-off] 仍保留 `farmland_grade_eval` 目录名，目录名称与公开模型编号不一致 → 将其视为底层实现包，公开模型身份由能力目录和 Agent 契约决定，避免大范围物理重命名。

## Migration Plan

1. 先更新能力目录和路由映射，使注册表只包含 6 个 Agent，并删除 model-7/旧公开名称的所有别名。
2. 将真实质量评价和潜力分析入口合并到模型2 Agent，补齐上下文透传和错误状态。
3. 同步更新 API 描述、OpenAPI、验证脚本、README 和测试断言。
4. 运行定向模型/路由测试，再运行完整 Python 测试套件；确认 A0001 回归值不变、`agents_invoked` 不出现 model-7。
5. 若回滚，只恢复旧能力目录和 Agent 注册；底层 Python 包及 CSV 不删除。
