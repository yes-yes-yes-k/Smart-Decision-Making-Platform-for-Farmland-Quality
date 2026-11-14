# Cd 能力迁移路线图（跨 change 单一真相源）

> 用途：让**任何一个新会话**在不依赖聊天记忆的前提下，知道 Cd 迁移有哪些阶段、做到第几步、下一步是什么。
> 维护纪律：**每个 change 归档时，必须在同一提交里回填本文件对应阶段的状态与归档日期。**
> 进度可用命令重建：`openspec list`（在途 change 与任务进度）+ `openspec/changes/archive/`（已归档）。

## 一、阶段总表

**阶段 0｜add-heavy-metal-cd-prediction｜已归档（2026-10-25）**
- 交付：本地 torch 双模型参数级推理（`framework/domain/other_models/heavy_metal_cd.py`）、模型资产 + manifest SHA-256、15 个测试
- 前置：无

**阶段 1｜add-heavy-metal-cd-database-backend｜已归档（2026-10-31）**
- 交付：两张结果表（与原系统同构、只存 ln 值）、数据库输入适配、地块级覆盖写库、mg/kg 读取还原、批量入口
- 前置：阶段 0
- 备注：输入覆盖率实测为 0（`docs/cd-input-coverage-report.md`），本阶段改为"完整特征行外部供给"；归档时 25/27 tasks，剩 2.4（待数据字典，未完成）
- 归档目录：`openspec/changes/archive/2026-10-31-add-heavy-metal-cd-database-backend/`

**阶段 2｜add-heavy-metal-cd-statistics-api｜已归档（2026-10-31）**
- 交付：8 项基础统计（总体标准差、下标分位数）、作物 Cd 三档分布、双模型综合统计、分页明细、CSV 导出、模型契约、6 个 HTTP 端点（JWT）
- 前置：阶段 1（已归档）
- 口径：1A 照抄下标分位数 / 2A 空数据 200 + has_data=false / 3A 区域过滤仅 area_code / CSV 上限 10 万行
- 备注：结果表当前 0 行，真实数值待输入到位；归档时 20/21 tasks（仅剩归档回填本身）
- 归档目录：`openspec/changes/archive/2026-10-31-add-heavy-metal-cd-statistics-api/`

**阶段 3｜add-heavy-metal-cd-spatial-analysis｜已归档（2026-10-31）**
- 交付：乡镇级 Cd 统计（最大面积归属）、单区域统计、点位 GeoJSON（地块质心）、边界复用 `farmland-statistics/boundaries`
- 前置：阶段 2（已归档）
- 口径：最大面积归属 / `min_count` 1 / 样本数降序 / 点位 bbox + limit 5000
- 实测：5488 地块全部有 township 归属；跨乡镇 530（9.6%）；探针 3 行分属 3 乡镇且三档正确；点位坐标与质心逐位一致
- 归档目录：`openspec/changes/archive/2026-10-31-add-heavy-metal-cd-spatial-analysis/`

**阶段 D1｜import-cd-ported-dataset｜已归档（2026-10-31）**
- 交付：原系统 Cd 数据集移植（`SGD_` 命名空间）、移植乡镇归属表 `cd_ported_parcel_township`、`source` 来源维度（统计/明细/CSV/乡镇/区域/点位）
- 前置：阶段 1–3（已归档）
- 目的：自有地块缺模型输入（覆盖率 0），先用移植数据把业务链路跑通；业务方数据到位后切 `source=native`
- 实测：两模型各 40100 行导入；归属点面 39831 + 回退 74（0.18%）；回归最大差 2.79e-06 / 1.03e-06；作物 Cd 均值 0.1125、中位 0.0986、max 0.4380；`geom IS NOT NULL` 仍 5488（既有统计未受污染）
- 文档：`docs/cd-ported-dataset.md`、`docs/cd-data-requirements.md`（给业务方的需求清单）
- 归档目录：`openspec/changes/archive/2026-10-31-import-cd-ported-dataset/`

