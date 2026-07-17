---
change: add-doc-dedup-and-cleanup
design-doc: docs/superpowers/specs/2026-07-17-doc-dedup-and-cleanup-design.md
base-ref: b36bfdfcb6e8c28af243d8a871861d61ca2cf37c
---

# 文档上传查重与删除清理 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为文档上传流程增加基于 SHA-256 内容哈希的查重机制（同用户下拒绝重复），并在删除文档时同步清理物理文件、向量库数据与数据库记录，删除失败采用容错策略。

**Architecture:** 在 `Document` 模型新增 `file_hash` 字段（nullable，历史数据为 NULL 不参与查重）；在 `file_upload.py` 新增分块流式哈希计算函数 `compute_file_hash`，并使 `save_uploaded_file` 返回三元组 `(new_filename, file_path, file_hash)`；在 `docs.py` 上传接口保存文件后查询同用户同哈希文档，重复则删除物理文件并返回 409；删除接口按「向量库（容错）→ 数据库（事务）→ 物理文件（容错）」顺序清理三资源。

**Tech Stack:** Python 3.10+、Flask 3、Flask-SQLAlchemy、Flask-JWT-Extended、ChromaDB、Python 标准库 `hashlib`/`os`、pytest

**设计文档：** [docs/superpowers/specs/2026-07-17-doc-dedup-and-cleanup-design.md](../specs/2026-07-17-doc-dedup-and-cleanup-design.md)

## Global Constraints

- 哈希算法：SHA-256，分块读取 chunk_size=8192 字节（设计文档 2.2）
- `file_hash` 字段：`String(64), nullable=True`，不加唯一约束（设计文档 2.1）
- 查重范围：同用户（`create_by=user_id`），不跨用户（设计文档 1.3 非目标）
- 历史文档 `file_hash=NULL` 不参与查重（设计文档 1.3 非目标、delta spec 场景）
- 删除顺序：向量库（容错）→ 数据库（事务）→ 物理文件（容错）（设计文档 2.4）
- 物理文件删除失败不阻塞数据库清理（设计文档 1.2 目标）
- 不做软删除/回收站，不迁移历史数据（设计文档 1.3 非目标）
- 无新增依赖，使用 Python 标准库 `hashlib`（proposal.md Impact）
- 测试运行命令：`python -m pytest tests/ -q`（项目既有约定）
- 数据库变更通过 `init_db.py` 的 `db.drop_all()` + `db.create_all()` 应用，无需单独迁移脚本（init_db.py 既有机制）

---

## 任务概览

| 计划任务 | 对应 tasks.md | 职责 |
|---------|--------------|------|
| Task 1 | 1.1 | Document 模型新增 `file_hash` 字段 |
| Task 2 | 1.2 | 新增 `compute_file_hash` 函数 |
| Task 3 | 1.3 | `save_uploaded_file` 返回三元组 |
| Task 4 | 2.1, 2.2, 2.3 | 上传接口查重逻辑 |
| Task 5 | 3.1, 3.2, 3.3 | 删除接口物理文件清理 |
| Task 6 | 4.1, 4.2, 4.3 | 端到端验证 |

---

### Task 1: Document 模型新增 file_hash 字段 ✓

**Files:**
- Modify: `framework/models/document.py`
- Test: `tests/test_upload.py`（既有文件，扩展测试用例）

**Interfaces:**
- Consumes: 无
- Produces: `Document.file_hash` 字段（`db.Column(db.String(64), nullable=True)`）；`Document.to_dict()` 返回值新增 `file_hash` 键。后续 Task 4 上传接口写入此字段，Task 4 查重查询 `filter_by(file_hash=...)` 依赖此字段。

- [ ] **Step 1: 编写失败测试（模型字段定义）**

在 `tests/test_upload.py` 的 `test_document_model_fields` 函数中追加 `file_hash` 字段断言：

```python
def test_document_model_fields():
    """测试文档模型字段定义"""
    from framework.models.document import Document
    assert Document.__tablename__ == 'kb_document'
    assert hasattr(Document, 'doc_name')
    assert hasattr(Document, 'file_path')
    assert hasattr(Document, 'file_type')
    assert hasattr(Document, 'file_size')
    assert hasattr(Document, 'chunk_count')
    assert hasattr(Document, 'status')
    assert hasattr(Document, 'category')
    assert hasattr(Document, 'create_by')
    assert hasattr(Document, 'file_hash')
    print("✓ 文档模型字段定义正确")
```

- [ ] **Step 2: 编写失败测试（to_dict 包含 file_hash）**

在 `tests/test_upload.py` 的 `test_document_to_dict` 函数中追加 `file_hash` 断言：

