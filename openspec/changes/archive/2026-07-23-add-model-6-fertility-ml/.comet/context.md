# Comet Design Handoff

- Change: add-model-6-fertility-ml
- Phase: design
- Mode: compact
- Context hash: 098b00b985b21328c5970b899b5597aa297916fef86edad839ebe8fe0c854f05

Generated-by: comet-handoff.sh

OpenSpec remains the canonical capability spec. This handoff is a deterministic, source-traceable context pack, not an agent-authored summary.

## openspec/changes/add-model-6-fertility-ml/proposal.md

- Source: openspec/changes/add-model-6-fertility-ml/proposal.md
- Lines: 1-64
- SHA256: 3f89fa2a3aa7d23368cf7b235fea0a30a9a9ed91e72c112e98482188cf3ccac6

```md
## Why

当前 `framework/agents/specialized/comprehensive_agent.py`（model-6）是占位用的综合编排器，仅根据规则拼接 model-4/model-5 的结论生成「分区分类提升建议」，并不具备真实的耕地肥力计算能力。同时 `framework/domain/other_models/model_6.py` 也只是返回空结果的 stub，未被任何 agent 实际调用。

用户提供的 ML demo（位于 `F:\BaiduNetdiskDownload\SOC（土壤有机碳）和Dose（施用量）预测模型\`）使用 ExtraTreesRegressor 训练了两个真实预测模型：
- **SOC 预测模型**（10 因子，5CV R²=0.89，测试集 R²=0.91）
- **Dose 施用量预测模型**（9 因子，5CV R²=0.43，测试集 R²=0.47）

按用户原始设想，6 个 model 都应是「计算模型」，model-6 的真实身份就是这套 SOC+Dose ML 预测。本次变更将 demo 转换为生产可用代码，替换占位实现，让 model-6 真正具备基于真实训练数据的预测能力。

## What Changes

- **新增** `framework/domain/other_models/model_6.py` 真实 ML 预测实现：替换占位 stub，调用预训练 `.joblib` 模型文件执行 SOC 和 Dose 预测
- **新增** `framework/agents/specialized/fertility_ml_agent.py`：`FertilityMLAgent` 类作为 model-6 的专业实现，封装 ML 预测调用与降级回退
- **修改** `framework/agents/specialized/__init__.py`：导出 `FertilityMLAgent`，移除 `ComprehensiveImprovementAgent` 导出
- **修改** `framework/agents/manager.py`：`_load_real_agents` 中 `model-6` 加载 `FertilityMLAgent`，依赖列表改为 `[]`（独立 ML 模型，不再依赖 model-4/5）
- **删除** `framework/agents/specialized/comprehensive_agent.py`：原占位编排器被替换
- **新增** `scripts/train_fertility_models.py`：从 Jupyter notebook 转换为 CLI 训练脚本，读取 xlsx → 训练 ETR → 保存 `.joblib`
- **新增** `data/fertility/` 目录：存放训练数据（`ML-data-SOC-RF_Manual_splits.xlsx`、`ML-data-Dose-RF_Manual_splits.xlsx`、`变量注释.xlsx`）和训练后的模型文件（`soc_etr_model.joblib`、`dose_etr_model.joblib`）
- **修改** `pyproject.toml`：新增依赖 `scikit-learn`、`joblib`
- **修改** `tests/test_agent_specialized.py`：更新 model-6 相关测试为 ML 预测断言，新增降级回退场景测试
- **修改** `.gitignore`：确保 `data/fertility/` 不被忽略，但忽略临时训练输出（如 `*.pkl.bak`）

## Capabilities

### New Capabilities
- `fertility-ml-prediction`: 基于 ExtraTreesRegressor 的耕地肥力机器学习预测能力。覆盖 SOC（土壤有机碳）和 Dose（施用量）两个 ETR 模型的训练数据资产、模型文件加载、预测调用契约、置信度与降级回退规则。该能力位于 `framework/domain/other_models/` 层，是 model-6 agent 的底层计算引擎。

### Modified Capabilities
- `professional-model-agents`: 现有 spec 中 `Requirement: ComprehensiveImprovementAgent 智能体`（model-6）的定义需要替换为 `Requirement: FertilityMLAgent 智能体`，行为从「综合编排多个模型结果」变更为「调用 ML 预测模型输出 SOC/Dose 预测值」。原 spec 中的两个 Scenario（综合提升建议、农户地块综合诊断）将被替换为 ML 预测相关场景。同时 model-6 的依赖关系从 `["model-4", "model-5"]` 改为 `[]`。

## Impact

**代码影响范围**：
- `framework/domain/other_models/model_6.py`：完全重写（stub → 真实 ML）
- `framework/domain/other_models/__init__.py`：保持导出 `model_6_execution` 名称不变（向后兼容）
- `framework/agents/specialized/fertility_ml_agent.py`：新文件
- `framework/agents/specialized/comprehensive_agent.py`：删除
- `framework/agents/specialized/__init__.py`：导出列表调整
- `framework/agents/manager.py`：`_load_real_agents` 中 model-6 加载逻辑调整，依赖列表调整
- `scripts/train_fertility_models.py`：新文件
- `data/fertility/`：新目录，包含 3 个 xlsx + 2 个 joblib
- `tests/test_agent_specialized.py`：测试用例调整
- `tests/test_agent_manager.py`：可能需要更新 model-6 相关断言

**API 影响范围**：
- Agent 内部调用契约变化：`ComprehensiveImprovementAgent.execute()` 返回 `{diagnosis, zoning_suggestions, priority_measures}` → `FertilityMLAgent.execute()` 返回 `{soc_prediction, dose_prediction, confidence, warning}`
- `AgentManager._summarize` 中 `details["model-6"]` 结构变化：上游消费者需感知此变更
- HTTP API `/api/chat` 端点响应中 model-6 字段结构变化

**依赖影响范围**：
- 新增 Python 依赖：`scikit-learn>=1.3.0`、`joblib>=1.3.0`
- 现有依赖 `pandas`、`numpy`、`openpyxl` 已满足
- 模型文件大小：SOC ETR（30 棵树）约 100-300KB，Dose ETR（290 棵树）约 1-3MB，均可入库

**向后兼容性**：
- `model_6_execution` 函数名保持不变，调用方无需修改
- `model_6_execution(input_data)` 的返回结构变化，但当前无外部调用者（仅 stub 被注册）
- AgentManager 接口保持 `process()` 不变，但 `details["model-6"]` 内部结构变化

**风险**：
- Dose 模型 R²=0.47，预测结果仅供参考，需在响应中明确标注置信度
- scikit-learn 安装会增加容器/部署体积约 100-200MB
- 训练数据 xlsx 文件大小未知，需评估是否适合入 git 仓库

```

