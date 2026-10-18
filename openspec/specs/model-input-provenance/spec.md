# model-input-provenance Specification

## Purpose
TBD - created by archiving change add-input-provenance-and-report-number-audit. Update Purpose after archive.
## Requirements
### Requirement: 字段级输入来源标注

系统 SHALL 支持在 `soil_indicators` 中为单个指标标注来源，来源取值限定为 `measured`、`region_mean_backfill` 和 `default`。未出现在来源标记中的字段 MUST 视为来源未知，系统 MUST NOT 把来源未知字段当作地块实测值用于降级判断或对外展示。

#### Scenario: 读取被回填的全氮

- **WHEN** 某地块的 `provenance.total_n` 为 `region_mean_backfill`
- **THEN** 系统 SHALL 将该字段判定为回填输入
- **AND** 该字段 MUST 进入 Model-5 的 `imputed_features`

#### Scenario: 字段没有来源标记

- **WHEN** 某地块的 `soil_indicators` 只包含数值、没有 `provenance` 子对象
- **THEN** 系统 SHALL 将所有字段视为来源未知
- **AND** 系统 MUST NOT 仅凭字段存在就认定其为实测值

#### Scenario: 来源标记不改变指标取值

- **WHEN** 系统读取被回填字段的数值
- **THEN** 数值本身 MUST 保持不变
- **AND** 系统 MUST NOT 把回填值改写为 `0` 或 `null`

### Requirement: 声明式来源台账与标注脚本

系统 SHALL 在 `framework/domain/provenance.py` 维护一份声明式来源台账，逐字段声明来源：由 `scripts/import_real_parcels.py` 从地块 shp 逐地块映射的字段 SHALL 为 `measured`；由 `scripts/link_soil_indicators.py` 用采样表平均值批量填充的字段（交换性氢、交换性铝、交换性酸总量、水解性总酸度、全氮、阳离子交换量）SHALL 为 `region_mean_backfill`；导入脚本写入的固定值（目标 pH、肥料类型）SHALL 为 `default`。系统 MUST NOT 依据数值分布特征推断字段来源。

标注脚本 SHALL 按台账写入来源标记，MUST 默认只读，只有显式 `--apply` 才写入；重复运行 MUST NOT 修改已有标记；`--revert` MUST 只移除台账中字段的来源标记，不触碰指标数值与其他字段。

#### Scenario: 默认运行标注脚本

- **WHEN** 运维人员不带 `--apply` 运行标注脚本
- **THEN** 系统 SHALL 输出台账清单、每个字段的来源、有值地块数与已标注地块数
- **AND** 系统 MUST NOT 写入数据库

#### Scenario: 按台账写入来源标记

- **WHEN** 运维人员执行 `--apply`
- **THEN** 系统 SHALL 按台账写入来源标记（实测、回填、默认三组）
- **AND** 未出现在台账中的字段 MUST NOT 被标记

#### Scenario: 重复执行标注

- **WHEN** 已标注字段被再次扫描
- **THEN** 系统 SHALL 跳过该字段
- **AND** 已写入的来源标记 MUST 保持不变

#### Scenario: 回滚来源标记

- **WHEN** 运维人员执行 `--revert`
- **THEN** 系统 SHALL 移除台账中字段的来源标记
- **AND** 系统 MUST NOT 修改指标数值或其他字段

#### Scenario: 源数据中取值恒定的字段

- **WHEN** 某字段在所有地块取同一值，但其值来自地块 shp 的逐地块映射
- **THEN** 系统 SHALL 依据台账将其标记为 `measured`
- **AND** 系统 MUST NOT 因为取值集中就判定为回填

### Requirement: 读侧字段名统一

读侧（`ParcelDataAccessor`、报告模板）MUST 通过统一映射取 `soil_indicators` 字段：Model-5 特征使用 `MODEL5_FEATURE_SOURCES`、Model-4 输入使用 `MODEL4_INPUT_SOURCES`，取值经 `map_feature_sources()`。系统 MUST NOT 在读取方各自硬编码字段名。字段名以 V3.0 命名为准（全氮为 `total_n`，遗留列名 `total_nitrogen` 不再作为 Model-5 取数来源）。来源标记属于元数据，MUST NOT 作为模型输入传递。

#### Scenario: 按统一映射取数

- **WHEN** 读侧需要 Model-5 的 `TN` 特征
- **THEN** 系统 SHALL 从 `MODEL5_FEATURE_SOURCES` 取出字段名（`total_n`）并读取该键
- **AND** 快照中只有遗留键 `total_nitrogen` 时，`TN` MUST 为 `None`

#### Scenario: 报告指标表

- **WHEN** 地块快照包含 `total_n`
- **THEN** 报告的地块指标表 SHALL 渲染“全氮”行
- **AND** 指标中文名表 MUST NOT 登记已废弃的 `total_nitrogen`

#### Scenario: 防止字段名再次漂移

- **WHEN** 映射表、实际取数字段或报告指标表登记出现不一致
- **THEN** 漂移测试（`test_model5_feature_sources_match_accessor`、`test_report_labels_use_central_field_names`）SHALL 失败