```python
def test_document_to_dict():
    """测试文档模型 to_dict 方法"""
    from framework.models.document import Document
    doc = Document()
    doc.id = 1
    doc.doc_name = "test.pdf"
    doc.file_type = "pdf"
    doc.file_size = 1024
    doc.chunk_count = 5
    doc.status = 1
    doc.category = "report"
    doc.create_by = 1
    doc.file_hash = "abc123def456"

    result = doc.to_dict()
    assert result["doc_name"] == "test.pdf"
    assert result["file_type"] == "pdf"
    assert result["file_size"] == 1024
    assert result["chunk_count"] == 5
    assert result["file_hash"] == "abc123def456"
    print("✓ 文档模型 to_dict 方法正常")
```

- [ ] **Step 3: 运行测试确认失败**

Run: `python -m pytest tests/test_upload.py::test_document_model_fields tests/test_upload.py::test_document_to_dict -v`
Expected: FAIL，`assert hasattr(Document, 'file_hash')` 为 False，且 `to_dict()` 无 `file_hash` 键

- [ ] **Step 4: 实现 file_hash 字段与 to_dict 更新**

修改 `framework/models/document.py`，在 `create_by` 字段后新增 `file_hash` 字段，并在 `to_dict` 中加入 `file_hash`：

```python
from datetime import datetime
from .user import db

class Document(db.Model):
    __tablename__ = 'kb_document'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True, comment='文档ID')
    doc_name = db.Column(db.String(255), nullable=False, comment='文档原始文件名')
    file_path = db.Column(db.String(500), nullable=False, comment='文件存储相对路径')
    file_type = db.Column(db.String(20), nullable=False, comment='文件类型')
    file_size = db.Column(db.BigInteger, default=0, comment='文件大小(字节)')
    chunk_count = db.Column(db.Integer, default=0, comment='文本分割后的片段数量')
    status = db.Column(db.SmallInteger, default=1, comment='状态')
    category = db.Column(db.String(30), default='other', comment='文档分类')
    treatment_type = db.Column(db.String(30), nullable=True, comment='治理类型')
    file_hash = db.Column(db.String(64), nullable=True, comment='文件内容SHA-256哈希')
    create_by = db.Column(db.Integer, nullable=False, comment='上传者用户ID')
    create_time = db.Column(db.DateTime, default=db.func.current_timestamp(), comment='上传时间')
    update_time = db.Column(db.DateTime, default=db.func.current_timestamp(), onupdate=db.func.current_timestamp(), comment='更新时间')

    def to_dict(self):
        return {
            'id': self.id,
            'doc_name': self.doc_name,
            'file_type': self.file_type,
            'file_size': self.file_size,
            'chunk_count': self.chunk_count,
            'status': self.status,
            'category': self.category,
            'treatment_type': self.treatment_type,
            'file_hash': self.file_hash,
            'create_by': self.create_by,
            'create_time': self.create_time.strftime('%Y-%m-%d %H:%M:%S') if self.create_time else None,
            'update_time': self.update_time.strftime('%Y-%m-%d %H:%M:%S') if self.update_time else None
        }
```

- [ ] **Step 5: 运行测试确认通过**

Run: `python -m pytest tests/test_upload.py::test_document_model_fields tests/test_upload.py::test_document_to_dict -v`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add framework/models/document.py tests/test_upload.py
git commit -m "feat(document): 新增 file_hash 字段存储文件内容SHA-256哈希"
```

---

### Task 2: 新增 compute_file_hash 函数 ✓

**Files:**
- Modify: `framework/upload/file_upload.py`
- Test: `tests/test_upload.py`（既有文件，扩展测试用例）

**Interfaces:**
- Consumes: 无
- Produces: `compute_file_hash(file_path: str, chunk_size: int = 8192) -> str` 函数。Task 3 的 `save_uploaded_file` 内部调用此函数；Task 4 上传接口间接依赖（通过 `save_uploaded_file` 返回值）。

- [ ] **Step 1: 编写失败测试（空文件哈希）**

在 `tests/test_upload.py` 末尾（`if __name__` 之前）新增测试函数：

```python
def test_compute_file_hash_empty_file():
    """测试空文件的SHA-256哈希"""
    import hashlib
    from framework.upload.file_upload import compute_file_hash
    test_file = os.path.join(os.path.dirname(__file__), "test_empty_hash.txt")
    with open(test_file, 'w', encoding='utf-8') as f:
        f.write("")

    result = compute_file_hash(test_file)
    expected = hashlib.sha256(b"").hexdigest()
    assert result == expected
    assert result == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    print("✓ 空文件哈希正确")
    os.remove(test_file)
```

- [ ] **Step 2: 编写失败测试（小文件正确性与一致性）**

```python
def test_compute_file_hash_small_file():
    """测试小文件SHA-256哈希正确性与一致性"""
    import hashlib
    from framework.upload.file_upload import compute_file_hash
    content = "这是测试文本内容，用于验证哈希计算。\n第二行内容。"
    test_file = os.path.join(os.path.dirname(__file__), "test_small_hash.txt")
    with open(test_file, 'w', encoding='utf-8') as f:
        f.write(content)

    result = compute_file_hash(test_file)
    expected = hashlib.sha256(content.encode('utf-8')).hexdigest()
    assert result == expected

    # 相同内容不同文件名，哈希应一致
    test_file2 = os.path.join(os.path.dirname(__file__), "test_small_hash_copy.txt")
    with open(test_file2, 'w', encoding='utf-8') as f:
        f.write(content)
    result2 = compute_file_hash(test_file2)
    assert result == result2
    print("✓ 小文件哈希正确且一致")
    os.remove(test_file)
    os.remove(test_file2)