**阶段 4｜add-heavy-metal-cd-visualization｜已归档（2026-11-07）**
- 交付：结果表 + 地块质心栅格化、可选 griddata 插值（nearest/linear/cubic，点数不足降级 nearest）、分级地图（作物三档 / 有效态分位数 6 级）、行政区描边（多要素，凸包兜底）、直方图、GeoTIFF 可选导出、产物目录 + meta.json + 3 个 HTTP 端点
- 前置：阶段 3（已归档）
- 实测：全部 Cd 测试 83 passed；真实库 40100 行 → 栅格 344×259、有效像元 17082、值域 0.0048–0.438 mg/kg；map.jpg / histogram.jpg / raster.tif 均生成
- 资产：原系统 `template.tif` 迁入 `data/model_artifacts/heavy_metal_cd/visualization/`（manifest 记录 SHA-256）
- 备注：21/21 tasks 完成；A/B/C 三项人工确认已于 2026-11-07 拍板——保留模板资产、有效态保留分位数 6 级（相对分级）、产物不自动清理
- 归档目录：`openspec/changes/archive/2026-11-07-add-heavy-metal-cd-visualization/`

**阶段 5｜add-cd-flux-accounting｜已归档（2026-11-07）**
- 交付：`cd_flux_input` / `cd_flux_output` 两表、CSV 导入（同键覆盖）、输入/输出/净通量与当年浓度计算（统一数据库模式公式，容重/初始值回退计数）、区域统计与四类分布（end 三档 GB15618、net 互斥三档、in/out 相对三档）、点位 GeoJSON、地图/直方图（复用阶段 4 引擎）、CSV 导出、7 个 HTTP 端点
- 前置：阶段 2 统计口径 + 阶段 3 归属依据（均已归档）
- 修正：原系统 net_cd 分箱重叠（负值/接近平衡可重复计入，占比可超 100%）→ 互斥三档并补差保证和恰为 100；CSV/DB 两套公式 → 统一数据库模式
- 实测：test_cd_flux 11 passed、全部 Cd 相关 94 passed；真实库建表成功、探针导入 3 行（回退计数 bd020_90=1/initial_cd=1）、计算 3 行、net 分布 0/66.67/33.33、导出 3 行、探针数据已清理
- 备注：22/25 tasks 完成；A（bd020_90 权威来源）/ B（net 平衡阈值 ±5）/ C（end_cd 阈值细分）三条人工确认项待拍板
- 归档目录：`openspec/changes/archive/2026-11-07-add-cd-flux-accounting/`

**阶段 6｜add-cd-removal-calculation｜已实现（2026-11-14，v2 基线，分支 `zsj_1114`）**
- 交付：籽粒移除 `exp(ln)×f11×0.5×15/1000`、秸秆移除 `exp(ln)/(exp(ln)×0.76−0.0034)×f11×0.5×15/1000`（分母非正按原系统静默跳过）、写回 v2 输入表 `grain_removal/straw_removal` 并触发 v2 重算、四类移除项统计/点位/导出/地图、5 个端点（`/api/v1/cd-flux/v2/removal/*`）
- 前置：阶段 5（已归档）+ master 上的通量 v2 契约（`cd_flux_v2`、`cd_flux_input_v2` / `cd_flux_output_v2`）
- v2 适配：写回按 `select_inputs` 返回的 `id` 精确定位，只改两列并递增 `input_revision`，不触碰其他列；v2 唯一键含 `accounting_year`，而作物结果表无年度字段，因此**写回必须显式提供 `year`**（技术必然，不是可选项）；`legacy_v1` 行不计算也不写回并计数披露；同地块样点在同一范围内命中多来源时判为歧义、拒绝写回
- 口径：与原系统一致——分母非正静默跳过（仅日志，响应计数只作可观测字段）；移除计算按全量执行、area 仅作出图边界
- 实测：`test_cd_removal` 15 passed（含年度隔离、legacy 跳过、歧义拒绝、修订递增、HTTP 端点）；Cd 相关回归 163 passed / 2 skipped；PG 测试用临时 schema 隔离，public 表零污染
- 备注：原 stage67 版（2026-11-07，基于 v1 通量契约）未合入主线，已被本 v2 实现取代；A（f11 原库实际值）/ B（秸秆经验式 0.76/0.0034 出处）/ C（是否建参数表）三条确认项登记在 `docs/cd-legacy-known-issues.md` 待议

