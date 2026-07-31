---
change: add-shaoguan-fertility-model
design-doc: docs/superpowers/specs/2026-07-31-add-shaoguan-fertility-model-design.md
base-ref: 8e0dbc8a01730495c0a1d0e21165e0346ce775c5
---

# 韶关区域肥力 Dose RF 模型集成 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不破坏现有全局 ETR 模型行为的前提下，为韶关区域（area_code="lechang"）接入按旱地/水田分别训练的 RandomForestRegressor Dose 预测模型，SOC 仍回退全局 ETR。

**Architecture:** 训练脚本扩展 `--sg` 子命令读取预切分 xlsx（SOMbe→SOCbe 重命名）训练 RF 模型并保存 .joblib+metadata.json；`model_6_execution` 新增 `land_type` 参数与 `SHAOGUAN_AREA_CODES` 路由——命中韶关时 Dose 走 SG RF（按 land_type 选子模型）、SOC 始终走全局 ETR，未命中则行为完全不变；`FertilityMLAgent` 与 `nodes.execute_models` 透传 `area_code`/`land_type`。

**Tech Stack:** Python 3.12、scikit-learn（RandomForestRegressor/ExtraTreesRegressor）、pandas、joblib、pytest、Flask、LangGraph。

## Global Constraints

- 训练超参固定为 `RandomForestRegressor(n_estimators=100, random_state=230)`，不重跑网格搜索。
- SG 模型文件路径固定：`data/fertility/models/sg_dose_upland_rf_model.joblib` + `sg_dose_upland_metadata.json`（paddy 同理）。
- 特征名 `SOMbe` 必须在训练与推理两侧统一映射为 `SOCbe`。
- 韶关区域集合 `SHAOGUAN_AREA_CODES = {"lechang"}`，`area_code` 判定前 `.lower()`。
- `land_type` 仅 "upland"/"paddy" 合法，非法值默认 upland 并附 dose_warning 提示。
- 现有非韶关调用方行为必须保持不变（不传 `area_code`/`land_type` 时走全局 ETR、默认 upland）。
- SG 模型惰性加载复用现有 `_LOAD_LOCK` double-checked locking 模式；模型文件缺失时返回 `fallback_reason="model_file_missing"`。
- 测试用 monkeypatch mock 模型对象，CI 零依赖真实 .joblib；集成测试通过 `skipif` 在模型不可用时跳过。
- 项目根目录为 `d:\17417\Documents\agent_culti_demo`，所有命令在该目录运行。

---

## 文件结构

| 文件 | 职责 | 操作 |
|------|------|------|
| `data/fertility/SG旱地-Dose-RF_Manual_splits.xlsx` | 韶关旱地预切分训练数据 | 新增（复制） |
| `data/fertility/SG水田-Dose-RF_Manual_splits.xlsx` | 韶关水田预切分训练数据 | 新增（复制） |
| `scripts/train_fertility_models.py` | 训练脚本：全局 ETR + SG RF | 修改 |
| `data/fertility/models/sg_dose_upland_rf_model.joblib` | 韶关旱地 RF 模型 | 新增（训练产出） |
| `data/fertility/models/sg_dose_upland_metadata.json` | 韶关旱地模型元数据 | 新增（训练产出） |
| `data/fertility/models/sg_dose_paddy_rf_model.joblib` | 韶关水田 RF 模型 | 新增（训练产出） |
| `data/fertility/models/sg_dose_paddy_metadata.json` | 韶关水田模型元数据 | 新增（训练产出） |
| `framework/domain/other_models/model_6.py` | model_6_execution 主入口 + 区域路由 | 修改 |
| `framework/agents/specialized/fertility_ml_agent.py` | FertilityMLAgent 适配 | 修改 |
| `framework/agents/nodes.py` | execute_models 节点透传 land_type | 修改 |
| `tests/test_fertility_ml_prediction.py` | model_6 单元/集成测试 | 修改 |
| `tests/test_agent_specialized.py` | FertilityMLAgent 透传测试 | 修改 |

---

### Task 1: SG 训练数据准备

**Files:**
- Create: `data/fertility/SG旱地-Dose-RF_Manual_splits.xlsx`（从源目录复制）
- Create: `data/fertility/SG水田-Dose-RF_Manual_splits.xlsx`（从源目录复制）

**Interfaces:**
- Consumes: 源文件 `D:\destkop\SG-旱地和水田-Dose预测模型\SG-旱地和水田-Dose预测模型\SG旱地-Dose-RF_Manual_splits.xlsx` 与 `SG水田-Dose-RF_Manual_splits.xlsx`
- Produces: `data/fertility/` 下两个 xlsx，供 Task 2/3 训练脚本读取

- [ ] **Step 1: 复制韶关旱地数据**

```powershell
Copy-Item "D:\destkop\SG-旱地和水田-Dose预测模型\SG-旱地和水田-Dose预测模型\SG旱地-Dose-RF_Manual_splits.xlsx" "d:\17417\Documents\agent_culti_demo\data\fertility\SG旱地-Dose-RF_Manual_splits.xlsx" -Force
```

- [ ] **Step 2: 复制韶关水田数据**

```powershell
Copy-Item "D:\destkop\SG-旱地和水田-Dose预测模型\SG-旱地和水田-Dose预测模型\SG水田-Dose-RF_Manual_splits.xlsx" "d:\17417\Documents\agent_culti_demo\data\fertility\SG水田-Dose-RF_Manual_splits.xlsx" -Force
```

- [ ] **Step 3: 验证文件存在与大小**

```powershell
Get-ChildItem "d:\17417\Documents\agent_culti_demo\data\fertility\SG*.xlsx" | Select-Object Name, Length
```

预期：两个文件均存在，旱地 ~20924 字节、水田 ~138812 字节。

- [ ] **Step 4: 验证 xlsx sheet 结构与特征列**

```powershell
python -c "import pandas as pd; xl=pd.ExcelFile(r'data\fertility\SG旱地-Dose-RF_Manual_splits.xlsx'); print('旱地 sheets:', xl.sheet_names); df=pd.read_excel(xl, sheet_name=xl.sheet_names[0]); print('旱地 Xtrain 列:', list(df.columns)); print('旱地 Xtrain 样本数:', len(df))"
python -c "import pandas as pd; xl=pd.ExcelFile(r'data\fertility\SG水田-Dose-RF_Manual_splits.xlsx'); print('水田 sheets:', xl.sheet_names); df=pd.read_excel(xl, sheet_name=xl.sheet_names[0]); print('水田 Xtrain 列:', list(df.columns)); print('水田 Xtrain 样本数:', len(df))"
```

预期：两个 xlsx 均含 Xtrain/Xtest/Ytrain/Ytest 四个 sheet（容错大小写/空格）；特征列含 `pH, SOMbe, TN, TP, TK, AP, AK, Gap, Fertilizer type`（9 个，无 Dose 自身）；旱地 Xtrain 样本数 ~185，水田样本数记录待确认（若水田 <30 则后续 Task 5 需触发低置信度提示）。

- [ ] **Step 5: 提交**

```bash
git add "data/fertility/SG旱地-Dose-RF_Manual_splits.xlsx" "data/fertility/SG水田-Dose-RF_Manual_splits.xlsx"
git commit -m "feat(fertility): 添加韶关旱地/水田 Dose RF 预切分训练数据"
```

---

### Task 2: 扩展训练脚本支持 SG RF 模型

**Files:**
- Modify: `scripts/train_fertility_models.py`
- Test: `tests/test_train_fertility_sg.py`（新建）

**Interfaces:**
- Consumes: Task 1 产出的 `data/fertility/SG旱地-Dose-RF_Manual_splits.xlsx` 与 `SG水田-Dose-RF_Manual_splits.xlsx`
- Produces:
  - `train_sg_dose_model(land_type: str, xlsx_path: Path, output_dir: Path) -> dict`：训练单个 SG RF 模型并保存 .joblib+metadata.json，返回 metadata
  - `train_all_sg_models(data_dir: Path, output_dir: Path) -> list[dict]`：训练旱地+水田
  - CLI 参数 `--sg`（仅 SG）、`--all`（全局+SG）；不传参时仅全局 ETR（行为不变）

- [ ] **Step 1: 写失败测试 — train_sg_dose_model 函数存在且能处理 SOMbe→SOCbe**

新建 `tests/test_train_fertility_sg.py`：