```

- [ ] **Step 3: 编写失败测试（大文件分块读取正确性）**

```python
def test_compute_file_hash_large_file_chunked():
    """测试大文件分块读取哈希正确性（超过8192字节触发多次分块）"""
    import hashlib
    from framework.upload.file_upload import compute_file_hash
    # 生成 20000 字节内容，确保超过 chunk_size=8192 触发多次分块
    content = "A" * 20000
    test_file = os.path.join(os.path.dirname(__file__), "test_large_hash.txt")
    with open(test_file, 'w', encoding='utf-8') as f:
        f.write(content)

    result = compute_file_hash(test_file)
    expected = hashlib.sha256(content.encode('utf-8')).hexdigest()
    assert result == expected

    # 验证自定义 chunk_size 不影响结果
    result_custom_chunk = compute_file_hash(test_file, chunk_size=1024)
    assert result == result_custom_chunk
    print("✓ 大文件分块哈希正确")
    os.remove(test_file)
```

- [ ] **Step 4: 运行测试确认失败**

Run: `python -m pytest tests/test_upload.py::test_compute_file_hash_empty_file tests/test_upload.py::test_compute_file_hash_small_file tests/test_upload.py::test_compute_file_hash_large_file_chunked -v`
Expected: FAIL，`ImportError: cannot import name 'compute_file_hash'`

- [ ] **Step 5: 实现 compute_file_hash 函数**

在 `framework/upload/file_upload.py` 顶部新增 `import hashlib`，并在 `save_uploaded_file` 函数之前新增 `compute_file_hash` 函数：

```python
import os
import uuid
import hashlib
from framework.config import Config

ALLOWED_EXTENSIONS = {'txt', 'md', 'pdf', 'docx', 'xlsx', 'xls'}

def allowed_file(filename: str) -> bool:
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

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

def save_uploaded_file(file) -> tuple[str, str]:
    os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)

    filename = file.filename
    extension = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
    new_filename = f"{uuid.uuid4().hex}.{extension}"
    file_path = os.path.join(Config.UPLOAD_FOLDER, new_filename)

    file.save(file_path)

    return new_filename, file_path

def get_file_type(filename: str) -> str:
    extension = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
    type_map = {
        'txt': 'txt',
        'md': 'md',
        'pdf': 'pdf',
        'docx': 'docx',
        'xlsx': 'xlsx',
        'xls': 'xlsx',
    }
    return type_map.get(extension, 'other')
```

- [ ] **Step 6: 运行测试确认通过**

Run: `python -m pytest tests/test_upload.py::test_compute_file_hash_empty_file tests/test_upload.py::test_compute_file_hash_small_file tests/test_upload.py::test_compute_file_hash_large_file_chunked -v`
Expected: PASS（3 个测试全部通过）

- [ ] **Step 7: 提交**

```bash
git add framework/upload/file_upload.py tests/test_upload.py
git commit -m "feat(file-upload): 新增 compute_file_hash 分块计算SHA-256哈希"
```

---

### Task 3: save_uploaded_file 返回三元组 ✓

**Files:**
- Modify: `framework/upload/file_upload.py`
- Modify: `framework/api/routes/docs.py`（调用方适配，仅解包变更，不含查重逻辑）
- Test: `tests/test_upload.py`（既有文件，扩展测试用例）

**Interfaces:**
- Consumes: Task 2 的 `compute_file_hash(file_path) -> str`
- Produces: `save_uploaded_file(file) -> tuple[str, str, str]`，返回 `(new_filename, file_path, file_hash)`。Task 4 上传接口依赖此三元组获取 `file_hash` 进行查重。

- [ ] **Step 1: 编写失败测试（返回三元组且哈希正确）**

在 `tests/test_upload.py` 末尾新增测试函数。使用临时 mock 文件对象模拟 Flask 的 `file.save()`：

```python
def test_save_uploaded_file_returns_triple():
    """测试 save_uploaded_file 返回三元组且哈希正确"""
    import tempfile
    import hashlib
    from framework.config import Config
    from framework.upload.file_upload import save_uploaded_file

    # 使用临时目录作为 UPLOAD_FOLDER
    original_folder = Config.UPLOAD_FOLDER
    tmp_dir = tempfile.mkdtemp()
    Config.UPLOAD_FOLDER = tmp_dir

    content = b"test content for save_uploaded_file triple return"

    class MockFile:
        filename = "test_triple.txt"
        def save(self, path):
            with open(path, 'wb') as f:
                f.write(content)

    try:
        new_filename, file_path, file_hash = save_uploaded_file(MockFile())
        assert new_filename.endswith(".txt")
        assert os.path.exists(file_path)
        assert file_hash == hashlib.sha256(content).hexdigest()
        print("✓ save_uploaded_file 返回三元组且哈希正确")
        os.remove(file_path)
    finally:
        Config.UPLOAD_FOLDER = original_folder
        os.rmdir(tmp_dir)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_upload.py::test_save_uploaded_file_returns_triple -v`
Expected: FAIL，`ValueError: too many values to unpack`（当前只返回二元组）

- [ ] **Step 3: 修改 save_uploaded_file 返回三元组**

修改 `framework/upload/file_upload.py` 的 `save_uploaded_file` 函数，在保存文件后调用 `compute_file_hash` 并返回三元组：

```python
def save_uploaded_file(file) -> tuple[str, str, str]:
    os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)

    filename = file.filename
    extension = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
    new_filename = f"{uuid.uuid4().hex}.{extension}"
    file_path = os.path.join(Config.UPLOAD_FOLDER, new_filename)

    file.save(file_path)
    file_hash = compute_file_hash(file_path)

    return new_filename, file_path, file_hash
