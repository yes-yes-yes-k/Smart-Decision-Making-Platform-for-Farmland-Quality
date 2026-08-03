## Context

酸化模型（model-4）在 `replace-acidification-with-process-model`（已归档 2026-07-31）中从规则式石灰施用量计算替换为基于过程的酸化模型（4 子模型：paddy/upland × urea/compound），输入 pH(SJD)+交换性氢(JHX)+交换性铝(JLA)，输出 YTK/MBNT(kg/ha)，`MODEL_VERSION = process_v1_20260801`。

模型作者于 2026-08-01 发布 v2 源码（`D:\destkop\模型\模型5_酸化模型_v2_20260801`）。经逐行三方对比（v2 docx 原理文档 / v2 源码 02_酸化模型计算.py / 项目实现 acidification.py）：

- **4 子模型数学公式、默认参数、系数完全一致**（paddy_urea/paddy_compound/upland_urea/upland_compound 的 Anit/Ano3_runoff/Ano3_crop/Avol/Aback/YTK/MBNT 公式逐行相同）
- v2 新增 `run_csv(input_file, output_file, land, fertilizer)` 批量计算函数（项目未实现）
- v2 提供 393 个地块测试数据（含极端值 Alex=8.95、SJD=4.19）
- v2 docx 原理文档有 3 处笔误（Aback 公式 9-SJD 减 9-SJD 应为 9-pHtarget；复合肥 Ano3_runoff 漏写 FertN 部分和 0.3 系数；复合肥 Sp/Smg 默认值 0.18%/0.21% 与源码 0.176%/0.212% 不一致），以 v2 源码为准

当前项目 spec 明确"按需计算模式下不再需要批量评估"（`evaluate_acidification` 已 deprecated），但用户希望引入批量 CSV 计算工具用于离线分析场景，同时不暴露为 HTTP API。

## Goals / Non-Goals

**Goals:**
- 将 `MODEL_VERSION` 升级为 `process_v2_20260801`，同步版本引用
- 新增 `run_csv` 批量 CSV 计算函数（内部）+ CLI 脚本（`scripts/run_acidification_batch.py`）
- 用 v2 的 393 个地块数据新增回归测试，验证极端值场景下的正确性
- 修订 spec 反映批量工具能力（不作为 API 端点）

**Non-Goals:**
- 不修改 4 子模型核心数学公式（已与 v2 一致）
- 不改变现有 HTTP API 接口（SJD/JHX/JLA → YTK/MBNT）
- 不通过 HTTP API 暴露 run_csv（仅内部函数 + CLI）
- 不暴露中间变量（Adep/Acrop/ANcy/Aagri/Aback）到标准 API 输出（仅在 run_csv 的 CSV 输出中包含）
- 不修改其他模型（model-3/5/6/7）

## Decisions

### D1: run_csv 实现位置与签名

**决策**：在 `src/ai_culti_demo/farmland_diagnosis/acidification.py` 新增 `run_csv` 函数，签名与 v2 源码一致：

```python
def run_csv(input_file: str, output_file: str, land_type: str, fertilizer_type: str) -> pd.DataFrame:
    """批量 CSV 计算：读 CSV → 4 子模型批量计算 → 输出 CSV。"""
```

**理由**：与 v2 源码语义一致，便于对照验证；放在 acidification.py 与 `calculate_acidification_amendment` 同模块，内聚性强。

**替代方案**：放在 `scripts/` 下作为独立工具脚本。否决，因为 scripts 应只做 CLI 封装，核心逻辑应在 domain 层。

### D2: run_csv 输出列设计

**决策**：输出 CSV 包含输入列（TYBH/SJD/Hex/Alex）+ 中间变量列（Adep/Acrop/ANcy/Aagri/Aback）+ 结果列（YTK/MBNT），与 v2 源码 04 csv 输出格式一致。

**理由**：与 v2 源码完全对齐，便于回归测试直接对比；中间变量对离线分析有价值。

**权衡**：这与 spec "不暴露中间产酸量分解" 略有张力，但 spec 原意是 API 输出不暴露，run_csv 是离线工具，可在 CSV 中包含。spec 会明确区分"API 输出"与"批量工具 CSV 输出"。

### D3: 缺失值处理策略

**决策**：与 v2 源码一致，对含 NaN 的行输出 7 个 None（Adep/Acrop/ANcy/Aagri/Aback/YTK/MBNT 全为空），不抛异常。

**理由**：v2 源码 `run_csv` 第 82 行 `[[None]*7 if pd.isna(v).any() else ...]` 即此行为；保持一致以通过回归测试。

### D4: 越界值处理策略

**决策**：`run_csv` 不做越界校验（[3.0, 10.0] 等），直接计算。越界校验仅在 `calculate_acidification_amendment` 单次入口生效。

**理由**：v2 源码 `run_csv` 不做越界校验，直接调用子模型函数；393 地块数据含 SJD=4.19（低于 3.0？不，4.19 > 3.0）等值，均能正常计算。回归测试需要与 v2 输出完全一致，故 run_csv 不加额外校验。

**权衡**：若用户通过 run_csv 处理含越界值的 CSV，不会被告知。但 run_csv 是离线工具，用户应自行检查输入数据质量。CLI 脚本会在文档中提示。

### D5: CLI 脚本设计

**决策**：`scripts/run_acidification_batch.py` 使用 argparse，参数：
- `--input`（必填）：输入 CSV 路径
- `--output`（必填）：输出 CSV 路径
- `--land`（必填）：paddy | upland
- `--fertilizer`（必填）：urea | compound

**理由**：与 v2 源码 `run_csv` 的 land/fertilizer 参数对齐；必填避免默认值歧义。

### D6: 回归测试数据放置

**决策**：v2 测试数据复制到 `tests/data/acidification_v2/`：
- `03_Data.csv`（393 地块输入）
- `04_upland_compound_expected.csv`（期望输出，旱地+复合肥场景）

**理由**：测试应自包含，不依赖外部路径 `D:\destkop\...`；复制到 tests/data/ 保证可移植性。

### D7: 回归测试覆盖范围

**决策**：回归测试 `test_acidification_v2_regression` 验证 393 地块在旱地+复合肥场景下与 04 csv 期望值偏差 < 0.01。其他 3 种 land/fertilizer 组合通过现有 `test_four_submodels_calculation` 已覆盖（单点验证），不重复全量 393 地块测试。

**理由**：v2 仅提供旱地+复合肥的期望输出 CSV（04 csv）；其他组合无期望值，无法做全量回归。单点验证（pHstart=4.31, Hex=1.56, Alex=4.08）已覆盖 4 组合的正确性。

## Risks / Trade-offs

- **[风险] run_csv 与 spec "不暴露中间变量" 的张力** → 缓解：spec 明确区分"API 输出（不暴露中间变量）"与"批量工具 CSV 输出（含中间变量）"；run_csv 不通过 API 暴露，仅离线使用
- **[风险] 越界值在 run_csv 中不校验** → 缓解：CLI 脚本文档提示用户自行检查输入数据质量；单次 API 入口 `calculate_acidification_amendment` 仍做越界校验
- **[风险] v2 docx 原理文档笔误误导** → 缓解：以 v2 源码为单一事实源，docstring 注明"原理文档有笔误，以源码为准"
- **[风险] 393 地块测试数据增加测试耗时** → 缓解：393 行计算在毫秒级，可接受；若未来扩展可改用参数化抽样
- **[权衡] MODEL_VERSION 升级可能影响依赖版本号的下游** → 评估：model_version 仅作为元数据返回，不参与逻辑判断；acidification_agent 透传该字段，无硬编码依赖 `process_v1`
