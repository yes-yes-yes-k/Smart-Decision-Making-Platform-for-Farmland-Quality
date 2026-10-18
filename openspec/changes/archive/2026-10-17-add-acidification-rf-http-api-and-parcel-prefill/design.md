# add-acidification-rf-http-api-and-parcel-prefill 设计

## Context

酸化 RF 能力已在 `add-acidification-rf-prediction` 中本地化：三个 pickle 资产、manifest 校验、批次均值填补、reduce 换算与水田绝对值语义均已就位，但只以内部 callable 形式存在。该 change 明确把"是否增加外部 HTTP API"留给后续 change。

前端联调需要可调用接口；同时落地过程中发现两个必须写进规格的事实：地块指标多数为区域平均回填，以及三个模型的特征集互不相同。

## Goals / Non-Goals

**Goals**

- 提供前端可直接调用的酸化 RF 接口，且不依赖旧系统服务。
- 让"哪些输入是实测、哪些是回填、哪些缺失"在接口层面可见可追。
- 修正水田模型的输入字段与列序，使预测基于其真实训练特征。
- 为缺失字段提供有依据、可拒绝、可追溯的参考值。

**Non-Goals**

- 不实现地块级自动组装（缺 NO3/NH4/FeO 与地块级 H/Al 真值）。
- 不做空间插值与样点匹配。
- 不改变 model-4，不建立两套模型的业务串联。

## Decisions

### 1. 端点由本项目 Flask 蓝图提供，不代理旧服务

新增 `framework/api/routes/acidification_rf.py`，在 `create_app()` 中以 `/api/v1/acidification-rf` 注册，沿用项目既有的 `@jwt_required()` 与 `jsonify` 约定。

理由：已归档 change 的边界是"不依赖旧系统 HTTP"，而非"本项目不得对外提供 API"。代理旧服务会重新引入外部运行时依赖；自建端点则复用本地资产与既有 domain 逻辑。

### 2. 特征集按模型 ID 定义，不按 `data_type` 统一

从三个 pickle 的 `feature_names_in_` 核实（2026-10-17）：

| 模型 | 类型 | 训练列（顺序不可变） |
|---|---|---|
| 33 | reduce | `pH/H/Al/OM/NO3/NH4/CEC` |
| 35 | reflux | `H/Al/OM/NO3/NH4/CEC` |
| 38 | reflux | `CEC/NH4/NO3/Al/FeO/OM` |

理由：水田与旱地 reflux 的字段集不同（水田有 FeO、无 H），原先按 `data_type` 统一会让模型 38 收到错字段与错列序。

### 3. 输入按列序构造 ndarray，因此列序必须显式

sklearn 在收到 ndarray 时不校验列名，错序不会报错而会静默产出错误预测。实现改为按 `_MODEL_COLUMNS[model_id]` 逐列取数，任何字段缺失进入批次均值填补或拒绝路径，不再依赖"输入列恰好排对"。

### 4. 预填只填已有既定映射，缺失项不填

`parcel_info.soil_indicators` → RF 字段的映射限定为 `soil_ph→init_pH`、`exchangeable_hydrogen→H`、`exchangeable_aluminum→Al`、`organic_matter→OM`、`cation_exchange_capacity→CEC`、`target_ph→target_pH`。`NO3`、`NH4`、`FeO` 无映射，直接列入 `missing_fields`。

理由：区域平均回填值与缺失字段若被自动补齐，前端会把它当作地块实测结果输出，违背既有的 provenance 约定。

### 5. 来源逐字段透传，未知不冒充实测

`provenance` 直接取自 `soil_indicators.provenance`；无标注时记 `unknown`，不得回落为 `measured`。`imputed_fields` 列出所有非实测的已填字段。

### 6. 参考值取训练集中位数，单独字段承载

按模型取对应训练集（33→`dataset_77`、35→`dataset_81`、38→`dataset_94`）的中位数，附 `n`、`P25–P75`、数据集与 `unit_status`。参考值放在 `suggestions`，不写入 `data`。

选择中位数而非均值：NO3/NH4 分布右偏，均值被长尾拉高（如 dataset_81 NO3 均值 32.701 vs 中位数 31.24）。

### 7. 采用参考值必须显式标注，结果强制降级

前端采用参考值时提交 `assumptions: {字段: 依据}`，`predict` 将其非空视为降级条件，`status` 强制为 `degraded` 并在 `assumed_fields` 回显。

已知限制：后端只收到数值，无法区分"用户手输的实测值"与"照抄的参考值"。未传 `assumptions` 时结果仍记为 `success`。该限制写入 Open Questions，不做指纹或 token 机制（避免额外复杂度）。

### 8. 单位为未核验状态，不标具体单位

旧系统代码、文档与前端表单均无 `NO3`、`NH4`、`FeO` 的单位记录，`unit_status` 固定为 `unverified`，接口与报告中不得标注 `mg/kg` 等具体单位。

## Migration and Rollback

- 无数据库变更；`reference_values.json` 为新增只读资产，删除即回到无参考值状态。
- 特征按模型定义后，水田预测数值会与旧实现不同（旧实现为错序计算），这不是回归而是修正；对照证据为 `feature_names_in_`。
- 回滚方式：撤销路由注册即可停止对外暴露，domain 能力仍可由内部调用。

## Risks / Trade-offs

- **参考值被当作实测**：靠 `assumptions` 契约约束，前端不遵守时无法识别。缓解：`suggestions` 与 `data` 分离、`warnings` 附带中文提示。
- **单位未核验**：参考值与训练集同尺度，但不能用于跨来源比较。缓解：`unit_status` 显式标注。
- **地块级映射缺口**：73/5491 地块可用三普剖面样点，覆盖不足 2%，因此本期不开放自动映射，避免以点代面。

## Open Questions

1. `NO3`、`NH4`、`FeO` 的单位口径与检测方法，需要向业务方或实验记录确认。
2. 是否存在地块级氮素与亚铁监测数据；若无，参考值形态是否长期保留。
3. 前端是否接受"采用参考值必须提交 `assumptions`"的契约；若否，需要评估服务端可验证的替代方案。
4. 三普样点空间匹配是否立独立 change，以及插值口径（最近邻 / 反距离加权）。