```

- [ ] **Step 4: 适配调用方 docs.py 解包（仅解包，不含查重逻辑）**

修改 `framework/api/routes/docs.py` 的 `upload_document` 函数第 31 行，将二元组解包改为三元组解包：

```python
    new_filename, file_path, file_hash = save_uploaded_file(file)
    file_type = get_file_type(file.filename)
```

- [ ] **Step 5: 运行测试确认通过**

Run: `python -m pytest tests/test_upload.py::test_save_uploaded_file_returns_triple -v`
Expected: PASS

- [ ] **Step 6: 运行全量测试确认无回归**

Run: `python -m pytest tests/test_upload.py -v`
Expected: PASS（所有 test_upload.py 测试通过）

- [ ] **Step 7: 提交**

```bash
git add framework/upload/file_upload.py framework/api/routes/docs.py tests/test_upload.py
git commit -m "feat(file-upload): save_uploaded_file 返回三元组含文件哈希"
```

---

### Task 4: 上传接口查重逻辑

**Files:**
- Modify: `framework/api/routes/docs.py`（`upload_document` 函数）
- Test: `tests/test_docs_dedup.py`（新建）

**Interfaces:**
- Consumes: Task 1 的 `Document.file_hash` 字段；Task 3 的 `save_uploaded_file` 三元组返回值 `(new_filename, file_path, file_hash)`
- Produces: 上传接口在检测到同用户同哈希重复时返回 409 Conflict，响应体包含 `existing_document_id`；非重复时 `Document` 记录写入 `file_hash` 字段。

- [ ] **Step 1: 创建集成测试文件与测试辅助**

创建 `tests/test_docs_dedup.py`，包含测试辅助函数（创建 Flask 测试 app、mock vector_store、注册用户获取 JWT token）：

```python
"""测试文档上传查重与删除清理功能"""
import sys
import os
import shutil
import tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from framework.api.app import create_app
from framework.models.user import db, User
from framework.config import Config, SQLiteConfig
from werkzeug.security import generate_password_hash


class MockVectorStore:
    """模拟向量库，避免测试依赖 ChromaDB 磁盘操作"""
    def __init__(self):
        self._should_fail = False

    def add_documents(self, texts, metadatas=None, ids=None):
        if self._should_fail:
            raise RuntimeError("mock vector store failure")
        return len(texts) if texts else 0

    def delete_by_source(self, source_doc_name):
        if self._should_fail:
            raise RuntimeError("mock vector store failure")
        return 0

    def set_fail(self, should_fail):
        self._should_fail = should_fail


@pytest.fixture
def client(monkeypatch):
    """创建测试客户端，使用 SQLite 临时文件数据库，mock 向量库"""
    tmp_upload = tempfile.mkdtemp(prefix="test_upload_")
    tmp_db_dir = tempfile.mkdtemp(prefix="test_db_")
    tmp_db_path = os.path.join(tmp_db_dir, "test.db")

    original_folder = Config.UPLOAD_FOLDER
    original_db_uri = SQLiteConfig.SQLALCHEMY_DATABASE_URI
    Config.UPLOAD_FOLDER = tmp_upload
    # 在 create_app 之前覆盖 SQLiteConfig 的 URI，确保引擎绑定到临时文件
    SQLiteConfig.SQLALCHEMY_DATABASE_URI = f'sqlite:///{tmp_db_path}'

    app = create_app('sqlite')
    app.config['TESTING'] = True

    mock_vs = MockVectorStore()
    monkeypatch.setattr('framework.api.routes.docs.vector_store', mock_vs)

    with app.app_context():
        db.drop_all()
        db.create_all()
        admin = User(
            username='admin',
            password=generate_password_hash('admin123'),
            nickname='管理员',
            role='admin',
            status=1
        )
        user2 = User(
            username='user2',
            password=generate_password_hash('user1234'),
            nickname='用户2',
            role='user',
            status=1
        )
        db.session.add(admin)
        db.session.add(user2)
        db.session.commit()
        admin_id = admin.id
        user2_id = user2.id

    client = app.test_client()

    # 暴露 app、mock_vs 和用户 ID 供测试使用
    client._app = app
    client._mock_vs = mock_vs
    client._admin_id = admin_id
    client._user2_id = user2_id
    client._tmp_upload = tmp_upload

    yield client

    Config.UPLOAD_FOLDER = original_folder
    SQLiteConfig.SQLALCHEMY_DATABASE_URI = original_db_uri
    shutil.rmtree(tmp_upload, ignore_errors=True)
    shutil.rmtree(tmp_db_dir, ignore_errors=True)


