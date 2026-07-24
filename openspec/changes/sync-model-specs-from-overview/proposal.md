## Why

`专业模型总览表(2).xlsx` 更新了六种专业模型的输入输出定义和领域涉及问题（省/县/农户三角色经典 Q&A），但当前系统的 spec 和 agent 代码与 xlsx 存在差异：模型 6 名称不一致（spec 为"耕地肥力机器学习预测模型"，xlsx 为"耕地综合地力改良提升模型"）、各模型输入输出未对齐 xlsx 详细定义、3 角色经典问题未覆盖。需要同步更新以确保 spec 和代码与权威文档一致。

## What Changes

- 更新 `professional-model-agents` spec 中六种模型的输入输出定义，对齐 xlsx 的数据名称、格式、来源
- 更新 model 6 规格名称为"耕地综合地力改良提升模型"（以 xlsx 为准），FertilityMLAgent 的 ML 预测作为内部实现保留
- 新增 3 角色经典问题场景（省市管理端、县域执行端、农户种植端）到各模型的 scenario 中
- 同步修改 agent 代码的 `answer_question` 逻辑和 `nodes.py` 的问题类型关键词/路由，确保能回答 xlsx 中定义的经典问题
- **BREAKING**: model 6 spec 名称从"耕地肥力机器学习预测模型"回退为"耕地综合地力改良提升模型"

## Capabilities

### New Capabilities

（无新增能力，均为现有能力的修改）

### Modified Capabilities
- `professional-model-agents`: 更新六种专业模型的输入输出定义（对齐 xlsx）、model 6 名称回退为"耕地综合地力改良提升模型"、新增 3 角色经典问题场景
- `role-based-routing`: 更新问题类型关键词和路由逻辑，覆盖 xlsx 中 3 角色的经典问题路由

## Impact

- **修改 spec**: `openspec/specs/professional-model-agents/spec.md`（6 个模型定义）、`openspec/specs/role-based-routing/spec.md`（路由规则）
- **修改代码**: `framework/agents/specialized/*.py`（各 agent 的 answer_question）、`framework/agents/nodes.py`（问题类型关键词）、`framework/agents/router.py`（角色路由）
- **无新增依赖**: 仅修改现有代码逻辑
- **运行时影响**: agent 回答内容将更贴近 xlsx 定义的领域问题；model 6 的 spec 名称变更不影响 API 接口
