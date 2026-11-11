## ADDED Requirements

### Requirement: 最终回答正文完整性兜底

多智能体聊天路径的最终回答 SHALL NOT 为空。当 LLM 总结返回空内容、超时或失败时，编排器 SHALL 以确定性模型结果摘要（`deterministic_answer` 拼接）作为正文兜底；禁止仅返回「分析对象：地块 xxx」前缀或空正文。

#### Scenario: LLM 总结返回空内容

- **WHEN** 专业模型已生成结构化结果，但最终 LLM 总结输出为空或超时
- **THEN** 编排器 SHALL 以专业模型结果的确定性摘要作为正文
- **AND** 回复正文 SHALL 非空
- **AND** 已有「分析对象/地块前缀」SHALL 保留在前，确定性正文 SHALL 拼接其后

#### Scenario: 正文只有前缀时判定为缺陷

- **WHEN** 最终回答仅包含分析对象或地块信息前缀、不包含任何业务结论
- **THEN** 该回答 SHALL 被视为不完整（`answer_incomplete`）
- **AND** 系统 SHALL 以最后一个专业模型结果的确定性摘要补齐正文

### Requirement: 同会话后续正文不得丢失

同一会话内连续请求的专业回答 SHALL 均包含完整正文；任何一轮出现「仅前缀、正文缺失」SHALL 视为回归缺陷，由会话级断言拦截。

#### Scenario: 连续多轮提问均有正文

- **WHEN** 用户在同一会话中连续提问等级、障碍度、酸化等专业问题
- **THEN** 每一轮回答 SHALL 均包含对应业务结论
- **AND** 任意一轮正文为空 SHALL 触发测试失败
