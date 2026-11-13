## ADDED Requirements

### Requirement: Conversational flux queries and annual comparison

系统 SHALL 通过受验证工具接入通量能力、统计、明细、参数定义/已有值和逐年对比，回答 MUST 包含范围、来源、业务年度、版本、单位与实际覆盖。无明确地区或全域意图时 MUST 追问，不得静默退回全库。预测数据无年份依据时 MUST 保持时期未知而不套用通量年度。

#### Scenario: Regional annual comparison
- **WHEN** 用户查询某县两个年度的 Cd 输入输出通量
- **THEN** 系统 MUST 按来源和年度分别展示实际结果、覆盖差异和缺项，无数据年度如实说明

#### Scenario: Existing parameter lookup
- **WHEN** 用户询问某地块某年已记录的通量参数
- **THEN** 系统 MUST 返回匹配值及单位/来源，保持未知项，不把其他年度或区域均值作为已有值

### Requirement: Independent eight-component conversational trials

系统 SHALL 支持八分项参数契约、多轮补参和修改，调用后端纯函数计算。草稿 MUST 隔离用户/会话并保存范围、年度、参数来源、单位、默认接受记录和 revision。范围切换 MUST 重新核验受影响值，迟到结果 MUST NOT 覆盖新草稿。对话工具 MUST NOT 暴露管理导入或业务覆盖重算。

#### Scenario: Amend enterprise input
- **WHEN** 用户补齐企业输入并修改上一组数值后重新试算
- **THEN** 系统 MUST 校验单位与缺项后以新 revision 计算，展示实际使用参数，业务输入输出表保持不变

#### Scenario: Defaults and unknown inputs
- **WHEN** 试算缺少参数或参数单位无法核验
- **THEN** 系统 MUST 列出缺项和可用默认的数值/依据，未经明确接受不采用默认，不将未知企业输入当零

#### Scenario: Changed scope and stale results
- **WHEN** 用户切换年度或地块，旧计算响应随后返回
- **THEN** 系统 MUST 保留新范围及 revision，旧结果关联旧修订，重新核验受影响参数

### Requirement: Versioned flux trial persistence

系统 SHALL 在明确保存时通过服务器所属消息的完整试算结果创建独立记录，包含类别、输入、来源、年度、计算版本、默认接受和输出。保存 MUST 校验归属并保持幂等，不更新业务核算结果。未完成或单位条件未满足的完整试算 MUST NOT 被标为已成功保存。

#### Scenario: Save and retry flux trial
- **WHEN** 用户重复或并发保存同一已完成结果
- **THEN** 系统 MUST 返回同一独立记录，失败可重试；修改参数后的新结果按新 revision 保存

#### Scenario: Other user's result
- **WHEN** 用户请求保存其他会话所有者的试算
- **THEN** 系统 MUST 拒绝且不泄露结果或创建记录

### Requirement: Consistent flux and artifact dialogue responses

系统 SHALL 在普通 HTTP 和 SSE 中输出一致的通量结果与附件引用，支持后续“画成图/下载刚才结果”继承已验证范围。回答 MUST 区分无数据、缺参数、单位未核验、不支持、服务失败与生成中状态，不伪造结果或附件。

#### Scenario: Follow-up visualization
- **WHEN** 用户对刚才某年某地区某来源结果要求画图
- **THEN** 系统 MUST 使用原筛选条件生成产物，不扩大至全库或换年度，普通和流式回复提供相同附件信息

#### Scenario: Rendering unavailable
- **WHEN** 制图依赖或模板不可用
- **THEN** 系统 MUST 给出具体不可用原因并保留已成功的查询结果，不返回虚构图片链接
