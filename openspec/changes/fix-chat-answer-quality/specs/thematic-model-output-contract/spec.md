## ADDED Requirements

### Requirement: Model-4 酸化结果必须携带实测酸碱度

Model-4 酸化评价结果在实测输入存在时 SHALL 在规范结果中携带 `soil_ph` 与 `acidification_level`（由 `soil_ph` 按阈值分级：<4.5 极强酸性、[4.5,5.5) 强酸性、[5.5,6.5) 酸性）；输入回填/降级仅允许清空定量用量字段（`background_acid`/`soil_conditioner_dosage`/`woody_peat_dosage`），禁止清空 `soil_ph`。缺失该字段时 SHALL 视为结果不完整。

#### Scenario: 实测 pH 存在时返回分级

- **WHEN** 地块数据库存在实测 `soil_ph` 数值且 Model-4 已执行
- **THEN** 规范结果 SHALL 携带该 `soil_ph` 值及对应的 `acidification_level` 分级
- **AND** 最终回答 SHALL 报告实测 pH 与「强酸性/酸性」判定，不得声称「缺少实测酸碱度」

#### Scenario: 实测 pH 缺失时给出确定性降级说明

- **WHEN** 地块数据库不存在实测 `soil_ph`
- **THEN** 回答 SHALL 明确说明缺少实测 pH 记录、给出分级阈值（强酸性 <5.5、酸性 5.5~6.5）与补测引导
- **AND** SHALL NOT 输出笼统「无法判断酸化是否严重」而不给出原因与路径

### Requirement: Model-1 稳定性结论在历史充足时必须输出

Model-1 稳定性评价在历史等级快照 ≥2 期时 SHALL 输出等级序列趋势、掉级风险等级与稳定性结论；禁止在历史可判定时仅返回单一等级或声称「缺少历史」。历史不足时 SHALL 沿用「因缺少至少 2 期历史等级快照，暂无法判断稳定性与退化风险高低」的契约降级文案。

#### Scenario: 历史快照充足时输出稳定性结论

- **WHEN** 地块存在 ≥2 期 `parcel_history_snapshot` 记录且问题为稳定性/退化风险类
- **THEN** 回答 SHALL 给出稳定性与退化风险结论（如等级趋势、是否有掉级风险）
- **AND** 不得以单一「质量等级 X 等」替代稳定性结论

#### Scenario: 历史快照不足时输出契约降级文案

- **WHEN** 地块历史等级快照不足 2 期
- **THEN** 回答 SHALL 明确告知「暂无法判断稳定性与退化风险高低，需补充历史等级记录」
- **AND** 不得含糊表述为「无法提供」或「无有效结果」

### Requirement: LLM 总结字段输出白名单

最终 LLM 总结 SHALL 只允许输出模型结果中实际存在的标准字段名（白名单 = 模型 `result` 键 ∪ 标准标签表）。禁止输出模型结果中不存在的字段名（如将「耕层质地」幻觉为「耕作制度」）；正文若出现白名单外字段 SHALL 触发该句丢弃或回退确定性模板。

#### Scenario: LLM 输出幻觉字段被拦截

- **WHEN** LLM 正文出现模型结果中不存在的字段名（如「耕作制度」）
- **THEN** 系统 SHALL 丢弃含该字段的句子并回退确定性模板渲染障碍度排序
- **AND** 最终回答 SHALL 只包含白名单字段
