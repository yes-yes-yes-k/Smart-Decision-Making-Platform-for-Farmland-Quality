# 修复 /api/v1/chat/ 接口 422 错误 - Verification Checklist

## JWT 错误处理修复验证
- [ ] Checkpoint 1: 不带 Authorization header 请求 `POST /api/v1/chat/` 返回 HTTP 401（而非 422）
- [ ] Checkpoint 2: 不带 token 时的响应体格式为 `{"status": "error", "message": "..."}`（而非 `{"msg": "..."}`）
- [ ] Checkpoint 3: 带格式错误的 token 请求时返回 HTTP 401 和统一错误格式
- [ ] Checkpoint 4: 带过期 token 请求时返回 HTTP 401 和统一错误格式
- [ ] Checkpoint 5: 错误信息为中文且清晰易懂（如"未登录或登录已过期"）

## 参数名统一验证
- [ ] Checkpoint 6: 发送 `{"content": "测试消息"}` 能被后端正确识别并处理
- [ ] Checkpoint 7: 发送 `{"message": "测试消息"}` 仍能正常工作（向后兼容）
- [ ] Checkpoint 8: 同时发送 `content` 和 `message` 时，优先使用 `content`
- [ ] Checkpoint 9: 缺少消息内容时返回 400 和"问题不能为空"的错误提示

## 功能完整性验证
- [ ] Checkpoint 10: 带有效 token 正常发送消息，返回 200 和正确的 AI 回答
- [ ] Checkpoint 11: 会话创建和消息持久化功能正常
- [ ] Checkpoint 12: `conversation_id` 存在时消息正确关联到对应会话
- [ ] Checkpoint 13: 不传 `conversation_id` 时自动创建新会话

## 兼容性验证
- [ ] Checkpoint 14: `GET /api/v1/chat/conversations` 接口认证行为不变
- [ ] Checkpoint 15: `GET /api/v1/auth/me` 接口认证行为不变
- [ ] Checkpoint 16: `POST /api/v1/auth/login` 接口不受影响
- [ ] Checkpoint 17: 其他需要 `@jwt_required()` 的接口错误响应格式统一
- [ ] Checkpoint 18: 现有测试套件 `pytest tests/` 全部通过

## 前端联调验证
- [ ] Checkpoint 19: 前端登录后能正常调用聊天接口并收到回复
- [ ] Checkpoint 20: 前端未登录时调用聊天接口能正确提示登录
- [ ] Checkpoint 21: AI 聊天面板的消息展示、引用来源等功能正常
