---
comet_change: implement-models-calculation-logic
role: technical-design
canonical_spec: openspec
archived-with: 2026-08-18-implement-models-calculation-logic
status: final
---

# 专题模型计算逻辑实现 — 技术设计

## Context

5 个专题模型 Agent 的 DB 数据流（`ParcelDataAccessor.get_parcel_indicators`）和持久化框架已就绪，但 `execute` 返回占位值（`quality_grade=0`、`obstacle_type=未知`、`model_unavailable`）。原始计算逻辑在 `D:\destkop\模型1-5`，使用 Python/NumPy/Pandas/Scipy 实现，输入为 Shapefile/CSV。本设计将其移植到框架，从 DB `soil_indicators` JSON 读取输入，计算后持久化到 V3.0 结果表。

### 关键现状（探索发现）

- `ParcelDataAccessor` 仅有 `get_parcel_indicators()` 返回原始 JSON，**无** `_map_indicators_to_inputs`；映射分散在各 Agent 且字段名有误（`soil_bulk_density` 应为 `bulk_density`、`topsoil_texture` 应为 `soil_texture`、`irrigation_capacity` 应为 `irrigation_condition`）。
- `framework/domain/calculations/` 目录不存在，所有计算模块需从零创建。
- DB `soil_indicators` 离散值用**英文**（"loam"/"dry"/"lower"），原始 `DISCRETE_CN_MAP` 是中文→代码，需补英文→代码映射层。
- 原始 RF notebook 未保存 `.joblib`，需构建时重训。
- ParcelInfo 已有 `land_type`/`fertilizer_type`/`target_ph`/`geom`(PostGIS)/`area_code` 字段可用。
- 种子数据缺 `exchangeable_aluminum`(Alex)、`plow_layer_thickness`(GCHD)、`soil_structure`(ZDGX)。

### 模型编号对应关系

原始文件夹编号与项目模型编号**互换**（OpenSpec 已采用项目编号）：

| 原始文件夹 | 项目模型 | 主题 |
|------------|----------|------|
| 模型1_v2 | Model-1 | 稳定性风险 |
| 模型2 | Model-2 | 质量等级 |
| 模型3_V2.0 | Model-3 | 障碍诊断 |
| 模型5_酸化模型 | Model-4 | 酸化改良 |
| 模型4-SG-Dose预测模型 | Model-5 | 有机质培肥(RF) |

## Goals / Non-Goals

**Goals:**
- 5 个模型各自执行真实计算逻辑（移植自原始代码），返回非占位结果
- Model-1 实现全部 9 个模块（含历史数据导入 + PostGIS 空间查询）
- 统一 V3.0 英文 snake_case 字段名到各模型输入参数的集中映射
- 计算结果持久化到 V3.0 结果表
- 每个模型可独立降级（DB 数据缺失时 fallback）

**Non-Goals:**
- 不修改 API 接口契约（`run_thematic_model` 入参/返回结构不变）
- 不修改现有 DB schema（仅新增 `parcel_history_snapshot` 表）
- 不重新设计前端展示
- 不修改已归档 change 的产物

## Decisions

### D1: 计算与映射架构 — 集中式计算层（方案 A）

**决策**: 创建 `framework/domain/calculations/` 集中存放 5 个模型计算模块；在 `ParcelDataAccessor` 新增 `_map_indicators_to_inputs(indicators, agent_id)` 统一映射方法。Agent 只编排（DB 读取→映射→计算→持久化），不内嵌计算。

**理由**:
- 计算逻辑可独立单测，逐函数对照原始公式验证
- 映射单一事实源（符合 OpenSpec design.md D4）
- 符合 tasks.md 中每个模型独立的单元测试要求
- 避免 5 个 Agent 重复映射逻辑

**替代方案**: 内嵌式（计算在 Agent 内）— 映射重复、难独立测试；混合式（共享系数分散映射）— 映射仍重复。均否决。

### D2: Model-1 范围 — 实现全部 9 模块（更新原 design.md D2）