def _login(client, username, password):
    """登录获取 JWT token"""
    resp = client.post('/api/v1/auth/login', json={
        'username': username,
        'password': password
    })
    assert resp.status_code == 200
    return resp.get_json()['data']['token']


def _upload(client, token, filename, content):
    """上传文件辅助函数"""
    resp = client.post(
        '/api/v1/docs/upload',
        headers={'Authorization': f'Bearer {token}'},
        data={'file': (content, filename)},
        content_type='multipart/form-data'
    )
    return resp
```

- [ ] **Step 2: 编写失败测试（首次上传成功且 file_hash 已记录）**

在 `tests/test_docs_dedup.py` 追加测试：

```python
def test_upload_first_occurrence_stores_hash(client):
    """首次上传成功，file_hash 已记录"""
    token = _login(client, 'admin', 'admin123')
    resp = _upload(client, token, 'first.txt', b'unique content for first upload')

    assert resp.status_code == 200
    data = resp.get_json()
    assert data['status'] == 'ok'
    assert data['data']['file_hash'] is not None
    assert len(data['data']['file_hash']) == 64
    print("✓ 首次上传成功，file_hash 已记录")
```

- [ ] **Step 3: 编写失败测试（同用户重复内容返回 409）**

```python
def test_upload_duplicate_same_user_returns_409(client):
    """同用户上传重复内容（不同文件名）返回 409 Conflict"""
    token = _login(client, 'admin', 'admin123')

    # 首次上传
    resp1 = _upload(client, token, 'original.txt', b'duplicate detection test content')
    assert resp1.status_code == 200
    existing_id = resp1.get_json()['data']['id']

    # 同用户再次上传相同内容，不同文件名
    resp2 = _upload(client, token, 'renamed_copy.txt', b'duplicate detection test content')

    assert resp2.status_code == 409
    data = resp2.get_json()
    assert data['status'] == 'error'
    assert data['existing_document_id'] == existing_id
    print("✓ 同用户重复上传返回 409 Conflict")
```

- [ ] **Step 4: 编写失败测试（跨用户相同内容上传成功）**

```python
def test_upload_same_content_different_users_succeeds(client):
    """跨用户上传相同内容返回 200 成功"""
    token1 = _login(client, 'admin', 'admin123')
    token2 = _login(client, 'user2', 'user1234')

    resp1 = _upload(client, token1, 'user1_doc.txt', b'shared content across users')
    assert resp1.status_code == 200

    resp2 = _upload(client, token2, 'user2_doc.txt', b'shared content across users')
    assert resp2.status_code == 200
    assert resp2.get_json()['data']['id'] != resp1.get_json()['data']['id']
    print("✓ 跨用户相同内容上传成功")
```

- [ ] **Step 5: 编写失败测试（历史文档 file_hash=NULL 不参与查重）**

在 `tests/test_docs_dedup.py` 追加测试。模拟历史文档（file_hash 为 NULL）存在时，上传新内容不应被误判为重复：

```python
def test_upload_skips_historical_null_hash_documents(client):
    """历史文档 file_hash=NULL 不参与查重，上传不同内容应成功"""
    from framework.models.document import Document
    token = _login(client, 'admin', 'admin123')

    # 直接向数据库插入一条历史文档（file_hash=NULL）
    with client._app.app_context():
        legacy_doc = Document(
            doc_name='legacy.txt',
            file_path='legacy_file.txt',
            file_type='txt',
            file_size=100,
            chunk_count=1,
            status=1,
            file_hash=None,
            create_by=client._admin_id,
        )
        db.session.add(legacy_doc)
        db.session.commit()

    # 上传不同内容的新文档，应成功（不被历史 NULL hash 文档干扰）
    resp = _upload(client, token, 'new_content.txt', b'brand new content different from legacy')
    assert resp.status_code == 200
    assert resp.get_json()['data']['file_hash'] is not None
    print("✓ 历史文档 file_hash=NULL 不参与查重")
```

- [ ] **Step 6: 编写失败测试（重复上传后物理文件已删除）**

```python
def test_upload_duplicate_deletes_physical_file(client):
    """检测到重复时，刚保存的物理文件应被删除"""
    token = _login(client, 'admin', 'admin123')
    _upload(client, token, 'keep.txt', b'keep this content')

    resp = _upload(client, token, 'dup.txt', b'keep this content')
    assert resp.status_code == 409

    # uploads 目录中应只有首次上传的文件，无重复文件
    files_after = os.listdir(client._tmp_upload)
    assert len(files_after) == 1
    print("✓ 重复上传时物理文件已清理")
