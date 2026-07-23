---
comet_change: add-model-6-fertility-ml
role: technical-design
canonical_spec: openspec
archived-with: 2026-07-23-add-model-6-fertility-ml
status: final
---

# Design Doc: add-model-6-fertility-ml

> 本文档是对 OpenSpec `openspec/changes/add-model-6-fertility-ml/` 中 proposal.md / design.md / tasks.md 的深度技术细化，聚焦实现细节、技术风险、测试策略与边界条件。需求事实源仍为 OpenSpec delta spec。

## 1. 架构总览

### 1.1 模块划分

```
framework/domain/other_models/
├── __init__.py                    # 保持 from .model_6 import model_6_execution（向后兼容）
└── model_6.py                     # ML 引擎层：lazy load + predict + fallback + range check

framework/agents/specialized/
├── __init__.py                    # 移除 ComprehensiveImprovementAgent，导出 FertilityMLAgent
├── fertility_ml_agent.py         # Agent 层：包装 model_6_execution，处理问答分支
└── (comprehensive_agent.py 删除)

scripts/
└── train_fertility_models.py      # 训练脚本：notebook → CLI（直接用最优参数，不重跑网格搜索）

data/fertility/
├── ML-data-SOC-RF_Manual_splits.xlsx     # 训练数据（SOC，10因子，52 训练样本）
├── ML-data-Dose-RF-Manual_splits.xlsx    # 训练数据（Dose，9因子）
├── 变量注释.xlsx                          # 特征字典
└── models/
    ├── soc_etr_model.joblib              # 训练好的 SOC ETR 模型（~300KB）
    ├── soc_metadata.json                 # SOC 元数据
    ├── dose_etr_model.joblib             # 训练好的 Dose ETR 模型（~3MB）
    └── dose_metadata.json                # Dose 元数据
```

### 1.2 组件职责边界

| 组件 | 输入 | 输出 | 依赖 | 不做 |
|---|---|---|---|---|
| `model_6.py` | `Dict[str, Any]` 特征字典 | `Dict[str, Any]` 预测结果字典 | sklearn, joblib | 不处理问答、不格式化文本、不知道 agent 存在 |
| `FertilityMLAgent` | `task: Dict`, `question: str` | `Dict` 含 answer/evidence | `model_6_execution` | 不直接调用 sklearn、不处理路由 |
| `train_fertility_models.py` | xlsx 文件路径 | .joblib + .json 文件 | pandas, sklearn | 不被运行时依赖 |
| `AgentManager` | 用户输入 | 聚合响应 | specialized agents | 不感知 model-6 是 ML 还是规则 |

### 1.3 依赖方向

```
pyproject.toml
   ├── scikit-learn >=1.3.0    (model_6.py 运行时硬依赖，缺失降级)
   ├── joblib >=1.3.0          (model_6.py 运行时硬依赖，缺失降级)
   ├── pandas >=2.0            (train_fertility_models.py 训练时)
   └── openpyxl >=3.1          (train_fertility_models.py 训练时)

framework/agents/specialized/fertility_ml_agent.py
   └── framework/domain/other_models/model_6.py
       └── data/fertility/models/*.joblib + *.json
```

## 2. 运行时行为

### 2.1 模块加载与首次预测时序

```
应用启动
  ↓
import framework.domain.other_models.model_6
  ├─ try: import sklearn, joblib → _SKLEARN_AVAILABLE = True
  ├─ except ImportError: _SKLEARN_AVAILABLE = False
  ├─ _SOC_MODEL = None, _DOSE_MODEL = None  (未加载)
  ├─ _SOC_META = None, _DOSE_META = None
  ├─ _SOC_LOAD_FAILED = False, _DOSE_LOAD_FAILED = False
  └─ _LOAD_LOCK = threading.Lock()  (保护并发首次加载)
  ↓
首次调用 model_6_execution(input_data)
  ├─ if not _SKLEARN_AVAILABLE → 走 fallback 分支（reason="sklearn_missing"）
  ├─ if _SOC_MODEL is None and not _SOC_LOAD_FAILED:
  │    with _LOAD_LOCK:
  │      if _SOC_MODEL is None and not _SOC_LOAD_FAILED:  (double-checked locking)
  │        try: 加载 soc_etr_model.joblib + soc_metadata.json
  │        except: _SOC_LOAD_FAILED = True, logger.exception(...)
  ├─ if _DOSE_MODEL is None and not _DOSE_LOAD_FAILED: 同上加载 dose
  ├─ if _SOC_LOAD_FAILED or _DOSE_LOAD_FAILED → fallback (reason="model_file_missing")
  └─ 执行预测
```

