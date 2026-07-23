## 1. 数据准备与依赖声明

- [x] 1.1 创建 `data/fertility/` 目录，从 `F:\BaiduNetdiskDownload\SOC（土壤有机碳）和Dose（施用量）预测模型\` 复制 `ML-data-SOC-RF_Manual_splits.xlsx`、`ML-data-Dose-RF_Manual_splits.xlsx`、`变量注释.xlsx` 三个训练数据文件
- [x] 1.2 创建 `data/fertility/models/` 子目录用于存放训练产物
- [x] 1.3 检查 `.gitignore`，确认 `data/fertility/` 不在忽略规则中（如被通用规则忽略需添加例外 `!data/fertility/`）
- [x] 1.4 修改 `pyproject.toml`，在 `[project.dependencies]` 中新增 `scikit-learn = "^1.3.0"` 与 `joblib = "^1.3.0"` 两行
- [x] 1.5 运行 `pip install -e .` 验证依赖可正常安装，执行 `python -c "import sklearn; import joblib; print(sklearn.__version__, joblib.__version__)"` 确认版本号
- [x] 1.6 使用 PowerShell `Get-Item ... | Select-Object Length` 检查三个 xlsx 文件大小，确认均 <10MB（直接入 git）

## 2. 训练脚本与模型生成

- [x] 2.1 新建 `scripts/train_fertility_models.py`，将两个 Jupyter notebook（SOC + Dose）的 ETR 7 步网格搜索流程转换为独立 Python CLI 脚本
- [x] 2.2 脚本参数化：支持 `--data-dir data/fertility`（默认值）和 `--output-dir data/fertility/models` 参数；使用项目相对路径替代 notebook 中的绝对路径 `C:\Users\26379\Desktop\...`
- [x] 2.3 在训练完成后保存两个 `.joblib` 文件：`data/fertility/models/soc_etr_model.joblib` 与 `data/fertility/models/dose_etr_model.joblib`
- [x] 2.4 同时保存两个元数据 JSON 文件：`soc_metadata.json` 与 `dose_metadata.json`，包含字段 `model_type`、`trained_at`（ISO 8601 时间戳）、`model_version`（"ETR_v1_20260713"）、`hyperparameters`（7 个超参数）、`metrics`（cv_r2、test_r2、test_rmse）、`feature_names`、`feature_means`（每列均值，用于运行时填充）
- [x] 2.5 训练脚本输出日志：打印每个模型的 5CV R²、测试集 R²、RMSE 与最优超参数组合；缺失训练数据文件时输出明确错误信息并以非零退出码退出
- [x] 2.6 运行训练脚本，确认 `data/fertility/models/` 下生成 4 个文件（2 个 joblib + 2 个 json）且元数据内容完整

## 3. model_6.py 真实 ML 实现替换

- [x] 3.1 重写 `framework/domain/other_models/model_6.py`，保持函数签名 `model_6_execution(input_data: Dict[str, Any]) -> Dict[str, Any]` 不变
- [x] 3.2 模块顶层 try/except 导入 sklearn 与 joblib，捕获 `ImportError` 时设置 `_SKLEARN_AVAILABLE = False`，模块仍可正常导入
- [x] 3.3 模块加载时通过惰性单例模式加载两个 `.joblib` 模型文件与对应 `metadata.json`（包含 feature_names、feature_means）；模型文件缺失时不抛异常，记录 `_MODEL_LOADED = False`
- [x] 3.4 实现 `_prepare_features(input_data, feature_names, feature_means)` 内部函数：从 input_data 提取特征，缺失字段用 feature_means 填充，返回 `(feature_df, imputed_features_list)` 二元组
- [x] 3.5 实现 SOC 预测：构建 10 特征输入（pH/SOCbe/TN/TP/TK/AP/AK/Gap/Dose/Fertilizer type），调用 `soc_model.predict()` 返回 `soc_prediction` float 值
- [x] 3.6 实现 Dose 预测：构建 9 特征输入（去掉 Dose 自身），调用 `dose_model.predict()` 返回 `dose_prediction` float 值
- [x] 3.7 主函数 `model_6_execution` 返回完整字典：`status`（"success"/"fallback"）、`soc_prediction`、`soc_confidence`（0.91 或 0.3）、`dose_prediction`、`dose_confidence`（0.47 或 0.3）、`dose_warning`、`imputed_features`、`imputation_applied`、`model_version`、`fallback_reason`（fallback 时填充）
- [x] 3.8 实现降级分支：当 `_SKLEARN_AVAILABLE = False` 返回 `fallback_reason: "sklearn_missing"`；当模型文件未加载返回 `fallback_reason: "model_file_missing"`；两种情况都返回训练集 SOC/Dose 均值作为占位预测，confidence 降为 0.3
- [x] 3.9 验证 `framework/domain/other_models/__init__.py` 中的 `from .model_6 import model_6_execution` 仍然可用（向后兼容）

## 4. FertilityMLAgent 实现

- [x] 4.1 新建 `framework/agents/specialized/fertility_ml_agent.py`，定义 `FertilityMLAgent(BaseAgent)` 类，`__init__` 中设置 `model_id="model-6"`、`domain="fertility_ml"`、`description="基于 ML 的耕地肥力 SOC/Dose 预测"`
- [x] 4.2 设置 `self.dependencies = []`（不再依赖 model-4/model-5）
- [x] 4.3 实现 `execute(task)` 方法：调用 `model_6_execution(task)`，将返回结果包装为 `{status, result, metadata}` 结构，调用 `MockDataLoader.mark_simulated` 标记
- [x] 4.4 实现 `answer_question(question, context)` 方法，分支处理：
  - 4.4.1 "有机碳" / "SOC" / "含量" 关键词 → 仅返回 SOC 预测结果
  - 4.4.2 "施用量" / "施肥" / "Dose" 关键词 → 仅返回 Dose 预测结果，answer 中标注"仅供参考"
  - 4.4.3 "肥力" / "综合" / 其他关键词 → 同时返回 SOC 和 Dose 两个预测值
  - 4.4.4 当 `status: "fallback"` 时，answer 中标注"基于训练集均值的估算"，confidence 降为 0.3
- [x] 4.5 `evidence` 字段包含 `[{metric: "soc_prediction", value, unit: "g/kg"}, {metric: "dose_prediction", value, unit: "kg/亩"}, {metric: "model_version", value}]` 结构
- [x] 4.6 处理空输入特征：当 `context.get("data")` 为空且 `task` 为空字典时，调用 `model_6_execution({})`，触发降级路径但仍返回响应

## 5. AgentManager 与 __init__ 调整

- [x] 5.1 修改 `framework/agents/specialized/__init__.py`：移除 `from .comprehensive_agent import ComprehensiveImprovementAgent`，新增 `from .fertility_ml_agent import FertilityMLAgent`；更新 `__all__` 列表
- [x] 5.2 修改 `framework/agents/manager.py` 的 `_load_real_agents`：将 `from .specialized.comprehensive_agent import ComprehensiveImprovementAgent` 替换为 `from .specialized.fertility_ml_agent import FertilityMLAgent`，`real["model-6"] = FertilityMLAgent()`
- [x] 5.3 修改 `framework/agents/manager.py` 的 `_register_agents` 中 specs 列表：model-6 的 class_name 改为 `"FertilityMLAgent"`、description 改为 `"耕地肥力 SOC/Dose ML 预测"`、domain 改为 `"fertility_ml"`
- [x] 5.4 修改 `framework/agents/manager.py` 中 `self.agents["model-6"].dependencies = ["model-4", "model-5"]` 为 `self.agents["model-6"].dependencies = []`

## 6. ComprehensiveImprovementAgent 清理

- [x] 6.1 删除 `framework/agents/specialized/comprehensive_agent.py` 文件
- [x] 6.2 使用 Grep 搜索整个仓库，确认无残留对 `ComprehensiveImprovementAgent` 或 `comprehensive_agent` 的引用（应在 `__init__.py`、`manager.py`、tests 中已被前面步骤替换）
- [x] 6.3 检查 `docs/api.md`、`docs/api-contract.md`、`docs/agent-integration.md` 等文档中是否提及 `ComprehensiveImprovementAgent`，若需要则更新为 `FertilityMLAgent`（仅限本次范围触及的部分，避免范围蔓延）

## 7. 测试更新

- [x] 7.1 修改 `tests/test_agent_specialized.py`：移除 `ComprehensiveImprovementAgent` 测试用例，新增 `FertilityMLAgent` 测试用例覆盖：完整特征预测、部分特征缺失、fallback 场景、answer_question 三个分支
- [x] 7.2 修改 `tests/test_agent_manager.py`：更新 model-6 相关断言，验证 `_load_real_agents` 加载 `FertilityMLAgent`，验证 `dependencies = []`，验证 `_topological_sort` 中 model-6 不再依赖 model-4/5
- [x] 7.3 新建 `tests/test_fertility_ml_prediction.py`（或在 test_agent_specialized.py 内追加）：单元测试 `model_6_execution` 函数
  - 7.3.1 完整 10 特征输入 → 验证 `soc_prediction` 是 float、`soc_confidence` 是 0.91、`status` 是 "success"
  - 7.3.2 部分特征输入 → 验证 `imputed_features` 列出被填充的特征、`imputation_applied: true`
  - 7.3.3 空字典输入 → 验证降级到均值、`status: "fallback"`
  - 7.3.4 mock sklearn 不可用 → 验证 `fallback_reason: "sklearn_missing"`
  - 7.3.5 mock 模型文件缺失 → 验证 `fallback_reason: "model_file_missing"`
- [x] 7.4 运行 `python -m pytest tests/ -v` 验证全部测试通过（不破坏现有 test_agent_base、test_agent_integration、test_multi_agent 等用例）

## 8. 端到端集成验证

- [x] 8.1 启动开发服务器（`python start_http_server.py` 或 `python -m framework.api.app`），验证 `AgentManager` 正常初始化无 ImportError
- [x] 8.2 通过 `/api/auth/login` 获取 JWT token
- [x] 8.3 调用 `/api/chat` 接口，传入农户角色问题（如"我的田肥力怎么样？"），验证响应中包含 `model-6` 的 ML 预测结果而非 `ComprehensiveImprovementAgent` 的分区建议
- [x] 8.4 验证响应中 `dose_warning` 字段被正确传递到 `details["model-6"]` 中
- [x] 8.5 临时重命名 `.joblib` 文件模拟模型缺失场景，验证 `AgentManager` 仍能返回 fallback 响应而非崩溃
- [x] 8.6 运行 `python -c "from framework.agents.manager import agent_manager; print(agent_manager.agents['model-6'].__class__.__name__)"` 确认输出为 `FertilityMLAgent`