```

- [ ] **Step 7: 运行测试确认失败**

Run: `python -m pytest tests/test_docs_dedup.py -v`
Expected: FAIL，`test_upload_first_occurrence_stores_hash` 中 `file_hash` 为 None（当前 docs.py 未写入 file_hash）；`test_upload_duplicate_same_user_returns_409` 返回 200 而非 409（当前无查重逻辑）

- [ ] **Step 8: 实现上传查重逻辑**

修改 `framework/api/routes/docs.py` 的 `upload_document` 函数，在 `save_uploaded_file` 之后、`parse_document` 之前插入查重逻辑，并在创建 `Document` 时写入 `file_hash`：

```python
@docs_bp.route('/upload', methods=['POST'])
@jwt_required()
def upload_document():
    user_id = get_jwt_identity()
    if 'file' not in request.files:
        return jsonify({"status": "error", "message": "未选择文件"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"status": "error", "message": "未选择文件"}), 400
    if not allowed_file(file.filename):
        return jsonify({"status": "error", "message": "不支持的文件类型"}), 400

    new_filename, file_path, file_hash = save_uploaded_file(file)
    file_type = get_file_type(file.filename)

    # 查重：同用户下相同 file_hash 视为重复
    existing = Document.query.filter_by(file_hash=file_hash, create_by=user_id).first()
    if existing:
        os.remove(file_path)
        return jsonify({
            "status": "error",
            "message": "文档内容已存在",
            "existing_document_id": existing.id
        }), 409

    content = parse_document(file_path, file_type)
    chunks = []
    if content:
        chunks = [content[i:i+800] for i in range(0, len(content), 800)]
        metadatas = [{"source": file.filename} for _ in chunks]
        vector_store.add_documents(chunks, metadatas)

    document = Document(
        doc_name=file.filename,
        file_path=new_filename,
        file_type=file_type,
        file_size=os.path.getsize(file_path),
        chunk_count=len(chunks) if content else 0,
        status=1,
        file_hash=file_hash,
        create_by=user_id,
    )
    db.session.add(document)
    db.session.commit()

    return jsonify({"status": "ok", "data": document.to_dict(), "message": "文档上传成功"})
```

- [ ] **Step 9: 运行测试确认通过**

Run: `python -m pytest tests/test_docs_dedup.py -v`
Expected: PASS（5 个测试全部通过）

- [ ] **Step 10: 运行全量测试确认无回归**

Run: `python -m pytest tests/ -q`
Expected: PASS（所有测试通过，无回归）

- [ ] **Step 11: 提交**

```bash
git add framework/api/routes/docs.py tests/test_docs_dedup.py
git commit -m "feat(docs): 上传接口增加基于SHA-256的内容查重，重复返回409"
```

---

### Task 5: 删除接口物理文件清理

**Files:**
- Modify: `framework/api/routes/docs.py`（`delete_document` 函数）
- Test: `tests/test_docs_dedup.py`（Task 4 创建的文件，扩展测试用例）

**Interfaces:**
- Consumes: `document.file_path`（存储相对路径，需与 `Config.UPLOAD_FOLDER` 拼接得到绝对路径）；`vector_store.delete_by_source(doc_name)`
- Produces: 删除接口按「向量库（容错）→ 数据库（事务）→ 物理文件（容错）」顺序清理，物理文件删除失败不阻塞业务，返回 200。

**删除顺序说明（设计文档 2.4）：** 先删向量库（容错）→ 再删数据库（事务）→ 最后删物理文件（容错）。此顺序确保数据库一致性优先：若物理文件删除失败，DB 和向量库已清理，系统仍一致，仅泄漏一个磁盘文件。

- [ ] **Step 1: 编写失败测试（正常删除清理三资源）**

在 `tests/test_docs_dedup.py` 追加测试：

```python
def test_delete_removes_db_vector_and_file(client):
    """正常删除：数据库记录、向量库数据、物理文件全删"""
    token = _login(client, 'admin', 'admin123')
    resp = _upload(client, token, 'to_delete.txt', b'content to be deleted')
    assert resp.status_code == 200
    doc_id = resp.get_json()['data']['id']
    file_path_relative = resp.get_json()['data'].get('file_path')

    # 确认物理文件存在
    files_before = os.listdir(client._tmp_upload)
    assert len(files_before) == 1

    # 删除文档
    del_resp = client.delete(
        f'/api/v1/docs/{doc_id}',
        headers={'Authorization': f'Bearer {token}'}
    )
    assert del_resp.status_code == 200

    # 验证数据库记录已删除
    from framework.models.document import Document
    with client._app.app_context():
        doc = Document.query.get(doc_id)
        assert doc is None

    # 验证物理文件已删除
    files_after = os.listdir(client._tmp_upload)
    assert len(files_after) == 0
    print("✓ 正常删除清理三资源完成")
