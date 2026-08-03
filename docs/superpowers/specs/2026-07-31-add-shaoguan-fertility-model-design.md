---
comet_change: add-shaoguan-fertility-model
role: technical-design
canonical_spec: openspec
archived-with: 2026-07-31-add-shaoguan-fertility-model
status: final
---

# Design Doc: 韶关区域肥力 Dose RF 模型集成

## 1. 背景与目标

现有 model-6（`framework/domain/other_models/model_6.py`）使用单全局 ExtraTreesRegressor 模型预测 SOC 和 Dose，Dose 模型仅 45 个训练样本、测试 R²=0.47。模型提供方提供了韶关（SG）区域专用 RandomForestRegressor Dose 预测模型，按旱地（upland, 185 样本）和水田（paddy）分别训练，数据量更大、区域适配性更强。项目默认 area_code="lechang"（乐昌，韶关下辖），本就在韶关区域运营。

**目标**：在不破坏现有全局 ETR 模型行为的前提下，为韶关区域接入 SG RF Dose 模型，提升本地 Dose 预测质量。

## 2. 技术决策

### D1: 签名设计 — 方案 A

```python
def model_6_execution(input_data: Dict[str, Any], land_type: str = "upland") -> Dict[str, Any]:
```

- `area_code` 从 `input_data` 读取（已在 context data 中自然流转，无需额外传递）
- `land_type` 作为显式可选参数（新概念，显式更清晰），默认 "upland"
- 向后兼容：现有调用方不传 `land_type` 时默认 upland，不传 `area_code` 时走全局 ETR

### D2: 区域路由

```python
SHAOGUAN_AREA_CODES = {"lechang"}  # 可扩展

area_code = (input_data or {}).get("area_code", "")
is_shaoguan = area_code.lower() in SHAOGUAN_AREA_CODES
```

- 命中韶关 → Dose 走 SG RF（按 land_type 选子模型），SOC 走全局 ETR
- 未命中 → Dose 和 SOC 均走全局 ETR（行为不变）

### D3: SG RF 模型惰性加载

镜像现有 ETR 的 double-checked locking 模式：

```python
_SG_UPLAND_MODEL = None
_SG_PADDY_MODEL = None
_SG_UPLAND_META = None
_SG_PADDY_META = None
_SG_UPLAND_LOAD_FAILED = False
_SG_PADDY_LOAD_FAILED = False
# 复用现有 _LOAD_LOCK

def _ensure_sg_model_loaded(land_type: str) -> bool:
    """按 land_type 惰性加载对应 SG RF 模型，返回是否加载成功"""
```

模型文件路径：
- `data/fertility/models/sg_dose_upland_rf_model.joblib` + `sg_dose_upland_metadata.json`
- `data/fertility/models/sg_dose_paddy_rf_model.joblib` + `sg_dose_paddy_metadata.json`

### D4: SOMbe→SOCbe 输入层映射

```python
def _normalize_input(input_data: Dict[str, Any]) -> Dict[str, Any]:
    """规范化输入字段名：SOMbe → SOCbe，strip 尾随空格"""
    normalized = {}
    for k, v in (input_data or {}).items():
        if v is None:
            continue
        key = "SOCbe" if k.strip() == "SOMbe" else k.strip()
        normalized[key] = v
    return normalized
```

在 `model_6_execution` 开头调用，使全局 ETR 和 SG RF 模型均消费 `SOCbe` 特征名。SG 模型训练时也将 `SOMbe` 列重命名为 `SOCbe`，确保 metadata.json 中 feature_names 一致。

### D5: 训练脚本扩展

```
python scripts/train_fertility_models.py        # 全局 ETR（现有，不变）
python scripts/train_fertility_models.py --sg   # SG RF 旱地+水田
python scripts/train_fertility_models.py --all  # 全部
```

SG 训练函数：
- 读取预切分 xlsx（Xtrain/Xtest/Ytrain/Ytest sheets）
- 将 `SOMbe` 列重命名为 `SOCbe`
- 训练 `RandomForestRegressor(n_estimators=100, random_state=230)`
- 保存 .joblib + metadata.json（含 model_type/feature_names/metrics/training_samples）
- 打印 5CV R² 和测试集 R²

## 3. model_6_execution 重构细节

现有函数流程保留，在关键位置插入区域路由：

```
model_6_execution(input_data, land_type="upland")
  │
  ├─ 1. _normalize_input(input_data)  ← 新增：SOMbe→SOCbe
  │
  ├─ 2. 检查 sklearn → fallback（不变）
  │
  ├─ 3. 区域判定：is_shaoguan = area_code.lower() in SHAOGUAN_AREA_CODES
  │
  ├─ 4. SOC 预测（始终全局 ETR，不变）：
  │     ├─ _ensure_models_loaded() → soc_etr_model
  │     └─ _prepare_features → soc_model.predict()
  │
  ├─ 5. Dose 预测（区域路由）：
  │     ├─ is_shaoguan=True：
  │     │   ├─ _ensure_sg_model_loaded(land_type)
  │     │   ├─ _prepare_features(sg_meta) → sg_model.predict()
  │     │   └─ dose_warning = "韶关{旱地|水田} RF 模型 R²=..."
  │     └─ is_shaoguan=False：
  │         ├─ _ensure_models_loaded() → dose_etr_model（不变）
  │         └─ _prepare_features → dose_model.predict()（不变）
  │
  └─ 6. 构造响应（land_type 未传时追加默认提示）
```

## 4. FertilityMLAgent 适配

```python
def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
    land_type = task.get("land_type", "upland")
    result = model_6_execution(task or {}, land_type=land_type)
    return MockDataLoader.mark_simulated({...})
```

`area_code` 已在 task（context data）中，无需额外传递。

## 5. API 层适配

请求 payload 新增可选 `land_type` 字段，经 core_engine adapter 透传到 FertilityMLAgent 的 context。

## 6. 测试策略

| 测试 | 方法 | 验证点 |
|------|------|--------|
| 非韶关回归 | area_code="other" | Dose+SOC 走全局 ETR，行为不变 |
| 韶关旱地 | area_code="lechang", land_type="upland" | Dose 走 SG upland RF，SOC 走 ETR |
| 韶关水田 | area_code="lechang", land_type="paddy" | Dose 走 SG paddy RF |
| SOMbe 映射 | input 含 SOMbe | _prepare_features 收到 SOCbe |
| land_type 默认 | 未传 land_type | 默认 upland + warning 提示 |
| SG fallback | mock 模型文件缺失 | status="fallback" |
| FertilityMLAgent | task 含 area_code+land_type | 正确透传到 model_6_execution |

Mock 策略：使用 monkeypatch 替换 `_ensure_sg_model_loaded` 返回 mock 模型对象，避免依赖真实 .joblib 文件。

## 7. 边界条件

| 条件 | 处理 |
|------|------|
| area_code 大小写 | `.lower()` 统一 |
| area_code 未传 | 空字符串 → 不命中 → 全局 ETR |
| land_type 非法值 | 默认 upland + dose_warning 提示 |
| SG 模型文件缺失 | `_SG_*_LOAD_FAILED=True` → fallback 响应 |
| SG 水田样本 <30 | metadata 标注低置信度，dose_warning 提示 |

