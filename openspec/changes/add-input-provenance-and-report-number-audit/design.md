# add-input-provenance-and-report-number-audit Design

## Context

`parcel_info.soil_indicators` 是一个 JSON 快照，历史上由两类脚本写入：

1. `scripts/import_real_parcels.py`：从 2024 年测试地块 shp 映射 12 个地块级指标（pH、有机质、有效磷、速效钾、容重、有效土层厚度、耕层厚度、质地、灌溉、排水、地形、土壤结构）以及耕地质量等级；
2. `scripts/link_soil_indicators.py`：把三普采样表的平均值回填到所有地块，补齐 Model-4/5 需要的交换性氢、交换性铝、交换性酸总量、水解性总酸度、全氮等字段。

第 2 类写入在数据语义上属于“区域平均回填”，但 JSON 里没有任何标记，读侧无法区分。项目已经为此付出了两次代价：早期是缺失值被当成 `0` 参与计算，现在是常量被当成实测值参与计算，且对外状态为 `ok`。

报告侧的情况是：`generate_report()` 的结构是对的（上下文聚合 → 章节生成 → 拼接），但 LLM 章节返回的文本没有经过任何约束校验。历史工作经验表明，提示词层面的“不得编造”不足以阻止语言模型补齐“听起来合理”的数字。

## Goals / Non-Goals

**Goals:**

- 让“这个字段值来自哪里”成为可机器读取的事实，而不是靠人工记忆。
- 让 Model-4/5 在输入被回填时返回 `degraded` 并列出被回填的特征。
- 让报告在生成后能证明“所有定量内容都能在输入中找到来源”，不能证明的按“暂无可靠估计”处理。
- 全部改动只读或可回滚，不破坏现有接口契约的字段结构。

**Non-Goals:**

- 不解决数据缺失本身。
- 不用常量的“数值大小”猜测字段真假，只用可观测的结构特征与脚本显式写入。
- 不重写报告生成链路，不替换 LLM 章节生成方式。

## Decisions

### 1. 来源标记写在 `soil_indicators` 内部，键名固定

来源标记作为 `soil_indicators` 的一个保留子对象保存：

```json
{
  "soil_ph": 5.31,
  "total_n": 1.4055,
  "provenance": {
    "total_n": "region_mean_backfill",
    "exchangeable_hydrogen": "region_mean_backfill",
    "target_ph": "default",
    "fertilizer_type": "default"
  }
}
```

来源取值限定为三类：

| 取值 | 含义 |
| --- | --- |
| `measured` | 由地块级来源数据映射得到 |
| `region_mean_backfill` | 由区域/全局平均值批量回填 |
| `default` | 代码默认值或模板值 |

未出现在 `provenance` 中的字段视为**来源未知**，不得当作实测值使用。选择该方案而不是新增数据库表，是因为：标记与被标记字段必须同步更新，放在同一个 JSON 中可以保证原子性；同时不需要数据库迁移。

### 2. 来源由写入路径声明，不做数值推断

来源是**写入方的事实**：`import_real_parcels.py` 从地块 shp 逐地块映射得到实测值；`link_soil_indicators.py` 用三普采样表平均值批量填充缺失字段；导入脚本还写入 `target_ph`、`fertilizer_type` 两个固定默认值。因此 `framework/domain/provenance.py` 维护一份声明式台账 `SOURCE_MANIFEST`（字段 -> 来源）作为唯一事实来源，标注脚本只负责把台账写入数据库。

**不使用**“跨地块取值集中度”等分布特征反推来源。实测反例：

- `plow_layer_thickness` 在 5491 个地块中有 5488 个都是 20 cm，但它是**源数据本身的常量（实测）**，按分布规则会被误判为回填；
- `link_soil_indicators.py` 只填充**缺失**字段，同一字段在不同地块可能一个来自实测、一个来自平均，数值分布无法区分；
- 若填充口径改为按区域平均，常量特征同样消失，规则会整体失效。

来源判定因此必须来自写路径，而不是数据统计。源数据中取值恒定但属于实测的字段（如 `plow_layer_thickness`）按 `measured` 标注，并在数据质量报告中说明“该指标在当前测试数据中没有空间差异”。

### 3. 模型守卫从“缺失”扩展为“缺失或回填”

`predict_dose()` 现有的守卫是：

```python
missing = [name for name in FEATURE_COLUMNS if indicators.get(name) is None]
```

改为同时计算 `imputed`：

```python
imputed = [name for name in FEATURE_COLUMNS if is_imputed(indicators, name)]
```

处理策略（与统一输出契约联动，已按实测行为记录）：

- 特征缺失：维持现有行为，`status=degraded`、`reason=MODEL5_INPUT_MISSING`、`dose=None`；
- 特征被回填：返回 `status=degraded`、`reason=MODEL5_INPUT_IMPUTED`、`result.imputed_features` 列出被回填特征，并在 `issues` 中给出稳定代码 `IMPUTED_INPUT`。此时统一输出契约按既有安全规则把 `soc_prediction`、`dose_prediction`、`dose`、`manure_dosage` 置空并附加 `MODEL5_QUANTITATIVE_UNAVAILABLE`，因为该规则要求“输入可验证”才输出定量值，而回填输入不满足该条件。

因此两种降级可以区分：`MODEL5_INPUT_MISSING` 表示字段缺失，`MODEL5_INPUT_IMPUTED` 加 `imputed_features` 表示字段存在但不是地块实测值。

