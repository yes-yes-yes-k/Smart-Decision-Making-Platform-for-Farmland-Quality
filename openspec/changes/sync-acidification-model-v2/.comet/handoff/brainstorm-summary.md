# Brainstorm Summary

- Change: sync-acidification-model-v2
- Date: 2026-08-01

## 确认的技术方案

### 核心方案：方案 A —— 重构子模型函数返回 7 值

修改 4 个子模型函数（`_paddy_urea`/`_paddy_compound`/`_upland_urea`/`_upland_compound`）和 `_finalize`，使其返回完整 7 字段 dict：`{Adep, Acrop, ANcy, Aagri, Aback, ytk, mbnt}`。

- `_finalize` 签名扩展为接收 `Adep/Acrop/ANcy/Aagri` 并返回 7 字段 dict
- `calculate_acidification_amendment` 从子模型返回值中取 `ytk/mbnt`（向后兼容，不破坏现有 API 输出结构）
- `run_csv` 取全部 7 个值用于 CSV 输出

### 参数组装逻辑复用

提取 `_build_params(land_type, fertilizer_type) -> dict` 内部函数：
- `calculate_acidification_amendment` 和 `run_csv` 都调用它
- `run_csv` 不支持可配参数覆盖（与 v2 源码一致，只用默认参数）
- `calculate_acidification_amendment` 保留可配参数覆盖逻辑

### 边界条件对齐

- `run_csv` 用英文 key（`paddy`/`upland`/`urea`/`compound`），与项目 `calculate_acidification_amendment` 一致
- 不沿用 v2 源码中文 key（`水田`/`旱地`）
- `land_type`/`fertilizer_type` 校验抛 `ValueError`，错误信息与 v2 源码一致（"土地类型只能为水田或旱地，肥料类型只能为尿素或复合肥"）
- `run_csv` 不做越界校验（D4 决策），仅 `calculate_acidification_amendment` 单次入口做

## 关键取舍与风险

- **重构现有子模型函数签名**：方案 A 改变 `_paddy_urea` 等函数返回值结构 → 缓解：`calculate_acidification_amendment` 内部适配，对外 API 输出不变；现有测试 `test_four_submodels_calculation` 等通过 `calculate_acidification_amendment` 调用，不直接断言子模型返回值结构
- **run_csv 与 spec"不暴露中间变量"的张力** → 缓解：spec 明确区分"API 输出（不暴露）"与"批量工具 CSV 输出（含中间变量）"；run_csv 不通过 API 暴露
- **越界值在 run_csv 中不校验** → 缓解：CLI 脚本文档提示用户自行检查输入数据质量
- **v2 docx 原理文档笔误** → 缓解：以 v2 源码为单一事实源，docstring 注明"原理文档有笔误，以源码为准"

## 测试策略

### 393 地块回归测试

- 用 pandas 读取 `run_csv` 输出和 `04_upland_compound_expected.csv`
- `pd.testing.assert_frame_equal` 对比 YTK/MBNT 列，`check_exact=False, atol=0.01`
- 失败时打印首个不一致行的实际值 vs 期望值
- 极端值（Alex=8.95、SJD=4.19、Hex=1.62）通过全量对比自动覆盖

### 现有测试更新

- `test_model_version_present` 断言更新为 `process_v2_20260801`
- `test_model4_execution_direct_inputs` 的 `model_version` 断言更新
- 其他测试逻辑不变（子模型重构不影响 `calculate_acidification_amendment` 返回的 ytk/mbnt）

## Spec Patch

无。delta spec 现有 12 个 scenario 已足够覆盖。`run_csv` 输出 CSV 的编码（`utf-8-sig`）和小数位数（`round(x,2)`）属于实现细节，不强制在 spec 中体现。
