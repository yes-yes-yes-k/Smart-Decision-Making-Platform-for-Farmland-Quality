# 酸化 RF 预测接口文档

> 版本: v1
> 前缀: `/api/v1/acidification-rf`
> 认证: JWT Token（`Authorization: Bearer <token>` 头，所有接口均需登录）

## 概述

本组接口提供酸化随机森林（RF）模型的清单查询、地块输入预填与在线预测能力。模型资产为从旧系统 `AcidificationModel` 移植并核验的 pickle 模型，登记于 `data/model_artifacts/acidification_rf/manifest.json`。

**定位与边界（重要）**

- RF 接口与 model-4 过程模型**并列存在、互不调用**，资产不可用时**不回退**到 model-4 或离线结果。
- RF 负责**预填与预测**：选地块自动填表、缺失字段参考值（训练集统计量）、在线预测。
- RF 预测结果**不等同于 model-4 的治理用量计算**，两者不可互相替代。
- 采用 prefill 建议值（`suggestions`）或参考值调用 `/predict` 时，**必须**通过 `assumptions` 声明来源依据，否则结果会被记为 `success`，无法区分实测值与采用值。

## 请求头

```http
Authorization: Bearer <token>
Content-Type: application/json
```

## 模型清单

### 1. 获取可用模型

**GET** `/api/v1/acidification-rf/models`

用途：返回当前登记的 RF 模型清单，供前端选择 `model_id` 与土地类型。无查询参数和请求体。

成功响应（200）：

