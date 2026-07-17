---
comet_change: add-doc-dedup-and-cleanup
role: technical-design
canonical_spec: openspec
archived-with: 2026-07-17-add-doc-dedup-and-cleanup
status: final
---

# 技术设计文档：文档上传查重与删除清理

## 1. 背景与目标

### 1.1 背景

当前文档上传流程（`framework/api/routes/docs.py`）直接保存文件、解析内容、入库，无查重机制。用户可重复上传相同内容的文档（即使文件名不同），导致向量库出现重复数据，浪费存储空间并影响 RAG 检索质量。

删除流程只调用 `vector_store.delete_by_source()` 和 `db.session.delete()`，未清理 `uploads/` 目录中的物理文件，造成磁盘空间泄漏。

### 1.2 目标

- 上传时基于文件内容 SHA-256 哈希检测重复，同用户下重复文档拒绝入库
- 删除文档时同步清理物理文件、向量库数据、数据库记录
- 物理文件删除失败不阻塞数据库清理（容错）

### 1.3 非目标

- 不做跨用户的文档查重（每个用户独立）
- 不做内容相似度检测（只做精确哈希去重）
- 不做软删除/回收站机制
- 不迁移历史数据（历史文档 `file_hash` 为空，不参与查重）

## 2. 技术方案

### 2.1 数据模型变更

`Document` 模型（`framework/models/document.py`）新增 `file_hash` 字段：

```python
file_hash = db.Column(db.String(64), nullable=True, comment='文件内容SHA-256哈希')
```

- `nullable=True`：历史数据该字段为 NULL，查重查询自动跳过
- 不加唯一约束：内部系统并发低，应用层查重已满足需求

### 2.2 文件哈希计算

新增 `compute_file_hash(file_path)` 函数（`framework/upload/file_upload.py`）：

```python
import hashlib

def compute_file_hash(file_path: str, chunk_size: int = 8192) -> str:
    """分块读取文件计算 SHA-256 哈希，避免大文件内存占用"""
    sha256 = hashlib.sha256()
    with open(file_path, 'rb') as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            sha256.update(chunk)
    return sha256.hexdigest()
```

`save_uploaded_file` 函数返回值变更为三元组：`(new_filename, file_path, file_hash)`。

### 2.3 上传查重流程

```
请求到达
  ↓
save_uploaded_file(file)  ← 保存文件 + 计算哈希
  ↓
Document.query.filter_by(file_hash=hash, create_by=user_id).first()
  ↓
  ├─ 重复 → os.remove(file_path) 删除刚保存的物理文件
  │        → 返回 409 Conflict，响应包含已存在文档 ID
  └─ 不重复 → 解析文档 → 创建 Document 记录（含 file_hash）
            → 向量化 → 返回 200
```

### 2.4 删除清理流程（方案 A）

```
请求到达
  ↓
try: vector_store.delete_by_source(doc_name)  ← 先删向量库（容错）
except: log error
  ↓
try: db.session.delete(document); db.session.commit()  ← 再删数据库（事务）
except: rollback, return 500
  ↓
try: os.remove(file_path)  ← 最后删物理文件（容错）
except: log error
  ↓
返回 200
```

**顺序选择理由**：
- 向量库删除失败不影响数据库和物理文件清理（数据一致性优先）
- 数据库事务保证 DB 一致性
- 物理文件删除失败仅日志记录，不阻塞业务

## 3. 技术风险与缓解

| 风险 | 缓解措施 |
|------|---------|
| 大文件哈希计算内存占用 | 分块读取（8192 字节/块）流式计算 |
| 查重只针对精确内容相同 | 接受此权衡，满足当前需求 |
| 物理文件删除失败导致磁盘泄漏 | 日志记录便于后续排查 |
| 数据库删除成功但物理文件删除失败 | 方案 A 的已知权衡，数据一致性优先 |
| 并发上传相同文件导致重复 | 不加唯一约束，接受极小概率（内部系统并发低） |

## 4. 测试策略

### 4.1 单元测试

- `compute_file_hash` 函数：
  - 空文件哈希
  - 小文件哈希正确性
  - 大文件分块读取正确性
  - 相同内容不同文件名哈希一致

### 4.2 集成测试

**上传查重：**
- 同用户上传重复内容（不同文件名）→ 409 Conflict
- 跨用户上传相同内容 → 200 成功
- 首次上传 → 200 成功，file_hash 已记录
- 历史文档（file_hash=NULL）不参与查重

**删除清理：**
- 正常删除：三资源（DB + 向量库 + 物理文件）全删
- 物理文件已不存在：DB 和向量库正常删除，返回 200
- 物理文件删除失败（权限）：DB 和向量库正常删除，返回 200
- 向量库删除失败：DB 和物理文件正常删除，返回 200

### 4.3 边界条件

- 历史文档 `file_hash=NULL` 不参与查重
- 空文件上传查重
- 数据库事务回滚验证

## 5. 实现范围

### 5.1 涉及文件

| 文件 | 变更 |
|------|------|
| `framework/models/document.py` | 新增 `file_hash` 字段 |
| `framework/upload/file_upload.py` | 新增 `compute_file_hash` 函数，修改 `save_uploaded_file` 返回值 |
| `framework/api/routes/docs.py` | 上传接口增加查重逻辑，删除接口增加物理文件清理 |

### 5.2 数据库变更

`kb_document` 表新增 `file_hash` 列（VARCHAR(64), nullable）。历史数据该字段为 NULL。

### 5.3 API 变更

- 上传接口：检测到重复时返回 409 Conflict，响应体包含 `existing_document_id`
- 删除接口：行为不变（仍返回 200），内部增加物理文件清理

## 6. Spec Patch

本次设计在 delta spec 的 MODIFIED Requirements 中补充了「向量库删除失败」场景，明确删除流程中向量库删除失败时的容错行为。

