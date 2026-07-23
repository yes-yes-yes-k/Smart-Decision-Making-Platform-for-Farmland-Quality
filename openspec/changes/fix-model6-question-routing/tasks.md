## 1. 修复问题路由

- [x] 1.1 在 `framework/agents/nodes.py` 中新增 `QUESTION_TYPE_4_KEYWORDS` 肥力关键词列表
- [x] 1.2 修改 `_identify_question_type_keyword` 函数，添加 question_type=4 判断逻辑
- [x] 1.3 运行单元测试验证修复效果

## 2. 验证修复

- [x] 2.1 运行 `python test_model6_api.py` 验证 model-6 正常响应
- [x] 2.2 运行完整测试套件确保无回归