**关键点**：
- 模块导入零文件 IO（仅 try import sklearn）
- 首次调用触发加载，`threading.Lock` + double-checked locking 保证线程安全
- 加载失败后**不重试**（`_SOC_LOAD_FAILED = True`），后续直接走 fallback，避免每次调用都尝试加载失败
- 模型文件路径用 `Path(__file__).resolve().parents[3] / "data" / "fertility" / "models"` 计算项目相对路径（model_6.py → other_models → domain → framework → 项目根 = 3 跳）

### 2.2 特征准备算法（`_prepare_features`）

```python
FEATURE_RANGES = {
    "pH":              (3.0,    11.0),     # 土壤 pH 物理可能范围
    "SOCbe":           (0.0,    100.0),    # g/kg
    "TN":              (0.0,    10.0),     # g/kg
    "TP":              (0.0,    10.0),     # g/kg
    "TK":              (0.0,    100.0),    # g/kg
    "AP":              (0.0,    200.0),    # mg/kg
    "AK":              (0.0,    500.0),    # mg/kg
    "Gap":             (-10.0,  50.0),     # g/kg，理论上可为负
    "Dose":            (0.0,    1000.0),   # t/ha
    "Fertilizer type": (1,      2),        # 枚举：1=秸秆, 2=有机肥
}

def _prepare_features(input_data, feature_names, feature_means):
    """
    输入：用户提供的特征字典（key 可能含/不含尾随空格，可能缺字段）
    输出：(feature_df[1, len(feature_names)], imputed_list, out_of_range_list)
    """
    # 1. 规范化 input_data 的 key（strip 尾随空格，兼容 "TN " / "TN"）
    normalized = {k.strip(): v for k, v in (input_data or {}).items() if v is not None}
    
    # 2. 按 feature_names 顺序构造一行
    row, imputed, out_of_range = {}, [], []
    for fname in feature_names:
        fname_stripped = fname.strip()
        if fname_stripped in normalized:
            try:
                value = float(normalized[fname_stripped])
                lo, hi = FEATURE_RANGES.get(fname_stripped, (None, None))
                if lo is not None and (value < lo or value > hi):
                    out_of_range.append({"feature": fname, "value": value, "valid_range": [lo, hi]})
                    # 越界字段也用均值填充，但记录到 out_of_range
                    row[fname] = feature_means[fname]
                    imputed.append(fname)
                else:
                    row[fname] = value
                continue
            except (ValueError, TypeError):
                pass  # 转换失败走填充
        # 缺失 / 转换失败 → 用均值填充
        row[fname] = feature_means[fname]
        imputed.append(fname)
    
    # 3. 构造 DataFrame，列名严格按 feature_names 顺序
    return pd.DataFrame([row], columns=feature_names), imputed, out_of_range
```

**关键点**：
- 特征名规范化在 input 层做 strip，**模型文件内保存的 feature_names 保持原始含空格形式**（`"TN "`、`"TP "`），与训练时 Xtrain.columns 一致
- 类型强制 `float()`：处理用户传 `"1.5"` 字符串或 `1` int 的情况
- `Fertilizer type` 用户传 `1` 或 `2`（int），强制转 `float` 后 ETR 仍能正确预测（树模型对 int/float 不敏感）
- 越界字段被记录到 `out_of_range` 列表，同时在 `imputed` 中标注（用均值填充）

### 2.3 预测调用流程

```python
def model_6_execution(input_data: Dict[str, Any]) -> Dict[str, Any]:
    try:
        # 1. 检查 sklearn 可用性
        if not _SKLEARN_AVAILABLE:
            return _fallback_response(input_data or {}, reason="sklearn_missing")
        
        # 2. 检查模型加载状态（首次触发加载）
        if not _ensure_models_loaded():
            return _fallback_response(input_data or {}, reason="model_file_missing")
        
        # 3. 准备 SOC 特征（10 因子）
        soc_df, soc_imputed, soc_oor = _prepare_features(
            input_data or {}, _SOC_META["feature_names"], _SOC_META["feature_means"]
        )
        
        # 4. 准备 Dose 特征（9 因子，去掉 Dose 自身）
        dose_input = {k: v for k, v in (input_data or {}).items() if k.strip() != "Dose"}
        dose_df, dose_imputed, dose_oor = _prepare_features(
            dose_input, _DOSE_META["feature_names"], _DOSE_META["feature_means"]
        )
        
        # 5. 范围校验：任一越界即拒绝
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
                "model_version": "ETR_v1_20260713",
            }
        
        # 6. 执行预测
        soc_pred = float(_SOC_MODEL.predict(soc_df)[0])
        dose_pred = float(_DOSE_MODEL.predict(dose_df)[0])
        
        # 7. 构造响应（confidence 保留 2 位小数与 spec 一致）
        return {
            "status": "success",
            "soc_prediction": round(soc_pred, 4),
            "soc_confidence": round(_SOC_META["metrics"]["test_r2"], 2),  # 0.91
            "dose_prediction": round(dose_pred, 4),
            "dose_confidence": round(_DOSE_META["metrics"]["test_r2"], 2),  # 0.47
            "dose_warning": "Dose 模型 R²=0.47，预测结果仅供参考，建议结合田间试验校准",
            "imputed_features": sorted(set(soc_imputed + dose_imputed)),
            "imputation_applied": bool(soc_imputed or dose_imputed),
            "model_version": "ETR_v1_20260713",
        }
    
    except Exception as e:
        logger.exception(f"model_6_execution unexpected error: {e}")
        return _fallback_response(input_data or {}, reason="unexpected_error")
```