**决策**: Model-1 实现全部 9 个模块（含需历史数据的模块 5-9 和需空间数据的模块 4/8）。新增 `parcel_history_snapshot` 表导入 2018/2021/2024 三期历史数据；模块 4/8 用 PostGIS `ST_DWithin` 查询邻域地块。

**理由**: 用户要求「确保计算逻辑都实现」，降级到 3 模块不满足目标。

**替代方案**: 仅 3 模块降级 — 不满足用户要求，否决。

### D3: Model-5 RF 模型 — 构建时重训 + 提交 .joblib

**决策**: 构建脚本 `scripts/train_dose_rf_models.py` 从 xlsx 读取训练数据，`RandomForestRegressor(n_estimators=100, random_state=230)` 重训，`joblib.dump` 保存到 `data/model_artifacts/{upland|paddy}_dose_rf.joblib`，模型文件提交仓库。运行时延迟加载。

**理由**: 原始 notebook 未保存模型；构建时重训可复现；scikit-learn 为构建+运行时依赖。

### D4: Model-4 酸化常数 — 硬编码为函数默认参数

**决策**: 4 个产酸平衡函数的农作物常数（RPH/R/Y/S/Yp/Yk/Yca/Ymg/Sp/Sk/Sca/Smg/FertN/Ndep）保留为函数默认参数（与原始 `02_酸化模型计算.py` 一致），不同 land_type×fertilizer_type 用不同默认值。`pHtarget` 从 `ParcelInfo.target_ph` 读取覆盖默认。

**理由**: 常数来自农学研究不常变；硬编码与原始逻辑完全一致；避免过度配置化。

### D5: 二级农业区代码 — area_code→ejnyq 映射

**决策**: 在 `coefficients.py` 定义 `AREA_TO_REGION` 映射表（如 `"440281"→{"secondary":"NL","primary":"HN","ejnyq_idx":3}`），不修改 DB schema，运行时查表。乐昌(440281)属华南区(HN)/南岭丘陵山地林农区(NL, index 3)。

**理由**: ParcelInfo 有 area_code 但无 ejnyq；映射表避免 schema 变更；area_code 是稳定的行政区码。

### D6: 离散值映射 — 英文/中文双映射

**决策**: 保留原始 `DISCRETE_CN_MAP`（中文→代码），新增 `DISCRETE_EN_MAP`（英文→代码），因 DB 存英文值（"loam"→RT、"dry"→BM/US、"lower"→LHR）。映射时先尝试英文，再回退中文。

**理由**: OpenSpec spec 写「中文值转代码」但 DB 实际存英文，需修正。

## Detailed Design

### 1. 共享基础设施

#### 1.1 `framework/domain/calculations/coefficients.py`

移植自原始 `模型2/config.py`（EvaluationConfig）和 `模型3/mappings_config.py`：

```python
# area_code → 农业区映射
AREA_TO_REGION = {
    "440281": {"secondary": "NL", "primary": "HN", "ejnyq_idx": 3},  # 乐昌
    # 其他区域按需补充
}

# Model-2 系数（4 个二级农业区，移植自 EvaluationConfig）
# ejnyq_idx 0=MNY 闽南粤中, 1=YXG 粤西桂南, 2=QN 琼雷, 3=NL 南岭
MODEL2_COEFFICIENTS = {
    0: {"a": [...], "c": [...], "ut1": [...], "ut2": [...],
        "mem_zdgc": [...], "mem_psnl": [...], "mem_ggnl": [...],
        "mem_dxbw": [...], "mem_zdgx": [...], "weights": [...]},
    # 1, 2, 3 同结构
}

# Model-3 隶属度系数（按一级农业区 HN/CJ，移植自 COEFFICIENTS）
MODEL3_COEFFICIENTS = {"HN": {...}, "CJ": {...}}

# Model-3 权重（按二级农业区 MNY/YXG/NL/QN，移植自 WEIGHTS）
MODEL3_WEIGHTS = {"MNY": {...}, "YXG": {...}, "NL": {...}, "QN": {...}}

# 等级阈值（按一级农业区，移植自 GRADE_CONFIG）
GRADE_CONFIG = {"HN": ([bounds], [labels]), "CJ": ([bounds], [labels])}

# 障碍等级阈值（移植自 calc_obstacle_level）
OBSTACLE_THRESHOLDS = {...}

# 离散映射（原始中文 + 新增英文）
DISCRETE_CN_MAP = {...}  # 移植自 mappings_config.py
DISCRETE_EN_MAP = {
    "GCZD": {"loam": "RT", "sandy_loam": "SRT", "clay_loam": "NRT", ...},
    "GGNL": {"dry": "US", "irrigated": "FS", ...},
    "PSNL": {"dry": "BM", "irrigated": "CM", ...},
    "DXBW": {"lower": "LHR", "middle": "MPH", "upper": "UHR", ...},
    "ZDGX": {...},
}
```

