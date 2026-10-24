# add-heavy-metal-cd-prediction Proposal

## Why

当前系统已有镉统计指标定义，但仅在导入污染物监测数据后可用，尚无可调用的镉预测模型。AcidMap 的在线接口面向区域地图与统计，不提供逐点 JSON 预测；其 crop_cd（14 项）和 effective_cd（21 项）为两个小型 PyTorch MLP，权重文件分别仅 48.6KB / 56.3KB，项目环境（agent_culti_demo_py312）已安装 torch 2.14.1+cpu，可直接加载权重推理，无需引入新依赖或转换格式。

已核验的本项目地块数据仅能对应少量输入字段，且缺少总镉 TCd 与上游络合计算值 `solution` / `Cdsolution`。因此本变更先提供显式参数级预测与可信的预填缺口表达，不宣称地块级 Cd 评估；缺失 `solution`/`Cdsolution` 时按用户拍板提供训练集中位数参考值并强制降级标注，其余字段缺失不得用统计值静默补齐。

## What Changes

- 将 AcidMap 的作物 Cd 与土壤有效态 Cd 推理能力本地化为 torch 直接加载推理，模型资产置于受控目录并配 manifest（SHA-256），不依赖旧系统在线服务。
- 固化两个模型的特征名称与顺序、scaler 维数断言、特殊特征索引（solution=13、Cdsolution=20），并以守门测试防错列。
- 提供统一输入契约与参数级预测领域函数（domain callable）：完整输入返回数值；缺失 `solution`/`Cdsolution` 时以训练集中位数作为显式 assumptions 参考值并强制 `degraded`；其他缺失或非法输入返回明确状态且不调用模型。
- 提供逐字段来源标注的地块部分预填能力（provenance / missing_fields），不自动补值、不自动预测。
- 返回模型数值及单位核验状态；不输出基于未核实阈值的安全等级。

## Capabilities

### New Capabilities

- `heavy-metal-cd-prediction`: 本地 Cd 模型资产、参数级预测、输入可信度与地块部分预填契约。

### Modified Capabilities

- 无。

## Impact

- 代码与资产位于 `framework/domain/other_models/`（新增 cd 模块）与 `data/model_artifacts/heavy_metal_cd/`。
- 本阶段交付为领域函数 + 测试（domain callable），不新增 Flask Blueprint / HTTP 路由；API 蓝图留待后续另行决策。
- 项目运行时新增 torch 依赖（已安装 2.14.1+cpu），不调用 AcidMap 服务，不修改地块业务数据。
- 预测结果的单位状态标记为未核实；不提供 0.2/0.3 mg/kg 安全分级。

## Non-Goals

- 不实现 MSM 络合计算、Cdsolution/solution 自动生成或旧系统逐点 HTTP 调用。
- 不将当前地块数据包装为完整地块级 Cd 评估；除已拍板的 solution/Cdsolution 参考值外，缺失字段不以区域均值、训练集统计值或零值填充。
- 不导入旧系统业务数据、不执行数据库迁移、不实现地图/栅格批处理或 Agent 编排。
- 本 change 不包含 HTTP API 蓝图与 JWT 保护（先做领域函数与测试，接口另行决策）。
- 不宣称未经核实的输入单位、阈值依据或法规安全等级。