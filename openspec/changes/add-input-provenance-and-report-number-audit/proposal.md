# add-input-provenance-and-report-number-audit Proposal

## Why

两条可信度风险目前都缺少机器可验证的依据。

**其一：模型输入无法区分“地块实测”与“区域平均回填”。** Model-4 需要交换性氢、交换性铝，Model-5 的随机森林需要全氮，这些字段在原始地块数据中并不存在，`scripts/link_soil_indicators.py` 用三普采样表的**全局平均值**回填到了所有地块。字段因此“有值”，`predict_dose()` 中的 `indicators.get(name) is None` 守卫不会触发，模型照常返回 `status=ok`、`simulated=false`、`data_source=rf_model`。当前数据库实测：

- `total_n`：5491 个地块全部为 `1.4055`（RF 训练时 TN 均值为 0.595 / 0.703，约为其 2 倍）；
- `exchangeable_hydrogen`：5488 个地块为 `0.2949`；
- `exchangeable_aluminum`：5488 个地块为 `4.0262`；
- `exchangeable_acid_total`、`hydrolytic_total_acidity`：各只有 1 个取值；
- `target_ph` 全部为 6.5，`fertilizer_type` 全部为 compound。

也就是说，交换性铝参与的酸缓冲量与木本泥炭用量、全氮参与 RF 预测的分支，在所有地块上来自同一个常数，但对外表现为“真实模型结果”。

**其二：报告生成的定量内容没有生成后审计。** 报告章节由 LLM 生成，酸化结论提示词仍要求“预期 pH 提升目标与增产潜力与效益”，而注入的上下文只有地块指标、用量和模型来源，没有作物基准产量、响应曲线、材料价格和投资口径。`generate_report()` 目前在拼接完成后没有任何数字比对，无法保证输出只引用输入中已有的数值。

## What Changes

- 新增字段级来源标注：`soil_indicators` 中的指标可以携带来源（`measured` / `region_mean_backfill` / `default`），并提供统一的读取与判定入口。
- 新增回填标注脚本：识别“跨地块常量”形式的回填字段，默认只输出报告，显式 `--apply` 才写入来源标记，重复运行不产生重复修改。
- 扩展 Model-5 与 Model-4 的输入守卫：从“是否为 None”扩展为“是否为回填输入”。命中时返回 `degraded`，`imputed_features` 必须列出被回填的特征，`issues` 使用稳定代码，定量结果保留但必须带来源说明。
- 报告生成后新增数字审计：抽取 LLM 章节中的敏感定量表述，与输入上下文白名单比对；无法追溯的数值按“暂无可靠估计”处理，报告整体标记 `degraded` 并在结果中返回问题清单。
- 报告“数据来源与计算依据”小节增加被回填输入字段的说明，使读者能看出哪些输入不是地块实测值。

## Capabilities

### New Capabilities

- `model-input-provenance`：地块指标字段级来源标注、回填字段识别、模型输入降级与 `imputed_features` 输出。

### Modified Capabilities

- `demo-report-export`：报告生成后必须执行数字审计，只允许引用输入中已有的定量内容。

## Impact

- 数据：`parcel_info.soil_indicators` 增加来源标记子结构；新增可 dry-run 的标注脚本。
- 模型层：`framework/domain/calculations/organic_matter_calculation.py`、`framework/agents/specialized/acidification_agent.py`、`framework/agents/specialized/organic_matter_agent.py`、`framework/agents/output_contract.py`。
- 报告层：`src/ai_culti_demo/report.py` 与新增的数字审计模块。
- 接口：报告生成响应的 `status` 可能由 `ok` 变为 `degraded`，并新增 `issues` 与审计信息；调用方与前端需要容忍该变化。
- 数据库结构不变，不新增表。

## Non-Goals

- 不修复缺失数据本身。地块级交换性氢、交换性铝、全氮需要新的实测数据源，本次不做空间插值或人工赋值。
- 不删除回填字段，也不把回填值改成 `0` 或 `null`。
- 不引入基于语言模型的二次复核。数字审计只做可机器验证的白名单比对。
- 不调整已归档报告的章节结构与模板顺序。