```python
"""测试 SG RF Dose 训练函数。

用 pandas 构造临时 xlsx，端到端验证 train_sg_dose_model 的 SOMbe→SOCbe 重命名、
模型保存与 metadata 完整性。sklearn 不可用时整体跳过。
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
from pathlib import Path

import pytest

pd = pytest.importorskip("pandas")
sklearn = pytest.importorskip("sklearn")
joblib = pytest.importorskip("joblib")


def _make_sg_xlsx(path: Path, feature_cols: list[str], n_train: int = 40, n_test: int = 10):
    """构造含 Xtrain/Xtest/Ytrain/Ytest 四 sheet 的临时 xlsx。"""
    import numpy as np
    rng = np.random.RandomState(230)
    Xtrain = pd.DataFrame(rng.rand(n_train, len(feature_cols)), columns=feature_cols)
    Xtest = pd.DataFrame(rng.rand(n_test, len(feature_cols)), columns=feature_cols)
    Ytrain = pd.DataFrame({"Dose": rng.rand(n_train) * 100})
    Ytest = pd.DataFrame({"Dose": rng.rand(n_test) * 100})
    with pd.ExcelWriter(path) as w:
        Xtrain.to_excel(w, sheet_name="Xtrain", index=False)
        Xtest.to_excel(w, sheet_name="Xtest", index=False)
        Ytrain.to_excel(w, sheet_name="Ytrain", index=False)
        Ytest.to_excel(w, sheet_name="Ytest", index=False)


def test_train_sg_dose_model_renames_sombe_and_saves(tmp_path):
    from scripts.train_fertility_models import train_sg_dose_model

    feature_cols = ["pH", "SOMbe", "TN", "TP", "TK", "AP", "AK", "Gap", "Fertilizer type"]
    xlsx = tmp_path / "sg_test.xlsx"
    _make_sg_xlsx(xlsx, feature_cols)

    meta = train_sg_dose_model("upland", xlsx, tmp_path)

    # SOMbe 应被重命名为 SOCbe
    assert "SOMbe" not in meta["feature_names"]
    assert "SOCbe" in meta["feature_names"]
    assert len(meta["feature_names"]) == 9

    # 模型文件存在
    assert (tmp_path / "sg_dose_upland_rf_model.joblib").exists()
    assert (tmp_path / "sg_dose_upland_metadata.json").exists()

    # metadata 完整性
    assert meta["model_type"] == "RandomForestRegressor"
    assert "metrics" in meta and "test_r2" in meta["metrics"]
    assert "training_samples" in meta
    assert meta["training_samples"] == 40

    # 模型可加载
    model = joblib.load(tmp_path / "sg_dose_upland_rf_model.joblib")
    assert hasattr(model, "predict")


def test_train_sg_dose_model_paddy_naming(tmp_path):
    from scripts.train_fertility_models import train_sg_dose_model

    xlsx = tmp_path / "sg_paddy_test.xlsx"
    _make_sg_xlsx(xlsx, ["pH", "SOMbe", "TN", "TP", "TK", "AP", "AK", "Gap", "Fertilizer type"])

    meta = train_sg_dose_model("paddy", xlsx, tmp_path)
    assert (tmp_path / "sg_dose_paddy_rf_model.joblib").exists()
    assert (tmp_path / "sg_dose_paddy_metadata.json").exists()
    assert meta["model_type"] == "RandomForestRegressor"
```

- [ ] **Step 2: 运行测试验证失败**

```bash
pytest tests/test_train_fertility_sg.py -v
```

预期：FAIL，`ImportError: cannot import name 'train_sg_dose_model' from 'scripts.train_fertility_models'`。

- [ ] **Step 3: 实现 train_sg_dose_model 与 CLI 扩展**

在 `scripts/train_fertility_models.py` 顶部 import 区新增：

```python
from sklearn.ensemble import RandomForestRegressor
```

在 `MODEL_VERSION = "ETR_v1_20260713"` 下方新增常量：

```python
SG_RF_PARAMS = {"n_estimators": 100, "random_state": 230}
SG_MODEL_VERSION = "SG_RF_v1_20260731"
SG_DOSE_FEATURE_COLS = ["pH", "SOMbe", "TN", "TP", "TK", "AP", "AK", "Gap", "Fertilizer type"]
```

在 `train_one_model` 函数之后新增 `train_sg_dose_model` 与 `train_all_sg_models`：

```python
def train_sg_dose_model(land_type: str, xlsx_path: Path, output_dir: Path) -> dict:
    """训练单个韶关 RF Dose 模型并保存 .joblib + metadata.json。

    - land_type: "upland" 或 "paddy"
    - 读取预切分 xlsx（Xtrain/Xtest/Ytrain/Ytest sheets）
    - 将特征列 SOMbe 重命名为 SOCbe，列名统一 strip
    - 训练 RandomForestRegressor(n_estimators=100, random_state=230)
    - 保存 sg_dose_{land_type}_rf_model.joblib 与 sg_dose_{land_type}_metadata.json
    """
    if land_type not in ("upland", "paddy"):
        raise ValueError(f"land_type 必须是 upland/paddy，收到: {land_type}")

    print(f"\n=== 训练韶关 {land_type} Dose RF 模型 ===")
    Xtrain, Xtest, Ytrain, Ytest = load_manual_splits(xlsx_path)

    # 列名 strip + SOMbe → SOCbe 重命名
    rename_map = {c: c.strip() for c in Xtrain.columns}
    rename_map = {k: ("SOCbe" if v == "SOMbe" else v) for k, v in rename_map.items()}
    Xtrain = Xtrain.rename(columns=rename_map)
    Xtest = Xtest.rename(columns=rename_map)

    print(f"训练集: {Xtrain.shape[0]} 样本, {Xtrain.shape[1]} 特征")
    print(f"测试集: {Xtest.shape[0]} 样本")
    print(f"特征名: {list(Xtrain.columns)}")

    model = RandomForestRegressor(**SG_RF_PARAMS)
    model.fit(Xtrain, Ytrain)

    # 5-fold CV（n_jobs=1 避免 Windows 并行开销，与 train_one_model 一致）
    cv_r2_scores = cross_val_score(
        RandomForestRegressor(**SG_RF_PARAMS), Xtrain, Ytrain, cv=5, scoring="r2"
    )
    cv_r2 = float(np.mean(cv_r2_scores))
    cv_mse_scores = cross_val_score(
        RandomForestRegressor(**SG_RF_PARAMS), Xtrain, Ytrain, cv=5,
        scoring="neg_mean_squared_error",
    )
    cv_rmse = float(np.sqrt(-np.mean(cv_mse_scores)))

    Ypred = model.predict(Xtest)
    test_r2 = float(model.score(Xtest, Ytest))
    test_rmse = float(np.sqrt(mean_squared_error(Ytest, Ypred)))

    print(f"5CV R²: {cv_r2:.4f}, 5CV RMSE: {cv_rmse:.4f}")
    print(f"Test R²: {test_r2:.4f}, Test RMSE: {test_rmse:.4f}")
    print(f"超参数: {SG_RF_PARAMS}")

    model_path = output_dir / f"sg_dose_{land_type}_rf_model.joblib"
    joblib.dump(model, model_path)
    print(f"模型已保存: {model_path}")

    meta = {
        "model_type": "RandomForestRegressor",
        "land_type": land_type,
        "region": "shaoguan",
        "trained_at": datetime.now().isoformat(timespec="seconds"),
        "model_version": SG_MODEL_VERSION,
        "hyperparameters": SG_RF_PARAMS,
        "metrics": {
            "cv_r2": round(cv_r2, 4),
            "cv_rmse": round(cv_rmse, 4),
            "test_r2": round(test_r2, 4),
            "test_rmse": round(test_rmse, 4),
        },
        "feature_names": list(Xtrain.columns),
        "feature_means": {k: float(v) for k, v in Xtrain.mean().items()},
        "training_samples": int(Xtrain.shape[0]),
        "test_samples": int(Xtest.shape[0]),
    }
    meta_path = output_dir / f"sg_dose_{land_type}_metadata.json"
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    print(f"元数据已保存: {meta_path}")

    return meta


def train_all_sg_models(data_dir: Path, output_dir: Path) -> list[dict]:
    """训练韶关旱地 + 水田 Dose RF 模型。"""
    upland_xlsx = data_dir / "SG旱地-Dose-RF_Manual_splits.xlsx"
    paddy_xlsx = data_dir / "SG水田-Dose-RF_Manual_splits.xlsx"
    for xlsx in [upland_xlsx, paddy_xlsx]:
        if not xlsx.exists():
            print(f"错误: 韶关训练数据文件不存在: {xlsx}", file=sys.stderr)
            sys.exit(1)

    metas = [
        train_sg_dose_model("upland", upland_xlsx, output_dir),
        train_sg_dose_model("paddy", paddy_xlsx, output_dir),
    ]
    return metas
```

替换 `main` 函数为支持 `--sg`/`--all` 的版本：

