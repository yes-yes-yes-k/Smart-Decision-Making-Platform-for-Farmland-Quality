# import-cd-ported-dataset Proposal

## Why

Cd 业务链路的代码已经跑通（阶段 0–3 全部归档：模型、结果表、统计、乡镇/点位），但**结果表是空的**，所有接口只能返回空态。

两条数据路都不通：

- 本项目自有数据：5488 个地块能凑齐模型输入的**数量为 0**（`docs/cd-input-coverage-report.md`）
- 直接从原系统取数：40100 个采样点与本项目地块按坐标匹配率仅 8.7%（≤100m），中位距离 57km，无法对应（`docs/cd-model-consistency-report.md`）

数据需求清单（`docs/cd-data-requirements.md`）已交给业务方，但数据到手需要时间。为了**先把业务跑通、把接口和页面验证起来**，本 change 把原系统整套 Cd 数据集移植进本项目数据库，使用**独立命名空间**，与自有地块数据并存但不混淆。

已实测的前提：本地推理与原系统结果逐位一致（作物 Cd 差 ≤1.9e-06；有效态按原系统列语义换算后差 ≤1.7e-07）。

## What Changes

- 新增导入脚本：从 `soilgd` 读 `Farmland_data` + `CropCd_input_data` + `EffCd_input_data` + `MSM_output_data`，按已核实的列映射组装 14/21 特征行，调用现有 `run(rows=..., apply=True)` 写入结果表。
- **独立命名空间**：移植数据的 `parcel_id` 统一加前缀 `SGD_`（如 `SGD_1`），`sample_id` 为 `SGD_<Farmland_ID>_<Sample_ID>`，与本项目 `parcel_id`（纯数字）严格隔离。
- `parcel_info` 插入移植地块行（有质心坐标、无几何），使点位与明细能 join 上。
- 新增移植地块的乡镇归属表，用 103 个乡镇边界做点面判断，使阶段 3 的乡镇统计对移植数据同样可用。
- 统计接口增加"数据来源"维度：可按 `native` / `ported` / `all` 过滤，并在响应里返回两侧样本数，避免把移植数据的统计误当成本项目地块的结论。

## Capabilities

### New Capabilities

- **heavy-metal-cd-ported-dataset**：原系统 Cd 数据集的可重复导入、命名空间隔离、乡镇归属与回归比对。

### Modified Capabilities

- **heavy-metal-cd-statistics**：统计响应增加数据来源维度（可选过滤 + 来源分解），不改变原有 8 项统计与分箱口径。

## Impact

- **数据库**：新增 1 张移植归属表；`parcel_info` 增加 40100 行（前缀隔离）；两张结果表各增加 40100 行
- **代码**：新增 `scripts/import_ported_cd_dataset.py`、`framework/domain/other_models/heavy_metal_cd_ported.py`；统计服务与路由增加 `source` 参数
- **接口**：`/statistics/*` 与 `/results*` 增加可选 `source` 参数（默认 `all`），响应增加 `source_breakdown`
- **不涉及**：模型推理逻辑、结果表结构、阶段 1 的写入语义

## Roadmap

- 阶段：**D1（数据通道，不属于 1–7 业务阶段）**
- 前置：阶段 1–3（已归档）
- 后续：数据齐备后由业务方数据替换/并存（另议迁移策略）
- 单一真相源：`docs/cd-migration-roadmap.md`

## Non-Goals

- 不把移植数据伪装成"本项目地块的评估结果"：必须带 `SGD_` 前缀与来源维度
- 不做坐标匹配式的"部分导入"（9–15% 覆盖率 + 张冠李戴，已否决）
- 不迁移原系统的图件/栅格产物（阶段 4 自己生成）
- 不引入 MSM 求解本体（直接用库里现成的 `Cd.solution`）
