## ADDED Requirements

### Requirement: 障碍度排序逐项有序渲染

字段直查对 `obstacle_degrees` 这类有序字典 SHALL 按权威键顺序逐项渲染为「字段名 + 数值」（如「质地构型 0.23」），禁止输出 Python dict 字面量（禁止 `str(dict)` 直接把 `{'土壤酸碱度': 0.14, ...}` 暴露给用户）。数值渲染允许为 0 的项使用统一小数位（如 0.00）。

#### Scenario: 障碍度排序字段直查展示

- **WHEN** 用户查询「障碍度排序」且模型结果包含 `obstacle_degrees` 有序字典
- **THEN** 字面量 SHALL 以「字段名 数值」形式逐项展示
- **AND** 回复 SHALL NOT 出现 Python dict 字面量或 `{`、`'` 形式输出
- **AND** 渲染顺序 SHALL 与权威 `obstacle_degrees` 键顺序一致

### Requirement: 模型字段标准名称白名单与别名映射

系统 SHALL 维护字段标准名称集合（含「耕层质地」「质地构型」等），LLM 与字段直查 SHALL 使用标准名；「耕作制度」等非模型字段 SHALL NOT 出现在回答中。对同义别名（如「土壤酸碱度」与「土壤 pH」）SHALL 使用统一标准名或明确说明其等价关系。

#### Scenario: 幻觉字段「耕作制度」被禁止

- **WHEN** LLM 正文将「耕层质地」改写为「耕作制度」
- **THEN** 该字段名 SHALL 被判定为非白名单字段并予以拦截/回退
- **AND** 最终回答 SHALL 使用标准字段名「耕层质地」（或按模型结果键输出）
