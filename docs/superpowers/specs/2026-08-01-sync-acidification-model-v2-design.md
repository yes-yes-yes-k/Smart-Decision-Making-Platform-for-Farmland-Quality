---
comet_change: sync-acidification-model-v2
role: technical-design
canonical_spec: openspec
---

# Design Doc: sync-acidification-model-v2

## 1. 上下文与目标

### 1.1 背景

酸化模型（model-4）在 `replace-acidification-with-process-model`（已归档 2026-07-31）中替换为基于过程的酸化模型（4 子模型：paddy/upland × urea/compound），`MODEL_VERSION = process_v1_20260801`。

模型作者于 2026-08-01 发布 v2 源码。经三方对比（v2 docx / v2 源码 / 项目实现），4 子模型核心数学公式、默认参数、系数完全一致；v2 新增 `run_csv` 批量函数、393 地块测试数据、原理文档（含笔误）。

### 1.2 目标

1. `MODEL_VERSION` 升级为 `process_v2_20260801`，同步版本引用
2. 新增 `run_csv` 批量 CSV 计算函数（内部）+ CLI 脚本（`scripts/run_acidification_batch.py`）
3. 用 v2 的 393 个地块数据新增回归测试
4. 修订 spec 反映批量工具能力（不作为 API 端点）

### 1.3 非目标

- 不修改 4 子模型核心数学公式
- 不改变现有 HTTP API 接口
- 不通过 HTTP API 暴露 `run_csv`
- 不修改其他模型（model-3/5/6/7）

## 2. 详细实现设计

### 2.1 子模型函数重构（方案 A）

**核心变更**：修改 `_finalize` 和 4 个子模型函数，返回完整 7 字段 dict。

#### `_finalize` 签名扩展

```python
def _finalize(pHstart, Hex, Alex, pHtarget, Adep, Acrop, ANcy, Aagri,
              ytk_coef, mbnt_a, mbnt_b) -> Dict[str, float]:
    """计算 Aback 与 YTK/MBNT，返回完整 7 字段 dict。"""
    Aback = (6.25 * (10 ** (9 - pHstart))
             - 6.25 * (10 ** (9 - pHtarget))
             + 2.5 * Hex * 1e7
             + 2.5 * Alex * 1e7) / 1000.0
    ytk = (Aback + 0.8 * Aagri) / 17.042 * ytk_coef
    mbnt = mbnt_a * Aagri / 1.89 + Alex * 590 * 15 * mbnt_b
    return {"Adep": Adep, "Acrop": Acrop, "ANcy": ANcy,
            "Aagri": Aagri, "Aback": Aback, "ytk": ytk, "mbnt": mbnt}
```

#### 子模型函数适配（以 `_paddy_urea` 为例）

```python
def _paddy_urea(pHstart, Hex, Alex, p):
    Adep = _adep(p["RPH"], p["R"])
    Acrop = _hcrop(p["Y"], p["S"], p)
    Anit = 2.221 * math.exp(0.0048 * (p["FertN"] + p["Ndep"])) * 1000 / 14
    Ano3_runoff = (p["Ndep"] - (0.16 * p["Ndep"] + 2.97)) * 1000 / 14 * 2
    Ano3_crop = 0.0
    Avol = (p["Ndep"] - (0.16 * p["Ndep"] + 2.97)) * 1000 / 14 * 2
    ANcy = Anit + Ano3_runoff + Ano3_crop + Avol
    Aagri = Adep + Acrop + ANcy
    return _finalize(pHstart, Hex, Alex, p["pHtarget"], Adep, Acrop, ANcy, Aagri,
                     ytk_coef=0.6, mbnt_a=0.1, mbnt_b=1.0)
```

4 个子模型函数均按此模式适配，传入 `Adep/Acrop/ANcy/Aagri` 给 `_finalize`。

#### `calculate_acidification_amendment` 适配

```python
out = sub_fn(float(pHstart), float(Hex), float(Alex), base)
result: Dict[str, Any] = {
    "status": "success",
    "ytk": out["ytk"],       # 从 7 字段 dict 取 ytk
    "mbnt": out["mbnt"],     # 从 7 字段 dict 取 mbnt
    "sub_model": sub_fn.__name__.lstrip("_"),
    ...
}
```

