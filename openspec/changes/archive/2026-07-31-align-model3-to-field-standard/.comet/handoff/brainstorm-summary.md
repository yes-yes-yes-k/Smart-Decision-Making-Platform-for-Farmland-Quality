# Brainstorm Summary

- Change: align-model3-to-field-standard
- Date: 2026-07-31

## 确认的技术方案

采用 **方案 C：重命名 + 移植 V2.0 关键函数**。保留 DB 持久化 + 在线查询架构（用户确认），字段全量重命名为标准码，同时把 V2.0 的关键函数移植进现有模块：

- `translate_obstacle_level(ind, level, orig_val)` 从 evaluate_single 抽离
- `replace_abbr_in_text(text, abbr_map)` 移植自 V2.0
- `diagnosis_row(row, indicator_names, level_cols, degree_cols)` 改签名为 V2.0 形式，返回 `(ZALX, ZYZAYS, CYZAYS)` 字符串三元组
- `GRADE_CONFIG` / `INDICATOR_DISPLAY_MAP` / `DISCRETE_CN_MAP` / `ALL_INDICATORS` 等常量提到 config.py
- 障碍等级/障碍度列统一用 `xxxZADJ` / `xxxZAD`（根治大小写 bug）

字段映射权威表：PH→SJD, YJ→YJZ, YXP→YXL, SXK→SXJ, RZ→TRRZ, GZ→GCZD, GG→GGNL, PS→PSNL, DX→DXBW, ZD→ZDGX, YXT→YXTCHD, GCH→GCHD；后缀 _LD→LSD, _OD→ZAD, 障碍等级→ZADJ；字段 composite_weight→ZHQZ, grade→GDZLDJ, JY/EJ→YJNYQ/EJNYQ, obstacle_type→ZALX, main_factors→ZYZAYS(string), secondary_factors→CYZAYS(string)。

## 关键取舍与风险

- **保留 DB 架构 vs V2.0 批处理**：选保留 DB（problem_agent/thematic_models 依赖在线查询），代价是需把 V2.0 函数适配到 DB 流程，不能直接照搬 main()。
- **diagnosis_row 返回类型从 list 改 string**：改变 storage（JSON list 列 → TEXT 列）和 problem_agent 消费方式，但符合 spec 和 V2.0。
- **CSV 表头 BREAKING**：中文表头 → 标准码表头，测试 CSV 需同步改。
- **顺带修两个潜伏 bug**：①diagnosis_row 大小写交集为空导致生产环境恒返回"无明显障碍"②acidification.py 读 'JY' 列（实际是 region_code）导致酸化评估恒用 HN 区。
- **acidification.py 原漏在 tasks.md 外**：本次补入（否则模块字段重命名后崩溃）。

## 测试策略

- 全量更新 tests/test_farmland_diagnosis.py：row 字典、record、CSV 表头、断言改标准码
- 新增测试：①障碍度不覆盖原始值（ZAD 独立于 SJD 原值）②diagnosis_row 返回字符串三元组 ③ZALX/ZYZAYS/CYZAYS 端到端
- 可选 golden test：用 V2.0 test.csv/test_result.csv 对照
- 运行整体测试套件确认 model-1/model-7 无回归

## Spec Patch

在 `specs/farmland-obstacle-diagnosis-model/spec.md` 补充一条验收场景：酸化改良模块 SHALL 使用标准字段名（SJD/YJZ/region_code）从 evaluation_results 读取数据。属补充验收场景，不改变范围结构。