#### 1.2 `ParcelDataAccessor._map_indicators_to_inputs(indicators, agent_id)`

```python
def _map_indicators_to_inputs(self, indicators: dict, agent_id: str) -> dict:
    """V3.0 snake_case → 模型输入字段统一映射。"""
    MAPPINGS = {
        "model-1": lambda ind: {**ind, "_stability_context": True},  # 原样 + 上下文
        "model-2": lambda ind: {
            "SJD": ind.get("soil_ph"), "YJZ": ind.get("organic_matter"),
            "YXL": ind.get("available_phosphorus"), "SXJ": ind.get("available_potassium"),
            "TRRZ": ind.get("bulk_density"), "YXTCHD": ind.get("topsoil_thickness"),
            "GCHD": ind.get("plow_layer_thickness"),
            "GCZD": self._to_code("GCZD", ind.get("soil_texture")),
            "GGNL": self._to_code("GGNL", ind.get("irrigation_condition")),
            "PSNL": self._to_code("PSNL", ind.get("drainage_capacity")),
            "DXBW": self._to_code("DXBW", ind.get("terrain_position")),
            "ZDGX": self._to_code("ZDGX", ind.get("soil_structure")),
        },
        "model-3": "同 model-2 字段映射",
        "model-4": lambda ind: {
            "SJD": ind.get("soil_ph"), "Hex": ind.get("exchangeable_hydrogen"),
            "Alex": ind.get("exchangeable_aluminum"),
        },
        "model-5": lambda ind: {
            "pH": ind.get("soil_ph"), "SOMbe": ind.get("organic_matter"),
            "AK": ind.get("available_potassium"), "AP": ind.get("available_phosphorus"),
            "TN": ind.get("total_nitrogen"),
        },
    }
    return MAPPINGS[agent_id](indicators)

def _to_code(self, indicator: str, value) -> str:
    """英文/中文值 → 代码（先英文后中文回退）。"""
    if value is None: return None
    from framework.domain.calculations.coefficients import DISCRETE_EN_MAP, DISCRETE_CN_MAP
    return DISCRETE_EN_MAP.get(indicator, {}).get(value) or DISCRETE_CN_MAP.get(indicator, {}).get(value)
```

#### 1.3 字段名修复

5 个 Agent 删除各自的 `_map_indicators_to_inputs`，改调 `ParcelDataAccessor._map_indicators_to_inputs(indicators, self.agent_id)`。

#### 1.4 种子数据补全（`scripts/verify_thematic_models_db.py`）

3 个测试地块 `soil_indicators` 补：
- `exchangeable_aluminum`（如 P-001=0.8, P-002=0.3, P-003=1.2 cmol/kg）
- `plow_layer_thickness`（如 15/18/12 cm）
- `soil_structure`（如 "loose"/"compact"/"interlayer"）

#### 1.5 Model-1 历史数据导入

新增 `parcel_history_snapshot` 表（V3.0 命名 + parcel_id 关联）：