## openspec/changes/add-model-6-fertility-ml/design.md

- Source: openspec/changes/add-model-6-fertility-ml/design.md
- Lines: 1-179
- SHA256: 01daeac23c8cc658f729650a4079b0f4cb20e8c76c0f9444dc2e06818fb91012

[TRUNCATED]

```md
## Context

当前项目的 6 个专业智能体（model-1 至 model-6）均采用基于规则的占位实现，并未承载真实计算逻辑。其中：

- `framework/agents/specialized/comprehensive_agent.py`（model-6）当前作为综合编排器存在，依赖 model-4/model-5 的结果生成"分区分类提升建议"，但内部逻辑是固定的 `IMPROVEMENT_MEASURES` 列表匹配，并非真正的计算模型。
- `framework/domain/other_models/model_6.py` 是更底层的占位 stub，函数签名 `model_6_execution(input_data: Dict) -> Dict` 返回固定空结果，未被任何 agent 实际调用。
- `AgentManager`（`framework/agents/manager.py`）通过 `_load_real_agents` 优先加载 specialized 实现并回退到 `_StubAgent`，依赖图显式声明 `model-6.dependencies = ["model-4", "model-5"]`。

用户提供的 ML demo 包含两个 Jupyter notebook，使用 `ExtraTreesRegressor` 训练 SOC（土壤有机碳）和 Dose（施用量）预测模型，性能分别为：
- SOC 模型：5CV R²=0.89，测试集 R²=0.91，RMSE=2.24（优秀）
- Dose 模型：5CV R²=0.43，测试集 R²=0.47，RMSE=320.52（较差）

训练数据为 `ML-data-SOC-RF_Manual_splits.xlsx`（10 因子：pH/SOCbe/TN/TP/TK/AP/AK/Gap/Dose/Fertilizer type）和 `ML-data-Dose-RF_Manual_splits.xlsx`（9 因子：去掉 Dose 自身）。两个 notebook 通过 7 步网格搜索确定最优超参数。

**约束与既有约定**（继承自 project_memory）：
- `src/ai_culti_demo/` 作为底层引擎必须保留，不可整体替换
- `framework/` 通过 `core_engine/adapter.py` 访问底层
- 开发环境使用 SQLite（`instance/development.db`），生产使用 `instance/production.db`
- API 端点需要 JWT 鉴权（`Authorization: Bearer <token>`）
- 绝对路径必须改为项目相对路径
- `.gitignore` 必须排除数据库文件，但训练数据需提交

## Goals / Non-Goals

**Goals:**
- 将 model-6 从占位编排器替换为真实 ML 预测计算模型（SOC + Dose）
- 保留训练好的模型文件（`.joblib`）作为项目资产，运行时直接加载，无需重新训练
- 提供独立的训练脚本，便于未来用新数据重训模型
- 在 Agent 层暴露 ML 预测能力，让 farmer 角色询问肥力问题时获得基于真实数据的回答
- 处理 Dose 模型质量较差的情况，在响应中明确标注置信度和警告
- 当模型文件缺失或 scikit-learn 未安装时优雅降级到规则回退

**Non-Goals:**
- 不重新调优 Dose 模型超参数或特征工程（保持 demo 现状）
- 不修改 OrganicMatterAgent（model-5）的规则逻辑
- 不修改 ROLE_AGENTS 路由表
- 不修改数据库 schema
- 不引入 xgboost、shap、matplotlib 等 notebook 中仅作分析用的依赖
- 不动 `src/ai_culti_demo/thematic_models.py`
- 不在本次实现 SHAP 特征重要性解释能力（notebook 中的 SHAP 分析仅作为模型开发期参考，运行时不需要）
- 不引入模型版本管理系统（首版采用简单元数据字段记录 R² 和训练时间戳）

## Decisions

### Decision 1: 模型部署策略——预训练 + 运行时加载

**选择**：在仓库中提交训练好的 `.joblib` 文件，应用启动时一次性加载到内存，预测时直接调用 `model.predict()`。

**备选方案**：
- A. 应用启动时训练：每次启动耗时 30-60 秒（7 步网格搜索 + 5 抹交叉验证），启动慢但内存占用最小
- B. 调用时训练：每次请求耗时分钟级，仅适合开发调试
- C. 预训练 + 加载（本方案）：启动时加载 <1 秒，预测延迟 <100ms，需要管理模型文件

**理由**：
- 训练数据稳定，无需运行时重训
- `.joblib` 文件小（SOC ~300KB，Dose ~3MB），适合入 git
- 用户在澄清中明确选择此方案
- 便于在生产环境部署（无训练开销）

### Decision 2: 模型与训练数据存放位置

**选择**：
- 训练数据 xlsx：`data/fertility/ML-data-SOC-RF_Manual_splits.xlsx`、`data/fertility/ML-data-Dose-RF_Manual_splits.xlsx`、`data/fertility/变量注释.xlsx`
- 模型文件：`data/fertility/models/soc_etr_model.joblib`、`data/fertility/models/dose_etr_model.joblib`
- 训练脚本：`scripts/train_fertility_models.py`

**备选方案**：
- A. `framework/ml_models/` 存放模型与训练脚本：与 framework 业务代码耦合过紧
- B. `framework/domain/other_models/artifacts/`：让其他模型类型可能误用
- C. `data/fertility/` 平铺所有文件（本方案变种）：不区分训练数据与模型文件

**理由**：
- `data/` 已是项目约定的数据资产目录（已有 `data/lechang/`）
- `scripts/` 已有同类脚本（`migrate_chroma.py`、`reindex_documents.py`），保持一致
- 子目录 `models/` 区分原始数据与生成产物，便于 `.gitignore` 管理（如未来需要忽略重训产生的临时文件）

### Decision 3: `model_6_execution` 函数签名保持不变

**选择**：`model_6_execution(input_data: Dict[str, Any]) -> Dict[str, Any]` 签名不变，内部实现替换为 ML 预测调用。


```

