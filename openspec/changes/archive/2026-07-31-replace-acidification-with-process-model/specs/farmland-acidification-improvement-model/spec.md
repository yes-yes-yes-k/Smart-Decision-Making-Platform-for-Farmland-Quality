## MODIFIED Requirements

### Requirement: 模型3 酸化因子提取
系统 SHALL 从请求参数中提取过程酸化模型所需的三普输入数据（pHstart 对应 SJD、交换性氢对应 JHX、交换性铝对应 JLA），以及子模型选择参数（land_type、fertilizer_type），为后续过程计算提供基础数据。

#### Scenario: 提取三普输入与子模型参数
- **WHEN** 系统收到酸化改良请求，且包含 SJD（pH）、JHX（交换性氢）、JLA（交换性铝）字段
- **THEN** 系统 SHALL 提取 pHstart=SJD、Hex=JHX、Alex=JLA，并读取 land_type（默认 upland）和 fertilizer_type（默认 compound）用于子模型选择

#### Scenario: 缺少必填输入
- **WHEN** 系统收到酸化改良请求，但缺少 JHX（交换性氢）或 JLA（交换性铝）
- **THEN** 系统 SHALL 返回 status="rejected" 和缺少必填字段的错误提示

### Requirement: 模型3 酸化程度分区
系统 SHALL 根据 land_type（水田 paddy / 旱地 upland）和 fertilizer_type（尿素 urea / 复合肥 compound）的组合，从4个过程子模型中选择唯一一个执行酸化计算。子模型映射：paddy_urea、paddy_compound、upland_urea、upland_compound。

#### Scenario: 水田复合肥（默认）
- **WHEN** land_type="paddy" 且 fertilizer_type="compound"（或 fertilizer_type 未传，默认 compound）
- **THEN** 系统 SHALL 选择 paddy_compound 子模型执行计算

#### Scenario: 旱地尿素
- **WHEN** land_type="upland"（或未传，默认 upland）且 fertilizer_type="urea"
- **THEN** 系统 SHALL 选择 upland_urea 子模型执行计算

#### Scenario: 非法参数回退
- **WHEN** land_type 或 fertilizer_type 为非法值（非 upland/paddy 或非 urea/compound）
- **THEN** 系统 SHALL 回退到默认值（upland + compound）并在 warning 中追加参数非法提示

### Requirement: 模型3 改良方案生成
系统 SHALL 使用选定的过程子模型，基于 pHstart、Hex、Alex 和~15个默认参数（RPH/R/Y/S/元素含量/FertN/Ndep/pHtarget 等），计算改良剂需求量：亿土康 YTK（kg/ha）和木本泥炭 MBNT（kg/ha）。部分默认参数（RPH/R/Y/S/FertN/Ndep/pHtarget）SHALL 支持通过 API 可选参数覆盖。

#### Scenario: 默认参数计算
- **WHEN** 系统使用默认参数执行过程模型计算，且 pHstart/Hex/Alex 均在合理范围内
- **THEN** 系统 SHALL 返回 YTK（亿土康 kg/ha）和 MBNT（木本泥炭 kg/ha）的数值结果

#### Scenario: 自定义参数覆盖
- **WHEN** API 请求中包含可选参数（如 FertN=200、pHtarget=6.0）
- **THEN** 系统 SHALL 使用传入值覆盖默认参数执行计算，并在结果中标注哪些参数被自定义

#### Scenario: 输入值越界
- **WHEN** pHstart 超出 [3.0, 10.0] 范围，或 Hex/Alex 为负值
- **THEN** 系统 SHALL 返回 status="rejected" 和越界字段列表

### Requirement: 模型3 酸化改良在线查询
系统 SHALL 提供按需计算接口，API 请求参数直接触发过程模型计算并返回结果，不依赖 DB 预计算。若请求包含 parcel_id，系统 MAY 从 evaluation_results 表查询 SJD 值作为 pHstart 补充输入，但 JHX/JLA 必须由请求显式提供。

#### Scenario: 按需计算
- **WHEN** 调用方以 SJD/JHX/JLA 参数发起请求
- **THEN** 系统 SHALL 直接执行过程模型计算并返回 YTK/MBNT，无需 DB 查询

#### Scenario: parcel_id 补充 SJD
- **WHEN** 调用方提供 parcel_id 但未提供 SJD，且 evaluation_results 表中存在该地块的 SJD 值
- **THEN** 系统 SHALL 从 DB 查询 SJD 作为 pHstart，与请求中的 JHX/JLA 一起执行计算

#### Scenario: parcel_id 查无数据
- **WHEN** 调用方提供 parcel_id 但 evaluation_results 表中无该地块，且请求未提供 SJD
- **THEN** 系统 SHALL 返回 status="rejected" 和"无法获取 pH 值，请提供 SJD 参数"的提示

### Requirement: 模型3 改良方案输出格式
系统 SHALL 以标准化格式输出改良方案，包含改良剂需求量（YTK/MBNT）、子模型标识和参数信息。不暴露中间产酸量分解（Adep/Acrop/ANcy/Aagri/Aback）。

#### Scenario: 标准化输出
- **WHEN** 系统成功完成过程模型计算
- **THEN** 输出 SHALL 包含：status（success/rejected）、ytk（亿土康 kg/ha）、mbnt（木本泥炭 kg/ha）、land_type、fertilizer_type、model_version、warning（可选）

#### Scenario: 错误输出
- **WHEN** 系统因输入缺失或越界无法完成计算
- **THEN** 输出 SHALL 包含：status="rejected"、reason（missing_input / input_out_of_range / invalid_parameter）、缺失或越界字段列表
