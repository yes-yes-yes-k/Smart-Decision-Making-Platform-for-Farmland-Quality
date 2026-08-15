## 新增需求

### 需求: 外部源字段适配

系统必须在肥力 ML 入口前提供显式字段适配，将外部模型字段 `SJD/YJZ/TD/TL/TJ/YXL/SXJ/YJZTSZ/YJFLX` 分别转换为 `pH/SOCbe/TN/TP/TK/AP/AK/Gap/Fertilizer type`。适配必须按字段业务含义和单位执行，不能按缩写字面猜测；规范字段优先，源字段与规范字段同时存在且值冲突时必须返回输入冲突错误。系统必须继续兼容训练侧字段别名 `SOMbe` 到 `SOCbe`。

#### 场景: 使用外部 CSV 字段调用
- **当** 输入包含外部字段 `SJD=6.2、YJZ=22.0、TD=1.1、TL=0.8、TJ=18.0、YXL=25.0、SXJ=80.0、YJZTSZ=5.0、YJFLX=1`
- **那么** 系统将其规范化为 `pH/SOCbe/TN/TP/TK/AP/AK/Gap/Fertilizer type` 后执行预测，并且模型输入中不再包含外部缩写字段

#### 场景: 外部字段与规范字段冲突
- **当** 同一请求同时提供 `YJZ=22.0` 和 `SOCbe=18.0`
- **那么** 系统返回 `status=rejected`、`reason=input_conflict`，不得静默选择任一值执行预测

### 需求: model-5 真实 ML 公开入口

系统必须通过 `framework/domain/other_models/model_5.py` 中的 `model_5_execution` 提供肥力 ML 预测能力。真实入口必须覆盖全局 SOC/Dose ETR 和韶关旱地/水田 Dose RF 路由；仓库不得保留 `model_6.py` 或 `model_6_execution` 作为该能力入口。

#### 场景: model-5 引擎可加载
- **当** 运行时安装了 scikit-learn/joblib 且 `data/fertility/models/` 下的全局与韶关模型文件和 metadata 存在
- **那么** `model_5_execution` 返回 `status=success`，并使用 metadata 中的实际 `model_version`

#### 场景: 旧 model-6 引擎路径不存在
- **当** 检查 `framework/domain/other_models/` 或尝试导入 RF 引擎
- **那么** 不存在 `model_6.py` 和 `model_6_execution`，调用方必须使用 `model_5.py/model_5_execution`

## 修改需求

### Requirement: SOC（土壤有机碳）ML 预测能力

系统 SHALL 通过 `framework/domain/other_models/model_5.py` 中的 `model_5_execution` 函数提供 SOC（土壤有机碳）的机器学习预测能力，底层使用预训练的 ExtraTreesRegressor 模型（保存在 `data/fertility/models/soc_etr_model.joblib`），输入 10 个规范土壤特征（pH、SOCbe、TN、TP、TK、AP、AK、Gap、Dose、Fertilizer type），返回 SOC 预测值（单位 g/kg）与模型质量元信息（R²=0.91、RMSE=2.24）。

#### Scenario: 完整特征输入的 SOC 预测
- **WHEN** 调用 `model_5_execution` 时 `input_data` 包含全部 10 个规范特征且均为有效数值
- **THEN** 系统 SHALL 加载 `soc_etr_model.joblib`，返回 `soc_prediction`、`soc_confidence=0.91`、`model_version`、空的 `imputed_features` 和 `status=success`

#### Scenario: 部分特征缺失的 SOC 预测
- **WHEN** 调用 `model_5_execution` 时只包含 pH、SOCbe、TN
- **THEN** 系统 SHALL 使用训练集均值填充缺失特征，返回 `imputation_applied=true` 和被填充字段列表

#### Scenario: 模型文件缺失时降级
- **WHEN** SOC 模型文件不存在或加载失败
- **THEN** 系统 SHALL 返回 `status=fallback`、`fallback_reason=model_file_missing`、均值预测和 `soc_confidence=0.3`，且不抛出异常

#### Scenario: 输入越界时拒绝
- **WHEN** 任一输入特征超出合法范围
- **THEN** 系统 SHALL 返回 `status=rejected`、`reason=input_out_of_range`、`out_of_range_features`，并将预测值置空

### Requirement: Dose（施用量）ML 预测能力

系统 SHALL 通过 `model_5_execution` 提供 Dose 预测能力。非韶关区域使用全局 ExtraTreesRegressor；`area_code` 命中 `SHAOGUAN_AREA_CODES` 时使用韶关 RandomForestRegressor，并按 `land_type=upland/paddy` 选择对应子模型。SOC 始终使用全局 ETR。成功响应的 `model_version` SHALL 等于实际使用模型 metadata 中的版本号。

#### Scenario: 韶关旱地 Dose 预测
- **WHEN** `area_code=lechang` 且 `land_type=upland` 或未传
- **THEN** 系统 SHALL 加载 `sg_dose_upland_rf_model.joblib`，返回韶关旱地 RF 的 Dose、置信度、warning 和 `model_version=SG_RF_v2_20260804`

#### Scenario: 韶关水田 Dose 预测
- **WHEN** `area_code=lechang` 且 `land_type=paddy`
- **THEN** 系统 SHALL 加载 `sg_dose_paddy_rf_model.joblib`，返回韶关水田 RF 的 Dose、置信度、warning 和 metadata 版本

#### Scenario: 非韶关区域 Dose 预测
- **WHEN** `area_code` 未命中韶关集合
- **THEN** 系统 SHALL 使用全局 Dose ETR，忽略 `land_type`，并在响应中标明全局模型来源

#### Scenario: 韶关模型文件缺失
- **WHEN** 对应土地类型的 SG RF 文件不存在或加载失败
- **THEN** 系统 SHALL 返回明确的 `fallback` 状态和原因，不得伪造 SG RF 的成功版本

### Requirement: 韶关区域路由与 land_type 参数支持

系统 SHALL 在 `model_5_execution` 中维护 `SHAOGUAN_AREA_CODES`（初始包含 `lechang`），根据 `area_code` 选择区域路径；韶关区域 Dose 预测 SHALL 接受可选 `land_type`，未传时默认 `upland` 并追加提示；非韶关区域 SHALL 忽略 `land_type`。

#### Scenario: 区域和土地类型透传
- **WHEN** 调用 `model_5_execution` 时同时提供 `area_code` 和 `land_type`
- **THEN** 系统 SHALL 消费两个字段并选择对应模型，返回实际区域和土地类型

#### Scenario: land_type 非法
- **WHEN** 韶关请求的 `land_type` 不是 `upland` 或 `paddy`
- **THEN** 系统 SHALL 使用明确的默认策略并在 warning 中说明，不得静默选择错误子模型
