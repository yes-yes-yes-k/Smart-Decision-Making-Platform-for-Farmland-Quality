## 1. 输入来源标注

- [x] 1.1 在 `soil_indicators` 中定义 `provenance` 子对象，限定 `measured`、`region_mean_backfill`、`default` 三类取值
- [x] 1.2 提供统一的来源读取与判定入口（判定字段是否被回填、列出被回填字段）
- [x] 1.3 未标注字段按“来源未知”处理，不得在守卫和展示中当作实测值

## 2. 来源台账与标注脚本

- [x] 2.1 在 `framework/domain/provenance.py` 维护声明式来源台账（实测 / 回填 / 默认三组字段）
- [x] 2.2 标注脚本按台账输出字段、来源、有值地块数与已标注地块数，默认只读
- [x] 2.3 `--apply` 才写入来源标记，重复运行不修改已标记字段
- [x] 2.4 提供 `--revert` 移除台账中字段的来源标记，不触碰其他字段
- [x] 2.5 移除基于“跨地块取值集中度”的统计推断：来源改由写入路径声明

## 3. Model-5 输入降级

- [x] 3.1 `predict_dose()` 的必填特征同时检查缺失与回填
- [x] 3.2 特征被回填时返回 `status=degraded`、`reason=MODEL5_INPUT_IMPUTED`
- [x] 3.3 规范结果填充 `result.imputed_features`，`issues` 使用稳定代码 `IMPUTED_INPUT`
- [x] 3.4 统一输出契约按既有安全规则处置定量字段（实测为置空并附加 `MODEL5_QUANTITATIVE_UNAVAILABLE`），行为已记入 design.md

## 4. Model-4 输入降级

- [x] 4.1 酸化链路识别被回填的交换性氢、交换性铝、目标 pH 与肥料类型
- [x] 4.2 命中时返回 `degraded`，并在结果中列出 `imputed_inputs`
- [x] 4.3 统一输出契约的 Model-4 投影保留 `imputed_inputs` 并容忍该降级原因

## 5. 报告生成后数字审计

- [x] 5.1 从上下文与 `data` 章节构建数值白名单
- [x] 5.2 抽取语言模型章节中的敏感定量表述（含单位、pH 数值与预测性时长）
- [x] 5.3 无法追溯的数值按“暂无可靠估计”处理，报告状态置为 `degraded`
- [x] 5.4 报告结果返回固定结构的 `audit` 信息（检查数、通过数、问题清单）
- [x] 5.5 酸化结论提示词与有机质结论保持一致，不再要求生成缺少依据的提升目标与效益

## 6. 报告披露与兼容

- [x] 6.1 “数据来源与计算依据”小节列出被回填输入字段及其来源类型
- [x] 6.2 在 proposal 的 Impact 与 design 的决策记录中说明报告 `status` 可能变为 `degraded`
- [x] 6.3 在 `docs/api-contract.md` 增补报告状态、数字审计与被回填输入披露说明

## 7. 验证

- [x] 7.1 单元测试覆盖来源台账、来源判定、特征取数字段一致性、Model-5/Model-4 降级、白名单比对与替换（24 项新增测试）
- [x] 7.2 使用当前数据库执行标注脚本 dry-run，确认台账各字段的来源分组、有值地块数与已标注数（未写库）
- [x] 7.3 构造包含“缺少依据的定量结论”的报告输入，验证审计拦截并替换为“暂无可靠估计”
- [x] 7.4 运行报告、模型、输出契约相关定向测试，290 项通过

## 8. 未完成（需人工确认后执行）

- [ ] 8.1 对生产/开发库执行 `--apply` 写入来源标记（dry-run 结果见 `docs/generated/provenance-manifest-20260912.json`）
- [x] 8.2 `plow_layer_thickness` 等源数据常量按 `measured` 处理，并在数据质量报告中说明其在测试数据中无空间差异
- [ ] 8.3 确认 Model-4 是否也应像 Model-5 一样在回填输入下置空用量
- [x] 8.4 发现并记录字段名不一致：model-5 的 `TN` 取自 `total_nitrogen`，而回填脚本写的是 `total_n`（已在 design.md 的 Open Questions 记录，并加漂移测试 `test_model5_feature_sources_match_accessor`）
- [ ] 8.5 决策：是否把 model-5 的 `TN` 取数字段改为 `total_n`（会触发 `MODEL5_INPUT_IMPUTED`，需与主线确认）