**阶段 7｜add-future-cd-projection｜已实现（2026-11-14，v2 基线，分支 `zsj_1114`）**
- 交付：`Future_Cd=(Initial+Net×years)/(2000×bulk_density_g_cm3)`（years 1–100，单个/列表）、回退计数、区域参数仅记录、原系统统计口径 + GB15618 三档、点位/地图/CSV 导出、5 个端点（`/api/v1/cd-flux/v2/projection/*`）
- 前置：阶段 5、阶段 6（净通量）、阶段 3（空间）
- v2 适配：取数走 `cd_flux_input_v2` ⋈ `cd_flux_output_v2`（按 `input_id + input_revision` 取**当前修订**的输出），跳过 `legacy_v1` 行；新增可选 `accounting_year` 作为数据维度筛选（默认不限年度，保持与原系统「全量一套结果」的可比性）
- 口径：**土重严格照抄原系统**——分母固定 `2000 × bulk_density_g_cm3`，**不读 `soil_depth_m`**（该式与 v2 `calculate` 的 `end_cd` 在 0.2m 耕层时数值等价，其他深度存在差异，已登记 `docs/cd-legacy-known-issues.md`）；`area` 仅记录不参与查询（`area_filter: not_applied`）；统计用样本标准差（ddof=1）+ 线性插值分位
- 实测：`test_cd_projection` 10 passed（含「soil_depth 不参与公式」守门用例、多年份、回退计数、年度隔离）；Cd 相关回归 163 passed
- 备注：A（年份上限 100 是否调）/ B（负浓度是否截断）/ C（是否落库缓存）三条确认项待拍板

依赖主链：`0 → 1 → 2 → 3 → 4`，`2 → 5 → 6 → 7`。

## 对话能力接入

**阶段 C1｜add-cd-conversation-capabilities｜已归档（2026-11-04）**
- 交付范围为已有土壤 Cd 统计、Cd 预测结果、参数查询、纯参数预测、多轮补参和独立试算保存的对话接入。
- 前置能力为阶段 0–3、D1 及现有区域与地块统计服务，按实际数据覆盖开放。
- 八类通量在本阶段登记能力状态与缺项说明。阶段 5、6 完成相应服务后，在后续独立变更中接入计算与统计。
- 第一批通过文字和表格呈现结果，阶段 4 的可视化按独立需求推进。
- 需求见 `docs/cd-conversation-design.md`，任务及验收见 `openspec/changes/archive/2026-11-04-add-cd-conversation-capabilities/`。相关回归 227 项通过。

## 二、为什么每个阶段独立归档，而不是"攒到最后统一归档"

1. **归档 = 规格生效，不是项目完成。** `openspec archive` 把该 change 的 spec delta 合入 `openspec/specs/<capability>/spec.md`。后续阶段的 `MODIFIED Requirements` 是**基于已归档基线**写的：阶段 1 不归档，阶段 2 的 delta 就没有"阶段 1 引入的要求"可改，`openspec validate` 与实际基线都对不上。
2. **归档不冻结 tasks。** 归档后 tasks.md 仍可编辑（只是 spec 定格），所以"完成度跟踪"不该依赖归档状态，而应依赖本文件 + `openspec list`。
3. **全攒会造成 list 噪音。** 8 个未归档 change 同时挂在 `changes/` 下，`openspec list` 无法区分"做完了"与"还没做"，反而更难判断进度。
4. **交付节点是分支合并，不是归档。** 阶段做完 → 归档 → 合并到 `origin/master`，这才是对外可验证的结果。

## 三、跨会话如何不遗忘（三层载体，都在仓库里）

- **第一层｜本文件**：阶段总表 + 状态 + 依赖。任何会话读它就能重建全局。
- **第二层｜`openspec/project.md` 第 11 节**：只放索引与原则（因为它是新 change 默认继承的长期上下文，`openspec instructions` 会读它）。
- **第三层｜每个 change 的 `proposal.md` 里的 `## Roadmap` 小节**：写明"本阶段是第几 / 前置哪个 / 后续哪个"，这样单独打开任一 change 也知道坐标，不依赖本文件。
- **纪律**：`AGENTS.md` 写明"处理 Cd 相关任务前先读本文件"；归档时回填本文件。

## 四、与其他文档的关系

- `docs/cd-system-migration-plan-1031.md`：**范围讨论稿（未拍板）**，记录源头系统构成、候选范围 A/B/C、待拍板决策点。它是"要不要做、做到哪"的输入，本文件是"已经做到哪一步"的账本。拍板结论应回填到对应 change 的 proposal/design。
- `docs/cd-input-coverage-report.md`：阶段 1 的输入覆盖率实测证据。
- `openspec/project.md`：项目总纲，变化慢；本文件是它的执行层补充。
