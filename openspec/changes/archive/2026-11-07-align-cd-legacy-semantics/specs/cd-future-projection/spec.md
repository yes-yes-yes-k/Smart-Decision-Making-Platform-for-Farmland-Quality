## MODIFIED Requirements

### Requirement: 区域与来源过滤

系统 SHALL 支持按区域（区域类型 + 标识）与数据来源过滤。与原系统一致，**区域参数 MUST 仅记录在响应中（`area_filter: not_applied`），MUST NOT 参与数据查询**（原系统 `predict_future_cd` 的 `area` 只进日志、源码标注 TODO）；数据来源过滤 MUST 生效。

#### Scenario: 指定乡镇

- **WHEN** 请求 `region_type=township&region_id=T1`
- **THEN** 响应 MUST 记录该区域参数并标注 `area_filter: not_applied`
- **AND** 查询 MUST 仍返回全域结果（与原系统一致）

### Requirement: 统计口径

系统 SHALL 复用原系统 `predict_future_cd` 的统计口径：`count / mean / std(ddof=1) / min / max / median / percentile_25 / percentile_75`，其中标准差 MUST 为**样本标准差（n−1）**、分位数 MUST 为**线性插值**，MUST 在响应中标注口径来源。该口径与阶段 2 的总体标准差口径不同，差异 MUST 记录在 `docs/cd-legacy-known-issues.md`。

#### Scenario: 标准差口径

- **WHEN** 请求某年份统计
- **THEN** 标准差 MUST 为样本标准差（除以 n−1）
- **AND** 分位数 MUST 使用线性插值
- **AND** 响应 MUST 注明口径与原系统一致
