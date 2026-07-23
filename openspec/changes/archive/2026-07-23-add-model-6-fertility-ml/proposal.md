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