```python
def main():
    parser = argparse.ArgumentParser(description="训练 SOC/Dose ETR 模型与韶关 SG RF Dose 模型")
    parser.add_argument("--data-dir", default="data/fertility", help="训练数据目录")
    parser.add_argument("--output-dir", default="data/fertility/models", help="模型输出目录")
    parser.add_argument("--sg", action="store_true", help="仅训练韶关 RF Dose 模型（旱地+水田）")
    parser.add_argument("--all", action="store_true", help="训练全部（全局 ETR + 韶关 RF）")
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    train_global = not args.sg or args.all
    train_sg = args.sg or args.all

    if train_global:
        # 注意：实际文件名是 ML-data-Dose-RF_Manual_splits.xlsx（RF 和 Manual 之间是下划线 _）
        soc_xlsx = data_dir / "ML-data-SOC-RF_Manual_splits.xlsx"
        dose_xlsx = data_dir / "ML-data-Dose-RF_Manual_splits.xlsx"
        for xlsx in [soc_xlsx, dose_xlsx]:
            if not xlsx.exists():
                print(f"错误: 训练数据文件不存在: {xlsx}", file=sys.stderr)
                sys.exit(1)
        soc_meta = train_one_model("SOC", soc_xlsx, SOC_BEST_PARAMS, output_dir)
        dose_meta = train_one_model("Dose", dose_xlsx, DOSE_BEST_PARAMS, output_dir)
        print("\n=== 全局 ETR 训练完成 ===")
        print(f"SOC test_r2: {soc_meta['metrics']['test_r2']}")
        print(f"Dose test_r2: {dose_meta['metrics']['test_r2']}")

    if train_sg:
        sg_metas = train_all_sg_models(data_dir, output_dir)
        print("\n=== 韶关 RF 训练完成 ===")
        for m in sg_metas:
            print(f"SG {m['land_type']} test_r2: {m['metrics']['test_r2']}, training_samples: {m['training_samples']}")
```

- [ ] **Step 4: 运行测试验证通过**

```bash
pytest tests/test_train_fertility_sg.py -v
```

预期：2 个测试 PASS。

- [ ] **Step 5: 验证 CLI 帮助与默认行为不变**

```bash
python scripts/train_fertility_models.py --help
```

预期：帮助文本显示 `--sg` 和 `--all` 参数；无参数时 `train_global=True, train_sg=False`（仅全局 ETR）。

- [ ] **Step 6: 提交**

```bash
git add scripts/train_fertility_models.py tests/test_train_fertility_sg.py
git commit -m "feat(train): 训练脚本支持 --sg/--all 训练韶关 RF Dose 模型"
```

---

### Task 3: 运行 SG 训练并验证产物

**Files:**
- Create: `data/fertility/models/sg_dose_upland_rf_model.joblib`（训练产出）
- Create: `data/fertility/models/sg_dose_upland_metadata.json`（训练产出）
- Create: `data/fertility/models/sg_dose_paddy_rf_model.joblib`（训练产出）
- Create: `data/fertility/models/sg_dose_paddy_metadata.json`（训练产出）

**Interfaces:**
- Consumes: Task 1 产出的 xlsx + Task 2 的训练函数
- Produces: 4 个模型/元数据文件，供 Task 4/5 的集成测试与 Task 8 验证使用

- [ ] **Step 1: 检查 sklearn 可用性**

```bash
python -c "import sklearn; print('sklearn', sklearn.__version__)"
```

预期：打印版本号（已装）。若失败则需先 `pip install scikit-learn`。

- [ ] **Step 2: 运行 SG 训练**

```bash
python scripts/train_fertility_models.py --sg
```

预期：控制台打印旱地/水田训练集样本数、特征名（含 SOCbe 不含 SOMbe）、5CV R²、Test R²、模型/元数据保存路径。退出码 0。

- [ ] **Step 3: 验证产物文件存在**

```bash
python -c "from pathlib import Path; d=Path('data/fertility/models'); [print(p.name, p.exists(), p.stat().st_size) for p in [d/'sg_dose_upland_rf_model.joblib', d/'sg_dose_upland_metadata.json', d/'sg_dose_paddy_rf_model.joblib', d/'sg_dose_paddy_metadata.json']]"
```

预期：4 个文件均存在，.joblib 文件非空。

- [ ] **Step 4: 验证 metadata.json 内容完整**

```bash
python -c "import json; from pathlib import Path; d=Path('data/fertility/models');
for lt in ['upland','paddy']:
    m=json.loads((d/f'sg_dose_{lt}_metadata.json').read_text(encoding='utf-8'))
    print(f'=== {lt} ==='); print('model_type:', m['model_type']); print('land_type:', m['land_type']); print('region:', m['region']); print('feature_names:', m['feature_names']); print('SOMbe in features:', 'SOMbe' in m['feature_names']); print('SOCbe in features:', 'SOCbe' in m['feature_names']); print('metrics:', m['metrics']); print('training_samples:', m['training_samples']); print('feature_means keys:', list(m['feature_means'].keys()))"
```

预期：model_type=RandomForestRegressor，land_type 对应，region=shaoguan，feature_names 含 SOCbe 不含 SOMbe，metrics 含 test_r2/cv_r2，training_samples 与 Step 2 打印一致。

- [ ] **Step 5: 记录水田样本量决策**

检查 Step 4 输出的水田 `training_samples`。若 <30，记录该事实——Task 5 需在 dose_warning 中追加"训练样本量较少，置信度偏低"提示。若 ≥30 则无需特殊处理。将结论写入提交信息。

- [ ] **Step 6: 提交**

```bash
git add "data/fertility/models/sg_dose_upland_rf_model.joblib" "data/fertility/models/sg_dose_upland_metadata.json" "data/fertility/models/sg_dose_paddy_rf_model.joblib" "data/fertility/models/sg_dose_paddy_metadata.json"
git commit -m "feat(fertility): 训练产出韶关旱地/水田 RF Dose 模型文件"
```

---

### Task 4: model_6.py 区域路由基础设施

**Files:**
- Modify: `framework/domain/other_models/model_6.py`
- Test: `tests/test_fertility_ml_prediction.py`（追加测试类）

**Interfaces:**
- Consumes: 现有 `_LOAD_LOCK`、`_load_model_and_meta`、`_MODELS_DIR`
- Produces:
  - 常量 `SHAOGUAN_AREA_CODES: set[str]`
  - 路径常量 `_SG_UPLAND_MODEL_PATH`/`_SG_UPLAND_META_PATH`/`_SG_PADDY_MODEL_PATH`/`_SG_PADDY_META_PATH`
  - 模块级状态 `_SG_UPLAND_MODEL`/`_SG_PADDY_MODEL`/`_SG_UPLAND_META`/`_SG_PADDY_META`/`_SG_UPLAND_LOAD_FAILED`/`_SG_PADDY_LOAD_FAILED`
  - `_normalize_input(input_data: Dict) -> Dict`：SOMbe→SOCbe + strip + 过滤 None
  - `_ensure_sg_model_loaded(land_type: str) -> bool`：按 land_type 惰性加载 SG 模型

- [ ] **Step 1: 写失败测试 — _normalize_input 与 SG 加载基础设施**

在 `tests/test_fertility_ml_prediction.py` 末尾追加：

```python
# ---- Task 4: 区域路由基础设施测试 ----

class TestNormalizeInput:
    def test_sombe_mapped_to_socbe(self):
        from framework.domain.other_models.model_6 import _normalize_input
        result = _normalize_input({"SOMbe": 15.0, "pH": 6.5})
        assert "SOCbe" in result
        assert "SOMbe" not in result
        assert result["SOCbe"] == 15.0
        assert result["pH"] == 6.5

    def test_sombe_with_trailing_space_stripped_then_mapped(self):
        from framework.domain.other_models.model_6 import _normalize_input
        result = _normalize_input({"SOMbe ": 15.0, "TN ": 1.2})
        assert "SOCbe" in result
        assert "SOMbe" not in result
        assert "TN" in result  # strip 尾随空格
        assert result["TN"] == 1.2

    def test_none_values_filtered(self):
        from framework.domain.other_models.model_6 import _normalize_input
        result = _normalize_input({"pH": None, "SOCbe": 12.0})
        assert "pH" not in result
        assert result["SOCbe"] == 12.0

    def test_none_input_returns_empty(self):
        from framework.domain.other_models.model_6 import _normalize_input
        assert _normalize_input(None) == {}

    def test_socbe_unchanged(self):
        from framework.domain.other_models.model_6 import _normalize_input
        result = _normalize_input({"SOCbe": 12.0})
        assert result == {"SOCbe": 12.0}


class TestShaoguanAreaCodes:
    def test_lechang_is_shaoguan(self):
        from framework.domain.other_models.model_6 import SHAOGUAN_AREA_CODES
        assert "lechang" in SHAOGUAN_AREA_CODES

    def test_other_codes_not_in_set(self):
        from framework.domain.other_models.model_6 import SHAOGUAN_AREA_CODES
        assert "other" not in SHAOGUAN_AREA_CODES
        assert "guangzhou" not in SHAOGUAN_AREA_CODES


class TestEnsureSgModelLoaded:
    def test_upland_load_success(self, monkeypatch):
        from framework.domain.other_models import model_6
        monkeypatch.setattr(model_6, "_SG_UPLAND_MODEL", None)
        monkeypatch.setattr(model_6, "_SG_UPLAND_META", None)
        monkeypatch.setattr(model_6, "_SG_UPLAND_LOAD_FAILED", False)

        fake_meta = {"feature_names": ["pH"], "metrics": {"test_r2": 0.6}, "feature_means": {"pH": 7.0}}
        def fake_load(mp, mt):
            return FakeModel(), fake_meta
        monkeypatch.setattr(model_6, "_load_model_and_meta", fake_load)

        ok = model_6._ensure_sg_model_loaded("upland")
        assert ok is True
        assert model_6._SG_UPLAND_MODEL is not None
        assert model_6._SG_UPLAND_META == fake_meta

    def test_paddy_load_success(self, monkeypatch):
        from framework.domain.other_models import model_6
        monkeypatch.setattr(model_6, "_SG_PADDY_MODEL", None)
        monkeypatch.setattr(model_6, "_SG_PADDY_META", None)
        monkeypatch.setattr(model_6, "_SG_PADDY_LOAD_FAILED", False)

        fake_meta = {"feature_names": ["pH"], "metrics": {"test_r2": 0.55}, "feature_means": {"pH": 7.0}}
        def fake_load(mp, mt):
            return FakeModel(), fake_meta
        monkeypatch.setattr(model_6, "_load_model_and_meta", fake_load)

        ok = model_6._ensure_sg_model_loaded("paddy")
        assert ok is True
        assert model_6._SG_PADDY_MODEL is not None

    def test_load_failure_sets_flag(self, monkeypatch):
        from framework.domain.other_models import model_6
        monkeypatch.setattr(model_6, "_SG_UPLAND_MODEL", None)
        monkeypatch.setattr(model_6, "_SG_UPLAND_META", None)
        monkeypatch.setattr(model_6, "_SG_UPLAND_LOAD_FAILED", False)

        def boom(mp, mt):
            raise FileNotFoundError("missing")
        monkeypatch.setattr(model_6, "_load_model_and_meta", boom)

        ok = model_6._ensure_sg_model_loaded("upland")
        assert ok is False
        assert model_6._SG_UPLAND_LOAD_FAILED is True

    def test_invalid_land_type_routes_to_upland(self, monkeypatch):
        """land_type 非法值（如 'foo'）应走 upland 分支"""
        from framework.domain.other_models import model_6
        monkeypatch.setattr(model_6, "_SG_UPLAND_MODEL", FakeModel())
        monkeypatch.setattr(model_6, "_SG_UPLAND_META", {"feature_names": [], "metrics": {"test_r2": 0.5}, "feature_means": {}})
        monkeypatch.setattr(model_6, "_SG_UPLAND_LOAD_FAILED", False)

        ok = model_6._ensure_sg_model_loaded("foo")
        assert ok is True  # 走 upland 已加载
```

