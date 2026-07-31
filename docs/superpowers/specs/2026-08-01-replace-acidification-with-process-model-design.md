---
comet_change: replace-acidification-with-process-model
role: technical-design
canonical_spec: openspec
archived-with: 2026-07-31-replace-acidification-with-process-model
status: final
---

# 技术设计：用过程模型替换酸化改良逻辑

## 1. 上下文

### 1.1 当前状态

系统 model-4（AcidificationRemediationAgent）通过 question_type=2 路由，处理酸化改良相关问题。现有实现链路：

```
chat.py → nodes.py(execute_models) → AgentManager.process → model-4 agent
  → _get_real_acidification → query_acidification (DB查询)
  → 失败时回退 → _compute (mock规则计算)
```

- `src/ai_culti_demo/farmland_diagnosis/acidification.py`：基于 GB/T 42817-2023 的规则导向计算（calculate_lime_demand 仅用 pH+有机质）+ DB 查询（query_acidification 按 parcel_id 查 acidification_results 表）
- `framework/agents/specialized/acidification_agent.py`：尝试 DB 查询，失败时回退到 mock（ph/organic_matter/cec/clay_content/exchangeable_al）
- `framework/domain/other_models/model_4.py`：占位实现（返回空结果）

### 1.2 模型5源码分析

模型5（D:\destkop\模型5\02_酸化模型计算-地块.py）包含4个子模型，每个子模型的计算流程：

```
输入：pHstart, Hex, Alex (+ ~15个默认参数)
  ↓
1. 酸沉降产酸量 Adep = 10^(-RPH) * 667 * (R/1000) * 1000 * 15
2. 植株吸收产H+量 Acrop = Hgrain + Hstraw（基于产量×元素含量）
3. 氮循环净产酸量 ANcy = Anit + Ano3_runoff + Ano3_crop + Avol
4. 农业活动总产酸量 Aagri = Adep + Acrop + ANcy
5. 土壤本底酸量 Aback = (6.25e(9-pHstart) - 6.25e(9-pHtarget) + 2.5*Hex*1e7 + 2.5*Alex*1e7) / 1000
6. 改良剂需求量：
   YTK = (Aback + 0.8*Aagri) / 17.042 * 系数(0.6/0.77/0.7)
   MBNT = MBNT系数 * Aagri / 1.89 + Alex * 590 * 15 * MBNT系数2
  ↓
输出：YTK(亿土康 kg/ha), MBNT(木本泥炭 kg/ha)
```

### 1.3 四子模型差异矩阵

| 参数/系数 | paddy_urea | paddy_compound | upland_urea | upland_compound |
|-----------|------------|----------------|-------------|-----------------|
| Y(籽粒产量) | 5109 | 5109 | 6700 | 6700 |
| S(秸秆产量) | 5109 | 5109 | 6968 | 6968 |
| pHtarget | 6.5 | 6.5 | 6.0 | 6.0 |
| Anit系数 | 2.221*exp(0.0048) | 2.221*exp(0.0048) | 2.7*exp(0.0088) | 2.7*exp(0.0088) |
| Ano3_runoff | Ndep-(0.16*Ndep+2.97) | FertN项+Ndep项 | Ndep-(0.17*Ndep-4.95) | FertN项+Ndep项 |
| Ano3_crop | 0 | -(Y*YN+S*SN)*0.3 | 0 | -(Y*YN+S*SN)*0.3 |
| Avol | Ndep项 | FertN项+Ndep项 | Ndep项 | FertN项+Ndep项 |
| YTK系数 | 0.6 | 0.6 | 0.77 | 0.7 |
| MBNT公式 | 0.1*Aagri/1.89+Alex*590*15 | 0.15*Aagri/1.89+Alex*590*15 | 0.1*Aagri/1.89+Alex*590*15*0.2 | 0.1*Aagri/1.89+Alex*590*15*0.3 |
| YN(籽粒N%) | - | 1.87 | - | 1.91 |
| SN(秸秆N%) | - | 1.15 | - | 0.66 |

## 2. 技术设计

### 2.1 模块结构

