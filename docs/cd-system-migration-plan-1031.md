# Cd 系统迁移规划讨论稿（zsj_1031 · 下周汇报）

> 状态：**讨论稿，未拍板**。所有事实均为 2026-10-25 本机实测。
> 待用户逐条拍板后才写 OpenSpec 提案与 tasks。

## 〇、基线同步与并入实测（2026-10-31 补充）

- 开工时 `zsj_1031` 基于**陈旧基线** `acfbbe7`，已执行 `git fetch --all --prune` 并 `git reset --hard origin/master` 重建到 **`300dd1f`**；该分支原本 0 个自有提交，重建无内容损失，未跟踪的本文档保留。
- 期间远端新增 4 个提交（来自 lili）：`fd0243c` 酸化 RF 预测接口 + 地块区域解析、`73508fa` 酸化测算记录模型及 API（新增 `routes/acidification_measurements.py`，改 `app.py`/`config.py`/`farmland_statistics.py`）。
- `framework/domain/other_models/acidification_rf.py` 上游已被 `fd0243c` 改过；`zsj_1024` 上的 `56345e0`（prefill 仅对 reflux 校验 land_type）**仍未合入 origin/master**，并入 Cd 时不要顺手带这个提交。
- cherry-pick 实测（临时 worktree 上真跑，非推测）：单独 pick `84b860c` 干净；单独 pick `55603f3` 会 `rename/delete` 冲突（它把 `openspec/changes/add-heavy-metal-cd-prediction/*` 改名进 archive，而基线上该目录不存在）。
- **可复现的并入序列**：`3b4ec22`（提案文档）→ `84b860c`（实现+资产+测试）→ `55603f3`（归档+合并 spec），三步全部 clean，落地后 `pytest tests/test_heavy_metal_cd.py` = **15 passed in 8.5s**（conda `agent_culti_demo_py312`）。

## 一、已核验事实边界

### 1. 源头系统构成（两个仓库，不是一体的）

| 部件 | 位置 | 形态 |
|---|---|---|
| 后端 | `D:\work\AcidMap` | FastAPI，11 个 API 模块 + 14 个服务 + alembic 迁移，连本机 PG `soilgd` 库（localhost:5432） |
| 前端 | `D:\work\fronted\12`（vue_soil） | Vue3 + Element Plus + Leaflet/腾讯地图 + ECharts；axios 分 api5000 / api8000 / apiMain 三套 baseURL（生产 soilgd.com） |

### 2. AcidMap 后端功能面（11 个 API 模块）

- `cd_prediction`：**全部是"生成地图/统计"型端点**——crop-cd / effective-cd 各 4 个（generate-and-get-map、generate-from-database、latest-map、latest-histogram）+ statistics / combined-statistics / town 统计。**无逐点 JSON 预测接口**（与既有核验一致）。
- `cd_flux` / `cd_flux_removal`：镉输入/输出通量（灌溉水、农业投入品、大气沉降、重金属企业、粮食移除、秸秆移除、渗漏、径流）。
- `water` / `agricultural_input` / `unit_grouping` / `raster` / `vector` / `geoserver` / `cascade_update` / `admin`：水样断面、农业投入品、单元分组、栅格/矢量/GeoServer 地图服务、级联更新、管理端。

### 3. 底层数据在本机完整可连

PG `soilgd` 库（242MB / 39 张表，localhost:5432）实测存在，含：

- **Cd 预测**：`CropCd_input_data` / `CropCd_output_data` / `EffCd_input_data` / `EffCd_output_data`（各 40100 条）
- **MSM**：`MSM_input_data` / `MSM_output_data`（`Cd.solution` 现成，无需求解代码）
- **通量/水/大气/农业**：`FluxCd_*`、`water_sampling_data`、`cross_section`、`Atmo_sample_data`、`atmo_company`、`agricultural_data`
- **空间与行政区划**：`raster_table` / `raster_table_v2`（栅格直接存库）、PostGIS（`spatial_ref_sys`）、`provinces/cities/counties/town/four_county_land`
- **其他**：`Assessment`、`Parameters`、`Soil_data`、`Farmland_data`、`surveydata`、`fifty_thousand_survey_data`、`nanxiong_soil_data`、`le_soil_data`、`unit_ceil`、`users`

### 4. 前端页面面（fronted/12）