### Requirement: Model-4 输入回填时的用量置空

当 Model-4 的输入（`soil_ph`、`exchangeable_hydrogen`、`exchangeable_aluminum`、`target_ph`、`fertilizer_type`）中存在被回填或被默认的字段时，系统 SHALL NOT 输出用量结论：`soil_conditioner_dosage`、`woody_peat_dosage`、`background_acid` MUST 置空，`status` SHALL 为 `degraded`，`reason` SHALL 为 `IMPUTED_INPUT`，`imputed_inputs` SHALL 列出被回填/默认的输入字段，`issues` SHALL 包含稳定代码 `MODEL4_QUANTITATIVE_UNAVAILABLE`。该规则 MUST 在统一输出契约与 Agent 落库两处同时生效（避免报告读库时又取到这些数值），报告补算路径 MUST 遵循同一规则。

#### Scenario: 契约层置空

- **WHEN** Model-4 执行结果带有非空的 `imputed_inputs`
- **THEN** 用量与酸缓冲量 SHALL 为 `null`
- **AND** `issues` MUST 包含 `MODEL4_QUANTITATIVE_UNAVAILABLE`

#### Scenario: 落库与补算一致

- **WHEN** 输入含回填或默认字段
- **THEN** 落库与报告补算结果 MUST 同样不包含用量数值
- **AND** 报告 MUST 能拿到 `imputed_inputs` 用于说明原因

#### Scenario: 输入为实测时不受影响

- **WHEN** 输入字段均未被标记为回填或默认
- **THEN** 用量 SHALL 照常输出
- **AND** `issues` MUST NOT 包含 `MODEL4_QUANTITATIVE_UNAVAILABLE`

### Requirement: Model-5 输入回填时的降级与标注
当 Model-5 的必填特征（`pH`、`SOMbe`、`AK`、`AP`、`TN`）中存在被回填字段时，系统 SHALL 返回 `status=degraded`，`reason` SHALL 为 `MODEL5_INPUT_IMPUTED`，`result.imputed_features` SHALL 列出被回填的特征名，`issues` SHALL 包含稳定代码 `IMPUTED_INPUT`。系统 MUST 通过上述标记使调用方能够区分“基于实测输入的预测”与“含回填输入的预测”；定量字段是否保留 SHALL 由统一输出契约的既有安全规则决定（当前实现为置空并附加 `MODEL5_QUANTITATIVE_UNAVAILABLE`）。特征缺失时的既有行为 MUST 保持不变。

#### Scenario: 全氮被回填

- **WHEN** 地块仅 `TN` 为回填输入、其余四项为地块级实测值
- **THEN** 系统 SHALL 返回 `status=degraded` 且 `reason=MODEL5_INPUT_IMPUTED`
- **AND** `result.imputed_features` SHALL 包含 `TN`
- **AND** `issues` SHALL 包含 `IMPUTED_INPUT`
- **AND** 定量字段 SHALL 由统一输出契约按既有安全规则处理（当前为置空）

#### Scenario: 特征缺失

- **WHEN** 地块缺少某个必填特征
- **THEN** 系统 SHALL 维持 `status=degraded`、`reason=MODEL5_INPUT_MISSING` 且定量字段为 `null`
- **AND** 系统 MUST NOT 用回填分支替代缺失分支

#### Scenario: 全部特征均为实测

- **WHEN** 所有必填特征均未标记为回填
- **THEN** 系统 SHALL 返回 `status=ok`
- **AND** `result.imputed_features` SHALL 为空

### Requirement: Model-4 输入回填时的降级与标注

当 Model-4 的输入（交换性氢、交换性铝、目标 pH、肥料类型）存在被回填或默认取值时，系统 SHALL 返回 `status=degraded`，`issues` SHALL 包含 `IMPUTED_INPUT` 并说明受影响的输入，结果中 SHALL 列出被回填输入字段。系统 MUST NOT 把回填输入与地块级实测输入混同后返回 `ok`。

#### Scenario: 交换性铝被回填

- **WHEN** 酸化计算使用的交换性铝来自区域平均回填
- **THEN** 系统 SHALL 返回 `status=degraded`
- **AND** 结果 SHALL 列出被回填输入字段
- **AND** `issues` SHALL 包含 `IMPUTED_INPUT`

#### Scenario: 目标 pH 与肥料类型为默认值

- **WHEN** 目标 pH 和肥料类型来自代码默认值而非地块数据
- **THEN** 系统 SHALL 将其标记为默认来源
- **AND** 两者 SHALL 出现在被回填输入列表中

### Requirement: 回填输入的对外披露

系统 SHALL 在报告等对外产物中披露被回填的输入字段，使读者能够识别哪些输入不是地块实测值。披露内容 MUST 由上下文的来源信息驱动，MUST NOT 由语言模型生成。

#### Scenario: 报告包含被回填输入

- **WHEN** 报告上下文中的模型结果依赖被回填输入
- **THEN** 报告 SHALL 在数据来源小节列出被回填字段及其来源类型
- **AND** 该内容 MUST NOT 由语言模型改写或补全