```
src/ai_culti_demo/farmland_diagnosis/
├── config.py                    # 新增 JHX/JLA 到 ALL_INDICATORS/CONTINUOUS_INDICATORS/INDICATOR_DISPLAY_MAP
├── acidification.py             # 完全重写：4子模型 + 统一入口 + 旧函数委托
│   ├── _PADDY_DEFAULTS          # 水田默认参数（共用）
│   ├── _UPLAND_DEFAULTS         # 旱地默认参数（共用）
│   ├── _PADDY_COMPOUND_EXTRA    # 水田复合肥额外参数（YN/SN）
│   ├── _UPLAND_COMPOUND_EXTRA   # 旱地复合肥额外参数（YN/SN）
│   ├── CONFIGURABLE_PARAMS      # 可配参数白名单 {"RPH","R","Y","S","FertN","Ndep","pHtarget"}
│   ├── _paddy_urea()            # 水田尿素子模型
│   ├── _paddy_compound()        # 水田复合肥子模型
│   ├── _upland_urea()           # 旱地尿素子模型
│   ├── _upland_compound()       # 旱地复合肥子模型
│   ├── _SUB_MODEL_MAP           # {(land_type, fertilizer_type): function}
│   ├── calculate_acidification_amendment()  # 统一入口
│   ├── [deprecated] query_acidification()   # 委托新模型
│   └── [deprecated] evaluate_acidification() # 委托新模型

framework/domain/other_models/
├── model_4.py                   # 替换占位：model_4_execution 入口

framework/agents/specialized/
├── acidification_agent.py       # 适配新参数和返回结构

framework/agents/
├── nodes.py                     # 透传 fertilizer_type

framework/api/routes/
├── chat.py                      # 接受 fertilizer_type 顶层参数
```

### 2.2 核心函数签名

#### `calculate_acidification_amendment`（src 层统一入口）

```python
def calculate_acidification_amendment(
    pHstart: float,
    Hex: float,
    Alex: float,
    land_type: str = "upland",
    fertilizer_type: str = "compound",
    **optional_params: float,
) -> Dict[str, Any]:
    """
    过程酸化模型统一入口。

    必填输入：pHstart(=SJD), Hex(=JHX), Alex(=JLA)
    子模型选择：land_type × fertilizer_type → 4子模型之一
    可配参数：RPH/R/Y/S/FertN/Ndep/pHtarget（通过 optional_params 覆盖）

    返回：
    {
        "status": "success" | "rejected",
        "ytk": float,           # 亿土康 kg/ha
        "mbnt": float,          # 木本泥炭 kg/ha
        "sub_model": str,       # "paddy_urea" / "paddy_compound" / "upland_urea" / "upland_compound"
        "land_type": str,
        "fertilizer_type": str,
        "customized_params": Dict[str, float],  # 被覆盖的参数
        "warning": str,         # 可选
        "model_version": str,
    }
    """
```

#### `model_4_execution`（framework 层入口）

```python
def model_4_execution(
    input_data: Dict[str, Any],
    land_type: Optional[str] = None,
    fertilizer_type: Optional[str] = None,
) -> Dict[str, Any]:
    """
    model-4 酸化改良模型入口。

    从 input_data 提取 SJD/JHX/JLA（或通过 parcel_id 从 DB 查 SJD），
    调用 calculate_acidification_amendment 执行计算。

    返回标准化结构（含 status/ytk/mbnt/land_type/fertilizer_type/model_version/warning/customized_params）。
    """
```

### 2.3 输入映射与校验

```
API 请求字段 → 内部参数映射：
  SJD  → pHstart
  JHX  → Hex
  JLA  → Alex

校验规则：
  pHstart: [3.0, 10.0]
  Hex:     >= 0
  Alex:    >= 0
  land_type:      "upland" | "paddy"（非法 → 默认 upland + warning）
  fertilizer_type: "compound" | "urea"（非法 → 默认 compound + warning）
```

### 2.4 parcel_id → SJD 补充逻辑

当 `input_data` 包含 `parcel_id` 但无 `SJD` 时：
1. 通过 `DiagnosisStorage` 查询 `evaluation_results` 表的 `SJD` 列
2. 查到 → 用作 pHstart
3. 查无 → 返回 `status="rejected"`, `reason="cannot_get_ph"`, 提示提供 SJD

### 2.5 AcidificationRemediationAgent 适配

