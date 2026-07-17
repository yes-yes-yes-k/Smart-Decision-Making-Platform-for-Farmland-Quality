## 1. 数据模型与工具函数

- [x] 1.1 在 `framework/models/document.py` 的 `Document` 模型中新增 `file_hash` 字段（String(64), nullable=True, comment='文件内容SHA-256哈希'）
- [ ] 1.2 在 `framework/upload/file_upload.py` 中新增 `compute_file_hash(file_path)` 函数，使用 `hashlib.sha256` 分块读取（8192 字节/块）计算文件哈希
- [ ] 1.3 在 `framework/upload/file_upload.py` 的 `save_uploaded_file` 函数返回值中增加文件哈希（返回三元组：new_filename, file_path, file_hash）

## 2. 上传查重逻辑

- [ ] 2.1 在 `framework/api/routes/docs.py` 的 `upload_document` 接口中，保存文件后计算哈希，查询 `Document.query.filter_by(file_hash=hash, create_by=user_id).first()` 检测重复
- [ ] 2.2 检测到重复时，删除刚保存的物理文件，返回 409 Conflict 错误，响应中包含已存在文档的 ID
- [ ] 2.3 未检测到重复时，在创建 `Document` 记录时填入 `file_hash` 字段

## 3. 删除清理逻辑

- [ ] 3.1 在 `framework/api/routes/docs.py` 的 `delete_document` 接口中，删除数据库记录前先删除物理文件
- [ ] 3.2 物理文件路径通过 `Config.UPLOAD_FOLDER + document.file_path` 拼接
- [ ] 3.3 使用 try-except 包裹物理文件删除逻辑，失败时 `print` 日志但继续删除数据库记录和向量库数据

## 4. 验证

- [ ] 4.1 上传相同内容不同文件名的文档，验证返回 409 Conflict
- [ ] 4.2 删除文档后，验证 `uploads/` 目录中对应物理文件已被删除
- [ ] 4.3 删除文档时物理文件已不存在，验证不报错且数据库记录正常删除