- 数据看板、系统介绍页（SoilPro/Overview/ResearchFindings/Unit）
- **Cd 预测模型页**：`CadmiumPredictionModel` / `EffectiveCadmiumModel`（用户所说"进入 Cd 网页状态"的目标页）
- 镉输入/输出通量全套页面（灌溉水、农业投入品、大气沉降、重金属企业、粮食移除、秸秆移除、地下渗漏、地表径流，各含采样说明/数据/通量页）
- 酸化模型页（Calculation / AcidNeutralizationModel / SoilAcidificationIterativeEvolution）、统计页（行政区/土壤重金属/作物重金属/土地利用/土壤酸化等）、模型选择/训练/阈值页、用户管理页

### 5. 本项目（agent_culti_demo）现状

- **Flask 后端 + 多智能体编排，无任何前端工程**（无 web / templates / static 页面），当前交互形态是聊天/API。
- `zsj_1024` 分支已有 **Cd 双模型本地 callable**（`framework/domain/other_models/heavy_metal_cd.py` + 资产 + 15 个测试 + OpenSpec 归档），**未合入 origin/master**（实测 `git branch -a --contains 84b860c` 只有 `zsj_1024`/`origin/zsj_1024`）；`zsj_1031` 已重建在 `300dd1f`，基线不含它。
- 开发库 `db_enterprise_qa_20261013` 与 `soilgd` 是两个独立库。

### 6. 已确认的限制（沿用既有核验）

- MSM 求解代码不在 AcidMap 仓库（`Cd.solution` 只能复用库中现成值，不能对任意地块现算）。
- 本项目地块数据面缺 Cd 特征 15/21 项（含总镉 `TCd`），只能"参数级预测"，不能宣称地块级 Cd 评估。
- AcidMap 的 cd_prediction 没有逐点 JSON 接口，"HTTP 调用 AcidMap"这条路由不成立，只能本地跑或复刻。

## 二、候选实现范围（每项附建议）

- **A. 核心 Cd 预测链路（建议起步）**
  - 后端：把 zsj_1024 的 callable 接成 Flask Blueprint（`/api/v1/cd/...`），复用本项目 JWT 认证；移植 cd_prediction 的"参数预测 + 统计/历史结果"能力。
  - 数据：本项目读 `soilgd` 的 CropCd/EffCd/MSM 表（先只读直连，见决策点 2）。
  - 前端：新建页面复刻 `CadmiumPredictionModel` / `EffectiveCadmiumModel` 的页面状态（见决策点 3）。
  - 产出：切到本项目的 Cd 页面 ≈ 进入 AcidMap 的 Cd 预测页，可演示。
- **B. 通量/水/大气/农业投入品模块**：依赖 GeoServer + PostGIS + 多个大服务，工作量是 A 的数倍；建议作为 A 之后的第二阶段，不在本次范围。
- **C. 完整复刻 AcidMap 全部 11 API + 全部页面**：数量级最大，不建议一次做完。

## 三、Non-Goals（本次明确不做）

1. 不迁移 AcidMap 的离线 CSV / 批处理脚本 / `Water/` 独立分析产物（历史分析，非在线能力）。
2. 不迁移 MSM 求解本体（本机无代码，用库中现成 `Cd.solution`）。
3. 不做地块级 Cd 评估承诺（数据面缺口，参数级预测边界如实标注）。
4. 不迁移 AcidMap 的 users/管理员体系，复用本项目认证。
5. 不引入 AcidMap 的 GeoServer 部署（若地图呈现另议，见决策点 5）。

## 四、待拍板决策点

1. **迁移范围**：A（核心 Cd 预测）/ B（含通量模块）/ C（全量）？建议 **A**，先可演示、可控，通量等后续扩。
2. **数据层**：soilgd 只读直连 vs 选择性导表到本项目开发库？建议**先只读直连验证链路**（soilgd 库数据现成），稳定后再评估是否导表。
3. **前端形态**：本项目无前端工程。"复刻网页状态"的实现方式三选一：
   - 新建独立 Vue3 工程（复用 fronted 组件改造）——工程量大但还原度高；
   - Flask 渲染页（Jinja + ECharts/Leaflet CDN）——轻量，够演示；
   - 聊天/API 形态呈现 Cd 能力（不新建页面）——最轻，但不符合"进入网页状态"的直觉。
   建议先 **Flask 渲染页**起步，能最快形成"切到页面=进入 Cd 状态"的演示。