**关键点**：
- `soc_confidence` / `dose_confidence` 来自元数据 `test_r2`，round 到 2 位小数与 OpenSpec spec 一致（0.91 / 0.47）
- SOC 和 Dose **独立预测**，互不依赖（Dose 模型不消费 SOC 预测值，与 notebook 一致）
- 三层异常防线：特征准备层（per-field try/except）、预测层（model.predict 调用）、顶层（model_6_execution 整体 try/except）

### 2.4 Fallback 决策树

```
input_data 进入 model_6_execution
  ↓
[1] sklearn 可用？──No──→ fallback_reason="sklearn_missing"
  ↓ Yes
[2] 模型文件加载成功？──No──→ fallback_reason="model_file_missing"
  ↓ Yes
[3] 输入特征范围校验通过？──No──→ status="rejected", reason="input_out_of_range"
  ↓ Yes
[4] 正常预测路径（status="success"）
```

**Fallback 响应统一结构**：
```python
def _fallback_response(input_data, reason):
    return {
        "status": "fallback",
        "soc_prediction": _SOC_META["feature_means"].get("SOCbe", 12.0) if _SOC_META else 12.0,
        "soc_confidence": 0.3,
        "dose_prediction": _DOSE_META["feature_means"].get("Dose", 100.0) if _DOSE_META else 100.0,
        "dose_confidence": 0.3,
        "dose_warning": "模型不可用，返回训练集均值估算" if reason != "input_out_of_range" else "输入值越界，未执行预测",
        "imputed_features": [],
        "imputation_applied": False,
        "model_version": "ETR_v1_20260713",
        "fallback_reason": reason,
    }
```

**关键点**：
- Fallback 时仍返回完整字段结构（不缺字段），保证 API 契约一致
- Fallback 用训练集均值作为粗估（来自 metadata），**不是 0 或 null**
- 任一模型文件缺失即整体降级（不混合正常+fallback），避免 agent answer 逻辑复杂化

### 2.5 并发请求处理

- **加载阶段**：`threading.Lock` 保证模型只加载一次
- **预测阶段**：`sklearn` 的 `ExtraTreesRegressor.predict()` 是**只读操作**，无状态变更，**线程安全**，无需加锁
- **并发模型**：waitress WSGI 8 线程 → 8 个并发预测可并行，每个预测 < 100ms，无瓶颈
- **不需要**：进程级互斥、模型实例池、预测结果缓存

## 3. FertilityMLAgent 设计

### 3.1 类定义

```python
class FertilityMLAgent(BaseAgent):
    model_id = "model-6"
    domain = "fertility_ml"
    description = "基于 ML 的耕地肥力 SOC/Dose 预测"
    
    def __init__(self):
        super().__init__()
        self.dependencies = []  # 独立 ML 模型，不再依赖 model-4/5
```

### 3.2 execute 方法

```python
def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
    # task 直接作为特征字典传入 model_6_execution
    result = model_6_execution(task or {})
    return {
        "status": result["status"],           # "success" | "fallback" | "rejected"
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
            "reason": result.get("reason"),  # rejected 时的原因
            "out_of_range_features": result.get("out_of_range_features"),
        }
    }
```

### 3.3 answer_question 关键词优先级

```python
FERTILITY_KEYWORDS = [
    # 明确指向 SOC
    "有机碳", "SOC", "soc",
    # 明确指向 Dose
    "施用量", "施肥量", "施肥", "Dose", "dose", "剂量", "施多少肥",
    # 明确指向综合肥力诊断
    "肥力", "综合肥力",
    # 明确指向肥料类型
    "秸秆", "有机肥", "培肥",
]

def answer_question(self, question: str, context: Dict[str, Any]) -> Dict[str, Any]:
    # 调用 execute 获取预测值
    exec_result = self.execute(context.get("data", {}) or context.get("task", {}) or {})
    pred = exec_result["result"]
    
    q_lower = question.lower()  # 大小写不敏感
    
    # 优先级 1：明确问 Dose / 施用量
    if any(kw.lower() in q_lower for kw in ["施用量", "施肥量", "Dose", "剂量", "施多少肥", "施肥"]):
        return self._format_dose_only(pred, exec_result)
    
    # 优先级 2：明确问 SOC / 有机碳
    if any(kw.lower() in q_lower for kw in ["有机碳", "SOC"]):
        return self._format_soc_only(pred, exec_result)
    
    # 优先级 3：肥力 / 综合 / 其他
    return self._format_both(pred, exec_result)
```