```python
class ParcelHistorySnapshot(db.Model):
    __tablename__ = "parcel_history_snapshot"
    id = db.Column(db.Integer, primary_key=True)
    parcel_id = db.Column(db.String(64), db.ForeignKey("parcel_info.parcel_id"), nullable=False)
    survey_year = db.Column(db.Integer, nullable=False, comment="调查年份 2018/2021/2024")
    soil_indicators = db.Column(db.JSON, comment="该年度指标快照")
    quality_grade = db.Column(db.String(8), comment="该年度质量等级")
    composite_index = db.Column(db.Float, comment="该年度综合指数")
    created_at = db.Column(db.DateTime(timezone=True), server_default=db.func.current_timestamp())
    __table_args__ = (
        db.UniqueConstraint("parcel_id", "survey_year", name="uk_parcel_history_parcel_year"),
        db.Index("idx_parcel_history_year", "survey_year"),
    )
```

导入脚本 `scripts/import_history_snapshots.py`：用 `pyshp`/`geopandas` 读 `模型1_v2` 下 2018/2021/2024 Shapefile，按 parcel_id 关联写入。

### 2. Model-1 稳定性风险评价（9 模块）

`framework/domain/calculations/stability_calculation.py`，移植自 `模型1_耕地质量稳定性与退化风险_九模块总流程.py`：

| 模块 | 函数 | 公式 | 数据源 |
|------|------|------|--------|
| 1 | `calculate_boundary_safety` | `SAFE_ABS = clip((ZHQZ - qmax + grade*w)/w, 0, 1)`, w=(qmax-qmin)/10 | parcel_info + 分区统计 |
| 2 | `calculate_support_balance` | `BAL_ABS = 1 - sqrt(clip(v/d, 0, inf))`, v=加权方差, d=m*(1-m) | soil_indicators LSD/QZ |
| 3 | `calculate_key_criticality` | `KEY_ABS = 1 - clip(margin/c, 0, 1)`, KEY_FAC=argmax | soil_indicators + 隶属度 |
| 4 | `calculate_neighborhood_consistency` | 邻域等级加权一致性 | **PostGIS ST_DWithin** |
| 5 | `calculate_history_trend` | `H_ABS = (1-delta)/2`, 历史斜率回归 | **parcel_history_snapshot** |
| 6 | `calculate_downgrade_risk` | 等级下降幅度概率 | parcel_history_snapshot |
| 7 | `calculate_factor_degradation` | 关键指标历史退化率 | parcel_history_snapshot |
| 8 | `calculate_degradation_clustering` | 邻域退化密度 | **PostGIS ST_DWithin** + history |
| 9 | `calculate_persistent_low_quality` | 连续低等级期数 | parcel_history_snapshot |

**PostGIS 邻域查询**：
```sql
SELECT parcel_id, quality_grade FROM parcel_info
WHERE ST_DWithin(geom, :center_geom, :radius_meters) AND parcel_id != :self_id
```

**LSD/QZ 派生**：模块 2/3 需隶属度和权重，调用 `grade_calculation.evaluate_land_quality()` 的中间结果。

### 3. Model-2 质量等级评价

`framework/domain/calculations/grade_calculation.py`，移植自 `模型2/evaluation.py` + `config.py`：