- [ ] **Step 2: 运行测试验证失败**

```bash
pytest tests/test_fertility_ml_prediction.py::TestNormalizeInput tests/test_fertility_ml_prediction.py::TestShaoguanAreaCodes tests/test_fertility_ml_prediction.py::TestEnsureSgModelLoaded -v
```

预期：FAIL，`ImportError: cannot import name '_normalize_input' / 'SHAOGUAN_AREA_CODES' / '_ensure_sg_model_loaded'`。

- [ ] **Step 3: 实现 SHAOGUAN_AREA_CODES 常量与 SG 路径/状态**

在 `framework/domain/other_models/model_6.py` 的 `_DOSE_META_PATH = ...` 行下方新增 SG 路径常量：

```python
# ---- 韶关（SG）区域 RF Dose 模型路径 ----
_SG_UPLAND_MODEL_PATH = _MODELS_DIR / "sg_dose_upland_rf_model.joblib"
_SG_UPLAND_META_PATH = _MODELS_DIR / "sg_dose_upland_metadata.json"
_SG_PADDY_MODEL_PATH = _MODELS_DIR / "sg_dose_paddy_rf_model.joblib"
_SG_PADDY_META_PATH = _MODELS_DIR / "sg_dose_paddy_metadata.json"

# 韶关区域 area_code 集合（可扩展）
SHAOGUAN_AREA_CODES = {"lechang"}
```

在现有 `_DOSE_LOAD_FAILED = False` 与 `_LOAD_LOCK = threading.Lock()` 之间新增 SG 模块级状态：

```python
# ---- 韶关 SG RF 模型惰性单例状态 ----
_SG_UPLAND_MODEL = None
_SG_PADDY_MODEL = None
_SG_UPLAND_META = None
_SG_PADDY_META = None
_SG_UPLAND_LOAD_FAILED = False
_SG_PADDY_LOAD_FAILED = False
```

- [ ] **Step 4: 实现 _normalize_input 函数**

在 `_prepare_features` 函数**之前**新增：

```python
def _normalize_input(input_data: Dict[str, Any]) -> Dict[str, Any]:
    """规范化输入字段名：SOMbe → SOCbe，strip 尾随空格，过滤 None 值。

    在 model_6_execution 开头调用，使全局 ETR 与 SG RF 模型均消费 SOCbe 特征名。
    """
    normalized: Dict[str, Any] = {}
    for k, v in (input_data or {}).items():
        if v is None:
            continue
        key = "SOCbe" if k.strip() == "SOMbe" else k.strip()
        normalized[key] = v
    return normalized
```

- [ ] **Step 5: 实现 _ensure_sg_model_loaded 函数**

在 `_ensure_models_loaded` 函数**之后**新增：

```python
def _ensure_sg_model_loaded(land_type: str) -> bool:
    """按 land_type 惰性加载对应 SG RF 模型，返回是否加载成功。

    - land_type="paddy" → 加载水田模型
    - 其他值（含 "upland" 及非法值）→ 加载旱地模型
    - 复用 _LOAD_LOCK 的 double-checked locking
    """
    global _SG_UPLAND_MODEL, _SG_PADDY_MODEL, _SG_UPLAND_META, _SG_PADDY_META
    global _SG_UPLAND_LOAD_FAILED, _SG_PADDY_LOAD_FAILED

    if land_type == "paddy":
        if _SG_PADDY_LOAD_FAILED:
            return False
        if _SG_PADDY_MODEL is None and not _SG_PADDY_LOAD_FAILED:
            with _LOAD_LOCK:
                if _SG_PADDY_MODEL is None and not _SG_PADDY_LOAD_FAILED:
                    try:
                        _SG_PADDY_MODEL, _SG_PADDY_META = _load_model_and_meta(
                            _SG_PADDY_MODEL_PATH, _SG_PADDY_META_PATH
                        )
                        logger.info(
                            "SG paddy model loaded, feature_names=%s, test_r2=%.4f",
                            _SG_PADDY_META["feature_names"],
                            _SG_PADDY_META["metrics"]["test_r2"],
                        )
                    except Exception:
                        _SG_PADDY_LOAD_FAILED = True
                        logger.exception("Failed to load SG paddy model")
        return not _SG_PADDY_LOAD_FAILED

    # upland 或非法值都走旱地分支
    if _SG_UPLAND_LOAD_FAILED:
        return False
    if _SG_UPLAND_MODEL is None and not _SG_UPLAND_LOAD_FAILED:
        with _LOAD_LOCK:
            if _SG_UPLAND_MODEL is None and not _SG_UPLAND_LOAD_FAILED:
                try:
                    _SG_UPLAND_MODEL, _SG_UPLAND_META = _load_model_and_meta(
                        _SG_UPLAND_MODEL_PATH, _SG_UPLAND_META_PATH
                    )
                    logger.info(
                        "SG upland model loaded, feature_names=%s, test_r2=%.4f",
                        _SG_UPLAND_META["feature_names"],
                        _SG_UPLAND_META["metrics"]["test_r2"],
                    )
                except Exception:
                    _SG_UPLAND_LOAD_FAILED = True
                    logger.exception("Failed to load SG upland model")
    return not _SG_UPLAND_LOAD_FAILED
```

- [ ] **Step 6: 运行测试验证通过**

```bash
pytest tests/test_fertility_ml_prediction.py::TestNormalizeInput tests/test_fertility_ml_prediction.py::TestShaoguanAreaCodes tests/test_fertility_ml_prediction.py::TestEnsureSgModelLoaded -v
```

预期：9 个测试全部 PASS。

- [ ] **Step 7: 提交**

```bash
git add framework/domain/other_models/model_6.py tests/test_fertility_ml_prediction.py
git commit -m "feat(model_6): 新增韶关区域路由基础设施（SHAOGUAN_AREA_CODES/_normalize_input/_ensure_sg_model_loaded）"
```

---

### Task 5: model_6_execution 区域路由实现

**Files:**
- Modify: `framework/domain/other_models/model_6.py:168-236`（`model_6_execution` 函数）
- Test: `tests/test_fertility_ml_prediction.py`（追加测试类）

**Interfaces:**
- Consumes: Task 4 的 `SHAOGUAN_AREA_CODES`/`_normalize_input`/`_ensure_sg_model_loaded`/`_SG_*_MODEL`/`_SG_*_META`
- Produces: `model_6_execution(input_data: Dict[str, Any], land_type: str = "upland") -> Dict[str, Any]` 新签名；区域路由后 Dose 在韶关走 SG RF、非韶关走全局 ETR；SOC 始终走全局 ETR

- [ ] **Step 1: 写失败测试 — 区域路由与 land_type 行为**

在 `tests/test_fertility_ml_prediction.py` 末尾追加。先在文件顶部 mock 数据区新增 SG mock helper 与常量：

