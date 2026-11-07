## MODIFIED Requirements

### Requirement: 缺失字段参考值与采用降级

系统 SHALL 为缺失字段提供可选参考值，参考值 MUST 来自该模型对应训练集的统计量，并 MUST 同时给出依据类型、数据集标识、样本量与分布区间。参考值 SHALL 与预填数据分字段存放，不得自动写入 `data`。调用方采用参考值时 MUST 通过 `assumptions` 声明来源依据，预测结果 SHALL 因此标记为 `degraded` 并在 `assumed_fields` 回显。对于单位未经核验的指标，系统 MUST 以 `unit_status=unverified` 标注且不得给出具体单位。面向用户的解读 MUST 对有明确默认单位的用户输入按该默认单位理解，不得仅因请求值未携带单位而称其“单位未提供”。预测下降量 MUST 按模型输出字段定义解释，不得自行声称其属于 0–1 范围或据此推导风险等级。

#### Scenario: 单位未核验

- **WHEN** 训练集与旧系统的单位记录缺失
- **THEN** 参考值 SHALL 标注 `unit_status=unverified`
- **AND** 接口与报告 MUST NOT 为其标注具体单位

#### Scenario: 用户输入采用默认单位

- **WHEN** 用户按表单配置的默认单位提交硝态氮或铵态氮，且提交值本身未重复携带单位
- **THEN** 解读 MUST 按表单对应的默认单位呈现该指标
- **AND** 解读 MUST NOT 称其单位未提供

#### Scenario: 用户输入没有配置默认单位

- **WHEN** 用户输入了硝态氮或铵态氮数值，但表单和模型契约均未配置可确认的默认单位
- **THEN** 解读 SHALL 展示用户输入的数值
- **AND** 解读 MUST NOT 提示单位未提供、单位缺失或使用其他等价表述
- **AND** 解读 MUST NOT 臆造或推断具体单位

#### Scenario: 降酸请求提供目标 pH

- **WHEN** 用户请求中包含初始 pH 与目标 pH
- **THEN** 解读 SHALL 使用请求中的目标 pH 描述治理目标
- **AND** 解读 MUST NOT 将已提供的目标 pH 描述为暂无记录或缺失

#### Scenario: 解释预测下降量

- **WHEN** 模型返回酸化预测下降量
- **THEN** 解读 SHALL 陈述返回数值及其在模型输出定义下的含义
- **AND** 解读 MUST NOT 声称该数值有 0–1 取值范围或由此推导重度/其他风险等级，除非模型契约明确规定该范围或等级