Full source: openspec/changes/add-model-6-fertility-ml/design.md

## openspec/changes/add-model-6-fertility-ml/tasks.md

- Source: openspec/changes/add-model-6-fertility-ml/tasks.md
- Lines: 1-76
- SHA256: 00169c006b451a3a4195b26cc98432574cb7e1a752d94fa1dd0e97d65db0c8d2

```md
## 1. 数据准备与依赖声明

- [ ] 1.1 创建 `data/fertility/` 目录，从 `F:\BaiduNetdiskDownload\SOC（土壤有机碳）和Dose（施用量）预测模型\` 复制 `ML-data-SOC-RF_Manual_splits.xlsx`、`ML-data-Dose-RF_Manual_splits.xlsx`、`变量注释.xlsx` 三个训练数据文件
- [ ] 1.2 创建 `data/fertility/models/` 子目录用于存放训练产物
- [ ] 1.3 检查 `.gitignore`，确认 `data/fertility/` 不在忽略规则中（如被通用规则忽略需添加例外 `!data/fertility/`）
- [ ] 1.4 修改 `pyproject.toml`，在 `[project.dependencies]` 中新增 `scikit-learn = "^1.3.0"` 与 `joblib = "^1.3.0"` 两行
- [ ] 1.5 运行 `pip install -e .` 验证依赖可正常安装，执行 `python -c "import sklearn; import joblib; print(sklearn.__version__, joblib.__version__)"` 确认版本号
- [ ] 1.6 使用 PowerShell `Get-Item ... | Select-Object Length` 检查三个 xlsx 文件大小，确认均 <10MB（直接入 git）

## 2. 训练脚本与模型生成

- [ ] 2.1 新建 `scripts/train_fertility_models.py`，将两个 Jupyter notebook（SOC + Dose）的 ETR 7 步网格搜索流程转换为独立 Python CLI 脚本
- [ ] 2.2 脚本参数化：支持 `--data-dir data/fertility`（默认值）和 `--output-dir data/fertility/models` 参数；使用项目相对路径替代 notebook 中的绝对路径 `C:\Users\26379\Desktop\...`
- [ ] 2.3 在训练完成后保存两个 `.joblib` 文件：`data/fertility/models/soc_etr_model.joblib` 与 `data/fertility/models/dose_etr_model.joblib`
- [ ] 2.4 同时保存两个元数据 JSON 文件：`soc_metadata.json` 与 `dose_metadata.json`，包含字段 `model_type`、`trained_at`（ISO 8601 时间戳）、`model_version`（"ETR_v1_20260713"）、`hyperparameters`（7 个超参数）、`metrics`（cv_r2、test_r2、test_rmse）、`feature_names`、`feature_means`（每列均值，用于运行时填充）
- [ ] 2.5 训练脚本输出日志：打印每个模型的 5CV R²、测试集 R²、RMSE 与最优超参数组合；缺失训练数据文件时输出明确错误信息并以非零退出码退出
- [ ] 2.6 运行训练脚本，确认 `data/fertility/models/` 下生成 4 个文件（2 个 joblib + 2 个 json）且元数据内容完整

## 3. model_6.py 真实 ML 实现替换

- [ ] 3.1 重写 `framework/domain/other_models/model_6.py`，保持函数签名 `model_6_execution(input_data: Dict[str, Any]) -> Dict[str, Any]` 不变
- [ ] 3.2 模块顶层 try/except 导入 sklearn 与 joblib，捕获 `ImportError` 时设置 `_SKLEARN_AVAILABLE = False`，模块仍可正常导入
- [ ] 3.3 模块加载时通过惰性单例模式加载两个 `.joblib` 模型文件与对应 `metadata.json`（包含 feature_names、feature_means）；模型文件缺失时不抛异常，记录 `_MODEL_LOADED = False`
- [ ] 3.4 实现 `_prepare_features(input_data, feature_names, feature_means)` 内部函数：从 input_data 提取特征，缺失字段用 feature_means 填充，返回 `(feature_df, imputed_features_list)` 二元组
- [ ] 3.5 实现 SOC 预测：构建 10 特征输入（pH/SOCbe/TN/TP/TK/AP/AK/Gap/Dose/Fertilizer type），调用 `soc_model.predict()` 返回 `soc_prediction` float 值
- [ ] 3.6 实现 Dose 预测：构建 9 特征输入（去掉 Dose 自身），调用 `dose_model.predict()` 返回 `dose_prediction` float 值
- [ ] 3.7 主函数 `model_6_execution` 返回完整字典：`status`（"success"/"fallback"）、`soc_prediction`、`soc_confidence`（0.91 或 0.3）、`dose_prediction`、`dose_confidence`（0.47 或 0.3）、`dose_warning`、`imputed_features`、`imputation_applied`、`model_version`、`fallback_reason`（fallback 时填充）
- [ ] 3.8 实现降级分支：当 `_SKLEARN_AVAILABLE = False` 返回 `fallback_reason: "sklearn_missing"`；当模型文件未加载返回 `fallback_reason: "model_file_missing"`；两种情况都返回训练集 SOC/Dose 均值作为占位预测，confidence 降为 0.3
- [ ] 3.9 验证 `framework/domain/other_models/__init__.py` 中的 `from .model_6 import model_6_execution` 仍然可用（向后兼容）

## 4. FertilityMLAgent 实现

- [ ] 4.1 新建 `framework/agents/specialized/fertility_ml_agent.py`，定义 `FertilityMLAgent(BaseAgent)` 类，`__init__` 中设置 `model_id="model-6"`、`domain="fertility_ml"`、`description="基于 ML 的耕地肥力 SOC/Dose 预测"`
- [ ] 4.2 设置 `self.dependencies = []`（不再依赖 model-4/model-5）
- [ ] 4.3 实现 `execute(task)` 方法：调用 `model_6_execution(task)`，将返回结果包装为 `{status, result, metadata}` 结构，调用 `MockDataLoader.mark_simulated` 标记
- [ ] 4.4 实现 `answer_question(question, context)` 方法，分支处理：
  - 4.4.1 "有机碳" / "SOC" / "含量" 关键词 → 仅返回 SOC 预测结果
  - 4.4.2 "施用量" / "施肥" / "Dose" 关键词 → 仅返回 Dose 预测结果，answer 中标注"仅供参考"
  - 4.4.3 "肥力" / "综合" / 其他关键词 → 同时返回 SOC 和 Dose 两个预测值
  - 4.4.4 当 `status: "fallback"` 时，answer 中标注"基于训练集均值的估算"，confidence 降为 0.3
- [ ] 4.5 `evidence` 字段包含 `[{metric: "soc_prediction", value, unit: "g/kg"}, {metric: "dose_prediction", value, unit: "kg/亩"}, {metric: "model_version", value}]` 结构
- [ ] 4.6 处理空输入特征：当 `context.get("data")` 为空且 `task` 为空字典时，调用 `model_6_execution({})`，触发降级路径但仍返回响应

## 5. AgentManager 与 __init__ 调整

- [ ] 5.1 修改 `framework/agents/specialized/__init__.py`：移除 `from .comprehensive_agent import ComprehensiveImprovementAgent`，新增 `from .fertility_ml_agent import FertilityMLAgent`；更新 `__all__` 列表
- [ ] 5.2 修改 `framework/agents/manager.py` 的 `_load_real_agents`：将 `from .specialized.comprehensive_agent import ComprehensiveImprovementAgent` 替换为 `from .specialized.fertility_ml_agent import FertilityMLAgent`，`real["model-6"] = FertilityMLAgent()`
- [ ] 5.3 修改 `framework/agents/manager.py` 的 `_register_agents` 中 specs 列表：model-6 的 class_name 改为 `"FertilityMLAgent"`、description 改为 `"耕地肥力 SOC/Dose ML 预测"`、domain 改为 `"fertility_ml"`
- [ ] 5.4 修改 `framework/agents/manager.py` 中 `self.agents["model-6"].dependencies = ["model-4", "model-5"]` 为 `self.agents["model-6"].dependencies = []`

## 6. ComprehensiveImprovementAgent 清理

- [ ] 6.1 删除 `framework/agents/specialized/comprehensive_agent.py` 文件
- [ ] 6.2 使用 Grep 搜索整个仓库，确认无残留对 `ComprehensiveImprovementAgent` 或 `comprehensive_agent` 的引用（应在 `__init__.py`、`manager.py`、tests 中已被前面步骤替换）
- [ ] 6.3 检查 `docs/api.md`、`docs/api-contract.md`、`docs/agent-integration.md` 等文档中是否提及 `ComprehensiveImprovementAgent`，若需要则更新为 `FertilityMLAgent`（仅限本次范围触及的部分，避免范围蔓延）

## 7. 测试更新

- [ ] 7.1 修改 `tests/test_agent_specialized.py`：移除 `ComprehensiveImprovementAgent` 测试用例，新增 `FertilityMLAgent` 测试用例覆盖：完整特征预测、部分特征缺失、fallback 场景、answer_question 三个分支
- [ ] 7.2 修改 `tests/test_agent_manager.py`：更新 model-6 相关断言，验证 `_load_real_agents` 加载 `FertilityMLAgent`，验证 `dependencies = []`，验证 `_topological_sort` 中 model-6 不再依赖 model-4/5
- [ ] 7.3 新建 `tests/test_fertility_ml_prediction.py`（或在 test_agent_specialized.py 内追加）：单元测试 `model_6_execution` 函数
  - 7.3.1 完整 10 特征输入 → 验证 `soc_prediction` 是 float、`soc_confidence` 是 0.91、`status` 是 "success"
  - 7.3.2 部分特征输入 → 验证 `imputed_features` 列出被填充的特征、`imputation_applied: true`
  - 7.3.3 空字典输入 → 验证降级到均值、`status: "fallback"`
  - 7.3.4 mock sklearn 不可用 → 验证 `fallback_reason: "sklearn_missing"`
  - 7.3.5 mock 模型文件缺失 → 验证 `fallback_reason: "model_file_missing"`
- [ ] 7.4 运行 `python -m pytest tests/ -v` 验证全部测试通过（不破坏现有 test_agent_base、test_agent_integration、test_multi_agent 等用例）

## 8. 端到端集成验证

- [ ] 8.1 启动开发服务器（`python start_http_server.py` 或 `python -m framework.api.app`），验证 `AgentManager` 正常初始化无 ImportError
- [ ] 8.2 通过 `/api/auth/login` 获取 JWT token
- [ ] 8.3 调用 `/api/chat` 接口，传入农户角色问题（如"我的田肥力怎么样？"），验证响应中包含 `model-6` 的 ML 预测结果而非 `ComprehensiveImprovementAgent` 的分区建议
- [ ] 8.4 验证响应中 `dose_warning` 字段被正确传递到 `details["model-6"]` 中
- [ ] 8.5 临时重命名 `.joblib` 文件模拟模型缺失场景，验证 `AgentManager` 仍能返回 fallback 响应而非崩溃
- [ ] 8.6 运行 `python -c "from framework.agents.manager import agent_manager; print(agent_manager.agents['model-6'].__class__.__name__)"` 确认输出为 `FertilityMLAgent`

```