```python
# ---- Task 5: SG 区域路由测试用 mock 数据 ----

FAKE_SG_UPLAND_META = {
    "model_type": "RandomForestRegressor",
    "land_type": "upland",
    "region": "shaoguan",
    "model_version": "SG_RF_v1_20260731",
    "feature_names": ["pH", "SOCbe", "TN", "TP", "TK", "AP", "AK", "Gap", "Fertilizer type"],
    "feature_means": {
        "pH": 7.0, "SOCbe": 12.0, "TN": 0.8, "TP": 0.5, "TK": 30.0,
        "AP": 50.0, "AK": 100.0, "Gap": 10.0, "Fertilizer type": 1.5,
    },
    "metrics": {"cv_r2": 0.55, "cv_rmse": 40.0, "test_r2": 0.62, "test_rmse": 38.0},
    "training_samples": 185,
}

FAKE_SG_PADDY_META = {
    "model_type": "RandomForestRegressor",
    "land_type": "paddy",
    "region": "shaoguan",
    "model_version": "SG_RF_v1_20260731",
    "feature_names": ["pH", "SOCbe", "TN", "TP", "TK", "AP", "AK", "Gap", "Fertilizer type"],
    "feature_means": {
        "pH": 6.5, "SOCbe": 14.0, "TN": 1.0, "TP": 0.6, "TK": 28.0,
        "AP": 45.0, "AK": 90.0, "Gap": 8.0, "Fertilizer type": 1.5,
    },
    "metrics": {"cv_r2": 0.40, "cv_rmse": 45.0, "test_r2": 0.48, "test_rmse": 42.0},
    "training_samples": 25,  # <30 触发低置信度提示
}


def _setup_mock_sg_models(monkeypatch):
    """将 SG 模型状态设为 mock 值，模拟 SG 模型已加载。需配合 _setup_mock_models 使用。"""
    from framework.domain.other_models import model_6
    monkeypatch.setattr(model_6, "_SG_UPLAND_MODEL", FakeModel())
    monkeypatch.setattr(model_6, "_SG_PADDY_MODEL", FakeModel())
    monkeypatch.setattr(model_6, "_SG_UPLAND_META", FAKE_SG_UPLAND_META)
    monkeypatch.setattr(model_6, "_SG_PADDY_META", FAKE_SG_PADDY_META)
    monkeypatch.setattr(model_6, "_SG_UPLAND_LOAD_FAILED", False)
    monkeypatch.setattr(model_6, "_SG_PADDY_LOAD_FAILED", False)
```

再追加测试类：

```python
# ---- Task 5: model_6_execution 区域路由测试 ----

class TestModel6ShaoguanRouting:
    def test_non_shaoguan_uses_global_etr(self, monkeypatch):
        """area_code='other' → Dose+SOC 走全局 ETR（回归测试，行为不变）"""
        _setup_mock_models(monkeypatch)
        from framework.domain.other_models.model_6 import model_6_execution
        inp = dict(FULL_VALID_INPUT, area_code="other")
        result = model_6_execution(inp)
        assert result["status"] == "success"
        assert result["dose_prediction"] == 42.0  # FakeModel 返回 42
        assert result["soc_prediction"] == 42.0
        assert result["dose_confidence"] == 0.47  # FAKE_DOSE_META test_r2
        assert "韶关" not in result["dose_warning"]

    def test_non_shaoguan_default_area_code(self, monkeypatch):
        """不传 area_code → 空字符串 → 不命中 → 全局 ETR"""
        _setup_mock_models(monkeypatch)
        from framework.domain.other_models.model_6 import model_6_execution
        result = model_6_execution(FULL_VALID_INPUT)
        assert result["status"] == "success"
        assert "韶关" not in result["dose_warning"]

    def test_shaoguan_upland_uses_sg_rf(self, monkeypatch):
        """area_code='lechang', land_type='upland' → Dose 走 SG upland RF, SOC 走 ETR"""
        _setup_mock_models(monkeypatch)
        _setup_mock_sg_models(monkeypatch)
        from framework.domain.other_models.model_6 import model_6_execution
        inp = dict(FULL_VALID_INPUT, area_code="lechang")
        result = model_6_execution(inp, land_type="upland")
        assert result["status"] == "success"
        assert result["dose_prediction"] == 42.0  # SG FakeModel 也返回 42
        assert result["soc_prediction"] == 42.0
        assert result["dose_confidence"] == 0.62  # FAKE_SG_UPLAND_META test_r2
        assert "韶关" in result["dose_warning"]
        assert "旱地" in result["dose_warning"]
        assert "0.62" in result["dose_warning"]

    def test_shaoguan_paddy_uses_sg_rf(self, monkeypatch):
        """area_code='lechang', land_type='paddy' → Dose 走 SG paddy RF"""
        _setup_mock_models(monkeypatch)
        _setup_mock_sg_models(monkeypatch)
        from framework.domain.other_models.model_6 import model_6_execution
        inp = dict(FULL_VALID_INPUT, area_code="lechang")
        result = model_6_execution(inp, land_type="paddy")
        assert result["status"] == "success"
        assert result["dose_confidence"] == 0.48  # FAKE_SG_PADDY_META test_r2
        assert "韶关" in result["dose_warning"]
        assert "水田" in result["dose_warning"]
        assert "0.48" in result["dose_warning"]

    def test_shaoguan_soc_always_global_etr(self, monkeypatch):
        """韶关区域 SOC 仍走全局 ETR（soc_confidence 用 ETR test_r2=0.91）"""
        _setup_mock_models(monkeypatch)
        _setup_mock_sg_models(monkeypatch)
        from framework.domain.other_models.model_6 import model_6_execution
        inp = dict(FULL_VALID_INPUT, area_code="lechang")
        result = model_6_execution(inp, land_type="upland")
        assert result["soc_confidence"] == 0.91  # FAKE_SOC_META test_r2，非 SG

    def test_shaoguan_area_code_case_insensitive(self, monkeypatch):
        """area_code='LeChang' → .lower() → 命中韶关"""
        _setup_mock_models(monkeypatch)
        _setup_mock_sg_models(monkeypatch)
        from framework.domain.other_models.model_6 import model_6_execution
        inp = dict(FULL_VALID_INPUT, area_code="LeChang")
        result = model_6_execution(inp, land_type="upland")
        assert result["status"] == "success"
        assert "韶关" in result["dose_warning"]

    def test_land_type_default_upland(self, monkeypatch):
        """未传 land_type → 默认 upland"""
        _setup_mock_models(monkeypatch)
        _setup_mock_sg_models(monkeypatch)
        from framework.domain.other_models.model_6 import model_6_execution
        inp = dict(FULL_VALID_INPUT, area_code="lechang")
        result = model_6_execution(inp)  # 不传 land_type
        assert result["status"] == "success"
        assert "旱地" in result["dose_warning"]  # 默认 upland

    def test_land_type_invalid_defaults_upland_with_warning(self, monkeypatch):
        """land_type='foo' → 默认 upland + dose_warning 含未识别提示"""
        _setup_mock_models(monkeypatch)
        _setup_mock_sg_models(monkeypatch)
        from framework.domain.other_models.model_6 import model_6_execution
        inp = dict(FULL_VALID_INPUT, area_code="lechang")
        result = model_6_execution(inp, land_type="foo")
        assert result["status"] == "success"
        assert "旱地" in result["dose_warning"]
        assert "foo" in result["dose_warning"] or "未识别" in result["dose_warning"]

    def test_sombe_input_mapped_to_socbe(self, monkeypatch):
        """输入含 SOMbe → _normalize_input 映射为 SOCbe → 不被当缺失填充"""
        _setup_mock_models(monkeypatch)
        from framework.domain.other_models.model_6 import model_6_execution
        # 用 SOMbe 替换 SOCbe，area_code 非韶关走全局 ETR
        inp = {k: v for k, v in FULL_VALID_INPUT.items() if k != "SOCbe"}
        inp["SOMbe"] = 15.0
        inp["area_code"] = "other"
        result = model_6_execution(inp)
        assert result["status"] == "success"
        # SOCbe 应被正确识别，不进 imputed_features
        assert "SOCbe" not in result["imputed_features"]

    def test_shaoguan_paddy_low_sample_warning(self, monkeypatch):
        """水田 training_samples<30 → dose_warning 含低置信度提示"""
        _setup_mock_models(monkeypatch)
        _setup_mock_sg_models(monkeypatch)
        from framework.domain.other_models.model_6 import model_6_execution
        inp = dict(FULL_VALID_INPUT, area_code="lechang")
        result = model_6_execution(inp, land_type="paddy")
        assert "样本" in result["dose_warning"] or "置信度" in result["dose_warning"]

    def test_shaoguan_model_missing_fallback(self, monkeypatch):
        """SG 模型文件缺失 → fallback, fallback_reason=model_file_missing"""
        _setup_mock_models(monkeypatch)
        from framework.domain.other_models import model_6
        monkeypatch.setattr(model_6, "_SG_UPLAND_MODEL", None)
        monkeypatch.setattr(model_6, "_SG_UPLAND_META", None)
        monkeypatch.setattr(model_6, "_SG_UPLAND_LOAD_FAILED", True)
        inp = dict(FULL_VALID_INPUT, area_code="lechang")
        result = model_6.model_6_execution(inp, land_type="upland")
        assert result["status"] == "fallback"
        assert result["fallback_reason"] == "model_file_missing"

    def test_backward_compat_no_land_type_param(self, monkeypatch):
        """旧调用方不传 land_type → 默认 upland，签名向后兼容"""
        _setup_mock_models(monkeypatch)
        from framework.domain.other_models.model_6 import model_6_execution
        result = model_6_execution(FULL_VALID_INPUT)
        assert result["status"] == "success"
```