```json
{
  "status": "ok",
  "models": [
    { "model_id": 33, "data_type": "reduce", "land_type": "dryland" },
    { "model_id": 35, "data_type": "reflux", "land_type": "dryland" },
    { "model_id": 38, "data_type": "reflux", "land_type": "paddy_field" }
  ]
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `model_id` | int | 模型编号 |
| `data_type` | string | 数据类型：`reduce`（降酸）或 `reflux`（返酸） |
| `land_type` | string | 土地类型：`dryland`（旱地）或 `paddy_field`（水田） |

> 响应只暴露公开身份字段，不含资产路径、哈希等内部信息。

失败响应（503，模型资产不可用）：

```json
{
  "status": "error",
  "reason": "model_unavailable"
}
```

| HTTP 状态码 | 场景 |
|------------|------|
| 401 | 未认证 |
| 503 | 资产缺失或 manifest 读取失败 |

---

## 地块输入预填

### 2. 获取地块 RF 输入预填值

**GET** `/api/v1/acidification-rf/parcels/<parcel_id>/prefill`

用途：按地块编号返回 RF 输入预填值，供前端「选地块 → 自动填表」。

查询参数：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `model_id` | int | 否 | 指定模型编号，须与地块土地类型匹配；缺省取该土地类型的 reflux 模型 |

规则说明：

- `data` 只包含有既定字段映射的指标，**不做任何推测性填充**；地块数据中无对应字段的 RF 输入列入 `missing_fields`，不会以零值、区域均值或训练分布推断补齐。
- `provenance` 标注每个已填字段的来源：`measured` / `region_mean_backfill` / `default` / `unknown`，用于向使用者披露非地块实测的输入。
- `suggestions` 为缺失字段提供的**可选参考值**（训练集中位数），不自动写入 `data`；采用后调用 `/predict` 时必须通过 `assumptions` 声明。
- 地块土地类型与指定模型不匹配时返回 400。

成功响应（200）：

```json
{
  "status": "need_input",
  "model_id": 33,
  "data_type": "reduce",
  "land_type": "dryland",
  "parcel_id": "4400002024001001",
  "land_type_parcel": "upland",
  "data": {
    "init_pH": 5.32,
    "target_pH": 6.0,
    "H": 1.56,
    "Al": 4.08,
    "OM": 24.5,
    "CEC": 11.2
  },
  "provenance": {
    "init_pH": "measured",
    "target_pH": "default",
    "H": "region_mean_backfill",
    "Al": "region_mean_backfill",
    "OM": "measured",
    "CEC": "measured"
  },
  "missing_fields": ["NO3", "NH4"],
  "imputed_fields": ["H", "Al"],
  "suggestions": {
    "NO3": {
      "value": 45.0,
      "basis": "training_median",
      "dataset": "training_rf_model_1101_1958",
      "row_count": 1101,
      "range_p25_p75": [30.0, 60.0],
      "unit_status": "unverified",
      "note": "训练样本中位数，非地块实测；采用后结论按降级处理"
    }
  },
  "warnings": [
    "H 为区域平均回填值，非地块实测",
    "target_pH 使用默认值",
    "NO3 在地块数据中没有对应字段，需手工填写",
    "NO3 可参考训练样本中位数 45.0（n=1101，非实测，采用后按降级处理）"
  ]
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `status` | string | `ready`（可预测）或 `need_input`（仍有缺失字段） |
| `model_id` | int | 实际使用的模型编号 |
| `data_type` | string | 数据类型：`reduce` / `reflux` |
| `land_type` | string | 模型土地类型 |
| `parcel_id` | string | 地块编号（回显） |
| `land_type_parcel` | string | 地块原始土地类型 |
| `data` | object | 已填字段（键为 RF 规范字段名） |
| `provenance` | object | 每个已填字段的来源标注 |
| `missing_fields` | string[] | 地块数据中无对应字段、需手工填写的 RF 输入 |
| `imputed_fields` | string[] | 来源为回填或默认值的字段（非实测） |
| `suggestions` | object | 缺失字段的可选参考值（训练集统计量） |
| `warnings` | string[] | 可直接展示给使用者的中文提示 |

`suggestions` 字段结构：

| 字段 | 类型 | 说明 |
|------|------|------|
| `value` | number | 训练样本中位数 |
| `basis` | string | 依据类型，固定 `training_median` |
| `dataset` | string | 训练数据集标识 |
| `row_count` | int | 样本量 |
| `range_p25_p75` | number[] | P25–P75 分布区间 |
| `unit_status` | string | 单位核验状态（`unverified` 表示单位未经核验，不得标注具体单位） |
| `note` | string | 使用提示：训练样本中位数，非实测 |

失败响应：

```json
{
  "status": "rejected",
  "reason": "parcel_not_found",
  "parcel_id": "4400002024001001"
}
```

| HTTP 状态码 | reason | 场景 |
|------------|--------|------|
| 404 | `parcel_not_found` | 地块不存在 |
| 400 | `unknown_land_type` | 地块土地类型不在映射范围内 |
| 400 | `land_type_mismatch` | 指定模型土地类型与地块不一致 |
| 503 | `model_unavailable` | 模型资产不可用 |
| 401 | — | 未认证 |

---

## 在线预测

### 3. 执行 RF 预测

**POST** `/api/v1/acidification-rf/predict`

用途：按 `model_id` 执行本地 RF 预测。`data` 支持单个对象或批量数组（多行一次预测）。

请求体：

```json
{
  "model_id": 33,
  "data": {
    "init_pH": 5.32,
    "target_pH": 6.0,
    "H": 1.56,
    "Al": 4.08,
    "OM": 24.5,
    "NO3": 45.0,
    "NH4": 18.2,
    "CEC": 11.2
  },
  "assumptions": {
    "NO3": "training_median",
    "NH4": "training_median"
  }
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `model_id` | int | 是 | 模型编号（来自 `/models`） |
| `data` | object \| object[] | 是 | 预测输入，字段名见下方各模型字段集 |
| `assumptions` | object | 否 | 字段名 → 依据；**采用 prefill 建议值时必须传**，后端据此将 `status` 强制降为 `degraded` 并在 `assumed_fields` 回显 |

各模型的规范字段集（键名大小写不敏感，支持 `init_ph`、`pH`、`al` 等别名）：

| model_id | data_type | land_type | 字段集 |
|----------|-----------|-----------|--------|
| 33 | reduce | dryland | `init_pH`、`target_pH`、`H`、`Al`、`OM`、`NO3`、`NH4`、`CEC` |
| 35 | reflux | dryland | `H`、`Al`、`OM`、`NO3`、`NH4`、`CEC` |
| 38 | reflux | paddy_field | `CEC`、`NH4`、`NO3`、`Al`、`FeO`、`OM` |

规则说明：

- reduce 模型（33）的 `init_pH` 与 `target_pH` 为必填，缺失返回 `rejected/missing_input`。
- 同一字段传入冲突值时返回 `rejected/input_conflict`。
- 请求批次内存在缺失值（非整列缺失）时，按**当前批次均值**填补，结果 `status=degraded`，`imputed_fields` 记录被填补字段；整列全缺失返回 `rejected/all_column_missing`。
- 传入 `assumptions` 时结果 `status=degraded`，`assumed_fields` 回显字段与依据。

成功响应（200，degraded 示例）：

```json
{
  "status": "degraded",
  "model_id": 33,
  "data_type": "reduce",
  "land_type": "dryland",
  "imputed_fields": [],
  "assumed_fields": {
    "NO3": "training_median",
    "NH4": "training_median"
  },
  "imputation": {
    "strategy": "mean",
    "fit": "request_batch"
  },
  "predictions": [
    {
      "raw_prediction": 1.2,
      "result": 8.0,
      "unit": "t/mu",
      "conversion": "Q=raw*(target_pH-init_pH); t/ha=Q*25; t/mu=t/ha/15"
    }
  ],
  "source": "acidification_rf_local"
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `status` | string | `success`（完整输入）/ `degraded`（存在批次均值填补或采用了建议值） |
| `model_id` | int | 模型编号 |
| `data_type` | string | 数据类型：`reduce` / `reflux` |
| `land_type` | string | 模型土地类型 |
| `imputed_fields` | string[] | 被批次均值填补的字段 |
| `assumed_fields` | object | 采用建议值且已声明依据的字段 |
| `imputation` | object | 填补策略说明：`strategy=mean`、`fit=request_batch` |
| `predictions` | object[] | 预测结果列表（与请求行一一对应） |
| `source` | string | 固定 `acidification_rf_local` |

`predictions` 元素结构：

| 字段 | 类型 | 说明 |
|------|------|------|
| `raw_prediction` | number | 模型原始预测值 |
| `result` | number | 业务转换值 |
| `unit` | string | 结果单位：reduce 为 `t/mu`；reflux 为 `raw_prediction` |
| `conversion` | string | 转换规则说明：reduce 为 `Q=raw*(target_pH-init_pH); t/ha=Q*25; t/mu=t/ha/15`；reflux 水田为 `abs`，旱地为 `identity` |

失败响应（400）：

```json
{
  "status": "rejected",
  "reason": "invalid_input",
  "predictions": []
}
```

| HTTP 状态码 | reason | 场景 |
|------------|--------|------|
| 400 | `invalid_input` | 请求体缺 `model_id`/`data`，或 `model_id` 非法，或输入无法解析 |
| 400 | `invalid_assumptions` | `assumptions` 非字典类型 |
| 400 | `missing_input` | reduce 模型缺少 `init_pH`/`target_pH` |
| 400 | `input_conflict` | 同一字段传入多个冲突值 |
| 400 | `all_column_missing` | 某列全部缺失，无法填补 |
| 503 | `model_unavailable` / `model_integrity_mismatch` / `model_metadata_invalid` | 模型资产缺失、哈希不一致或元数据无效（不回退到其他模型） |
| 401 | — | 未认证 |