## openspec/changes/add-model-6-fertility-ml/specs/fertility-ml-prediction/spec.md

- Source: openspec/changes/add-model-6-fertility-ml/specs/fertility-ml-prediction/spec.md
- Lines: 1-72
- SHA256: 0965c78d49caf610fcdaf6809e95fe2fbb426815678b015bbff393805062a180

```md
## ADDED Requirements

### Requirement: SOC（土壤有机碳）ML 预测能力
系统 SHALL 通过 `framework/domain/other_models/model_6.py` 中的 `model_6_execution` 函数提供 SOC（土壤有机碳）的机器学习预测能力，底层使用预训练的 ExtraTreesRegressor 模型（保存在 `data/fertility/models/soc_etr_model.joblib`），输入 10 个土壤特征（pH、SOCbe、TN、TP、TK、AP、AK、Gap、Dose、Fertilizer type），返回 SOC 预测值（单位 g/kg）与模型质量元信息（R²=0.91、RMSE=2.24）。

#### Scenario: 完整特征输入的 SOC 预测
- **WHEN** 调用 `model_6_execution` 时 `input_data` 包含全部 10 个特征字段（pH、SOCbe、TN、TP、TK、AP、AK、Gap、Dose、Fertilizer type）且均为有效数值
- **THEN** 系统 SHALL 加载 `data/fertility/models/soc_etr_model.joblib` 模型文件，调用 `model.predict()` 返回结构包含：`soc_prediction`（float，单位 g/kg）、`soc_confidence`（值为 0.91）、`model_version`（如 "ETR_v1_20260713"）、`imputed_features`（空列表）、`status`（值为 "success"）

#### Scenario: 部分特征缺失的 SOC 预测
- **WHEN** 调用 `model_6_execution` 时 `input_data` 仅包含 3 个核心特征（如 pH、SOCbe、TN），其余 7 个特征缺失
- **THEN** 系统 SHALL 使用训练集对应列的均值填充缺失特征，在响应 `imputed_features` 字段中列出被填充的特征名列表（如 ["TP", "TK", "AP", "AK", "Gap", "Dose", "Fertilizer type"]），`soc_prediction` 仍返回有效数值，`soc_confidence` 保持 0.91 但附带 `imputation_applied: true` 标记

#### Scenario: 模型文件缺失时的降级回退
- **WHEN** `data/fertility/models/soc_etr_model.joblib` 文件不存在或加载失败
- **THEN** 系统 SHALL 返回 `soc_prediction` 为训练集 SOC 均值（约 13-15 g/kg），`status` 字段值为 "fallback"，`fallback_reason` 字段值为 "model_file_missing"，`soc_confidence` 字段值为 0.3，且不抛出异常

#### Scenario: scikit-learn 依赖缺失时的优雅降级
- **WHEN** 运行时未安装 `scikit-learn` 包导致 `ImportError`
- **THEN** 系统 SHALL 在模块导入层捕获异常，`model_6_execution` 仍可被调用并返回降级响应（`status: "fallback"`、`fallback_reason: "sklearn_missing"`、`soc_confidence: 0.3`），不影响 `AgentManager` 启动与其他 agent 的注册

#### Scenario: 输入特征越界时拒绝预测
- **WHEN** 调用 `model_6_execution` 时 `input_data` 中任一特征值超出合法范围（如 pH=99、Fertilizer type=3）
- **THEN** 系统 SHALL 返回 `status` 字段值为 "rejected"，`reason` 字段值为 "input_out_of_range"，`out_of_range_features` 字段为列表（每个元素含 `feature`、`value`、`valid_range` 三个字段），`soc_prediction` 与 `dose_prediction` 为 null，不执行预测。合法范围定义：pH(3-11)、SOCbe(0-100 g/kg)、TN(0-10 g/kg)、TP(0-10 g/kg)、TK(0-100 g/kg)、AP(0-200 mg/kg)、AK(0-500 mg/kg)、Gap(-10 to 50 g/kg)、Dose(0-1000 t/ha)、Fertilizer type(1-2，1=秸秆, 2=有机肥)

### Requirement: Dose（施用量）ML 预测能力
系统 SHALL 通过 `model_6_execution` 函数同时提供 Dose（施用量）的机器学习预测能力，底层使用预训练的 ExtraTreesRegressor 模型（保存在 `data/fertility/models/dose_etr_model.joblib`），输入 9 个土壤特征（pH、SOCbe、TN、TP、TK、AP、AK、Gap、Fertilizer type，不含 Dose 自身），返回 Dose 预测值（单位 t/ha）、置信度（R²=0.47）与质量警告信息。

#### Scenario: 完整特征输入的 Dose 预测
- **WHEN** 调用 `model_6_execution` 时 `input_data` 包含全部 9 个 Dose 模型所需特征
- **THEN** 系统 SHALL 加载 `data/fertility/models/dose_etr_model.joblib`，调用 `model.predict()` 返回 `dose_prediction`（float，单位 t/ha）、`dose_confidence`（值为 0.47）、`dose_warning`（值为 "Dose 模型 R²=0.47，预测结果仅供参考，建议结合田间试验校准"）

#### Scenario: Dose 预测时显式标注低置信度
- **WHEN** Dose 模型预测被执行且 `status` 为 "success"
- **THEN** 响应 SHALL 包含 `dose_warning` 字段，明文标注 "Dose 模型 R²=0.47，预测结果仅供参考，建议结合田间试验校准"，`dose_confidence` 字段值为 0.47，单位为 t/ha（与训练数据 `变量注释.xlsx` 中 Dose 的原始单位一致）

#### Scenario: 部分特征缺失的 Dose 预测
- **WHEN** 调用 `model_6_execution` 时部分 Dose 模型特征缺失
- **THEN** 系统 SHALL 使用训练集均值填充缺失特征，在 `imputed_features` 中累计列出 SOC 与 Dose 模型各自被填充的特征，`dose_confidence` 保持 0.47 并附带 `imputation_applied: true`

#### Scenario: Dose 模型文件缺失时的降级回退
- **WHEN** `data/fertility/models/dose_etr_model.joblib` 不存在
- **THEN** 系统 SHALL 返回 `dose_prediction` 为训练集 Dose 均值（约 600-800 kg/亩），`status: "fallback"`，`fallback_reason: "model_file_missing"`，`dose_confidence: 0.3`

### Requirement: 训练脚本可重训模型
系统 SHALL 提供 `scripts/train_fertility_models.py` 作为独立 CLI 脚本，从原始 xlsx 训练数据训练 SOC 和 Dose 两个 ExtraTreesRegressor 模型，执行 7 步网格搜索确定最优超参数，并将训练好的模型保存为 `.joblib` 文件。

#### Scenario: 重新训练并保存模型
- **WHEN** 运行 `python scripts/train_fertility_models.py`（无参数或带 `--data-dir data/fertility` 参数）
- **THEN** 系统 SHALL 读取 `data/fertility/ML-data-SOC-RF_Manual_splits.xlsx` 与 `data/fertility/ML-data-Dose-RF_Manual_splits.xlsx`，按 notebook 中的 7 步网格搜索流程训练两个 ETR 模型，保存到 `data/fertility/models/soc_etr_model.joblib` 与 `data/fertility/models/dose_etr_model.joblib`，并打印每个模型的 5CV R² 与测试集 R²

#### Scenario: 训练数据文件缺失时报错
- **WHEN** 训练数据 xlsx 文件不存在
- **THEN** 系统 SHALL 输出明确的错误信息指明缺失文件路径，并以非零退出码退出，不创建任何 `.joblib` 文件

### Requirement: 训练数据资产可追溯
系统 SHALL 在 `data/fertility/` 目录中保留完整的训练数据资产，包括原始训练数据（xlsx 文件）与训练好的模型文件（.joblib 文件），并在模型文件旁附带 JSON 格式的元数据文件记录训练时间、模型版本、超参数与性能指标。

#### Scenario: 训练数据完整性
- **WHEN** 检查 `data/fertility/` 目录
- **THEN** 目录 SHALL 包含 `ML-data-SOC-RF_Manual_splits.xlsx`、`ML-data-Dose-RF_Manual_splits.xlsx`、`变量注释.xlsx` 三个训练数据文件，以及 `models/soc_etr_model.joblib`、`models/dose_etr_model.joblib`、`models/soc_metadata.json`、`models/dose_metadata.json` 四个生成产物

#### Scenario: 模型元数据可读
- **WHEN** 读取 `data/fertility/models/soc_metadata.json` 文件
- **THEN** 文件 SHALL 包含 `model_type`（"ExtraTreesRegressor"）、`trained_at`（ISO 8601 时间戳）、`model_version`（如 "ETR_v1_20260713"）、`hyperparameters`（包含 n_estimators、max_depth、min_samples_split、min_samples_leaf、max_features、criterion、random_state）、`metrics`（包含 cv_r2、test_r2、test_rmse）字段

### Requirement: 依赖声明
系统 SHALL 在 `pyproject.toml` 中新增 `scikit-learn>=1.3.0` 与 `joblib>=1.3.0` 两个运行时依赖，确保 ML 预测能力可在生产环境正常加载模型。

#### Scenario: 新增依赖可安装
- **WHEN** 执行 `pip install -e .`（基于更新后的 `pyproject.toml`）
- **THEN** 安装 SHALL 成功完成，且 `python -c "import sklearn; import joblib"` 无 ImportError

```