对外 API 输出结构不变（仍只暴露 `ytk/mbnt`，不暴露中间变量）。

### 2.2 参数组装逻辑复用

提取 `_build_params` 内部函数：

```python
def _build_params(land_type: str, fertilizer_type: str) -> Dict[str, float]:
    """组装默认参数（不含可配覆盖）。"""
    base: Dict[str, float] = dict(_UPLAND_DEFAULTS) if land_type == "upland" else dict(_PADDY_DEFAULTS)
    if fertilizer_type == "compound":
        base.update(_UPLAND_COMPOUND_EXTRA if land_type == "upland" else _PADDY_COMPOUND_EXTRA)
    return base
```

- `calculate_acidification_amendment` 调用 `_build_params` 后，再应用可配参数覆盖
- `run_csv` 调用 `_build_params`，不应用可配参数覆盖（与 v2 源码一致）

### 2.3 `run_csv` 函数实现

```python
def run_csv(input_file: str, output_file: str,
            land_type: str, fertilizer_type: str) -> "pd.DataFrame":
    """批量 CSV 计算：读 CSV → 4 子模型批量计算 → 输出 CSV。

    与 v2 源码 02_酸化模型计算.py 语义一致：
    - 输入 CSV 需包含 SJD（或 pH）、Hex、Alex 列
    - 输出 CSV 含输入列 + 中间变量列（Adep/Acrop/ANcy/Aagri/Aback）+ 结果列（YTK/MBNT）
    - NaN 行输出 7 个 None
    - 不做越界校验（仅单次入口 calculate_acidification_amendment 做）
    """
    if land_type not in ("paddy", "upland") or fertilizer_type not in ("urea", "compound"):
        raise ValueError("土地类型只能为水田或旱地，肥料类型只能为尿素或复合肥")

    df = pd.read_csv(input_file, encoding="utf-8-sig")
    p_col = "SJD" if "SJD" in df else "pH"
    if not {p_col, "Hex", "Alex"} <= set(df):
        raise ValueError("CSV必须包含pH或SJD、Hex、Alex列")

    sub_fn = _SUB_MODEL_MAP[(land_type, fertilizer_type)]
    params = _build_params(land_type, fertilizer_type)
    cols = ["Adep", "Acrop", "ANcy", "Aagri", "Aback", "YTK", "MBNT"]

    def _compute_row(v):
        if pd.isna(v).any():
            return [None] * 7
        out = sub_fn(*map(float, v), params)
        return [round(out["Adep"], 2), round(out["Acrop"], 2), round(out["ANcy"], 2),
                round(out["Aagri"], 2), round(out["Aback"], 2),
                round(out["ytk"], 2), round(out["mbnt"], 2)]

    df[cols] = [_compute_row(v) for v in df[[p_col, "Hex", "Alex"]].to_numpy()]
    df.to_csv(output_file, index=False, encoding="utf-8-sig")
    return df
```

**关键设计点**：
- 列名兼容 `SJD` 或 `pH`（与 v2 源码一致）
- NaN 行输出 7 个 None（与 v2 源码一致）
- 结果保留 2 位小数（`round(x, 2)`，与 v2 源码一致）
- 输出编码 `utf-8-sig`（与 v2 源码一致）
- 不做越界校验（D4 决策）

### 2.4 CLI 脚本实现

`scripts/run_acidification_batch.py`：

```python
"""批量酸化模型 CSV 计算工具（CLI）。

用法：
    python scripts/run_acidification_batch.py --input <input.csv> --output <output.csv> \
        --land <paddy|upland> --fertilizer <urea|compound>

注意：run_csv 不做输入数据越界校验，请自行检查输入数据质量。
"""
import argparse
import sys
from ai_culti_demo.farmland_diagnosis.acidification import run_csv


def main():
    parser = argparse.ArgumentParser(description="酸化模型批量 CSV 计算工具")
    parser.add_argument("--input", required=True, help="输入 CSV 路径（需含 SJD/pH、Hex、Alex 列）")
    parser.add_argument("--output", required=True, help="输出 CSV 路径")
    parser.add_argument("--land", required=True, choices=["paddy", "upland"], help="土地类型")
    parser.add_argument("--fertilizer", required=True, choices=["urea", "compound"], help="肥料类型")
    args = parser.parse_args()

    try:
        df = run_csv(args.input, args.output, args.land, args.fertilizer)
        print(f"批量计算完成：共处理 {len(df)} 行，输出写入 {args.output}")
    except ValueError as e:
        print(f"错误：{e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
```