- [ ] **Step 2: 运行测试验证失败**

```bash
pytest tests/test_fertility_ml_prediction.py::TestModel6ShaoguanRouting -v
```

预期：多数测试 FAIL（`model_6_execution() got an unexpected keyword argument 'land_type'` 或 dose_warning 不含"韶关"）。

- [ ] **Step 3: 重构 model_6_execution 实现区域路由**

将 `framework/domain/other_models/model_6.py` 中整个 `model_6_execution` 函数（从 `def model_6_execution(input_data: Dict[str, Any]) -> Dict[str, Any]:` 到文件末尾）替换为：

```python
def model_6_execution(input_data: Dict[str, Any], land_type: str = "upland") -> Dict[str, Any]:
    """SOC + Dose ML 预测主入口。

    输入：特征字典（key 可含/不含尾随空格，可缺字段；可含 area_code/land_type）
    输出：预测结果字典，含 status/soc_prediction/dose_prediction 等字段

    区域路由：
    - area_code 命中 SHAOGUAN_AREA_CODES → Dose 走 SG RF（按 land_type 选子模型），SOC 始终走全局 ETR
    - 未命中 → Dose 和 SOC 均走全局 ETR（行为不变）
    - land_type 仅 "upland"/"paddy" 合法，非法值默认 upland 并附 dose_warning 提示
    """
    try:
        # 1. 输入规范化（SOMbe → SOCbe，strip，过滤 None）
        input_data = _normalize_input(input_data)

        # 2. 检查 sklearn 可用性
        if not _SKLEARN_AVAILABLE:
            return _fallback_response(input_data, reason="sklearn_missing")

        # 3. 区域判定
        area_code = input_data.get("area_code", "")
        is_shaoguan = isinstance(area_code, str) and area_code.lower() in SHAOGUAN_AREA_CODES

        # 4. land_type 规范化（非法值默认 upland）
        land_type_norm = land_type if land_type in ("upland", "paddy") else "upland"
        land_type_invalid = land_type not in ("upland", "paddy")
        land_type_warning = (
            f"（未识别的 land_type={land_type}，默认按旱地处理）" if land_type_invalid else ""
        )

        # 5. SOC 始终走全局 ETR（先确保全局模型加载）
        if not _ensure_models_loaded():
            return _fallback_response(input_data, reason="model_file_missing")

        soc_df, soc_imputed, soc_oor = _prepare_features(
            input_data, _SOC_META["feature_names"], _SOC_META["feature_means"]
        )

        # 6. Dose 特征（去掉 Dose 自身）
        dose_input = {k: v for k, v in input_data.items() if k.strip() != "Dose"}

        # 7. Dose 区域路由
        if is_shaoguan:
            if not _ensure_sg_model_loaded(land_type_norm):
                return _fallback_response(input_data, reason="model_file_missing")
            if land_type_norm == "paddy":
                sg_model = _SG_PADDY_MODEL
                sg_meta = _SG_PADDY_META
                land_label = "水田"
            else:
                sg_model = _SG_UPLAND_MODEL
                sg_meta = _SG_UPLAND_META
                land_label = "旱地"
            dose_df, dose_imputed, dose_oor = _prepare_features(
                dose_input, sg_meta["feature_names"], sg_meta["feature_means"]
            )
        else:
            dose_df, dose_imputed, dose_oor = _prepare_features(
                dose_input, _DOSE_META["feature_names"], _DOSE_META["feature_means"]
            )

        # 8. 范围校验：任一越界即拒绝
        all_oor = soc_oor + dose_oor
        if all_oor:
            return {
                "status": "rejected",
                "reason": "input_out_of_range",
                "out_of_range_features": all_oor,
                "soc_prediction": None,
                "soc_confidence": 0.0,
                "dose_prediction": None,
                "dose_confidence": 0.0,
                "dose_warning": "输入值越界，未执行预测",
                "imputed_features": [],
                "imputation_applied": False,
                "model_version": _MODEL_VERSION,
            }

        # 9. 执行预测
        soc_pred = float(_SOC_MODEL.predict(soc_df)[0])

        if is_shaoguan:
            dose_pred = float(sg_model.predict(dose_df)[0])
            sg_test_r2 = sg_meta["metrics"]["test_r2"]
            dose_warning = (
                f"韶关{land_label} RF 模型 R²={sg_test_r2:.2f}，预测结果仅供参考"
                f"{land_type_warning}"
            )
            dose_confidence = round(sg_test_r2, 2)
            # 低样本量提示
            if sg_meta.get("training_samples", 0) < 30:
                dose_warning += "（训练样本量较少，置信度偏低）"
        else:
            dose_pred = float(_DOSE_MODEL.predict(dose_df)[0])
            dose_warning = (
                "Dose 模型 R²=0.47，预测结果仅供参考，建议结合田间试验校准"
                f"{land_type_warning}"
            )
            dose_confidence = round(_DOSE_META["metrics"]["test_r2"], 2)

        logger.info(
            "model_6_execution success: SOC=%.4f, Dose=%.4f, is_shaoguan=%s, land_type=%s",
            soc_pred, dose_pred, is_shaoguan, land_type_norm,
        )

        # 10. 构造响应
        return {
            "status": "success",
            "soc_prediction": round(soc_pred, 4),
            "soc_confidence": round(_SOC_META["metrics"]["test_r2"], 2),
            "dose_prediction": round(dose_pred, 4),
            "dose_confidence": dose_confidence,
            "dose_warning": dose_warning.strip(),
            "imputed_features": sorted(set(soc_imputed + dose_imputed)),
            "imputation_applied": bool(soc_imputed or dose_imputed),
            "model_version": _MODEL_VERSION,
        }

    except Exception as e:
        logger.exception(f"model_6_execution unexpected error: {e}")
        return _fallback_response(input_data, reason="unexpected_error")
```

- [ ] **Step 4: 运行新测试验证通过**

```bash
pytest tests/test_fertility_ml_prediction.py::TestModel6ShaoguanRouting -v
```

预期：12 个测试全部 PASS。

- [ ] **Step 5: 运行原有 model_6 测试确认无回归**

```bash
pytest tests/test_fertility_ml_prediction.py::TestModel6Execution -v
```

预期：原有 13 个测试全部 PASS（向后兼容，旧调用不传 land_type 时默认 upland、不传 area_code 时走全局 ETR）。

- [ ] **Step 6: 提交**

```bash
git add framework/domain/other_models/model_6.py tests/test_fertility_ml_prediction.py
git commit -m "feat(model_6): model_6_execution 实现韶关区域路由（land_type 参数 + Dose 走 SG RF）"
```

---

### Task 6: FertilityMLAgent 适配

**Files:**
- Modify: `framework/agents/specialized/fertility_ml_agent.py:36-56`（execute 与 answer_question）
- Test: `tests/test_fertility_ml_prediction.py`（追加测试类）

**Interfaces:**
- Consumes: Task 5 的 `model_6_execution(input_data, land_type="upland")` 新签名
- Produces: `FertilityMLAgent.execute(task)` 从 task 提取 `land_type` 透传；`answer_question` 从 context 顶层提取 `area_code`/`land_type` 注入 task

- [ ] **Step 1: 写失败测试 — Agent 透传 area_code/land_type**

在 `tests/test_fertility_ml_prediction.py` 末尾追加：

