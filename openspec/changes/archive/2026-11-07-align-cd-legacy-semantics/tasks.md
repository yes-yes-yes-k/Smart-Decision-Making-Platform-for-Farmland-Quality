## 1. 回退净通量分档

- [x] 1.1 `cd_flux._distribution` 恢复原系统三档定义（负/平衡/正，允许重叠）
- [x] 1.2 占比恢复 `round(...,2)`、去掉补差，允许占比之和 > 100%
- [x] 1.3 更新 `test_cd_flux` 分箱测试（重叠、占比 150.01%）

## 2. 回退区域过滤

- [x] 2.1 `cd_removal.calculate` 按全量执行，区域参数仅记录（`area_filter: not_applied`）
- [x] 2.2 `cd_removal` 统计/点位/导出保留区域过滤（对应原系统按乡镇空间过滤的统计入口）
- [x] 2.3 `cd_projection._base_rows` 不再按区域筛选，响应标注 `area_filter: not_applied`
- [x] 2.4 更新 `test_cd_removal` / `test_cd_projection` 区域断言

## 3. 回退未来预测统计口径

- [x] 3.1 `cd_projection._stats` 改为 `count/mean/std(ddof=1)/min/max/median/p25/p75`
- [x] 3.2 去掉阶段 2 口径标注与 GB15618 分布字段
- [x] 3.3 更新 `test_cd_projection` 统计断言

## 4. 回退可视化插值降级

- [x] 4.1 `heavy_metal_cd_visualization._interpolate_nan` 异常时返回原栅格（保留 NaN），不降级 nearest

## 5. 文档与验证

- [x] 5.1 新增 `docs/cd-legacy-known-issues.md`（10 条原系统已知问题）
- [x] 5.2 Cd 相关测试 97 passed
- [x] 5.3 周报（`土壤质量大模型demo-1107.md`）改为"沿用原系统口径"表述