```python
# 原始 evaluation.py 用 1-based idx，峰型 idx in (1,5) = SJD/TRRZ。
# 本实现统一用 0-based idx 0-6 对应 SJD/YJZ/YXL/SXJ/TRRZ/YXTCHD/GCHD。
PEAK_TYPE_INDICES = {0, 4}  # SJD(pH) 和 TRRZ(容重) 为峰型，其余戒上型

def membership_numeric(u, a, c, ut1, ut2, idx):
    """数值指标隶属度（移植自 evaluation.py membership_numeric）。
    峰型(idx 0,4): 超出 [ut1,ut2] 为 0，区间内 1/(1+a*(u-c)^2)。
    戒上型(其他): <=ut1 为 0，[ut1,c) 用公式，>=c 为 1.0（无上限）。"""
    if u is None:
        return 0.0
    if idx in PEAK_TYPE_INDICES:  # 峰型（SJD pH, TRRZ 容重）
        if u <= ut1 or u >= ut2:
            return 0.0
        return 1.0 / (1.0 + a * (u - c) ** 2)
    else:  # 戒上型
        if u <= ut1:
            return 0.0
        if u < c:
            return 1.0 / (1.0 + a * (u - c) ** 2)
        return 1.0

def membership_concept(code, lookup_table):
    """概念指标隶属度。lookup_table 以字符串代码为键（RT/FS/CM 等）。"""
    return lookup_table.get(code, 0.0)

def evaluate_land_quality(indicators, area_code):
    ejnyq_idx = AREA_TO_REGION[area_code]["ejnyq_idx"]
    primary = AREA_TO_REGION[area_code]["primary"]
    coef = MODEL2_COEFFICIENTS[ejnyq_idx]
    # 7 个数值指标（SJD/YJZ/YXL/SXJ/TRRZ/YXTCHD/GCHD）
    numeric_abbrs = ["SJD", "YJZ", "YXL", "SXJ", "TRRZ", "YXTCHD", "GCHD"]
    memberships = [membership_numeric(indicators[abbr], coef["a"][i], coef["c"][i],
                                      coef["ut1"][i], coef["ut2"][i], i)
                   for i, abbr in enumerate(numeric_abbrs)]
    # 5 个概念指标（GCZD/GGNL/PSNL/DXBW/ZDGX），mem_* 表在 coefficients.py 中
    # 已从原始 list 索引(1-12)转为字符串代码为键的 dict（如 {"RT": 1.0, "SRT": 0.75, ...}）
    concept_specs = [("GCZD", "mem_zdgc"), ("GGNL", "mem_ggnl"),
                     ("PSNL", "mem_psnl"), ("DXBW", "mem_dxbw"), ("ZDGX", "mem_zdgx")]
    memberships += [membership_concept(indicators[abbr], coef[mem_key])
                    for abbr, mem_key in concept_specs]
    quality_index = sum(m * w for m, w in zip(memberships, coef["weights"]))
    grade = determine_grade(quality_index, GRADE_CONFIG[primary])
    return quality_index, grade, memberships
```

### 4. Model-3 障碍诊断

`framework/domain/calculations/obstacle_calculation.py`，移植自 `模型3/calculatorall.py` + `mappings_config.py`：

```python
def calc_obstacle_level(indicator, value):
    """移植 calc_obstacle_level，按阈值返回 重度/中度/轻度/无障碍。"""
    # SJD: <=4.5 or >9.5 重度; <=5.5 or >8.5 中度; <6.5 or >7.5 轻度; 6.5-7.5 无
    # YJZ: <=10/20/25; YXL: <=10/20/35; SXJ: <=50/100/150
    # TRRZ: <=0.9 or >1.4 重度; GCHD: <=10/15/20; YXTCHD: <60/80/100
    # 概念指标按代码映射

def calc_obstacle_degree(memberships, weights):
    zads = [(1 - m) * w for m, w in zip(memberships, weights)]
    total = sum(zads)
    return [z / total for z in zads] if total > 0 else [0.0] * len(zads)

def diagnosis(obstacle_degrees, indicators):
    pairs = sorted(zip(indicators, obstacle_degrees), key=lambda x: x[1], reverse=True)
    primary = [ind for ind, deg in pairs if deg >= 0.20]
    secondary = [ind for ind, deg in pairs if 0.10 <= deg < 0.20]
    if not primary: obstacle_type = "无明显障碍"
    elif len(primary) == 1 and not secondary: obstacle_type = "单一障碍"
    else: obstacle_type = "多障碍"
    return obstacle_type, primary, secondary
```

### 5. Model-4 酸化改良