**优先级规则**：Dose > SOC > 综合/默认。理由：用户问"施用量"时不需要 SOC（避免信息过载），用户问"肥力"是开放问题给完整诊断。

### 3.4 三种 answer 格式

```python
def _format_soc_only(self, pred, exec_result):
    if exec_result["status"] == "rejected":
        oor = exec_result["metadata"].get("out_of_range_features", [])
        oor_text = "; ".join([f"{f['feature']}={f['value']}（合法范围 {f['valid_range'][0]}-{f['valid_range'][1]}）" for f in oor])
        return {
            "answer": f"输入值异常，无法预测。越界特征：{oor_text}。请检查输入后重试。",
            "evidence": [],
            "sources": [],
        }
    
    confidence_text = f"（置信度 {pred['soc_confidence']:.0%}）" if exec_result["status"] == "success" else "（模型不可用，返回训练集均值估算）"
    return {
        "answer": f"基于 ML 预测，您的土壤有机碳（SOC）预测值约 {pred['soc_prediction']:.2f} g/kg{confidence_text}",
        "evidence": [
            {"metric": "soc_prediction", "value": pred["soc_prediction"], "unit": "g/kg"},
            {"metric": "soc_confidence", "value": pred["soc_confidence"]},
        ],
        "sources": [],  # ML 预测无文档来源
    }

def _format_dose_only(self, pred, exec_result):
    if exec_result["status"] == "rejected":
        # 同 _format_soc_only 的 rejected 处理
        ...
    
    confidence_text = f"（置信度 {pred['dose_confidence']:.0%}，{pred['dose_warning']}）" if exec_result["status"] == "success" else "（模型不可用，返回训练集均值估算）"
    return {
        "answer": f"基于 ML 预测，建议施肥量约 {pred['dose_prediction']:.2f} t/ha{confidence_text}",
        "evidence": [
            {"metric": "dose_prediction", "value": pred["dose_prediction"], "unit": "t/ha"},
            {"metric": "dose_confidence", "value": pred["dose_confidence"]},
        ],
        "sources": [],
    }

def _format_both(self, pred, exec_result):
    if exec_result["status"] == "rejected":
        # 同 _format_soc_only 的 rejected 处理
        ...
    
    imputation_note = "\n（注：部分特征用训练集均值填充，已标注于 imputed_features）" if pred["imputation_applied"] else ""
    fallback_note = "\n（模型不可用，以上为训练集均值估算）" if exec_result["status"] == "fallback" else ""
    
    return {
        "answer": (
            f"基于 ML 预测的综合肥力诊断：\n"
            f"- SOC（土壤有机碳）：{pred['soc_prediction']:.2f} g/kg（置信度 {pred['soc_confidence']:.0%}）\n"
            f"- Dose（施肥量）：{pred['dose_prediction']:.2f} t/ha（置信度 {pred['dose_confidence']:.0%}，{pred['dose_warning']}）"
            f"{imputation_note}{fallback_note}"
        ),
        "evidence": [
            {"metric": "soc_prediction", "value": pred["soc_prediction"], "unit": "g/kg"},
            {"metric": "soc_confidence", "value": pred["soc_confidence"]},
            {"metric": "dose_prediction", "value": pred["dose_prediction"], "unit": "t/ha"},
            {"metric": "dose_confidence", "value": pred["dose_confidence"]},
        ],
        "sources": [],
    }
```

**关键点**：
- `sources: []` 始终为空（ML 预测不引用文档，与 RAG 不同）
- 置信度用百分比显示（`0.91` → `91%`，使用 `:.0%` 格式化）
- `dose_warning` 在所有 Dose 相关响应中**都明文展示**
- fallback 时显式提示"模型不可用，返回训练集均值估算"
- rejected 时列出所有越界特征及合法范围

### 3.5 单位约定（修正 OpenSpec spec 中的歧义）

OpenSpec spec 中 Dose 单位写为 "kg/亩"，但根据 `变量注释.xlsx`：
- `Dose`：肥料累计添加量（**t/ha**）

**统一采用 t/ha**（与训练数据原始单位一致）。Spec Patch 中将修正这一描述。

## 4. AgentManager 集成

### 4.1 按需预测过滤

**核心变更**：`AgentManager` 不再无条件执行 model-6，**仅在问题与肥力相关时才触发预测**。**不修改 ROLE_AGENTS 路由表**（符合 Non-Goal）。

