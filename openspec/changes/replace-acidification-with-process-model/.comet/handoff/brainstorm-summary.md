# Brainstorm Summary

- Change: replace-acidification-with-process-model
- Date: 2026-08-01

## 确认的技术方案

### 四子模型架构
- 直接移植模型5源码4个函数：paddy_urea/paddy_compound/upland_urea/upland_compound
- 每个子模型独立定义默认参数（_PADDY_DEFAULTS/_UPLAND_DEFAULTS + 复合肥额外 YN/SN）
- 水田 vs 旱地差异：产量/元素含量/pHtarget(6.5 vs 6.0)/Anit系数/YTK系数/MBNT系数
- 尿素 vs 复合肥差异：复合肥多YN/SN参数，Ano3_crop/Ano3_runoff/Avol公式不同

### 参数覆盖机制
- 可配参数白名单（7个）：RPH/R/Y/S/FertN/Ndep/pHtarget
- 不可配参数（元素含量）：Yp/Yk/Yca/Ymg/Sp/Sk/Sca/Smg/YN/SN 保持内置
- 覆盖逻辑：API传入的可配参数覆盖默认值，结果中标注 customized_params

### 旧函数处理
- query_acidification/evaluate_acidification → 委托 calculate_acidification_amendment
- classify_acidification/generate_amendment/calculate_lime_demand → 标记 deprecated

### Agent answer 生成
- 保留 pH 分级描述（强酸性/酸性/微酸性/中性）用于酸化程度问答
- "调理剂/改良"类问题 → 直接给出 YTK/MBNT 施用量
- 移除 GB/T 42817-2023 和 NY/T 443-2019 引用

## 关键取舍与风险

- **取舍**：4个独立 DEFAULT_PARAMS dict vs 统一 dict → 选独立 dict，清晰且易维护
- **取舍**：旧函数委托 vs 删除 → 选委托，保持导入兼容性但返回值 BREAKING
- **风险**：4子模型的系数差异容易移植出错 → 缓解：逐行对照源码 + 示例值测试
- **风险**：parcel_id 查 SJD 依赖 evaluation_results 表有数据 → 缓解：查无数据时返回 rejected + 提示

## 测试策略

- 计算正确性：源码示例值 pHstart=4.31, Hex=1.56, Alex=4.08 → 4子模型各跑一次验证
- 子模型选择：4种 land_type×fertilizer_type 组合验证
- 参数覆盖：FertN=200 → 验证 customized_params 和 ytk/mbnt 变化
- 边界测试：SJD越界/JHX负值/缺少必填 → rejected
- parcel_id 补充 SJD：mock DB 返回 SJD → 验证 pHstart 取自 DB
- 回归测试：question_type=2 → model-4 路由不变

## Spec Patch

无（delta spec 的5项 MODIFIED Requirements 已覆盖全部验收场景，无需补充）
