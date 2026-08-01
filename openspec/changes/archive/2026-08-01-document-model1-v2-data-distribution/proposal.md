## Why

模型1 v2 数据目录保留了过期来源、过期示例和错误的结果库路径，接收方无法据此获得、校验和部署最新数据。

## What Changes

- 记录模型1 v2 数据版本、原始交付来源和项目内运行位置。
- 记录标准数据包、快速演示包和接收方预计算步骤。
- 为 15 个原始 Shapefile 组件提供 SHA-256 校验值。
- 说明 Git 忽略规则、数据授权边界和预计算产物路径。

## Capabilities

### New Capabilities

- 无。

### Modified Capabilities

- `standalone-integration-runtime`: 为项目内承载的大型模型数据补充分发说明与完整性校验要求。

## Impact

- 更新 `data/farmland_stability/README.md`。
- 不修改模型算法、接口、数据文件或运行时配置。