### 2.5 版本标识升级

3 处改动：
1. `src/ai_culti_demo/farmland_diagnosis/acidification.py`：`MODEL_VERSION = "process_v2_20260801"`
2. `framework/domain/other_models/model_4.py`：3 处 fallback 返回值的 `model_version` 字段（model_unavailable × 1 + cannot_get_ph × 1 + 末尾默认 × 1，共 3 处 `"process_v1_20260801"` → `"process_v2_20260801"`）
3. docstring 源码路径引用更新

## 3. 测试策略

### 3.1 393 地块回归测试

`tests/test_model4_acidification.py` 新增：

```python
import pandas as pd
import pandas.testing as pdt

V2_DATA_DIR = os.path.join(os.path.dirname(__file__), "data", "acidification_v2")


def test_acidification_v2_regression():
    """v2 源码 393 地块回归测试（旱地+复合肥场景）。"""
    from ai_culti_demo.farmland_diagnosis.acidification import run_csv

    input_csv = os.path.join(V2_DATA_DIR, "03_Data.csv")
    expected_csv = os.path.join(V2_DATA_DIR, "04_upland_compound_expected.csv")
    output_csv = os.path.join(V2_DATA_DIR, "_test_output.csv")

    df = run_csv(input_csv, output_csv, "upland", "compound")
    expected = pd.read_csv(expected_csv, encoding="utf-8-sig")

    # 对比 YTK/MBNT（允许浮点误差 < 0.01）
    for col in ["YTK", "MBNT"]:
        actual = df[col].astype(float)
        exp = expected[col].astype(float)
        assert (actual - exp).abs().max() < 0.01, (
            f"{col} 不一致：最大偏差 {(actual - exp).abs().max()}，"
            f"首行 actual={actual.iloc[0]} expected={exp.iloc[0]}"
        )
```

**覆盖范围**：
- 393 地块全量对比 YTK/MBNT
- 极端值（Alex=8.95、SJD=4.19、Hex=1.62）通过全量对比自动覆盖
- 中间变量（Adep/Acrop 等）可选验证（测试默认仅验证 YTK/MBNT）

### 3.2 现有测试更新

- `test_model_version_present`：断言 `process_v2_20260801`
- `test_model4_execution_direct_inputs`：`model_version` 断言 `process_v2_20260801`
- 其他测试逻辑不变（子模型重构不影响 `calculate_acidification_amendment` 返回的 ytk/mbnt）

## 4. 技术风险与缓解

| 风险 | 缓解 |
|------|------|
| 重构 `_finalize` 签名可能影响其他调用方 | 全局搜索确认 `_finalize` 仅在 4 个子模型函数内调用，无外部调用 |
| 393 地块测试数据增加测试耗时 | 393 行计算在毫秒级，可接受 |
| `run_csv` 越界值不校验 | CLI 文档提示；单次 API 入口仍做校验 |
| v2 docx 笔误误导 | docstring 注明"以源码为准" |
| `MODEL_VERSION` 升级影响下游 | model_version 仅作元数据返回，无逻辑依赖 |

## 5. 实现顺序建议

1. **子模型函数重构**（2.1）—— 先改 `_finalize` 和 4 个子模型，运行现有测试确认无回归
2. **参数组装提取**（2.2）—— 提取 `_build_params`，`calculate_acidification_amendment` 复用
3. **版本标识升级**（2.5）—— 更新 `MODEL_VERSION` 和 model_4.py，更新现有测试断言
4. **run_csv 实现**（2.3）—— 新增函数
5. **CLI 脚本**（2.4）—— 新增脚本
6. **测试数据准备**（tasks.md §4）—— 复制 v2 数据到 tests/data/
7. **回归测试**（3.1）—— 新增 v2 回归测试
8. **集成验证**（tasks.md §8）—— CLI + 测试套件
