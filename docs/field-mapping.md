# 字段映射与回退规则

## 总览接口字段

| 接口字段 | 含义 | 当前来源 | 是否必须 | 回退策略 |
| --- | --- | --- | --- | --- |
| `area.code` | 区域编码 | 本仓库配置 | 是 | 固定为 `lechang` |
| `area.name` | 区域名称 | 本仓库配置 | 是 | 固定为 `乐昌市` |
| `layers[].id` | 图层标识 | `data/lechang/catalog.json` | 是 | 无 |
| `layers[].source.asset_ids` | 来源资产 | `data/lechang/catalog.json` | 是 | 无 |
| `layers[].status` | 图层状态 | 本仓库配置 | 是 | `stub` |

## 诊断接口字段

| 接口字段 | 含义 | 当前来源 | 是否必须 | 回退策略 |
| --- | --- | --- | --- | --- |
| `topic` | 诊断主题 | 调用方传入 | 是 | 无效时返回 `INVALID_TOPIC` |
| `area_code` | 区域编码 | 调用方传入 | 否 | 缺省使用 `lechang` |
| `longitude` | 经度 | 调用方传入 | 否 | 缺失时使用县域级诊断 |
| `latitude` | 纬度 | 调用方传入 | 否 | 缺失时使用县域级诊断 |
| `evidence` | 判定依据 | 本仓库规则与资产元数据 | 是 | 使用规则占位证据 |
| `recommended_layers` | 推荐图层 | 主题到图层映射 | 是 | 使用 `quality-overview` |

## 结果整理接口字段

| 接口字段 | 含义 | 当前来源 | 是否必须 | 回退策略 |
| --- | --- | --- | --- | --- |
| `diagnosis_id` | 诊断结果标识 | 诊断接口输出 | 是 | 缺失时返回 `MISSING_DIAGNOSIS` |
| `summary` | 结论摘要 | 诊断结果 | 是 | 使用诊断主题模板 |
| `findings` | 关键发现 | 诊断结果 | 是 | 使用证据字段生成 |
| `recommendations` | 治理建议 | 诊断结果 | 是 | 使用主题建议模板 |
| `actions` | 后续行动项 | 规则模板 | 是 | 使用默认行动项 |

## 可靠性标记

| 字段 | 取值 | 含义 |
| --- | --- | --- |
| `reliability.level` | `demo_stub` | 演示占位规则，未接真实模型 |
| `reliability.level` | `derived` | 由本仓库本地资产派生 |
| `reliability.level` | `model_output` | 由真实模型输出 |
| `fallback.used` | `true` / `false` | 是否使用回退 |
| `fallback.fields[]` | 字段名列表 | 使用回退的字段 |