## openspec/changes/add-model-6-fertility-ml/specs/professional-model-agents/spec.md

- Source: openspec/changes/add-model-6-fertility-ml/specs/professional-model-agents/spec.md
- Lines: 1-45
- SHA256: 82f93629b78df49de0b2f9544886dae23118f8bb4db3ddc27dae898efd6a9792

```md
## MODIFIED Requirements

### Requirement: FertilityMLAgent 智能体
系统 SHALL 实现 `FertilityMLAgent` 智能体，对应模型6「耕地肥力机器学习预测模型」，负责调用预训练的 ExtraTreesRegressor 模型对 SOC（土壤有机碳）和 Dose（施用量）进行预测，并通过 `framework/agents/manager.py` 注册为 `model-6`。该智能体不再依赖其他模型结果，作为独立的计算单元接入 farmer 角色路由。

#### Scenario: 农户 SOC 预测查询
- **WHEN** 农户询问"我的田土壤有机碳含量大概多少？"，且 `framework/agents/manager.py` 已将 `FertilityMLAgent` 注册为 `model-6`
- **THEN** 智能体 SHALL 调用 `framework/domain/other_models/model_6.py` 中的 `model_6_execution`，传入从问题中提取或默认填充的土壤特征字典，返回包含 `soc_prediction`（g/kg）、`soc_confidence`（0.91）、`model_version` 的结构化结果，并由 `answer_question` 方法包装为包含 `answer`、`evidence`、`confidence` 字段的自然语言响应

#### Scenario: 农户 Dose 施用量预测查询
- **WHEN** 农户询问"我这块地大概需要施多少有机肥？"
- **THEN** 智能体 SHALL 调用 `model_6_execution` 返回 `dose_prediction`（kg/亩）、`dose_confidence`（0.47）、`dose_warning` 字段，并在自然语言回答中明确标注"预测结果仅供参考"

#### Scenario: 综合肥力诊断查询
- **WHEN** 农户询问"我的田肥力怎么样？"
- **THEN** 智能体 SHALL 同时返回 SOC 和 Dose 两个预测值，并提供综合诊断说明（如"SOC 预测 X g/kg，建议施肥量约 Y kg/亩"），`evidence` 字段包含两个预测值的指标列表

#### Scenario: 模型降级时的回退响应
- **WHEN** `model_6_execution` 返回 `status: "fallback"`（模型文件缺失或 sklearn 未安装）
- **THEN** 智能体 SHALL 在 `answer` 中标注"基于训练集均值的估算"而非"基于 ML 模型预测"，`confidence` 字段值降低到 0.3，并在 `evidence` 中包含 `fallback_reason` 字段

#### Scenario: Agent 独立执行无依赖
- **WHEN** `AgentManager.process` 调用 farmer 角色对应的智能体集合 `["model-4", "model-5", "model-6"]`
- **THEN** `model-6`（FertilityMLAgent）的 `dependencies` SHALL 为空列表 `[]`，可在拓扑排序中与 `model-4`、`model-5` 并行执行，不等待上游 agent 结果

#### Scenario: 非肥力相关问题跳过 model-6
- **WHEN** 农户角色提出的问题不包含肥力相关关键词（如"我的田 pH 如何"），且 `AgentManager` 路由到 model-6
- **THEN** `AgentManager._should_execute_agent` SHALL 返回 False，model-6 不被执行（不触发模型加载），`details["model-6"]` 字段值为 `{status: "skipped", reason: "question_not_related"}`。肥力关键词列表包括：有机碳、SOC、施用量、施肥量、施肥、Dose、剂量、施多少肥、肥力、综合肥力、秸秆、有机肥、培肥

#### Scenario: 输入越界时返回拒绝响应
- **WHEN** `FertilityMLAgent.execute` 收到包含越界特征值的输入，`model_6_execution` 返回 `status: "rejected"`
- **THEN** Agent SHALL 在 `answer` 中明文标注越界特征和合法范围（如"输入值异常，无法预测。越界特征：pH=99.0（合法范围 3.0-11.0）"），不返回预测值，`evidence` 为空列表

## REMOVED Requirements

### Requirement: ComprehensiveImprovementAgent 智能体
**Reason**: 原 `ComprehensiveImprovementAgent`（model-6）是占位用的综合编排器，仅基于规则拼接 model-4/model-5 的结论生成"分区分类提升建议"，并非用户原始设想中的"计算模型"。本次变更将其替换为 `FertilityMLAgent`，让 model-6 真正具备基于真实训练数据的 ML 预测能力。

**Migration**:
- `framework/agents/specialized/comprehensive_agent.py` 文件将被删除
- `framework/agents/specialized/__init__.py` 移除 `ComprehensiveImprovementAgent` 导出，新增 `FertilityMLAgent` 导出
- `framework/agents/manager.py` 的 `_load_real_agents` 中 model-6 加载逻辑由 `ComprehensiveImprovementAgent()` 改为 `FertilityMLAgent()`
- `framework/agents/manager.py` 中 `self.agents["model-6"].dependencies` 由 `["model-4", "model-5"]` 改为 `[]`
- `tests/test_agent_specialized.py` 与 `tests/test_agent_manager.py` 中 model-6 相关测试用例同步更新为 `FertilityMLAgent` 的 ML 预测断言
- 原由 `ComprehensiveImprovementAgent.answer_question` 处理的"综合诊断"类问题，由 `FertilityMLAgent.answer_question` 接管，回答内容从"综合分区建议"变为"SOC + Dose 预测值"

```