```python
# framework/agents/manager.py

FERTILITY_KEYWORDS = [
    "有机碳", "SOC", "soc",
    "施用量", "施肥量", "施肥", "Dose", "dose", "剂量", "施多少肥",
    "肥力", "综合肥力",
    "秸秆", "有机肥", "培肥",
]

def _should_execute_agent(self, agent_id: str, question: str) -> bool:
    """问题感知过滤：model-6 仅在肥力相关问题时执行"""
    if agent_id == "model-6":
        q_lower = question.lower()
        return any(kw.lower() in q_lower for kw in FERTILITY_KEYWORDS)
    return True  # 其他 agent 始终执行

def process(self, question: str, role: str, ...) -> Dict:
    routed = self._route(role)  # ["model-4", "model-5", "model-6"] for farmer
    order = self._topological_sort(routed)
    
    results = {}
    for agent_id in order:
        if not self._should_execute_agent(agent_id, question):
            results[agent_id] = {"status": "skipped", "reason": "question_not_related"}
            continue
        results[agent_id] = self.agents[agent_id].execute(task)
    
    return self._summarize(results, question)
```

**收益**：
- 非肥力问题不触发 model-6 执行（连模型加载都不触发，节省首次加载开销）
- 与未来其他 on-demand agent 模式一致
- `_should_execute_agent` 是通用扩展点

### 4.2 _register_agents 修改

```python
# specs 列表中 model-6 配置：
{"id": "model-6", "class_name": "FertilityMLAgent", "description": "耕地肥力 SOC/Dose ML 预测", "domain": "fertility_ml", "dependencies": []}
```

### 4.3 _load_real_agents 修改

```python
try:
    from .specialized.fertility_ml_agent import FertilityMLAgent
    real["model-6"] = FertilityMLAgent()
except ImportError:
    pass  # 回退到 _StubAgent
```

### 4.4 _summarize 修改

- 不再把 `zoning_suggestions` 平铺（已不存在）
- 在 summary 中追加 `model_6_status` 字段（"success"/"fallback"/"rejected"/"skipped"）
- 在 summary 中追加 `model_6_warning` 字段（dose_warning 内容，便于上层快速判断）
- 跳过时 `details["model-6"] = {"status": "skipped", "reason": "question_not_related"}`

### 4.5 /api/chat 响应中 model-6 字段的结构变化

**变更前**（ComprehensiveImprovementAgent）：
```json
{
  "details": {
    "model-6": {"diagnosis": "...", "zoning_suggestions": [...], "priority_measures": [...]}
  }
}
```

**变更后**（FertilityMLAgent）：
```json
{
  "details": {
    "model-6": {
      "status": "success",
      "result": {
        "soc_prediction": 12.3456,
        "soc_confidence": 0.91,
        "dose_prediction": 156.7890,
        "dose_confidence": 0.47,
        "dose_warning": "Dose 模型 R²=0.47，预测结果仅供参考...",
        "imputed_features": ["TN"],
        "imputation_applied": true
      },
      "metadata": {"model_version": "ETR_v1_20260713"}
    }
  }
}
```

**Breaking change**：`details["model-6"]` 字段结构变化。已确认无外部消费者（仅 stub 被注册）。

## 5. 训练脚本设计

### 5.1 CLI 接口

```bash
python scripts/train_fertility_models.py \
    --data-dir data/fertility \
    --output-dir data/fertility/models \
    --random-state-soc 0 \
    --random-state-dose 86
```

**简化策略**：**不重新跑 7 步网格搜索**，直接使用 notebook 已确定的最优超参数（hardcoded）。理由：7 步搜索耗时 30-60 秒但结果确定，用户已确认"不重新调优"（Non-Goal）。

### 5.2 最优超参数（hardcoded）

```python
SOC_BEST_PARAMS = {
    "n_estimators": 30, "max_depth": 10,
    "min_samples_split": 2, "min_samples_leaf": 1,
    "max_features": None, "criterion": "squared_error",
    "random_state": 0, "n_jobs": -1,
}
DOSE_BEST_PARAMS = {
    "n_estimators": 290, "max_depth": 10,
    "min_samples_split": 10, "min_samples_leaf": 1,
    "max_features": 0.7, "criterion": "friedman_mse",
    "random_state": 86, "n_jobs": -1,
}
```

### 5.3 metadata.json 完整 schema

```json
{
  "model_type": "ExtraTreesRegressor",
  "trained_at": "2026-07-18T10:30:00",
  "model_version": "ETR_v1_20260713",
  "hyperparameters": {
    "n_estimators": 30,
    "max_depth": 10,
    "min_samples_split": 2,
    "min_samples_leaf": 1,
    "max_features": null,
    "criterion": "squared_error",
    "random_state": 0
  },
  "metrics": {
    "cv_r2": 0.8916,
    "cv_rmse": 2.1454,
    "test_r2": 0.9096,
    "test_rmse": 2.2351
  },
  "feature_names": ["pH", "SOCbe", "TN ", "TP ", "TK ", "AP", "AK", "Gap", "Dose", "Fertilizer type"],
  "feature_means": {
    "pH": 7.85,
    "SOCbe": 12.34,
    "TN ": 0.78,
    ...
  },
  "training_samples": 52,
  "test_samples": 13
}
```

