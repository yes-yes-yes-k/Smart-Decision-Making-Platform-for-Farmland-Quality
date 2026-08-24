# area-code-mapping Specification

## Purpose

Define how administrative area codes (行政区划代码) map to agricultural region coefficients, enabling Models 1-3 to select correct membership coefficients and weights based on parcel geographic location. The mapping SHALL be stored in a dedicated database table for maintainability and future extension.

## ADDED Requirements

### Requirement: Area code region mapping table

系统 SHALL 提供 `area_code_region_map` 数据库表作为行政区划代码到农业区映射的唯一数据源。每个映射记录 SHALL 包含：
- `area_code`: 行政区划代码（主键，如 "440281"）
- `region_name`: 行政区名称（如 "乐昌市"）
- `primary`: 一级农业区代码（HN=华南区, CJ=长江中下游区）
- `secondary`: 二级农业区代码（MNY=闽南粤中, YXG=粤西桂南, QN=琼雷, NL=南岭丘陵山地林农区）
- `ejnyq_idx`: 二级农业区索引（0-3），用于选择 MODEL2_COEFFICIENTS 中的参数组
- `enabled`: 是否启用（布尔，默认 true）
- `created_at` / `updated_at`: 时间戳

#### Scenario: 映射表结构
- **WHEN** 数据库迁移或建表
- **THEN** `area_code_region_map` 表 SHALL 被创建，包含上述所有字段
- **AND** `area_code` 列 SHALL 有唯一约束

#### Scenario: 初始数据
- **WHEN** 建表后首次初始化
- **THEN** 系统 SHALL 自动插入乐昌市（440281）和新丰县（440233）的映射记录

### Requirement: Region mapping service

系统 SHALL 提供 `get_region_mapping(area_code)` 服务函数，从 `area_code_region_map` 表查询映射。该函数 SHALL 遵循以下优先级：
1. 模块级缓存（首次查询加载全表到内存）
2. 硬编码 `AREA_TO_REGION` 字典（DB 不可用时的回退）
3. 默认降级值

#### Scenario: 缓存命中
- **WHEN** `get_region_mapping("440281")` 被首次调用
- **THEN** 系统 SHALL 从 `area_code_region_map` 表加载全量数据到模块级缓存
- **AND** 返回 `{"primary": "HN", "secondary": "NL", "ejnyq_idx": 3}`

#### Scenario: 缓存刷新
- **WHEN** 运维修改了 `area_code_region_map` 表数据
- **THEN** 调用 `refresh_region_cache()` SHALL 清空缓存，下次查询重新从 DB 加载

#### Scenario: DB 不可用时回退
- **WHEN** 数据库连接失败或表不存在
- **THEN** `get_region_mapping` SHALL 回退到 `AREA_TO_REGION` 硬编码字典
- **AND** 系统 SHALL 记录 warning 日志标注 `reason: "db_unavailable_fallback_to_hardcoded"`

#### Scenario: 未知 area_code 降级
- **WHEN** area_code 在 DB 和硬编码字典中都不存在
- **THEN** 系统 SHALL 降级使用默认值 `primary: "HN"`, `secondary: "MNY"`, `ejnyq_idx: 0`
- **AND** 系统 SHALL 在日志中记录 warning，标注 `reason: "unknown_area_code"`

### Requirement: 映射一致性验证

系统 SHALL 提供 `validate_region_mappings()` 函数，验证每个 ejnyq_idx 和 primary/secondary 组合在 MODEL2_COEFFICIENTS、MODEL3_COEFFICIENTS、MODEL3_WEIGHTS 中都有对应的配置。

#### Scenario: 有效映射验证
- **WHEN** `validate_region_mappings()` 被调用
- **THEN** 每个映射的 ejnyq_idx SHALL 在 MODEL2_COEFFICIENTS 中存在
- **AND** 每个映射的 secondary SHALL 在 MODEL3_WEIGHTS 中存在
- **AND** 每个映射的 primary SHALL 在 MODEL3_COEFFICIENTS 中存在

#### Scenario: 缺失系数检测
- **WHEN** 映射中的某个 ejnyq_idx 在 MODEL2_COEFFICIENTS 中不存在
- **THEN** 验证 SHALL 返回失败，并列出不一致的映射条目

## MODIFIED Requirements

### Requirement: area_code 映射到二级农业区代码

系统 SHALL 通过 `get_region_mapping(area_code)` 服务函数将 `ParcelInfo.area_code` 转换为二级农业区代码（ejnyq），用于选择隶属度参数和权重。乐昌(440281)→ejnyq_idx=3（南岭丘陵山地林农区，一级区 HN）。新丰县(440233)→ejnyq_idx=3（同属华南区/南岭丘陵山地林农区）。

#### Scenario: 已知 area_code
- **WHEN** area_code 为 "440281" 或 "440233"
- **THEN** ejnyq_idx=3，使用 MODEL2_COEFFICIENTS[3] 的 a/c/ut1/ut2 和 weights

#### Scenario: 未知 area_code
- **WHEN** area_code 在映射表中不存在
- **THEN** 降级到默认 ejnyq_idx=0（闽南粤中），标注 reason=unknown_area_code

### Requirement: area_code 映射到农业区代码选择系数

系统 SHALL 通过 `get_region_mapping(area_code)` 服务函数将 `ParcelInfo.area_code` 转换为一级农业区代码（primary，HN/CJ）选择隶属度系数，二级农业区代码（secondary，MNY/YXG/NL/QN）选择权重。乐昌(440281)和新丰县(440233)→primary=HN、secondary=NL。

#### Scenario: 已知 area_code
- **WHEN** area_code 为 "440281" 或 "440233"
- **THEN** 使用 MODEL3_COEFFICIENTS["HN"] 的隶属度系数和 MODEL3_WEIGHTS["NL"] 的权重

#### Scenario: 未知 area_code
- **WHEN** area_code 在映射表中不存在
- **THEN** 降级到默认 primary=HN、secondary=MNY，标注 reason=unknown_area_code
