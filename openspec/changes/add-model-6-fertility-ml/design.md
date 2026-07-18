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

**备选方案**：
- A. 拆分为 `predict_soc(features)` 和 `predict_dose(features)` 两个函数：更清晰但破坏现有导出契约
- B. 在 `__init__.py` 中同时导出 `model_6_execution`、`predict_soc`、`predict_dose`

**理由**：
- 向后兼容：现有 `from .model_6 import model_6_execution` 调用无需修改
- 单一入口便于 Agent 调用：传入完整特征字典，返回包含两个预测值的结果
- 未来如需独立函数，可在 `__init__.py` 中追加导出而不破坏现有契约

### Decision 4: 输入特征缺失处理——部分提供 + 训练集均值填充

**选择**：调用方传入的特征字典中缺失的字段，使用训练集对应列的均值填充，并在响应中通过 `imputed_features` 字段列出被填充的特征名。

**备选方案**：
- A. 强制要求所有特征：调用方负担过重
- B. 用固定默认值（如 pH=6.5）：偏离训练集分布，预测偏差大
- C. 抛出 `ValueError`：体验差，无法支持快速查询场景

**理由**：
- 训练集均值在统计上最接近"无信息先验"，对模型预测的扰动最小
- 透明记录 imputed_features 让下游应用能判断预测可靠度
- 实现简单：训练时一并保存 `feature_means.json`，加载模型时一并加载

### Decision 5: Agent 层降级回退策略

**选择**：`FertilityMLAgent` 在以下情况自动回退到基于规则的简化预测：
- 模型文件 `.joblib` 不存在
- scikit-learn 未安装（ImportError）
- 输入特征完全缺失（空字典）

**回退规则**（基于训练集统计）：
- SOC 预测：返回训练集 SOC 均值（约 13-15 g/kg）+ `fallback: "mean_baseline"`
- Dose 预测：返回训练集 Dose 均值（约 600-800 kg/亩）+ `fallback: "mean_baseline"`
- 响应中 `confidence` 字段从 ML 模型 R² 改为 0.3（标记低置信度）

**备选方案**：
- A. 直接抛出异常：用户体验差，整个 Agent 链失败
- B. 返回 None：下游处理复杂

**理由**：
- 与现有 `_StubAgent` 的优雅降级模式一致
- 与 `MockDataLoader.mark_simulated` 的标记模式兼容
- 让生产环境在模型文件丢失时仍能返回有意义的占位结果

### Decision 6: 删除 `ComprehensiveImprovementAgent` 而非保留并行

**选择**：直接删除 `comprehensive_agent.py` 文件，从 `__init__.py` 移除导出，从 `manager.py` 的 `_load_real_agents` 中移除加载逻辑。

**备选方案**：
- A. 保留并重命名为 `_LegacyComprehensiveImprovementAgent`：增加维护负担，无人调用
- B. 保留文件但内部抛出 `DeprecationWarning`：徒增代码

**理由**：
- 原实现是占位 mock，无真实业务价值
- 用户在澄清中明确选择"直接替换"
- `git log` 保留历史可追溯，无需在代码中保留弃用桩
- 减少 spec 漂移：避免出现"已弃用但未删除"的僵尸代码

### Decision 7: model-6 依赖图变更

**选择**：`FertilityMLAgent.dependencies = []`（不再依赖 model-4/model-5）。

**理由**：
- ML 预测模型是独立的计算单元，输入为土壤特征字典，不依赖其他 agent 的输出
- 原依赖声明是为了让 `ComprehensiveImprovementAgent` 的 `_extract_upstream_summary` 能拿到 model-4/5 的结果
- 新的 `FertilityMLAgent` 不消费上游 agent 结果，依赖关系应清空

**对路由影响**：
- `ROLE_AGENTS["farmer"] = ["model-4", "model-5", "model-6"]` 不变
- 但 model-6 不再等待 model-4/5 完成，可并行执行
- `_topological_sort` 仍会按依赖关系排序，无依赖的节点可任意顺序执行

### Decision 8: Dose 模型低质量处理

**选择**：在 `model_6_execution` 返回中明确包含：
- `dose_confidence`: 0.47（来自测试集 R²）
- `dose_warning`: "Dose 模型 R²=0.47，预测结果仅供参考，建议结合其他 agronomic 因素综合判断"
- `model_version`: "ETR_v1_20260713"
- `soc_confidence`: 0.91

**备选方案**：
- A. 不集成 Dose 模型：但用户明确要求"两个都集成"
- B. 重新调优：用户明确说"不重新调优"

**理由**：
- 透明披露模型质量比隐藏缺陷更负责任
- 下游 Agent 在生成自然语言回答时可参考 confidence 字段决定措辞
- 符合 `MockDataLoader.mark_simulated` 现有的元数据披露模式

## Risks / Trade-offs

- **[风险] 训练数据 xlsx 文件大小未知** → 提交前用 `Get-Item ... | Select-Object Length` 检查；若 >10MB 改用 git-lfs 或仅提交 `.joblib`；若 <1MB 直接提交
- **[风险] Dose 模型 R²=0.47 可能误导用户** → 在响应中明确标注 `dose_warning` 字段，Agent 在自然语言回答中需提示"仅供参考"
- **[风险] scikit-learn 安装增加部署体积约 100-200MB** → 在 README 中说明依赖变化；生产 Dockerfile 中使用多阶段构建分离构建依赖与运行依赖（本次不做，留待后续 ops change）
- **[风险] 模型文件损坏或与 scikit-learn 版本不兼容** → 在 `model_6.py` 中 try/except 捕获 `ModuleNotFoundError` 与 `joblib.exceptions`，触发降级回退
- **[风险] 删除 ComprehensiveImprovementAgent 破坏现有测试** → 同步更新 `tests/test_agent_specialized.py` 与 `tests/test_agent_manager.py` 中的 model-6 相关断言
- **[权衡] 训练脚本与运行时代码解耦** → 训练脚本放 `scripts/`，运行时仅依赖 `.joblib` 文件，生产环境无需训练依赖（如 `matplotlib`、`shap`、`seaborn`），但 `scikit-learn` 在运行时仍需要
- **[权衡] 输入特征缺失时用均值填充会引入预测偏差** → 通过 `imputed_features` 字段透明披露，下游应用可据此降低 confidence
- **[权衡] 不实现模型版本管理** → 首版用简单元数据字段（`model_version`、`trained_at`、`r2_score`）嵌入 `.joblib` 旁的 `.json` 文件，未来如需可演进为完整 MLOps 流程
