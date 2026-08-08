---
comet_change: unify-model2-real-integration
role: technical-design
canonical_spec: openspec
---

# 模型2真实能力归并设计

## 1. 设计目标

本设计细化 `unify-model2-real-integration` change，目标是将项目中真实的耕地质量评价、障碍度和提升潜力计算统一接入专题模型2，并从运行时、公开能力目录和路由中彻底删除模型7。底层 `src/ai_culti_demo/farmland_grade_eval` 包继续作为内部计算模块，算法公式和 CSV 数据契约不变。

最终运行时拓扑为：

```text
question_type=5 质量等级/综合指数/障碍度 ─┐
                                           ├─ model-2 ── farmland_grade_eval
question_type=6 单地块/县域提升潜力 ───────┘
```

## 2. 当前执行链路与问题

`AgentManager._execute_with_dependencies()` 对每个 Agent 调用 `analyze(payload)`，再调用 `answer_from_analysis(analysis)` 生成聊天结果。因此真实计算必须进入模型2的 `execute(payload)`，只修改 `answer_question()` 不会影响统一聊天链路。

当前 `PotentialAssessmentAgent` 的 `execute()` 固定复制 `MOCK_INDICATORS` 并标记 `simulated=True`；当前 `FarmlandGradeAgent` 才会调用 `run_grade_evaluation()`。能力目录和路由还把这两个入口分别识别为 model-2 和 model-7，造成公开身份错位。

## 3. 组件设计

### 3.1 能力目录

- `PROFESSIONAL_CAPABILITIES` 只保留 6 项，删除独立 `model-7` 项。
- `model-2` 使用规范公开 ID `improvement-potential-assessment`，领域为 `potential`。
- 为模型2增加质量等级计算所需的 `parcel_code` 前提，并声明单地块/县域潜力的可选参数。
- `ProfessionalCapability` 增加问题类型别名表达能力：规范的 `question_type` 保留 6，同时允许 `question_type=5` 作为同一 Agent 的路由别名；`CAPABILITY_BY_QUESTION_TYPE` 和公开 descriptor 必须保持确定性。
- 删除 `quality-grade-evaluation`、`model-7` 和 `LEGACY_MODEL_ALIASES` 中相关历史记录，不做输入迁移。

### 3.2 路由器

`TYPE_AGENTS` 改为显式或由别名展开生成：

```python
{
    1: ["model-1"],
    2: ["model-4"],
    3: ["model-3"],
    4: ["model-6"],
    5: ["model-2"],
    6: ["model-2"],
    7: ["model-5"],
}
```

路由器允许多个问题类型指向同一个 Agent，但每个问题类型仍只调用一个 Agent。任何路由结果不得包含 `model-7`。

### 3.3 模型2 Agent

保留 `PotentialAssessmentAgent` 作为唯一模型2实现，重写 `execute(payload)`：

1. 读取 `question_type`、`parcel_code`、`xqmc_code`、`scenario` 和可选 `csv_path`。
2. `question_type=5` 调用 `run_grade_evaluation(parcel_code, dat_path=csv_path)`，返回质量等级、综合指数、12 项指标和障碍度。
3. `question_type=6` 且有 `parcel_code` 时调用 `run_potential_analysis(parcel_code, csv_path)`。
4. `question_type=6` 且有县域编码和情景时调用 `run_county_potential(xqmc_code, scenario, csv_path)`。
5. 缺少 `parcel_code` 或县域潜力所需参数时返回：

   ```json
   {
     "status": "error",
     "error": {
       "code": "MISSING_PARCEL_CODE",
       "message": "缺少地块编码 parcel_code"
     },
     "metadata": {"simulated": false}
   }
   ```

6. 底层 `DEPLOYMENT_ERROR`、`PARCEL_NOT_FOUND`、字段越界等错误原样保留错误码和消息；任何异常都转成结构化错误，不回退到 `MOCK_INDICATORS`。
7. 返回 `metadata.simulated=false`，并在结果中保留 `model_version="python_v1_20260801"`（质量评价结果）或潜力分析的底层结果字段。

`answer_from_analysis()` 负责通用结构化摘要；模型2可覆盖该方法以生成包含“质量等级/潜力等级/综合指数/全改良结果”的简明中文答复，但不得重新计算数值。

### 3.4 AgentManager 与上下文

- `_register_agents()` 只根据 6 项能力目录注册 Agent，删除 `self.agents["model-7"]` 依赖声明和 `FarmlandGradeAgent` 加载分支。
- `execute_models` 继续透传 `question_type`、`parcel_code`、`parcel_id`、`xqmc_code`、`scenario` 和 `csv_path`；其中 `parcel_id` 仍供 model-1/3/4 使用，`parcel_code` 供 model-2 使用。
- `_analysis_payload()` 保留这些字段，不能把 `parcel_code` 丢在嵌套 `data` 中。
- 未知公开模型 ID（包括旧 model-7 标识）返回未知模型错误，不做 alias 解析。

## 4. 数据流与错误契约

真实请求的数据流为：

```text
API/chat request
  -> question type identification
  -> context(parcel_code, question_type, scenario, csv_path)
  -> AgentManager
  -> model-2.execute
  -> farmland_grade_eval.runner
  -> structured analysis
  -> answer_from_analysis
```

错误处理契约：

| 条件 | 状态 | 错误码 | 是否模拟 |
|---|---|---|---|
| 缺少 `parcel_code` | `error` | `MISSING_PARCEL_CODE` | `false` |
| CSV 不存在/不可读 | `error` | `DEPLOYMENT_ERROR` | `false` |
| 地块不存在 | `error` | `PARCEL_NOT_FOUND` | `false` |
| 编码字段越界 | `error` | 底层字段错误码 | `false` |
| 计算成功 | `ok` | 无 | `false` |
| 旧 model-7 标识 | `error` | `UNKNOWN_MODEL` | `false` |

## 5. 测试策略

### 定向单元测试

- 能力目录长度为 6，且不包含 model-7/quality-grade-evaluation。
- `TYPE_AGENTS[5] == ["model-2"]`、`TYPE_AGENTS[6] == ["model-2"]`。
- AgentManager 注册表只有 model-1 至 model-6。
- `model-2.execute()` 对 A0001 返回真实质量等级和 `simulated=False`。
- `model-2.execute()` 对 A0001 返回单地块潜力结果，并验证逐项潜力和全改良结果字段。
- 县域情景返回等级分布和障碍度统计。
- 缺少 `parcel_code`、CSV 缺失、地块不存在和旧 model-7 标识分别返回指定错误。

### 回归与集成验证

- 保留 `farmland_grade_eval` 现有 A0001 数值回归（综合指数约 0.6728、10 等）。
- 验证聊天链路 type 5/type 6 的 `agents_invoked` 均为 `["model-2"]`，不出现 model-7。
- 运行完整测试套件，确认其他五个专题模型和 RAG 路由无回归。
- 更新验证报告生成器和 API 文档后，重新生成并检查六模型能力表。

## 6. 风险与回滚

- **风险：** 原有针对 `FarmlandGradeAgent` 的测试和导入路径会失效。**处理：** 将测试迁移到模型2统一入口，删除旧模型7相关测试，不保留兼容别名。
- **风险：** 县域潜力请求缺少情景参数。**处理：** 返回明确输入错误，不默认选择情景。
- **风险：** 真实 CSV 的内容版本与外部源目录不同。**处理：** 本 change 不自动覆盖 CSV；使用当前项目已部署数据，数据同步另行处理。
- **回滚：** 回滚代码提交和对应 change 即可恢复旧注册表；不删除底层 `farmland_grade_eval` 包或 CSV。

