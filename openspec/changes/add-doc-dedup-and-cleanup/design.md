## Context

当前文档上传流程（`framework/api/routes/docs.py`）直接保存文件、解析内容、入库，无查重机制。删除流程只调用 `vector_store.delete_by_source()` 和 `db.session.delete()`，未清理 `uploads/` 目录中的物理文件。

数据库表 `kb_document` 当前字段：`doc_name`, `file_path`, `file_type`, `file_size`, `chunk_count`, `status`, `category`, `treatment_type`, `create_by`, `create_time`, `update_time`。

## Goals / Non-Goals

**Goals:**
- 上传时基于文件内容 SHA-256 哈希检测重复，同用户下重复文档拒绝入库
- 删除文档时同步清理物理文件、向量库数据、数据库记录
- 物理文件删除失败不阻塞数据库清理（容错）

**Non-Goals:**
- 不做跨用户的文档查重（每个用户独立）
- 不做内容相似度检测（只做精确哈希去重）
- 不做软删除/回收站机制
- 不迁移历史数据（历史文档 `file_hash` 为空，不参与查重）

## Decisions

### Decision 1: 使用 SHA-256 计算文件内容哈希

**选择**: 使用 Python 标准库 `hashlib.sha256` 对文件二进制内容计算哈希。

**理由**: SHA-256 碰撞率极低，性能足够（50MB 文件 < 100ms），无需新增依赖。

**备选方案**:
- MD5：更快但碰撞率较高，不推荐用于去重
- 文件名 + 文件大小：不可靠，不同文件名可能内容相同

### Decision 2: 查重范围为同用户下

**选择**: 上传时查询 `Document.query.filter_by(file_hash=hash, create_by=user_id).first()`，仅在当前用户范围内查重。

**理由**: 不同用户可能需要独立维护自己的文档副本；跨用户查重会引入权限复杂度。

### Decision 3: 物理文件删除失败时容错处理

**选择**: 删除物理文件时 try-except 包裹，失败时 `print` 日志但继续删除数据库记录。

**理由**: 物理文件可能已被手动删除或权限问题，不应阻塞数据库清理。保持数据库与向量库的一致性优先级高于物理文件清理。

### Decision 4: `file_hash` 字段可为空

**选择**: `file_hash` 字段设为 `nullable=True`，历史数据该字段为 NULL。

**理由**: 避免历史数据迁移复杂性。查重查询时 `file_hash IS NOT NULL` 自动跳过历史数据。

## Risks / Trade-offs

- **[风险] 大文件哈希计算内存占用** → 使用分块读取（8192 字节/块）流式计算，避免一次性加载整个文件到内存
- **[权衡] 查重只针对精确内容相同** → 无法检测"近似重复"文档，但实现简单可靠，满足当前需求
- **[风险] 物理文件删除失败导致磁盘泄漏** → 通过日志记录便于后续排查，不阻塞业务流程