```python
class AcidificationRemediationAgent(BaseAgent):
    def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        land_type = (task or {}).get("land_type")
        fertilizer_type = (task or {}).get("fertilizer_type")
        result = model_4_execution(task or {}, land_type=land_type, fertilizer_type=fertilizer_type)
        return MockDataLoader.mark_simulated({
            "status": result["status"],
            "result": {
                "ytk": result["ytk"],
                "mbnt": result["mbnt"],
                "sub_model": result.get("sub_model"),
                "customized_params": result.get("customized_params", {}),
            },
            "metadata": {
                "model_version": result["model_version"],
                "warning": result.get("warning"),
                "reason": result.get("reason"),
            },
        })

    def answer_question(self, question: str, context: Dict[str, Any]) -> Dict[str, Any]:
        # 从 context 提取 land_type/fertilizer_type 透传
        task = context.get("data", {}) or context.get("task", {}) or {}
        enriched = dict(task)
        for key in ("land_type", "fertilizer_type", "parcel_id", "parcel_code"):
            if key in context and key not in enriched:
                enriched[key] = context[key]

        exec_result = self.execute(enriched)
        # 基于 ytk/mbnt 生成 answer（移除 GB/T 42817-2023 引用）
        ...
```

### 2.6 旧函数委托策略

```python
# 旧函数保留签名但委托新模型
def query_acidification(parcel_id: str, db_path: str = None) -> Dict[str, Any]:
    """
    [DEPRECATED] 使用 calculate_acidification_amendment 替代。
    保留签名以兼容导入，内部委托新模型。
    注意：需要 parcel_id + JHX + JLA 才能计算，仅 parcel_id 不足以触发计算。
    """
    # 从 DB 查 SJD → 调用 calculate_acidification_amendment
    # 但 JHX/JLA 无法从 DB 获取 → 返回 not_ready 提示
    ...

def evaluate_acidification(db_path: str = None) -> Dict[str, Any]:
    """
    [DEPRECATED] 按需计算模式下不再需要批量评估。
    """
    return {"status": "deprecated", "message": "使用 calculate_acidification_amendment 按需计算"}
```

## 3. 测试策略

### 3.1 单元测试（tests/test_model4_acidification.py）

| 测试类别 | 测试用例 | 验证点 |
|---------|---------|--------|
| 计算正确性 | pHstart=4.31, Hex=1.56, Alex=4.08 × 4子模型 | YTK/MBNT 与手动计算值一致（±0.01） |
| 子模型选择 | 4种 land_type×fertilizer_type 组合 | sub_model 字段正确 |
| 非法参数回退 | land_type="foo", fertilizer_type="bar" | 回退 upland+compound + warning |
| 输入校验-缺失 | 无 JHX 或 JLA | status="rejected", reason="missing_input" |
| 输入校验-越界 | SJD=2.5, JHX=-1 | status="rejected", reason="input_out_of_range" |
| 参数覆盖 | FertN=200 | customized_params={"FertN":200}, ytk/mbnt 变化 |
| parcel_id补充 | parcel_id="1" + JHX + JLA（mock DB SJD=5.5） | pHstart=5.5, 计算成功 |
| parcel_id查无 | parcel_id="999" + JHX + JLA（mock DB 无数据） | status="rejected", reason="cannot_get_ph" |

### 3.2 Agent 测试（tests/test_agent_specialized.py 更新）

- mock `model_4_execution` 返回值结构
- 验证 land_type/fertilizer_type 透传
- 验证 answer 不含 GB/T 42817-2023 引用

### 3.3 回归测试

- question_type=2 → model-4 路由不变
- 其他 question_type（1/3/4/5）不受影响

## 4. 风险与缓解

| 风险 | 影响 | 缓解 |
|------|------|------|
| 4子模型系数移植错误 | YTK/MBNT 计算错误 | 逐行对照源码 + 示例值测试断言 |
| 旧函数委托后返回值 BREAKING | 调用方解析失败 | acidification_agent 已同步更新 |
| parcel_id 查 SJD 依赖 DB 有数据 | 查无数据时无法计算 | 返回 rejected + 提示提供 SJD |
| JHX/JLA 未在数据管道流转 | CSV 导入不含此字段 | 按需计算不依赖 CSV 导入，API 直接接受参数 |
| API 响应字段 BREAKING | 前端解析 lime_demand 失败 | 文档同步更新，openapi.json 版本升级 |

