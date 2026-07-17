# Brainstorm Summary

- Change: add-doc-dedup-and-cleanup
- Date: 2026-07-17

## 确认的技术方案

### 上传查重
- 保存文件到 uploads/ → compute_file_hash（SHA-256 分块 8192 字节）→ 查询 Document.filter_by(file_hash=hash, create_by=user_id) → 重复则删物理文件返回 409，不重复则入库含 file_hash

### 删除清理（方案 A）
- 顺序：先删向量库（容错）→ 再删数据库（事务）→ 最后删物理文件（try-except 容错）
- 物理文件删除失败仅日志记录，不阻塞业务

### 并发处理
- 不加数据库唯一约束，接受极小概率并发重复（内部系统并发低）

## 关键取舍与风险

- **取舍**：查重只针对精确内容相同，无法检测近似重复（满足当前需求，实现简单可靠）
- **取舍**：不加唯一约束，应用层查重已够用（避免 IntegrityError 处理复杂度）
- **风险**：大文件哈希计算内存占用 → 分块读取流式计算
- **风险**：物理文件删除失败导致磁盘泄漏 → 日志记录便于排查
- **风险**：数据库删除成功但物理文件删除失败 → 磁盘泄漏（方案 A 的已知权衡，数据一致性优先）

## 测试策略

- **单元测试**：compute_file_hash 函数（空文件、小文件、大文件分块）
- **集成测试**：
  - 上传查重：同用户重复返回 409、跨用户允许、首次上传成功
  - 删除清理：三资源全删、物理文件缺失容错、物理文件删除失败容错
- **边界条件**：历史文档 file_hash=NULL 不参与查重

## Spec Patch

补充「向量库删除失败」场景到 delta spec 的 MODIFIED Requirements：

```
#### Scenario: Delete document when vector store deletion fails
- **WHEN** a user deletes a document and vector store deletion raises an error
- **THEN** the system SHALL log the error, continue to remove the database record and physical file, and return success
```