```python
# ---- Task 6: FertilityMLAgent 透传测试 ----

class TestFertilityMLAgentPassthrough:
    def test_execute_passes_land_type_to_model_6(self, monkeypatch):
        """execute(task) 应从 task['land_type'] 提取并传给 model_6_execution"""
        _setup_mock_models(monkeypatch)
        _setup_mock_sg_models(monkeypatch)
        from framework.agents.specialized.fertility_ml_agent import FertilityMLAgent

        captured = {}
        def spy_model_6(inp, land_type="upland"):
            captured["land_type"] = land_type
            captured["area_code"] = inp.get("area_code")
            return {
                "status": "success",
                "soc_prediction": 42.0, "soc_confidence": 0.91,
                "dose_prediction": 42.0, "dose_confidence": 0.62,
                "dose_warning": "韶关旱地 RF 模型 R²=0.62",
                "imputed_features": [], "imputation_applied": False,
                "model_version": "ETR_v1_20260713",
            }
        monkeypatch.setattr(
            "framework.agents.specialized.fertility_ml_agent.model_6_execution",
            spy_model_6,
        )

        agent = FertilityMLAgent()
        task = dict(FULL_VALID_INPUT, area_code="lechang", land_type="upland")
        agent.execute(task)
        assert captured["land_type"] == "upland"
        assert captured["area_code"] == "lechang"

    def test_execute_default_land_type_when_missing(self, monkeypatch):
        """task 不含 land_type → 默认 upland 传给 model_6"""
        _setup_mock_models(monkeypatch)
        from framework.agents.specialized.fertility_ml_agent import FertilityMLAgent

        captured = {}
        def spy_model_6(inp, land_type="upland"):
            captured["land_type"] = land_type
            return {"status": "success", "soc_prediction": 1.0, "soc_confidence": 0.5,
                    "dose_prediction": 1.0, "dose_confidence": 0.5, "dose_warning": "x",
                    "imputed_features": [], "imputation_applied": False, "model_version": "v"}
        monkeypatch.setattr(
            "framework.agents.specialized.fertility_ml_agent.model_6_execution",
            spy_model_6,
        )

        agent = FertilityMLAgent()
        agent.execute({"pH": 6.5})
        assert captured["land_type"] == "upland"

    def test_answer_question_enriches_task_with_context_area_code(self, monkeypatch):
        """answer_question 应从 context 顶层提取 area_code/land_type 注入 task"""
        _setup_mock_models(monkeypatch)
        _setup_mock_sg_models(monkeypatch)
        from framework.agents.specialized.fertility_ml_agent import FertilityMLAgent

        captured = {}
        def spy_model_6(inp, land_type="upland"):
            captured["area_code"] = inp.get("area_code")
            captured["land_type"] = land_type
            return {"status": "success", "soc_prediction": 1.0, "soc_confidence": 0.5,
                    "dose_prediction": 1.0, "dose_confidence": 0.5, "dose_warning": "x",
                    "imputed_features": [], "imputation_applied": False, "model_version": "v"}
        monkeypatch.setattr(
            "framework.agents.specialized.fertility_ml_agent.model_6_execution",
            spy_model_6,
        )

        agent = FertilityMLAgent()
        # context 顶层有 area_code/land_type，data 里没有
        context = {"area_code": "lechang", "land_type": "paddy", "data": {"pH": 6.5}}
        agent.answer_question("施肥量多少", context)
        assert captured["area_code"] == "lechang"
        assert captured["land_type"] == "paddy"

    def test_answer_question_task_data_takes_precedence(self, monkeypatch):
        """context['data'] 内的 area_code 优先于 context 顶层"""
        _setup_mock_models(monkeypatch)
        from framework.agents.specialized.fertility_ml_agent import FertilityMLAgent

        captured = {}
        def spy_model_6(inp, land_type="upland"):
            captured["area_code"] = inp.get("area_code")
            return {"status": "success", "soc_prediction": 1.0, "soc_confidence": 0.5,
                    "dose_prediction": 1.0, "dose_confidence": 0.5, "dose_warning": "x",
                    "imputed_features": [], "imputation_applied": False, "model_version": "v"}
        monkeypatch.setattr(
            "framework.agents.specialized.fertility_ml_agent.model_6_execution",
            spy_model_6,
        )

        agent = FertilityMLAgent()
        context = {
            "area_code": "other",
            "data": {"pH": 6.5, "area_code": "lechang"},  # data 内优先
        }
        agent.answer_question("施肥量", context)
        assert captured["area_code"] == "lechang"
```

- [ ] **Step 2: 运行测试验证失败**

```bash
pytest tests/test_fertility_ml_prediction.py::TestFertilityMLAgentPassthrough -v
```

预期：FAIL（`test_execute_passes_land_type_to_model_6` 等——当前 execute 不传 land_type，answer_question 不注入 context 顶层字段）。

- [ ] **Step 3: 改造 FertilityMLAgent.execute 与 answer_question**

将 `framework/agents/specialized/fertility_ml_agent.py` 的 `execute` 方法替换为：

```python
    def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """调用 model_6_execution 执行 ML 预测，包装为三层结构。

        从 task 提取 land_type（默认 upland）透传给 model_6_execution。
        area_code 已在 task 字典中自然流转，无需额外传递。
        """
        land_type = (task or {}).get("land_type", "upland")
        result = model_6_execution(task or {}, land_type=land_type)
        return MockDataLoader.mark_simulated({
            "status": result["status"],
            "result": {
                "soc_prediction": result["soc_prediction"],
                "soc_confidence": result["soc_confidence"],
                "dose_prediction": result["dose_prediction"],
                "dose_confidence": result["dose_confidence"],
                "dose_warning": result["dose_warning"],
                "imputed_features": result["imputed_features"],
                "imputation_applied": result["imputation_applied"],
            },
            "metadata": {
                "model_version": result["model_version"],
                "fallback_reason": result.get("fallback_reason"),
                "reason": result.get("reason"),
                "out_of_range_features": result.get("out_of_range_features"),
            },
        })
```

将 `answer_question` 方法替换为：

```python
    def answer_question(self, question: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """按关键词优先级处理问答：Dose > SOC > 综合/默认。

        从 context 顶层提取 area_code/land_type 注入 task（task 内已有值则不覆盖），
        确保 model_6_execution 能收到区域与土地类型信息。
        """
        task = context.get("data", {}) or context.get("task", {}) or {}
        enriched = dict(task)
        # 透传 context 顶层的 area_code/land_type（task 内已有值优先）
        if "area_code" in context and "area_code" not in enriched:
            enriched["area_code"] = context["area_code"]
        if "land_type" in context and "land_type" not in enriched:
            enriched["land_type"] = context["land_type"]

        exec_result = self.execute(enriched)
        pred = exec_result["result"]

        q_lower = question.lower()

        # 优先级 1：明确问 Dose / 施用量
        if any(kw.lower() in q_lower for kw in DOSE_KEYWORDS):
            return self._format_dose_only(pred, exec_result)

        # 优先级 2：明确问 SOC / 有机碳
        if any(kw.lower() in q_lower for kw in SOC_KEYWORDS):
            return self._format_soc_only(pred, exec_result)

        # 优先级 3：肥力 / 综合 / 其他
        return self._format_both(pred, exec_result)
```

- [ ] **Step 4: 运行 Agent 测试验证通过**

```bash
pytest tests/test_fertility_ml_prediction.py::TestFertilityMLAgentPassthrough -v
```

预期：4 个测试全部 PASS。

- [ ] **Step 5: 运行现有 agent 测试确认无回归**

```bash
pytest tests/test_agent_specialized.py -v -k "fertility or Fertility"
```

预期：现有 FertilityMLAgent 相关测试全部 PASS（若有）。

- [ ] **Step 6: 提交**

```bash
git add framework/agents/specialized/fertility_ml_agent.py tests/test_fertility_ml_prediction.py
git commit -m "feat(agent): FertilityMLAgent 透传 area_code/land_type 到 model_6_execution"
```

---

### Task 7: API 层适配（nodes.execute_models 透传 land_type）

**Files:**
- Modify: `framework/agents/nodes.py:233-247`（execute_models 节点）
- Test: `tests/test_fertility_ml_prediction.py`（追加测试）

**Interfaces:**
- Consumes: Task 6 的 FertilityMLAgent 适配
- Produces: `execute_models` 节点将 `state["request"]["land_type"]` 透传到 agent context 顶层

**说明:** `framework/api/routes/chat.py` 的 `orchestrator_request = {"question": message, **context}` 已自动把客户端 `context.land_type` 展开到 request 顶层，无需修改 chat.py。`framework/api/routes/models.py` 的 `/run` 路径不调用 FertilityMLAgent（走 thematic_models），无需修改。本任务仅改 `nodes.execute_models` 的 context 构造。

- [ ] **Step 1: 写失败测试 — execute_models 透传 land_type**

在 `tests/test_fertility_ml_prediction.py` 末尾追加：

```python
# ---- Task 7: nodes.execute_models 透传 land_type 测试 ----

class TestExecuteModelsLandTypePassthrough:
    def test_execute_models_passes_land_type_to_agent_context(self, monkeypatch):
        """execute_models 应将 request['land_type'] 透传到 agent_manager.process 的 context 顶层"""
        from framework.agents import nodes

        captured = {}
        def fake_process(question, context):
            captured["context"] = context
            return {"status": "ok", "data": {"summary": "", "details": {}, "agents_invoked": [], "recommendations": []}}
        monkeypatch.setattr(nodes, "agent_manager", type("M", (), {"process": staticmethod(fake_process)})())

        state = {
            "request": {
                "question": "施肥量多少",
                "area_code": "lechang",
                "land_type": "paddy",
            },
            "data": {},
            "question_type": 1,
        }
        nodes.execute_models(state)
        assert captured["context"]["land_type"] == "paddy"
        assert captured["context"]["area_code"] == "lechang"

    def test_execute_models_without_land_type_omits_key(self, monkeypatch):
        """request 不含 land_type → context 不含 land_type（agent 侧默认 upland）"""
        from framework.agents import nodes

        captured = {}
        def fake_process(question, context):
            captured["context"] = context
            return {"status": "ok", "data": {"summary": "", "details": {}, "agents_invoked": [], "recommendations": []}}
        monkeypatch.setattr(nodes, "agent_manager", type("M", (), {"process": staticmethod(fake_process)})())

        state = {
            "request": {"question": "施肥量", "area_code": "lechang"},
            "data": {},
            "question_type": 1,
        }
        nodes.execute_models(state)
        assert "land_type" not in captured["context"]
```