**关键点**：
- `feature_names` 保留原始含空格形式（`"TN "`、`"TP "`），与训练时 `Xtrain.columns` 一致
- `feature_means` 的 key 也保留含空格形式，便于 `_prepare_features` 直接索引
- `metrics.test_r2` 用于运行时 `soc_confidence` / `dose_confidence`，round 到 2 位小数

### 5.4 输出文件清单

```
data/fertility/models/
├── soc_etr_model.joblib        # SOC ETR 模型（~300KB）
├── soc_metadata.json           # SOC 元数据
├── dose_etr_model.joblib       # Dose ETR 模型（~3MB）
└── dose_metadata.json          # Dose 元数据
```

所有文件入库（不忽略）。模型文件大小总计 ~3.3MB，适合 git，无需 LFS。

### 5.5 .gitignore 调整

```gitignore
# 已有：忽略数据库
chroma_db/chroma.sqlite3
instance/development.db

# 新增：确保训练数据与模型文件入库（不忽略）
!data/fertility/
!data/fertility/**

# 忽略训练过程的临时文件（如有）
*.pkl.bak
__pycache__/
```

## 6. 错误处理与边界条件

### 6.1 输入特征异常情况矩阵

| 输入情况 | 处理方式 | 触发 fallback？ |
|---|---|---|
| `input_data = {}` 空字典 | 所有特征用训练集均值填充，正常预测（imputation_applied=true，imputed_features 列出全部 10 个） | 否 |
| `input_data = None` | 入口处 coerce 为 `{}`，走空字典路径 | 否 |
| 特征值是字符串 `"1.5"` | `_prepare_features` 内 `float()` 强制转换 | 否 |
| 特征值是字符串 `"abc"` | `float()` 抛 `ValueError` → 该字段用均值填充，加入 `imputed_features` | 否 |
| 特征值是 `None` | 视为缺失，用均值填充 | 否 |
| 特征值是 `np.nan` | 视为缺失，用均值填充 | 否 |
| 特征值超出合法范围（如 pH=99） | 加入 `out_of_range_features`，**整体拒绝** → `status: "rejected"` | 是（rejected） |
| `Fertilizer type` 传 `3` | 越界（合法范围 1-2），整体拒绝 | 是（rejected） |
| 未知特征名（如 `"foo": 1`） | 忽略，不报错（`_prepare_features` 只按 `feature_names` 取值） | 否 |

### 6.2 异常捕获层次

**三层防线**：
1. **特征准备层**：`_prepare_features` 内部 try/except 包裹每个特征的 `float()` 转换，单字段失败不阻塞整体
2. **预测层**：`model.predict()` 调用包含在顶层 try/except 中，失败走 fallback
3. **顶层**：整个 `model_6_execution` 用 try/except 兜底，捕获任何未预期异常 → `fallback_reason="unexpected_error"`

### 6.3 模型文件加载失败的处理

| 失败情况 | 处理 |
|---|---|
| `soc_etr_model.joblib` 缺失，`dose_etr_model.joblib` 存在 | **整体降级**（任一缺失即 `model_file_missing`），不混合正常+fallback |
| `soc_metadata.json` 缺失 | 整体降级（metadata 是预测的必需依赖） |
| `joblib.load` 抛异常（文件损坏） | 捕获后设置 `_SOC_LOAD_FAILED = True`，整体降级 |
| `metadata.json` JSON 解析失败 | 同上 |
| 元数据缺 `feature_names` 字段 | 同上 |

### 6.4 日志策略

```python
import logging
logger = logging.getLogger(__name__)

# 模块加载时
logger.info("model_6 module imported, sklearn_available=%s", _SKLEARN_AVAILABLE)

# 首次加载模型
logger.info("Loading SOC ETR model from %s", soc_model_path)
logger.info("SOC model loaded, feature_names=%s, test_r2=%.4f", meta["feature_names"], meta["metrics"]["test_r2"])

# 预测时
logger.debug("model_6_execution input: %s", input_data)  # debug 级别
logger.info("SOC prediction: %.4f, Dose prediction: %.4f", soc_pred, dose_pred)

# fallback 时
logger.warning("model_6 fallback: reason=%s, sklearn_available=%s", reason, _SKLEARN_AVAILABLE)

# 异常时
logger.exception("model_6 unexpected error")
```

### 6.5 文件路径解析

