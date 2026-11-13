# heavy-metal-cd-visualization Specification

## Purpose
把 Cd 双模型结果表转成可交付的分布图、直方图与栅格产物：结果表 + 地块质心栅格化、可选空间插值、分级地图（作物三档 / 有效态分位数）、行政区描边、受控目录导出与下载。

## Requirements

### Requirement: 可视化数据来源与区域过滤

系统 SHALL 从 Cd 结果表（`cd_crop_prediction_result` / `cd_effective_prediction_result`）读取数值，坐标 MUST 取地块质心，数值 MUST 以 `exp(ln)` 还原为 mg/kg 并在产物元信息中标注单位与 `unit_status`。系统 MUST 支持按数据来源（自有/移植）过滤，且 MUST 支持按区域（区域类型 + 区域标识）限定生成范围；区域过滤 MUST 使用与阶段 3 一致的归属依据。系统 MUST NOT 重新调用预测模型。

#### Scenario: 全量生成

- **WHEN** 调用方请求某模型的分布图且不指定区域
- **THEN** 系统 MUST 使用该模型结果表的全部可用行（含质心坐标的行）
- **AND** 产物元信息 MUST 记录数据行数、来源过滤值与生成时间

#### Scenario: 指定区域生成

- **WHEN** 调用方指定 `region_type=township` 与 `region_id`
- **THEN** 系统 MUST 只使用归属该乡镇的地块结果
- **AND** 系统 MUST 使用与阶段 3 乡镇统计相同的归属依据

#### Scenario: 模板范围外无数据

- **WHEN** 过滤后的点集没有任何点落入模板栅格范围
- **THEN** 系统 MUST 返回机器可读的 `no_data_in_template` 错误
- **AND** 系统 MUST NOT 产出空白图片

### Requirement: 栅格化与边界掩膜

系统 SHALL 以受控模板栅格为网格基准执行栅格化，像元值 MUST 来自点值，无点像元 MUST 为 NaN。系统 MUST 支持行政区边界掩膜与描边，边界 MUST 支持包含多个要素（MultiPolygon / 多个 feature）的区域，不得只取第一个要素。系统 MUST 在未提供边界或边界为空时使用点集凸包作为兜底掩膜，并在产物元信息中标注 `boundary_source`。

#### Scenario: 多要素边界

- **WHEN** 请求的区域边界包含多个 feature
- **THEN** 系统 MUST 对全部要素应用掩膜与描边
- **AND** 系统 MUST NOT 只绘制第一个要素

#### Scenario: 无边界兜底

- **WHEN** 请求未提供边界或边界查询为空
- **THEN** 系统 MUST 使用点集凸包限制着色范围
- **AND** 产物元信息 MUST 标注 `boundary_source="convex_hull"`

### Requirement: 可选空间插值

系统 SHALL 支持 `nearest` / `linear` / `cubic` 三种插值方法填充无点像元，且默认 MUST 关闭插值。开启插值后系统 MUST 在插值完成后重新应用边界掩膜，使边界外保持 NaN；产物元信息 MUST 标注 `interpolated` 与方法名。

#### Scenario: 默认不插值

- **WHEN** 调用方未指定插值参数
- **THEN** 系统 MUST 保留无点像元为空白
- **AND** 产物元信息 MUST 标注 `interpolated=false`

#### Scenario: 开启插值并回扣掩膜

- **WHEN** 调用方开启 `linear` 插值且提供边界
- **THEN** 系统 MUST 用 `griddata` 填充内部 NaN
- **AND** 系统 MUST 在填充后把边界外像元重新置为 NaN

#### Scenario: 有效点不足时降级

- **WHEN** 调用方开启 `linear` / `cubic` 插值但有效像元不足以构造三角剖分
- **THEN** 系统 MUST 降级为 `nearest` 插值而不是让请求失败
- **AND** 产物元信息 MUST 在 `interpolation_effective` 中标出实际使用的方法

### Requirement: 分级地图与图例

系统 SHALL 输出分级地图，作物 Cd MUST 使用三档阈值 `0.0–0.2 / 0.2–0.3 / ≥0.3 mg/kg` 与对应颜色，有效态 Cd MUST 使用有效像元分位数 6 级。系统 MUST 在产物元信息中给出图例（`legend.mode` 为 `threshold` 或 `quantile`，含各档边界与颜色），且 MUST NOT 把展示分级表述为统计分箱或安全判定。

#### Scenario: 作物 Cd 三档

- **WHEN** 生成作物 Cd 地图
- **THEN** 图例 MUST 为三档阈值分级
- **AND** `legend.mode` MUST 为 `threshold`

#### Scenario: 有效态分位数分级

- **WHEN** 生成有效态 Cd 地图
- **THEN** 图例 MUST 基于有效像元的分位数边界
- **AND** `legend.mode` MUST 为 `quantile`
- **AND** 系统 MUST NOT 将该分级描述为超标判定

### Requirement: 直方图

系统 SHALL 基于同一栅格的有效像元输出直方图（频率密度 + 密度曲线），无效值 MUST 被排除；当有效像元全部相同时 MUST 输出单值示意图而不是空图。直方图 MUST 与地图来自同一栅格。

#### Scenario: 正常分布

- **WHEN** 栅格包含多个不同有效像元值
- **THEN** 系统 MUST 输出直方图与核密度曲线
- **AND** 图表 MUST 排除 nodata / NaN 像元

#### Scenario: 单值栅格

- **WHEN** 所有有效像元值相同
- **THEN** 系统 MUST 输出单值柱状示意图
- **AND** 系统 MUST NOT 因密度估计失败而报错

### Requirement: 产物管理与导出

系统 SHALL 把每次生成的产物写入受控目录，包含地图图片、直方图与可选 GeoTIFF，并写入 `meta.json`（请求参数、口径、图例、统计摘要、文件清单、生成时间、数据行数）。系统 MUST 提供产物列表与按产物 ID 下载的能力，下载 MUST 校验产物 ID 格式与文件名白名单并限制在受控根目录内。

#### Scenario: 生成并列出产物

- **WHEN** 一次生成成功完成
- **THEN** 系统 MUST 返回产物 ID 与各类产物的相对路径
- **AND** 列表端点 MUST 能按模型与区域筛出该产物

#### Scenario: 非法下载请求

- **WHEN** 下载请求的产物 ID 非 32 位十六进制或文件名不在白名单
- **THEN** 系统 MUST 拒绝请求
- **AND** 系统 MUST NOT 返回受控目录之外的文件

#### Scenario: 无数据语义

- **WHEN** 该模型结果表没有任何可用行
- **THEN** 系统 MUST 返回 `no_data` 错误
- **AND** 系统 MUST NOT 生成空图或 0 字节文件