`framework/domain/calculations/acidification_calculation.py`，移植自 `02_酸化模型计算.py`（公式已精确核对）：

```python
import math

def paddy_urea(SJD, Hex, Alex, RPH=5.5, R=1893, Y=5109, S=5109, Yp=0.35, Yk=0.19,
               Yca=0.03, Ymg=0.12, Sp=0.176, Sk=1.99, Sca=0.54, Smg=0.212,
               FertN=180, Ndep=47.6, pHtarget=6.5):
    Adep = 10**(-RPH) * 667 * (R/1000) * 1000 * 15
    Hgrain = -Y*Yp*1000/100/30.97 + Y*Yk*1000/100/39.1 + Y*Yca*1000/100*2/40.08 + Y*Ymg*1000/100*2/24.305
    Hstraw = -S*Sp*1000/100/30.97 + S*Sk*1000/100/39.1 + S*Sca*1000/100*2/40.08 + S*Smg*1000/100*2/24.305
    Acrop = Hgrain + Hstraw
    Anit = 2.221 * math.exp(0.0048*(FertN+Ndep)) * 1000/14
    Ano3_runoff = (Ndep - (0.16*Ndep + 2.97)) * 1000/14 * 2
    Avol = (Ndep - (0.16*Ndep + 2.97)) * 1000/14 * 2
    ANcy = Anit + Ano3_runoff + Avol  # Ano3_crop=0
    Aagri = Adep + Acrop + ANcy
    Aback = (6.25*10**(9-SJD) - 6.25*10**(9-pHtarget) + 2.5*Hex*10**7 + 2.5*Alex*10**7) / 1000
    YTK = (Aback + 0.8*Aagri) / 17.042 * 0.6
    MBNT = 0.1*Aagri/1.89 + Alex*590*15
    return {"Adep": Adep, "Acrop": Acrop, "ANcy": ANcy, "Aagri": Aagri,
            "Aback": Aback, "YTK": YTK, "MBNT": MBNT}

# paddy_compound / upland_urea / upland_compound 同结构，差异：
# - upland: Y=6700, S=6968, Yp=0.41, Yk=0.44, Anit=2.7*exp(0.0088*...), pHtarget=6.0
# - YTK 系数: paddy_urea=0.6, paddy_compound=0.6, upland_urea=0.77, upland_compound=0.7
# - MBNT: paddy_compound=0.15*Aagri/1.89, upland_urea=...*0.2, upland_compound=...*0.3
# - compound 函数含 Ano3_crop 和复合肥径向/挥发分项

FUNCTION_SELECTOR = {
    ("paddy", "urea"): paddy_urea,
    ("paddy", "compound"): paddy_compound,
    ("upland", "urea"): upland_urea,
    ("upland", "compound"): upland_compound,
}
```

`pHtarget` 从 `ParcelInfo.target_ph` 读取覆盖默认值。

### 6. Model-5 有机质培肥（RF）

`scripts/train_dose_rf_models.py`（构建时）：
```python
import pandas as pd, joblib
from sklearn.ensemble import RandomForestRegressor

def train_and_save(xlsx_path, output_path):
    df = pd.read_excel(xlsx_path)
    X = df[["pH", "SOMbe", "AK", "AP", "TN"]]
    y = df["Dose"]
    rf = RandomForestRegressor(n_estimators=100, random_state=230)
    rf.fit(X, y)
    joblib.dump(rf, output_path)

train_and_save(".../SG旱地-Dose-RF_Manual_splits.xlsx", "data/model_artifacts/upland_dose_rf.joblib")
train_and_save(".../SG水田-Dose-RF_Manual_splits.xlsx", "data/model_artifacts/paddy_dose_rf.joblib")
```