```python
from pathlib import Path

# model_6.py 位于 framework/domain/other_models/model_6.py
# data/fertility/models/ 位于项目根
_MODELS_DIR = Path(__file__).resolve().parents[3] / "data" / "fertility" / "models"
# parents[3]: model_6.py -> other_models -> domain -> framework -> project_root

_SOC_MODEL_PATH = _MODELS_DIR / "soc_etr_model.joblib"
_SOC_META_PATH = _MODELS_DIR / "soc_metadata.json"
_DOSE_MODEL_PATH = _MODELS_DIR / "dose_etr_model.joblib"
_DOSE_META_PATH = _MODELS_DIR / "dose_metadata.json"
```

避免硬编码绝对路径（project_memory 约束）。

## 7. 测试策略

### 7.1 测试文件组织

```
tests/
├── test_fertility_ml_prediction.py   # 新文件：model_6_execution 单元测试 + 集成测试
├── test_agent_specialized.py          # 修改：新增 FertilityMLAgent 测试
└── test_agent_manager.py              # 修改：新增 _should_execute_agent 测试
```

### 7.2 单元测试（mock sklearn/joblib，CI 零依赖）

**`test_fertility_ml_prediction.py`** —— 全部用 `monkeypatch`：

```python
class TestModel6Execution:
    def test_success_full_features(self, monkeypatch):
        """完整 10 特征 → status=success"""
    
    def test_success_partial_features_imputation(self, monkeypatch):
        """部分特征缺失 → imputation_applied=true, imputed_features 非空"""
    
    def test_fallback_sklearn_missing(self, monkeypatch):
        """sklearn 不可用 → status=fallback, fallback_reason=sklearn_missing"""
    
    def test_fallback_model_file_missing(self, monkeypatch, tmp_path):
        """模型文件缺失 → status=fallback, fallback_reason=model_file_missing"""
    
    def test_rejected_out_of_range(self, monkeypatch):
        """pH=99 → status=rejected, out_of_range_features 包含 pH"""
    
    def test_rejected_fertilizer_type_invalid(self, monkeypatch):
        """Fertilizer type=3 → status=rejected"""
    
    def test_empty_input_uses_all_means(self, monkeypatch):
        """空字典 → 全部特征用均值填充，imputed_features 列出全部 10 个"""
    
    def test_none_input_coerced_to_empty(self, monkeypatch):
        """None 输入 → coerce 为 {} 后走空字典路径"""
    
    def test_string_numeric_coercion(self, monkeypatch):
        """'1.5' 字符串 → float 转换成功"""
    
    def test_string_non_numeric_uses_mean(self, monkeypatch):
        """'abc' 字符串 → 转换失败，用均值填充"""
    
    def test_feature_name_with_trailing_space(self, monkeypatch):
        """用户传 'TN'，模型 feature_names 含 'TN ' → 正确匹配"""
    
    def test_unexpected_error_fallback(self, monkeypatch):
        """model.predict 抛异常 → status=fallback, fallback_reason=unexpected_error"""
```

### 7.3 集成测试（真实模型，可跳过）

```python
@pytest.mark.skipif(
    not (_SKLEARN_AVAILABLE and _SOC_MODEL_LOADED and _DOSE_MODEL_LOADED),
    reason="sklearn 或模型文件不可用"
)
class TestModel6Integration:
    def test_real_soc_prediction_in_range(self):
        """真实预测：典型土壤样本 → SOC 在 0-50 g/kg 合理范围"""
    
    def test_real_dose_prediction_in_range(self):
        """真实预测：Dose 在 0-1000 t/ha 合理范围"""
    
    def test_real_model_files_exist(self):
        """验证 .joblib 与 metadata.json 文件存在且可加载"""
```

### 7.4 Agent 测试

```python
class TestFertilityMLAgent:
    def test_execute_returns_status_result_metadata(self, monkeypatch):
        """execute 返回结构包含 status/result/metadata 三层"""
    
    def test_answer_question_dose_keywords(self, monkeypatch):
        """问'施用量' → 仅返回 Dose 预测"""
    
    def test_answer_question_soc_keywords(self, monkeypatch):
        """问'有机碳' → 仅返回 SOC 预测"""
    
    def test_answer_question_fertility_keywords(self, monkeypatch):
        """问'肥力' → 返回 SOC + Dose 综合诊断"""
    
    def test_answer_question_fallback_status(self, monkeypatch):
        """status=fallback → answer 标注'模型不可用，返回训练集均值估算'"""
    
    def test_answer_question_rejected_status(self, monkeypatch):
        """status=rejected → answer 标注越界特征"""
    
    def test_dependencies_empty(self):
        """dependencies == []，不依赖 model-4/5"""
```

### 7.5 AgentManager 测试

