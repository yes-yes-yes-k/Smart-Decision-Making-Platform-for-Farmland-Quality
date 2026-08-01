## Why

模型1此前使用旧字段口径，且运行依赖外部交付目录或在数据未就绪时回退为模拟结果，无法在项目内稳定执行最新的耕地质量稳定性与退化风险识别流程。

## What Changes

- 将模型1核心计算字段更新为 v2 的 `TYBH`、`SJD`、`TRRZ`、`YXTCHD` 等口径。
- 将三期 Shapefile 运行数据部署到项目内数据目录，并以清单描述运行输入。
- 预计算流程读取 `TYBH` 作为地块统一编码，生成九模块结果、SQLite 查询库、Shapefile 和 Excel 输出。
- 修正模型1聊天 Agent 对分组模块结果的读取，返回真实稳定性和掉级风险指标。
- 固定使用项目 Conda 环境内的 PROJ 数据库，避免系统级坐标系配置污染。

## Capabilities

### New Capabilities

- 无。

### Modified Capabilities

- `professional-model-agents`: 为模型1增加本地 v2 数据预计算、真实查询和可靠性标识要求。

## Impact

- 影响 `src/ai_culti_demo/farmland_stability` 的计算和预计算流程。
- 影响 `model-1/stability-risk-evaluation` 的 Agent 真实结果展示。
- 需要 Python 3.12 环境中的 GeoPandas、SciPy、Shapely、Pyogrio 及 PROJ 数据库。
- Shapefile 和预计算产物保留在本地数据目录且不纳入 Git；清单和代码纳入版本控制。
