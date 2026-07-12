# 模拟专题模型调用示例

以下示例展示未来大模型如何先列举模型，再按 `model_id` 调用单个模型。

## 列举可用模型

```bash
python -m ai_culti_demo.cli models
```

或使用 HTTP：

```text
GET /api/models?area_code=lechang
```

## 调用单个模拟模型

```bash
python -m ai_culti_demo.cli model --model-id acidification-governance --area-code lechang --longitude 113.35 --latitude 25.13
```

或使用 HTTP：

```json
POST /api/models/run
{
  "model_id": "multi-factor-collaborative-improvement",
  "area_code": "lechang"
}
```

返回结果会固定包含 `status`、`model`、`summary`、`findings`、`recommended_layers`、`recommendations`、`lineage`、`reliability` 和 `fallback` 等字段。
