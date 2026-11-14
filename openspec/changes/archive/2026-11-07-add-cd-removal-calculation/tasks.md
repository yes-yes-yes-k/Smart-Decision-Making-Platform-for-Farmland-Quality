# add-cd-removal-calculation Tasks

## 1. 计算服务

- [x] 1.1 新增 `framework/domain/other_models/cd_removal.py`：籽粒公式 `exp(ln)×f11×0.5×15/1000`
- [x] 1.2 秸秆公式 `exp(ln)/(exp(ln)×0.76−0.0034)×f11×0.5×15/1000`，分母 ≤0 跳过并计数
- [x] 1.3 `f11` 参数（默认 800）与区域/来源过滤（复用阶段 3 归属）

## 2. 写回与重算

- [x] 2.1 写回 `cd_flux_input.ZL_Cd / JG_Cd`（只更新两列，按 `(parcel_id, sample_id)`）
- [x] 2.2 触发阶段 5 `cd_flux.calculate()`，分别报告 `updated_inputs` 与 `recalculated`
- [x] 2.3 `write_back=false` 只算不写（核对模式）

## 3. 统计 / 空间 / 导出

- [x] 3.1 四类字段统计：grain/straw 来自计算，leaching/runoff 读输入表（不计算）
- [x] 3.2 点位 GeoJSON（地块质心，复用阶段 5 形状）
- [x] 3.3 CSV 导出（10 万行上限）
- [x] 3.4 地图/直方图（复用阶段 4 渲染引擎，产物目录沿用）

## 4. HTTP 端点

- [x] 4.1 `POST /cd-flux/removal/calculate`
- [x] 4.2 `GET /cd-flux/removal/statistics`、`/points`、`/export.csv`
- [x] 4.3 `POST /cd-flux/removal/visualization`
- [x] 4.4 错误语义与阶段 5 一致（`unknown_field`/`invalid_*` 400、`no_data` 404/200 + has_data=false）

## 5. 文档与验证

- [x] 5.1 `docs/cd-migration-roadmap.md` 阶段 6 状态回填（归档时）
- [x] 5.2 定向测试：公式数值、分母跳过计数、写回与重算、只算不写、区域过滤
- [x] 5.3 真实库探针：用真实作物 Cd 结果计算 → 写回 → 重算 → 校验 → 清理
- [x] 5.4 `openspec validate add-cd-removal-calculation` 通过

## 未完成（需人工确认后执行）

- [ ] A. `f11` 原库（`Parameters.area="韶关"`）实际值确认（本机无法读取原库）
- [ ] B. 秸秆转换式 `C×0.76−0.0034` 的出处与适用范围
- [ ] C. 是否需要建参数表按区域配置 `f11`