`framework/domain/calculations/organic_matter_calculation.py`（运行时）：
```python
_model_cache = {}

def predict_dose(indicators, land_type):
    model_path = f"data/model_artifacts/{land_type}_dose_rf.joblib"
    if not scikit_learn_available() or not os.path.exists(model_path):
        return degrade_to_rules(indicators), True  # simulated=True
    if model_path not in _model_cache:
        _model_cache[model_path] = joblib.load(model_path)
    rf = _model_cache[model_path]
    features = [[indicators["pH"], indicators["SOMbe"], indicators["AK"],
                 indicators["AP"], indicators["TN"]]]
    dose = float(rf.predict(features)[0])
    return dose, False  # simulated=False
```

## Testing Strategy

### 单元测试（`tests/calculations/`）

| 测试文件 | 覆盖范围 | 关键断言 |
|----------|----------|----------|
| `test_coefficients.py` | area_code→ejnyq、英文→代码、系数查表 | 440281→NL/HN/idx3; loam→RT; dry→BM |
| `test_grade_calculation.py` | 峰型/戒上型隶属度、概念查找、加权和、等级 | SJD 在 [ut1,ut2] 边界; TRRZ u<c vs u>=c; quality_index∈[0,1]; grade 1-10 |
| `test_obstacle_calculation.py` | 障碍等级阈值、障碍度和为1、诊断分类 | pH4.5→重度; 有机质25→无; 障碍度和≈1.0; 多障碍/单一/无明显 |
| `test_acidification_calculation.py` | 4 函数对照原始输出 | 固定 SJD/Hex/Alex 断言 YTK/MBNT（容差 1e-2） |
| `test_organic_matter_calculation.py` | RF 加载、特征映射、降级 | joblib 可用时 simulated=False; 不可用时降级 |
| `test_stability_calculation.py` | 9 模块公式 | 边界安全度 clip; 均衡度; 邻域 PostGIS mock; 历史回归 |

### 集成测试（每 Agent 全链路）

- 用补全后的 3 个测试地块（P-VERIFY-001/002/003）
- 断言：`status=ok`、`data_source=db`、`simulated=False`、结果非占位、持久化成功

### 回归测试

- 现有 566 passed 套件保持绿色
- `scripts/verify_thematic_models_db.py` 重新验证 5 模型 × 3 地块

## Spec Patches（设计发现，需回写 OpenSpec delta spec）

1. **farmland-stability-risk-evaluation/spec.md**：ADD 模块 4-9 Requirement（邻域一致性 PostGIS、历史趋势/掉级/退化集聚/持续低质依赖 parcel_history_snapshot）+ 历史数据导入 Requirement
2. **professional-model-agents/spec.md**：离散指标映射「中文值转代码」修正为「英文/中文值转代码」（DB 存英文值）
3. **farmland-quality-grade-evaluation/spec.md** + **farmland-obstacle-diagnosis-model/spec.md**：ADD area_code→ejnyq 映射 Requirement
4. **openspec/changes/.../design.md D2**：从「降级 3 模块」更新为「实现全 9 模块 + 历史数据导入」

## Dependencies

- **新增**：`scikit-learn`（构建+运行时，RF）、`pyshp`/`geopandas`（一次性导入脚本）
- **已有**：PostGIS（模块 4/8 空间查询）、`sqlalchemy`/`geoalchemy2`（ORM）
- **数据库**：新增 `parcel_history_snapshot` 表（不改现有 schema）
- **模型文件**：`data/model_artifacts/{upland|paddy}_dose_rf.joblib`（提交仓库）

## Risks

| 风险 | 缓解 |
|------|------|
| Model-1 历史数据 Shapefile parcel_id 与 DB parcel_id 不一致 | 导入脚本建立映射表，缺失地块降级 |
| PostGIS 邻域查询性能 | GIST 索引已存在；限制 radius |
| RF 重训结果与原始 notebook 不完全一致 | 固定 random_state=230；对照原始评估 RMSE |
| 离散值英文→代码映射不完整 | 未知值降级为默认隶属度 0.5 |
| Model-2/3 系数按一级区(HN/CJ)但权重按二级区(MNY/YXG/NL/QN) | coefficients.py 明确区分两层 |