- [ ] **Step 2: 运行测试验证失败**

```bash
pytest tests/test_fertility_ml_prediction.py::TestExecuteModelsLandTypePassthrough -v
```

预期：FAIL（当前 execute_models 不透传 land_type，context 中无 land_type 键）。

- [ ] **Step 3: 改造 execute_models 节点透传 land_type**

在 `framework/agents/nodes.py` 的 `execute_models` 函数中，将 context 构造的 for 循环：

```python
        # 透传可能的土壤参数
        for key in ("longitude", "latitude", "target_ph", "context"):
            if key in state["request"]:
                context[key] = state["request"][key]
```

替换为（新增 `land_type`）：

```python
        # 透传可能的土壤参数与区域/土地类型
        for key in ("longitude", "latitude", "target_ph", "context", "land_type"):
            if key in state["request"]:
                context[key] = state["request"][key]
```

- [ ] **Step 4: 运行测试验证通过**

```bash
pytest tests/test_fertility_ml_prediction.py::TestExecuteModelsLandTypePassthrough -v
```

预期：2 个测试全部 PASS。

- [ ] **Step 5: 运行 nodes 相关测试确认无回归**

```bash
pytest tests/test_agent_integration.py tests/test_multi_agent.py -v
```

预期：现有测试全部 PASS（context 仅新增可选 land_type 键，不影响其他 agent）。

- [ ] **Step 6: 提交**

```bash
git add framework/agents/nodes.py tests/test_fertility_ml_prediction.py
git commit -m "feat(api): execute_models 节点透传 land_type 到 agent context"
```

---

### Task 8: 集成测试与全量回归验证

**Files:**
- Test: `tests/test_fertility_ml_prediction.py`（追加 SG 集成测试类）
- Verify: 全量测试套件

**Interfaces:**
- Consumes: Task 3 产出的真实 SG 模型文件 + Task 4-7 的实现
- Produces: 集成测试覆盖真实 SG 模型加载与预测；全量回归无失败

- [ ] **Step 1: 追加 SG 真实模型集成测试**

在 `tests/test_fertility_ml_prediction.py` 末尾追加：

```python
# ---- Task 8: SG 真实模型集成测试（模型不可用时跳过）----

def _check_sg_integration_available():
    try:
        from framework.domain.other_models import model_6
        return (
            model_6._SKLEARN_AVAILABLE
            and model_6._ensure_models_loaded()
            and model_6._ensure_sg_model_loaded("upland")
            and model_6._ensure_sg_model_loaded("paddy")
        )
    except Exception:
        return False


@pytest.mark.skipif(
    not _check_sg_integration_available(),
    reason="sklearn 或 SG 模型文件不可用"
)
class TestModel6ShaoguanIntegration:
    def test_real_sg_upland_dose_in_range(self):
        """真实 SG 旱地预测：Dose 在 0-1000 合理范围"""
        from framework.domain.other_models.model_6 import model_6_execution
        inp = dict(FULL_VALID_INPUT, area_code="lechang")
        result = model_6_execution(inp, land_type="upland")
        assert result["status"] == "success"
        assert 0.0 <= result["dose_prediction"] <= 1000.0
        assert "韶关" in result["dose_warning"]
        assert "旱地" in result["dose_warning"]

    def test_real_sg_paddy_dose_in_range(self):
        """真实 SG 水田预测：Dose 在 0-1000 合理范围"""
        from framework.domain.other_models.model_6 import model_6_execution
        inp = dict(FULL_VALID_INPUT, area_code="lechang")
        result = model_6_execution(inp, land_type="paddy")
        assert result["status"] == "success"
        assert 0.0 <= result["dose_prediction"] <= 1000.0
        assert "韶关" in result["dose_warning"]
        assert "水田" in result["dose_warning"]

    def test_real_sg_soc_uses_global_etr(self):
        """真实 SG 区域 SOC 仍走全局 ETR（soc_confidence 用 ETR test_r2）"""
        from framework.domain.other_models.model_6 import model_6_execution
        from framework.domain.other_models.model_6 import _SOC_META
        inp = dict(FULL_VALID_INPUT, area_code="lechang")
        result = model_6_execution(inp, land_type="upland")
        assert result["status"] == "success"
        assert result["soc_confidence"] == round(_SOC_META["metrics"]["test_r2"], 2)

    def test_real_sg_model_files_exist(self):
        """验证 SG .joblib 与 metadata.json 文件存在"""
        from framework.domain.other_models.model_6 import (
            _SG_UPLAND_MODEL_PATH, _SG_UPLAND_META_PATH,
            _SG_PADDY_MODEL_PATH, _SG_PADDY_META_PATH,
        )
        assert _SG_UPLAND_MODEL_PATH.exists()
        assert _SG_UPLAND_META_PATH.exists()
        assert _SG_PADDY_MODEL_PATH.exists()
        assert _SG_PADDY_META_PATH.exists()

    def test_real_non_shaoguan_unchanged(self):
        """真实非韶关预测：Dose 走全局 ETR，dose_warning 不含韶关"""
        from framework.domain.other_models.model_6 import model_6_execution
        inp = dict(FULL_VALID_INPUT, area_code="other")
        result = model_6_execution(inp)
        assert result["status"] == "success"
        assert "韶关" not in result["dose_warning"]
```

- [ ] **Step 2: 运行 SG 集成测试**

```bash
pytest tests/test_fertility_ml_prediction.py::TestModel6ShaoguanIntegration -v
```

预期：5 个测试全部 PASS（真实模型文件已在 Task 3 产出）。若 SG 模型文件未生成则被 skipif 跳过。

- [ ] **Step 3: 运行 model-6 全量测试**

```bash
pytest tests/test_fertility_ml_prediction.py -v
```

预期：所有测试 PASS（含原有 TestModel6Execution/TestModel6Integration、Task 4-7 新增单元测试、Task 8 集成测试）。

- [ ] **Step 4: 运行 Agent 相关测试**

```bash
pytest tests/test_agent_specialized.py tests/test_agent_integration.py tests/test_multi_agent.py tests/test_agent_manager.py -v
```

预期：全部 PASS，无回归。

- [ ] **Step 5: 运行全量测试套件**

```bash
pytest tests/ -v --tb=short
```

预期：全部 PASS（排除预先存在的、与本变更无关的失败）。若发现失败，检查是否由本变更引入（特别关注 model_6/FertilityMLAgent/nodes 相关）。

- [ ] **Step 6: 手动验证 SG 预测数值合理性**

```bash
python -c "
from framework.domain.other_models.model_6 import model_6_execution
inp = {'pH': 6.5, 'SOCbe': 15.0, 'TN': 1.2, 'TP': 0.8, 'TK': 25.0, 'AP': 30.0, 'AK': 80.0, 'Gap': 5.0, 'Dose': 200.0, 'Fertilizer type': 1, 'area_code': 'lechang'}
for lt in ['upland', 'paddy']:
    r = model_6_execution(inp, land_type=lt)
    print(f'{lt}: status={r[\"status\"]}, SOC={r[\"soc_prediction\"]}, Dose={r[\"dose_prediction\"]}, conf={r[\"dose_confidence\"]}, warn={r[\"dose_warning\"]}')
# 非韶关回归
r = model_6_execution({**inp, 'area_code': 'other'})
print(f'non-sg: status={r[\"status\"]}, Dose={r[\"dose_prediction\"]}, warn={r[\"dose_warning\"]}')
"
```

预期：韶关旱地/水田 status=success，Dose 在 0-1000 合理范围，dose_warning 含"韶关旱地/水田"与 R² 值；非韶关 dose_warning 为原"Dose 模型 R²=0.47..."。

- [ ] **Step 7: 提交**

```bash
git add tests/test_fertility_ml_prediction.py
git commit -m "test(fertility): 新增韶关 SG RF 模型集成测试与全量回归验证"
```

---

## 自检清单（实施完成后核对）

- [ ] **spec 覆盖**：D1（area_code 路由 + land_type 显式参数）→ Task 4/5；D2（区域路由）→ Task 5；D3（SG 惰性加载）→ Task 4；D4（SOMbe→SOCbe）→ Task 2（训练）+ Task 4（推理）；D5（训练脚本扩展）→ Task 2。
- [ ] **tasks.md 覆盖**：1.1-1.3 → Task 1；2.1-2.5 → Task 2/3；3.1-3.7 → Task 4/5；4.1-4.2 → Task 6；5.1-5.2 → Task 7；6.1-6.8 → Task 5/6/8；7.1-7.3 → Task 8。
- [ ] **向后兼容**：旧调用方不传 `land_type`/`area_code` 时行为不变（Task 5 Step 5 验证）。
- [ ] **类型一致**：`_ensure_sg_model_loaded(land_type)` 在 Task 4 定义、Task 5 调用，签名一致；`model_6_execution(input_data, land_type="upland")` 在 Task 5 定义、Task 6 调用，签名一致。
- [ ] **无占位符**：所有步骤含完整代码或具体命令。