4. **zsj_1024 Cd 实现并入方式**：实测序列 `3b4ec22` → `84b860c` → `55603f3` 在 `300dd1f` 上全部 clean、落地后 15 个测试全绿；只 pick `84b860c` + `55603f3` 会在 rename/delete 上冲突。建议按该三步序列 pick（不要带 `56345e0`），而不是重写。
5. **地图/栅格呈现**：AcidMap 用 GeoServer + raster_table。本项目是否引入 GIS 栈，还是先以图表（histogram/statistics）+ 表格呈现预测结果？建议**先图表+表格**，GIS 栈后议。
6. **交互形态**：是否保留 AcidMap 式"生成地图"交互（异步任务生成栅格图），还是先做**参数级预测页**（填特征→出预测值/风险）？建议后者，与第 5 点一致。

## 五、实测后的成本与待澄清事实（2026-10-31）

### 1. 数据面（实测可连）

- soilgd 库可用**本项目 `.env` 的 postgres 凭据直连**（39 表 / 242MB）；AcidMap `config.env` 里那套密码已失效（认证失败），不要照抄。
- `CropCd_input_data` 40100 行 / 17 列，14 个特征名与 `heavy_metal_cd.py` 的 `_MODEL_COLUMNS` 完全一致；`EffCd_input_data` 40100 行 / 22 列，21 特征齐全。
- 输出表 `CropCd_output_data`/`EffCd_output_data` 各 40100 行，只有 `ID, Farmland_ID, Sample_ID, Ln*`，**无经纬度**；`MSM_output_data` 含现成 `Cd.solution`。
- `raster_table` 仅 3 行、`raster_table_v2` 0 行；`four_county_land` 66803 行带 `geom`。

### 2. 页面形态（源码实测，纠正直觉）

- `fronted/12/src/views/User/cadmiumPrediction/CropCadmiumPrediction.vue` 的实际内容只有：上传 CSV / 从数据库计算 → **静态地图图片** + **统计表格**（统计项/值/单位/描述） + **直方图图片**。
- 后端 12 个端点全是"生成地图 / 取最新地图 / 取最新直方图 / 统计"，**没有逐点 JSON 预测接口**；默认且唯一支持的县是乐昌市（`region_code=440282`）。
- 统计与直方图直接读输出表（`exp(LnCropCd)` 还原），**不需要跑模型**即可复现。

### 3. 三条实现线的成本

- 统计/直方图：本项目 env 已有 pandas 3.0.5、matplotlib 3.11.1、psycopg2 2.9.12、scipy 1.18、jinja2 3.1.6 → **零新增依赖**。
- 地图图片：`utils/mapping_utils.py` 依赖 geopandas + rasterio + seaborn + scipy + shapely + `template.tif`（仓库内 175KB 存在）→ 本项目 env **缺 rasterio / geopandas / seaborn**，需新装 GIS 依赖。
- 页面工程：仓库仍**无** `templates/`、`static/`（全仓仅 docs 下一份报告 html），现有端点 50 处走 JWT；做页面需新增模板/静态目录并决定页面鉴权方式。

### 4. 两处必须澄清的口径

- manifest `crop_cd.baseline_prediction_means_input = 0.266523` 与库内 `exp(avg(LnCropCd)) = 0.084436`（min 0.004774 / max 0.437994，同批 40100 样本）差约 3 倍，需确认"训练集预测均值"的口径。
- 有效态 Cd 的统计只有**基础统计 8 项**（源码 `get_effective_cd_statistics` 无阈值分箱）；`0.2~0.3 / ≥0.3` 分箱仅用于作物 Cd。`exp(LnEffCd)` 实测落在 1.004–2.295 mg/kg，量级与"土壤有效态 Cd"常规值不符，需确认单位（`unit_status=unverified`）。
- 参考分布（作物 Cd，40100 点）：`<0.2` 34704（86.54%）、`0.2~0.3` 3583（8.94%）、`≥0.3` 1813（4.52%）。

## 六、下周汇报口径建议（拍板后按此收敛）

- 表述为"重金属 Cd 预测能力从 AcidMap 系统向本 demo 迁移：双模型本地推理 → 预测/统计页面"，数据边界（参数级、Cd.solution 复用库中值）如实保留。
- 不与"地块级 Cd 评估"混淆；不写工程依赖细节（GeoServer/许可等）。
