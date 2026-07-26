## Why

`POST /api/v1/models/run` 原有文档只有一个不完整的请求样例，且未展示路由层实际返回的 `status` 与 `data` 包装结构。调用者若要测试不同专题模型，需要手动复制并修改请求体，容易使用未受支持的字段或模型标识。

## What Changes

- 为模型调用接口补充真实、完整的成功响应和参数错误响应示例。
- 将请求体示例扩展为 6 个具名示例，分别对应项目当前支持的 6 个专题模型。
- 在请求定义中列举受支持的 `model_id`，并说明可选字段的传递与缺失坐标时的回退行为。
- 将更新后的 OpenAPI 规范同步至 Apifox，使文档使用者无需手动替换请求体即可切换模型。

## Capabilities

### New Capabilities

- `api-documentation-examples`: 为对外 API 提供与实际路由契约一致、可直接用于调试的请求和响应示例。

### Modified Capabilities

- 无。

## Impact

- 更新 `docs/openapi.json` 中 `/api/v1/models/run` 的接口定义。
- 更新 Apifox 项目「默认模块」中相同路径的接口文档。
- 不改变模型执行逻辑、认证逻辑、请求字段处理或运行时行为。