Model-4 采用“降级但保留用量”的策略：过程模型其余输入（pH、地类）仍是地块级真实值，且统一输出契约对 Model-4 没有置空规则，因此 `soil_conditioner_dosage`、`woody_peat_dosage` 保留，同时在结果中列出 `imputed_inputs`。两个模型的差异是有意为之，是否对 Model-4 也置空列入 Open Questions。

### 4. 数字审计采用白名单比对，不做语义判断

审计分三步：

1. **构建白名单**：递归遍历报告上下文（范围、地块指标、模型结果、统计值、来源元数据）与 `data` 章节已渲染的 HTML，抽取全部数值并归一化（去千分位、去单位、保留必要小数位），形成允许集合；
2. **抽取待审数值**：只针对“敏感定量表述”抽取，即带单位或指标语义的数字，包括百分比（`%`）、`g/kg`、`mg/kg`、`kg/亩`、`cm`、`元`/`万元`、以及“提升/增产/增幅/效益 + 数字”的组合。叙述性的年份区间（如“分三个阶段实施”）本身不作为违规，除非同句出现预测性动词；
3. **判定与处理**：能在白名单中找到对应值的数值放行；找不到的数值进入问题清单，并将其在原句中的数值表达替换为“暂无可靠估计”，报告 `status` 置为 `degraded`，`issues` 使用稳定代码 `UNGROUNDED_QUANTITATIVE_CLAIM` 并携带章节标题与原始片段。

不采用“让另一个模型检查第一个模型输出”的方案：成本高、结果不可复现，也无法给出机器可验证的通过条件。

### 5. 审计结果必须随报告一起返回

报告结果新增审计信息，结构固定：

```json
{
  "status": "degraded",
  "audit": {
    "checked_claims": 12,
    "grounded_claims": 10,
    "issues": [
      {
        "code": "UNGROUNDED_QUANTITATIVE_CLAIM",
        "section": "结论与建议",
        "claim": "38.6%",
        "message": "该数值未出现在报告输入中，已按暂无可靠估计处理"
      }
    ]
  }
}
```

这样调用方无需解析 HTML 即可判断报告是否只在引用输入事实。

### 6. 标注脚本幂等且可回滚

`scripts/annotate_soil_indicator_provenance.py`：

- 默认只读，输出字段级判定结果与将被写入的标记；
- `--apply` 才写入 `provenance`；
- 重复运行不改变已有标记（已标记字段跳过）；
- `--revert` 按脚本写入的标记清单移除来源标记，不触碰其他字段；
- 写入前打印汇总（字段、不同取值数、最高频占比、将被标记的地块数）。

### 7. 报告披露被回填输入

报告“数据来源与计算依据”小节新增一行，列出被回填的输入字段及其来源类型，使报告读者能直接看到哪些输入不是地块实测值。该行由上下文的来源信息驱动，不由语言模型生成。

## Risks / Trade-offs

- [既有数据未标注] → 在标注脚本运行前，所有字段都视为“来源未知”，模型守卫按保守策略处理：只有明确标记为 `region_mean_backfill` 或 `default` 的字段才算回填。为覆盖既有数据，脚本需先以 dry-run 输出待标注清单并人工确认后 `--apply`。
- [审计误报] → 白名单只覆盖输入侧数值，章节约叙述性内容可能包含无法匹配的表述。采用“敏感模式”收敛范围，并把处理方式限定为替换为“暂无可靠估计”，不删除整段文字。
- [审计漏报] → 语言模型可能用文字描述数字（如“提升三成”）。当前版本不覆盖中文数字表述，作为已知限制记录在非目标之外的遗留项中。
- [状态变化影响调用方] → 报告 `status` 由 `ok` 变为 `degraded` 属于可见变更，需在接口文档与本次 change 的 tasks 中记录兼容说明。

## Migration and Rollback

1. 部署代码后，报告与新守卫立即生效（未标注数据按保守策略处理）。
2. 运行标注脚本 dry-run，确认常量字段清单与业务预期一致。
3. `--apply` 写入来源标记；如需回退，运行 `--revert` 移除标记。
4. 回填数据的数值修复不在本次范围，待新的实测数据源到位后另行提案。

## Open Questions

- 交换性氢、交换性铝、全氮的地块级数据来源尚未确定（现有三普数据为脱敏点，且没有地块编号）。
- **已发现字段名不一致**：`ParcelDataAccessor` 的 model-5 映射把 `TN` 取自 `total_nitrogen`（当前库中仅 3 个 P-VERIFY 地块有值），而 `link_soil_indicators.py` 回填的是 `total_n`（5491 个地块全部有值）。实测结果是：5488 个正式地块在 DB 路径上 TN 缺失，Model-5 返回 `MODEL5_INPUT_MISSING` 而不是 `MODEL5_INPUT_IMPUTED`——**回填值目前根本没有进入 RF 输入**。本次只把来源映射对齐到实际取数字段并加了漂移测试；是否把取数字段改为 `total_n`（届时那 5488 个地块会得到基于常量 TN 的预测，并被 `MODEL5_INPUT_IMPUTED` 拦住）需要单独决策。
- 是否需要把中文数字表述（“提升三成”）纳入审计范围，待前端与业务反馈。
- 报告 `degraded` 状态在前端的具体展示方式需要与前端确认。
- Model-4 是否也应像 Model-5 一样在回填输入下置空用量。
