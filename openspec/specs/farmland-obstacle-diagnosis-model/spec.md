# farmland-obstacle-diagnosis-model Specification

## Purpose
TBD - created by archiving change add-stability-risk-and-grade-evaluation. Update Purpose after archive.
## Requirements
### Requirement: 模型3 批量质量等级评价
系统 SHALL 提供基于 CSV 的批量质量等级评价入口，对包含 12 项指标（SJD/pH、YJZ/有机质、YXL/有效磷、SXJ/速效钾、TRRZ/容重、GCZD/耕层质地、GGNL/灌溉能力、PSNL/排水能力、DXBW/地形部位、ZDGX/质地构型、YXTCHD/有效土层、GCHD/耕层厚度）和区域信息（YJNYQ 一级农业区、EJNYQ 二级农业区）的 CSV 数据执行隶属度计算、综合权重计算和质量等级划分(1-10等)。障碍度 SHALL 存储在独立的 `xxxZAD` 列中，不得覆盖原始指标值。

#### Scenario: 执行批量评价
- **WHEN** 管理员触发批量评价，且 CSV 文件已部署到指定目录，包含必需字段（YJNYQ、EJNYQ、SJD、YJZ、YXL、SXJ、TRRZ、GCZD、GGNL、PSNL、DXBW、ZDGX、YXTCHD、GCHD）
- **THEN** 系统 SHALL 调用评价逻辑处理 CSV，计算各指标隶属度（`xxxLSD` 列）、综合权重（`ZHQZ` 列）、质量等级（`GDZLDJ` 列），并按区域配置的阈值划分质量等级，输出包含 `xxxLSD`、`ZHQZ`、`GDZLDJ` 的结果

#### Scenario: 障碍度不覆盖原始值
- **WHEN** 系统计算障碍度时
- **THEN** 障碍度 SHALL 存储在独立的 `xxxZAD` 列中，原始指标值（如 SJD、YJZ 等） SHALL 保持不变，不得被覆盖为 NaN

#### Scenario: CSV 字段缺失
- **WHEN** 批量评价被触发，但 CSV 文件缺少必需字段（如 YJNYQ、SJD、YJZ 等）
- **THEN** 系统 SHALL 返回明确的错误信息，列出缺失的字段，不执行部分计算

#### Scenario: 区域名称无效
- **WHEN** CSV 中存在未在 REGION_MAP 或 SECONDARY_REGION_MAP 中定义的区域名称
- **THEN** 系统 SHALL 返回错误信息，列出无效区域名称所在的行号

### Requirement: 模型3 障碍诊断
系统 SHALL 基于评价输出（包含隶属度 `xxxLSD`、综合权重 `ZHQZ`、质量等级 `GDZLDJ`）执行障碍诊断，计算各指标障碍度（`xxxZAD`）和障碍等级（`xxxZADJ`），识别障碍类型（`ZALX`：单一障碍/多障碍/无明显障碍）、主要障碍因素（`ZYZAYS`）和次要障碍因素（`CYZAYS`）。

#### Scenario: 执行障碍诊断
- **WHEN** 评价输出已就绪，且包含所有指标隶属度和障碍度字段
- **THEN** 系统 SHALL 对每行数据进行障碍诊断，输出 `ZALX`（障碍类型）、`ZYZAYS`（主要障碍因素描述，含中文指标名）、`CYZAYS`（次要障碍因素描述，无次要因素时显示"无"）

#### Scenario: 障碍度计算
- **WHEN** 系统计算各指标障碍度
- **THEN** 障碍度 SHALL 按 `(1-隶属度)*权重 / 总和` 计算，存储在 `xxxZAD` 列中，障碍等级存储在 `xxxZADJ` 列中（含方向描述，如"重度酸化"、"中度板结"）

#### Scenario: 无明显障碍
- **WHEN** 某地块所有指标的障碍度均低于阈值（主要障碍度 < 20%，次要障碍度 < 10%）
- **THEN** 系统 SHALL 返回 `ZALX` 为"无明显障碍"，`ZYZAYS` 和 `CYZAYS` 为空

#### Scenario: 单一障碍
- **WHEN** 某地块只有一个指标的障碍度达到主要障碍阈值（>= 20%），且没有其他中度以上障碍
- **THEN** 系统 SHALL 返回 `ZALX` 为"单一障碍"，`ZYZAYS` 仅列出该指标，`CYZAYS` 显示"无"

#### Scenario: 多障碍
- **WHEN** 某地块有多个指标的障碍度达到主要或次要障碍阈值
- **THEN** 系统 SHALL 返回 `ZALX` 为"多障碍"，`ZYZAYS` 和 `CYZAYS` 按障碍度降序列出主要和次要因素

### Requirement: 模型3 障碍组合类型识别
系统 SHALL 识别障碍组合类型，支持单一障碍、双重障碍和多因素叠加障碍等组合类型的判定。障碍类型结果存储在 `ZALX` 字段中。

#### Scenario: 识别障碍组合类型
- **WHEN** 系统完成障碍诊断后，识别到多个中度以上障碍因素
- **THEN** 系统 SHALL 返回 `ZALX` 为"多障碍"，并在 `ZYZAYS` 中列出障碍组合描述（如"pH(重度酸化, 11.2%)；速效钾(重度缺乏, 26.5%)"）

### Requirement: 模型3 在线障碍诊断查询
系统 SHALL 提供在线查询接口，按地块 ID 从批量评价和障碍诊断结果中查询障碍诊断信息，对接 `run_thematic_model()` 的统一调用契约。查询结果 SHALL 包含标准字段命名的评价和诊断数据。

#### Scenario: 查询指定地块的障碍诊断结果
- **WHEN** 调用方以地块 ID 发起在线查询，且批量评价和障碍诊断结果已就绪
- **THEN** 系统 SHALL 返回该地块的 `ZALX`（障碍类型）、`ZYZAYS`（主要障碍因素）、`CYZAYS`（次要障碍因素）、`GDZLDJ`（质量等级）和各指标障碍度排序

#### Scenario: 诊断数据未就绪
- **WHEN** 调用方发起在线查询，但批量评价和障碍诊断尚未完成或结果文件缺失
- **THEN** 系统 SHALL 返回 `status: "not_ready"` 和"数据未就绪，请先执行批量评价"的提示

#### Scenario: 酸化改良模块字段对齐
- **WHEN** 酸化改良模块（evaluate_acidification / query_acidification）从 evaluation_results 读取地块数据执行酸化分区与改良方案生成
- **THEN** 系统 SHALL 使用标准字段名读取数据：pH 值取自 `SJD` 列、有机质取自 `YJZ` 列、区域代码取自 `region_code` 列；不得引用旧字段名（`PH`、`YJ`、`JY`），并 SHALL 按地块实际 `region_code` 选择酸化分级配置（不得因字段缺失恒回退到默认区）

### Requirement: 模型3 数据导入接口
系统 SHALL 提供数据导入接口，支持上传新的 CSV 数据并触发重新评价和诊断。CSV 数据 SHALL 使用标准字段命名（YJNYQ、EJNYQ、SJD、YJZ 等）。

#### Scenario: 导入新 CSV 数据
- **WHEN** 用户通过导入接口上传 CSV 文件
- **THEN** 系统 SHALL 将文件部署到数据目录，并提示用户触发批量评价以更新诊断结果

#### Scenario: 导入数据格式校验
- **WHEN** 用户上传的 CSV 缺少必需字段（如 YJNYQ、EJNYQ、12 项标准指标字段）
- **THEN** 系统 SHALL 拒绝导入并返回缺失字段列表

