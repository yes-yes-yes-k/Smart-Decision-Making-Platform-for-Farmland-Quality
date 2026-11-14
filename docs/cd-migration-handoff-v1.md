# 镉能力迁移：交接文档

> 版本 v1，整理日期 2026-11-14。分支 `zsj_1114`（基于 `origin/master` 4ddf14f，**尚未合并**）。
> 用途：后续接手、联调与验收时，一份文档说清"已有什么能力、怎么调、数据前提、已知限制、怎么回退"。
> 能力状态的单一真相源仍是 `docs/cd-migration-roadmap.md`；口径差异逐条记在 `docs/cd-legacy-known-issues.md`。

## 一、能力与端点

服务前缀 `/api/v1/cd-flux`，全部要求 JWT。`CD_FLUX_V2_ENABLED=false` 时 `/v2/*` 返回 503。

| 能力 | 端点 | 说明 |
| --- | --- | --- |
| 通量输入导入 | `POST /api/v1/cd-flux/v2/inputs/import` | multipart `file`；新版 CSV 默认，`?mode=legacy` 接受旧七项字段并保留未知年度 |
| 通量核算 | `POST /api/v1/cd-flux/v2/calculate` | 范围参数 `source` / `year` / `parcel_id` / `region_type` / `region_id` |
| 结果明细 | `GET /api/v1/cd-flux/v2/results` | 输入 + 当前修订输出 |
| 通量统计 | `GET /api/v1/cd-flux/v2/statistics` | `field=in_cd/out_cd/net_cd/end_cd`，按来源与年度分组 |
| 年度对比 | `GET /api/v1/cd-flux/v2/compare` | 重复参数 `years`，最多 20 年 |
| 移除项计算 | `POST /api/v1/cd-flux/v2/removal/calculate` | 籽粒/秸秆移除，写回输入并触发重算；**写回时 `year` 必填** |
| 移除项统计 | `GET /api/v1/cd-flux/v2/removal/statistics` | `field=grain/straw/leaching/runoff` |
| 移除项点位 | `GET /api/v1/cd-flux/v2/removal/points` | GeoJSON，地块质心 |
| 移除项导出 | `GET /api/v1/cd-flux/v2/removal/export.csv` | 上限 10 万行 |
| 移除项分布图 | `POST /api/v1/cd-flux/v2/removal/visualization` | 复用阶段 4 渲染引擎 |
| 未来情景预测 | `POST /api/v1/cd-flux/v2/projection` | `years` 1–100，单个或列表 |
| 预测统计 | `GET /api/v1/cd-flux/v2/projection/statistics` | 原系统统计口径（样本标准差 + 线性插值分位） |
| 预测点位 | `GET /api/v1/cd-flux/v2/projection/points` | GeoJSON |
| 预测导出 | `GET /api/v1/cd-flux/v2/projection/export.csv` | 上限 10 万行 |
| 预测分布图 | `POST /api/v1/cd-flux/v2/projection/visualization` | 指定年份出图 |

阶段 2/3/4 的统计、乡镇归属、点位与可视化能力挂在 `/api/v1/heavy-metal-cd`，本轮不改动。

## 二、数据前提

- 两张结果表：`cd_flux_input_v2`、`cd_flux_output_v2`。唯一键 `(source, parcel_id, sample_id, accounting_year)`（`NULLS NOT DISTINCT`）；输出唯一键 `(input_id, input_revision, calculation_version)`。
- 输入 CSV 必需列：`source, accounting_year, parcel_id, sample_id` + 8 个分项 + `initial_cd, bulk_density_g_cm3, soil_depth_m`。单位：分项 `g/ha/a`、初始储量 `g/ha`、容重 `g/cm³`、厚度 `m`。空数值表示未知，系统不猜单位。
- 改输入 = 新修订：重导或写回都会递增 `input_revision`，旧输出保留但不再作为当前结果。
- `contract_version='legacy_v1'` 的旧七项行不参与计算、不写回，只在覆盖信息里披露。

## 三、运行与验证命令

```bash
# 1) 备份（先做，输出路径必须不存在）
python scripts/backup_cd_development_db.py --env-file .env --database db_enterprise_qa_20261013 --output <未存在的dump>

# 2) 迁移（默认全量回滚演练，不落库）
python scripts/migrate_cd_flux_v2.py --env-file .env --database db_enterprise_qa_20261013
python scripts/migrate_cd_flux_v2.py --env-file .env --database db_enterprise_qa_20261013 --apply

# 3) 定向测试
python -m pytest tests/test_cd_removal.py tests/test_cd_projection.py -q
```

Python 解释器固定用 `C:\Users\PC\.conda\envs\agent_culti_demo_py312\python.exe`。

## 四、已知限制与失败项

细节见 `docs/cd-legacy-known-issues.md`（13 条）。影响使用方式的几条：

- **写回必须显式 `year`**：作物 Cd 结果表无年度字段，无法推导归属年度；缺年度直接拒绝（`year_required`），批处理需按年度分批。
- **写回只覆盖指定年度**：同年限其他年度、其他来源保持原值；同地块样点在同一范围内命中多来源时判为歧义、拒绝写回。
- **阶段 7 土重口径照抄原系统**：分母固定 `2000 × bulk_density_g_cm3`，不读 `soil_depth_m`。与 v2 当年浓度（`soil_depth_m × 容重` 推导）仅在耕层 0.2 m 时等价，其他深度有系统性差异（0.15 m 差约 1.33 倍）。
- **容重缺失回退 1.0**：耕地实际容重多 1.1–1.5，回退会使浓度偏高约 20–30%。
- **区域参数在计算侧不生效**：移除与预测的 `area` 只记录、不参与查询（与原系统一致），统计/点位/导出侧才按区域过滤。
- **秸秆分母非正静默跳过**：`exp(ln)×0.76−0.0034 ≤ 0` 的样点无秸秆值，响应给计数，不改数值。
- **输入数据仍依赖外部供给**：当前开发库通量输入为 0 行，真实分布与量级尚未验证。

## 五、待决策项

| 项 | 问题 |
| --- | --- |
| 亩产量 `f11` | 是否继续固定默认 800（原系统 `Parameters(area='韶关')`），还是建参数表按区域/年度取值 |
| 秸秆经验式 | `0.76 / 0.0034` 出处未考证，是否保留 |
| 预测年份上限 | 1–100 年是否调整 |
| 负浓度 | 净通量为负时外推可能得负浓度，是否截断 |
| 预测结果是否落库 | 当前按需计算、不落库（与原系统一致） |
| 年度维度 | 是否为作物结果表补年度，或建「地块—年度」对照表 |

## 六、回退

1. `CD_FLUX_V2_ENABLED=false` 并重启服务：`/v2/*` 返回 503，旧入口继续可用，新表与年度数据保持原样。
2. 迁移事务失败会自动回滚；schema 不兼容需人工核对，脚本不自动删表。
3. 本轮改动尚未合并到 `origin/master`，未合并前不影响主线；合并后回退按提交回滚。

## 七、未覆盖

- 完整灾难恢复（pg_restore 全库演练）未做；
- 前端联调（对话与页面消费这些端点）未做；
- 移除项/预测在对话侧的接入未做，C1 阶段只登记了能力状态与缺项。
