## Why

当前文档上传流程缺少查重机制，用户可以重复上传相同内容的文档（即使文件名不同），导致向量库中出现重复数据，浪费存储空间并影响 RAG 检索质量。同时，删除文档时只清理了数据库记录和向量库数据，但 `uploads/` 目录中的物理文件未被删除，造成磁盘空间泄漏。

## What Changes

- 上传时基于文件内容哈希（SHA-256）检测重复文档，拒绝重复入库
- `Document` 模型新增 `file_hash` 字段存储文件内容哈希
- 删除文档时同步删除 `uploads/` 目录中的物理文件
- 删除操作失败时（如物理文件已被手动删除）记录日志但不阻塞数据库清理

## Capabilities

### New Capabilities
<!-- 本次无新增 capability，仅修改现有 capability -->

### Modified Capabilities
- `file-upload-management`: 新增文档内容查重要求（上传时基于 SHA-256 哈希去重）；完善删除文档要求（删除时同步清理物理文件）

## Impact

- **代码**:
  - `framework/models/document.py` — 新增 `file_hash` 字段
  - `framework/upload/file_upload.py` — 新增文件哈希计算函数
  - `framework/api/routes/docs.py` — 上传接口增加查重逻辑，删除接口增加物理文件清理
  - `framework/config.py` — 可能新增配置项
- **数据库**: `kb_document` 表新增 `file_hash` 列（需要数据库迁移）
- **API**: 上传接口在检测到重复时返回 409 Conflict；删除接口行为不变（仍返回 200）
- **依赖**: 无新增依赖，使用 Python 标准库 `hashlib`