```python
class TestAgentManagerFertilityFilter:
    def test_should_execute_model6_fertility_question(self):
        """问'肥力' → _should_execute_agent('model-6', ...) = True"""
    
    def test_should_skip_model6_non_fertility_question(self):
        """问'pH' → _should_execute_agent('model-6', ...) = False"""
    
    def test_topological_sort_model6_no_dep(self):
        """model-6 dependencies=[]，不依赖 model-4/5"""
    
    def test_model6_skipped_in_details(self):
        """跳过时 details['model-6'] = {status: 'skipped', reason: ...}"""
```

### 7.6 测试运行命令

```bash
# 全部测试（CI）
python -m pytest tests/ -v

# 仅 model_6 单元测试（快速，无 sklearn 依赖）
python -m pytest tests/test_fertility_ml_prediction.py -v -k "not Integration"

# 集成测试（需 sklearn + 模型文件）
python -m pytest tests/test_fertility_ml_prediction.py -v -k "Integration"
```

## 8. Spec Patch（需回写 OpenSpec delta spec）

### 8.1 Patch 1: `specs/fertility-ml-prediction/spec.md`

**SOC 预测能力下新增 Scenario**：
```markdown
#### Scenario: 输入特征越界时拒绝预测
- **WHEN** 调用 `model_6_execution` 时 `input_data` 中任一特征值超出合法范围（如 pH=99、Fertilizer type=3）
- **THEN** 系统 SHALL 返回 `status` 字段值为 "rejected"，`reason` 字段值为 "input_out_of_range"，`out_of_range_features` 字段为列表，每个元素含 `feature`、`value`、`valid_range` 三个字段，`soc_prediction` 与 `dose_prediction` 为 null，不执行预测
```

**Dose 预测能力下新增 Scenario**：
```markdown
#### Scenario: Dose 预测时显式标注低置信度
- **WHEN** Dose 模型预测被执行且 `status` 为 "success"
- **THEN** 响应 SHALL 包含 `dose_warning` 字段，明文标注"Dose 模型 R²=0.47，预测结果仅供参考，建议结合田间试验校准"，`dose_confidence` 字段值为 0.47，单位为 t/ha（与训练数据原始单位一致）
```

### 8.2 Patch 2: `specs/professional-model-agents/spec.md`

**FertilityMLAgent 智能体下新增 Scenario**：
```markdown
#### Scenario: 非肥力相关问题跳过 model-6
- **WHEN** 农户角色提出的问题不包含肥力相关关键词（如"我的田 pH 如何"），且 `AgentManager` 路由到 model-6
- **THEN** `AgentManager._should_execute_agent` SHALL 返回 False，model-6 不被执行（不触发模型加载），`details["model-6"]` 字段值为 `{status: "skipped", reason: "question_not_related"}`
```

**FertilityMLAgent 智能体下新增 Scenario**：
```markdown
#### Scenario: 输入越界时返回拒绝响应
- **WHEN** `FertilityMLAgent.execute` 收到包含越界特征值的输入，`model_6_execution` 返回 `status: "rejected"`
- **THEN** Agent SHALL 在 `answer` 中明文标注越界特征和合法范围（如"输入值异常，无法预测。越界特征：pH=99.0（合法范围 3.0-11.0）"），不返回预测值
```

## 9. 实现顺序（与 tasks.md 对齐）

1. **数据准备与依赖声明**（tasks 1.x）：复制 xlsx，新增依赖，验证 .gitignore
2. **训练脚本**（tasks 2.x）：实现 `scripts/train_fertility_models.py`，生成 4 个文件
3. **model_6.py 真实实现**（tasks 3.x）：替换 stub，实现 lazy load + predict + fallback + range check
4. **FertilityMLAgent**（tasks 4.x）：实现 execute + answer_question 三分支
5. **AgentManager 调整**（tasks 5.x）：_should_execute_agent 过滤、_load_real_agents、_register_agents specs、dependencies=[]
6. **ComprehensiveImprovementAgent 清理**（tasks 6.x）：删除文件，搜索残留引用
7. **测试更新**（tasks 7.x）：单元测试 + 集成测试 + Agent 测试 + AgentManager 测试
8. **端到端验证**（tasks 8.x）：启动服务器，调用 /api/chat，验证响应结构

## 10. 风险与缓解

| 风险 | 缓解 |
|---|---|
| `details["model-6"]` 结构 breaking change | 已确认无外部消费者；测试覆盖新结构 |
| sklearn 安装增加容器体积 100-200MB | 接受；可选优化：使用 scikit-learn-minimal 或拆分镜像 |
| 关键词过滤可能漏掉某些肥力相关表述 | 测试覆盖常见问法；`FERTILITY_KEYWORDS` 列表可扩展 |
| Dose 模型 R²=0.47 低质量 | `dose_warning` 明文标注；`dose_confidence` 字段透传 |
| 训练数据仅 52 样本，泛化能力有限 | metadata 记录 `training_samples`；未来如有更多数据可重训 |
| 模型文件被误删 | fallback 机制兜底；metadata 与 model 配套校验 |

