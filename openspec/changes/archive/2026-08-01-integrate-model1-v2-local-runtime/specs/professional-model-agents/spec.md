## ADDED Requirements

### Requirement: 模型1 v2 使用项目内数据完成真实预计算和查询

系统 SHALL 使用项目内 `data/farmland_stability/manifest.json` 定义的三期 Shapefile 运行模型1 v2。清单 SHALL 声明当前文件、历史文件、年份和地块统一编码字段。预计算 SHALL 将九模块结果持久化到本地查询库，并生成空间和表格结果；运行时 SHALL NOT 依赖外部模型交付目录。

#### Scenario: 执行模型1 v2 预计算
- **WHEN** 系统读取模型1 v2 清单并执行预计算
- **THEN** 系统 SHALL 使用 `TYBH` 作为地块统一编码
- **AND** SHALL 计算并持久化全部九个稳定性与退化风险模块
- **AND** SHALL 返回处理地块数和项目内输出文件路径

#### Scenario: 查询已预计算的模型1结果
- **WHEN** 调用方以存在的 `parcel_id` 请求 `stability-risk-evaluation`
- **THEN** 系统 SHALL 从本地稳定性结果库返回真实结果
- **AND** 结果可靠性 SHALL 标记为 `real_model`，而不是模拟结果

#### Scenario: 聊天 Agent 展示真实掉级风险
- **WHEN** 用户询问已预计算地块的退化风险或掉级风险
- **THEN** 模型1 Agent SHALL 从第六模块的已持久化结果读取掉级风险绝对值
- **AND** SHALL NOT 使用模拟默认风险分数替代真实结果
