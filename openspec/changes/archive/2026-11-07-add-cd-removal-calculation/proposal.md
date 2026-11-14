# add-cd-removal-calculation Proposal

## Why

阶段 5 已让通量核算可用，但输出通量四项里只有「地下渗漏 / 地表径流」来自输入行，「籽粒移除 / 秸秆移除」两项在原系统是按作物 Cd 浓度与产量参数算出来的（`app/services/cd_flux_removal_service.py`）。本项目尚未迁移这条链路，`cd_flux_input.ZL_Cd / JG_Cd` 只能靠人工填写。

核验原系统实现时确认：① 籽粒/秸秆移除有明确经验公式（含亩产量参数 F11 与 0.5×15/1000 系数）；② 秸秆公式分母 `C×0.76−0.0034` 可能非正，原系统对这类样点静默跳过——本 change 要显式计数披露；③ 地表径流/地下渗漏在原系统**没有计算逻辑**（两个 update 函数是空壳，直接返回"数据已存在"），其数值本来就来自输入表，因此本阶段不重造计算，只做统计/空间/导出。

## What Changes

- 新增移除项计算服务：由 `cd_crop_prediction_result`（作物 Cd 结果）+ 亩产量参数 `f11` 计算籽粒移除与秸秆移除通量。
- 新增写回链路：计算结果写回 `cd_flux_input.ZL_Cd / JG_Cd`（按 `(parcel_id, sample_id)` 覆盖），随后触发阶段 5 的 `calculate()` 重算 `cd_flux_output`。
- 新增四类移除项的统计、点位 GeoJSON、CSV 导出与地图/直方图（复用阶段 4/5 的渲染与产物规范）。
- 新增 HTTP 端点：计算并触发重算 / 统计 / 点位 / 导出 / 可视化。
- 产量参数 `f11` 由请求提供（默认 800 斤/亩，与原系统模型默认值一致），写入响应与产物元信息。

## Capabilities

### New Capabilities

- `cd-removal-calculation`: 籽粒移除与秸秆移除通量计算、写回输入表并触发通量重算、四类移除项的统计/空间/导出。

### Modified Capabilities

无。本 change 复用阶段 5 的 `cd_flux_input/cd_flux_output` 与 `calculate()`、阶段 2 的作物 Cd 结果表、阶段 3 的归属依据与阶段 4 的渲染引擎；不改变它们的既有行为。

## Impact

- 代码：新增 `framework/domain/other_models/cd_removal.py`、`framework/api/routes/cd_flux.py` 增补端点（或独立蓝图）、测试 `tests/test_cd_removal.py`。
- 数据：只写 `cd_flux_input` 的 `ZL_Cd/JG_Cd` 两列并触发 `cd_flux_output` 重算；不新增表。
- 接口：新增 `/api/v1/cd-flux/removal/*` 端点（JWT）。
- 依赖：复用现有 numpy/pandas/rasterio/matplotlib。

## Roadmap

- 阶段：**6 / 7**（阶段 0–5 与 D1 已归档）
- 前置：`add-cd-flux-accounting`（阶段 5，已归档，提供输入/输出表与重算）；籽粒/秸秆移除另需阶段 2 的作物 Cd 结果表
- 后续：`add-future-cd-projection`（阶段 7：未来 N 年情景）
- 单一真相源：`docs/cd-migration-roadmap.md`；归档时需回填该文件状态

## Non-Goals

- 不重新实现地下渗漏/地表径流的物理计算（原系统即空壳，数据来自输入表）。
- 不做未来年份预测（阶段 7）。
- 不引入原系统 `Parameters` 表的 F1–F10 参数（只有 F11 参与本阶段公式）。
- 不改变阶段 5 的计算公式与分箱口径。
