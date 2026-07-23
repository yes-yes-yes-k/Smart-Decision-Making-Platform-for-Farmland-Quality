# fertility-ml-prediction Specification

## Purpose
TBD - created by archiving change add-model-6-fertility-ml. Update Purpose after archive.
## Requirements
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