```

- [ ] **Step 2: 编写失败测试（物理文件已不存在时不报错）**

```python
def test_delete_when_physical_file_missing(client):
    """物理文件已不存在时，DB 和向量库正常删除，返回 200"""
    token = _login(client, 'admin', 'admin123')
    resp = _upload(client, token, 'file_will_be_missing.txt', b'content for missing file test')
    assert resp.status_code == 200
    doc_id = resp.get_json()['data']['id']

    # 手动删除物理文件模拟文件已不存在
    files = os.listdir(client._tmp_upload)
    for f in files:
        os.remove(os.path.join(client._tmp_upload, f))

    # 删除文档，应不报错
    del_resp = client.delete(
        f'/api/v1/docs/{doc_id}',
        headers={'Authorization': f'Bearer {token}'}
    )
    assert del_resp.status_code == 200

    from framework.models.document import Document
    with client._app.app_context():
        assert Document.query.get(doc_id) is None
    print("✓ 物理文件已不存在时删除不报错")
```

- [ ] **Step 3: 编写失败测试（物理文件删除失败时不阻塞）**

```python
def test_delete_when_physical_file_deletion_fails(client, monkeypatch):
    """物理文件删除失败（权限错误）时，DB 和向量库正常删除，返回 200"""
    token = _login(client, 'admin', 'admin123')
    resp = _upload(client, token, 'protected.txt', b'content for deletion failure test')
    assert resp.status_code == 200
    doc_id = resp.get_json()['data']['id']

    # mock os.remove 抛出权限异常
    import builtins
    original_remove = os.remove
    def fail_remove(path):
        raise PermissionError("mock permission denied")
    monkeypatch.setattr(os, 'remove', fail_remove)

    del_resp = client.delete(
        f'/api/v1/docs/{doc_id}',
        headers={'Authorization': f'Bearer {token}'}
    )

    # 恢复 os.remove 以便清理
    monkeypatch.setattr(os, 'remove', original_remove)

    assert del_resp.status_code == 200
    from framework.models.document import Document
    with client._app.app_context():
        assert Document.query.get(doc_id) is None
    print("✓ 物理文件删除失败时不阻塞业务")
```

- [ ] **Step 4: 编写失败测试（向量库删除失败时不阻塞）**

```python
def test_delete_when_vector_store_fails(client):
    """向量库删除失败时，DB 和物理文件正常删除，返回 200"""
    token = _login(client, 'admin', 'admin123')
    resp = _upload(client, token, 'vector_fail_test.txt', b'content for vector store failure test')
    assert resp.status_code == 200
    doc_id = resp.get_json()['data']['id']

    # 配置 mock 向量库删除时抛异常
    client._mock_vs.set_fail(True)

    del_resp = client.delete(
        f'/api/v1/docs/{doc_id}',
        headers={'Authorization': f'Bearer {token}'}
    )

    client._mock_vs.set_fail(False)

    assert del_resp.status_code == 200
    from framework.models.document import Document
    with client._app.app_context():
        assert Document.query.get(doc_id) is None
    # 物理文件应已被删除
    files_after = os.listdir(client._tmp_upload)
    assert len(files_after) == 0
    print("✓ 向量库删除失败时不阻塞业务")
```

- [ ] **Step 5: 运行测试确认失败**

Run: `python -m pytest tests/test_docs_dedup.py -v -k "delete"`
Expected: FAIL，`test_delete_removes_db_vector_and_file` 中物理文件仍存在（当前 docs.py 未清理物理文件）；其余删除失败场景测试失败

- [ ] **Step 6: 实现删除清理逻辑**

修改 `framework/api/routes/docs.py` 的 `delete_document` 函数，按设计文档 2.4 顺序清理三资源，每步容错：

```python
@docs_bp.route('/<int:id>', methods=['DELETE'])
@jwt_required()
def delete_document(id):
    user_id = get_jwt_identity()
    document = Document.query.filter_by(id=id, create_by=user_id).first()
    if not document:
        return jsonify({"status": "error", "message": "文档不存在"}), 404

    # 1. 先删向量库（容错）
    try:
        vector_store.delete_by_source(document.doc_name)
    except Exception as e:
        print(f"向量库删除失败，已跳过: {e}")

    # 2. 再删数据库（事务）
    try:
        db.session.delete(document)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"数据库删除失败: {e}")
        return jsonify({"status": "error", "message": "文档删除失败"}), 500

    # 3. 最后删物理文件（容错）
    file_path = os.path.join(Config.UPLOAD_FOLDER, document.file_path)
    try:
        os.remove(file_path)
    except Exception as e:
        print(f"物理文件删除失败，已跳过: {e}")

    return jsonify({"status": "ok", "message": "文档删除成功"})
