## Context

模型1 v2 输入使用三期耕地质量 Shapefile，其中地块唯一标识为 `TYBH`，并使用 12 个 v2 指标及对应 LSD/QZ 字段。项目原有流程已经提供九模块计算、SQLite 持久化和 Agent 查询，但字段口径与聊天层的结果读取方式未与 v2 对齐。

## Decisions

- 使用 `data/farmland_stability/manifest.json` 描述项目内输入文件、年份和 `id_column=TYBH`，避免运行时引用外部交付路径。
- 保留模型计算和存储的既有九模块结构，仅切换 v2 指标字段和预计算地块编码。
- 将 PROJ 数据目录固定到当前 Python 解释器所在 Conda 环境，保障空间邻域计算不受系统环境变量影响。
- Agent 从 `module_2` 和 `module_6` 中读取已持久化的中文指标名，避免错误使用模拟默认值。

## Verification

- 在指定 Python 3.12 环境中完成三期 Shapefile 预计算，处理 5,488 个地块。
- 将生成 Excel 与 v2 交付结果逐列比对，78 个共同字段均一致。
- 运行模型1预计算、结果读取和 Agent 回答回归测试。