```

- [ ] **Step 7: 在 docs.py 顶部补充 Config 导入**

确认 `framework/api/routes/docs.py` 顶部导入 `Config`（当前文件未导入）。修改导入段：

```python
import os
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from framework.config import Config
from framework.models.document import Document
from framework.models.user import db
from framework.upload.file_upload import allowed_file, save_uploaded_file, get_file_type
from framework.upload.document_parser import parse_document
from framework.vector_store.chroma_store import vector_store
```

- [ ] **Step 8: 运行删除测试确认通过**

Run: `python -m pytest tests/test_docs_dedup.py -v -k "delete"`
Expected: PASS（4 个删除测试全部通过）

- [ ] **Step 9: 运行全量测试确认无回归**

Run: `python -m pytest tests/ -q`
Expected: PASS（所有测试通过，无回归）

- [ ] **Step 10: 提交**

```bash
git add framework/api/routes/docs.py tests/test_docs_dedup.py
git commit -m "feat(docs): 删除接口按容错顺序清理向量库、数据库、物理文件"
```

---

### Task 6: 端到端验证

**Files:**
- 无新增文件，运行既有测试与手动验证

**Interfaces:**
- Consumes: Task 1-5 的全部实现
- Produces: 验证报告（对应 tasks.md 4.1, 4.2, 4.3）

- [ ] **Step 1: 验证上传查重返回 409（tasks.md 4.1）**

Run: `python -m pytest tests/test_docs_dedup.py::test_upload_duplicate_same_user_returns_409 tests/test_docs_dedup.py::test_upload_same_content_different_users_succeeds tests/test_docs_dedup.py::test_upload_first_occurrence_stores_hash tests/test_docs_dedup.py::test_upload_duplicate_deletes_physical_file tests/test_docs_dedup.py::test_upload_skips_historical_null_hash_documents -v`
Expected: PASS（5 个查重相关测试通过，覆盖：同用户重复 409、跨用户成功、首次上传记录 hash、重复时物理文件清理、历史 NULL hash 不参与查重）

- [ ] **Step 2: 验证删除清理物理文件（tasks.md 4.2）**

Run: `python -m pytest tests/test_docs_dedup.py::test_delete_removes_db_vector_and_file -v`
Expected: PASS（验证删除后 `uploads/` 目录中物理文件已被删除）

- [ ] **Step 3: 验证物理文件已不存在时不报错（tasks.md 4.3）**

Run: `python -m pytest tests/test_docs_dedup.py::test_delete_when_physical_file_missing tests/test_docs_dedup.py::test_delete_when_physical_file_deletion_fails tests/test_docs_dedup.py::test_delete_when_vector_store_fails -v`
Expected: PASS（3 个容错场景测试通过：文件缺失、文件删除失败、向量库删除失败）

- [ ] **Step 4: 运行全量测试套件确认无回归**

Run: `python -m pytest tests/ -q`
Expected: PASS（所有测试通过，无回归）

- [ ] **Step 5: 数据库结构验证（init_db.py 重建）**

Run: `python init_db.py`
Expected: 输出 `[初始化] 数据库表结构创建完成`，无报错。`kb_document` 表包含 `file_hash` 列。

验证 `file_hash` 列存在：
Run: `python -c "from framework.api.app import create_app; from framework.models.user import db; from sqlalchemy import inspect; app=create_app('sqlite'); app.app_context().push(); db.create_all(); cols=[c['name'] for c in inspect(db.engine).get_columns('kb_document')]; print('file_hash' in cols)"`
Expected: `True`

- [ ] **Step 6: 提交验证结果（如有变更）**

若验证过程中发现并修复了问题，提交修复。若无变更则跳过此步。

```bash
git status
# 若有变更：
git add -A
git commit -m "test: 端到端验证文档查重与删除清理功能"
```

---

## 执行顺序

按 Task 1 → 2 → 3 → 4 → 5 → 6 顺序执行。每个 Task 内部按 Step 顺序执行（TDD：先写测试 → 确认失败 → 实现 → 确认通过 → 提交）。

Task 1-3 为基础设施（模型字段、哈希函数、返回值），互相有依赖（Task 3 依赖 Task 2，Task 4 依赖 Task 1 和 Task 3）。Task 4 和 Task 5 互相独立但都依赖 Task 1-3。Task 6 为最终验证。

## 风险与缓解

| 风险 | 缓解措施 |
|------|---------|
| `save_uploaded_file` 返回值从二元组变三元组，可能影响其他调用方 | 仅 `docs.py` 一处调用（已通过全局搜索确认），Task 3 同步适配 |
| 集成测试中 ChromaDB 初始化写磁盘 | 测试使用 `MockVectorStore` 通过 monkeypatch 替换，避免真实 ChromaDB 操作 |
| 删除顺序与 tasks.md 3.1 描述不同 | 以设计文档 2.4 为准（向量库→DB→物理文件），设计文档提供明确数据一致性 rationale，delta spec 场景与此顺序一致 |
| 历史文档 `file_hash=NULL` | 查重查询 `filter_by(file_hash=file_hash)` 中 `file_hash` 为非 NULL 哈希值，NULL 记录不匹配，自动跳过 |
| 数据库 schema 变更 | `init_db.py` 使用 `db.drop_all()` + `db.create_all()`，重新运行即可应用新 schema，无需迁移脚本 |
