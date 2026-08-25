---
change: kb-ingestion-quality
design-doc: docs/superpowers/specs/2026-08-25-kb-ingestion-quality-design.md
base-ref: 51adad01597cc00b44c8715cec047247dae7e794
---

# kb-ingestion-quality 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: 使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务执行本计划。步骤用复选框（`- [ ]`）语法跟踪进度。

**Goal:** 在 P0（hybrid retrieval：向量 + BM25 + RRF + rerank）与 P1（同义词预处理 + chunk 元数据 + 分领域 collection）之上，补齐入库质量治理与可观测性：解析后文本清洗、上传管线异步化、OCR/表格解析主路径化、答案引用溯源到 chunk/页码、检索质量评估脚本（hit_rate@K + MRR）。

**Architecture:** 最小侵入式（方案 A）。新增独立模块 `framework/upload/text_cleaner.py`（纯函数清洗）与 `framework/upload/ingestion_worker.py`（ThreadPoolExecutor 异步 worker + 状态机）；`document_parser.py` 增 `page_aware` 参数与图片型 PDF 检测/表格 Markdown 提取；`chunker.py` 新增 `split_text_with_pages()`（跨页不拼接，page 字段精确）；`chain.py` sources 由「按文档去重」改为「按 chunk 输出」并补 `chunk_index/page`；新增 `scripts/eval_retrieval.py` + `tests/fixtures/eval_queries.yaml`。每项能力保留向后兼容签名，避免影响既有调用方。

**Tech Stack:** Python 3.10+、Flask、Flask-SQLAlchemy、pdfplumber、pytesseract、pdf2image、Pillow、ChromaDB、PyYAML、pytest。

## Global Constraints

- **工作方式（用户已确认）**：worktree 隔离 + direct 执行（full workflow 用 direct，需 `direct_override=true`）+ TDD（每任务先 Red 失败测试 → Green 实现 → Refactor）+ thorough 审查（每 3 任务分段审查 + 最终完整审查）。
- **Comet 上下文**：当前 change 为 `kb-ingestion-quality`，workflow=classic。本计划属于 Classic Build 阶段实施计划，落地写入由 Classic Hook Guard 裁决；实施时按 `/comet-classic` Build 阶段协议推进。
- **status 枚举重定义不迁移数据**：`STATUS_PENDING=0 / STATUS_COMPLETED=1 / STATUS_PROCESSING=2 / STATUS_FAILED=3`；现有 `status=1` 数据继续表「已完成」，无需 schema 变更。
- **跨页 chunk 不拼接**：`split_text_with_pages` 每页独立切分，page 字段精确表示 chunk 所属页；代价是页末块可能小于 `CHUNK_SIZE`，溯源精确度优先。
- **OCR 阈值**：`Config.PDF_OCR_THRESHOLD=50`（平均字符/页，低于触发全本 OCR 主路径）；含图但文本层正常的 PDF 走文本层路径。
- **clean_text 接入点**：`document_parser.py` 各 `_parse_*` 函数 return 前调用；OCR 路径同样在最后 return 前调用。
- **流式与非流式 sources 一致**：`chat()` 与 `chat_stream()` 两处都改造，避免前端两套格式。
- **不引入 Celery/Redis**（项目 Non-Goals）；worker 复用 `data_trigger.py` 的 `ThreadPoolExecutor` 模式。
- **无依赖新增**：pdfplumber/pytesseract/pdf2image/Pillow 已在 P0 引入；PyYAML 已存在于测试环境。
- 命名与路径严格遵循 Design Doc 第 3 节文件改动清单。
- 语言：代码注释、测试断言说明使用简体中文。
- 提交信息格式：`feat(kb): ...` / `test(kb): ...` / `refactor(kb): ...`。
- 测试兼容：`tests/conftest.py` 默认关闭 function calling；现有 `test_upload.py` 若依赖同步 `status=1`，需调整为对 `status` 流转的等价断言（不破坏断言语义）。

## 任务映射与依赖说明

本计划 14 个任务对应 tasks.md 的 6 组 14 项，编号与 tasks.md 顺序一致。其中：
- **Task 7**（`split_text_with_pages`）是 Design Doc 2.4 节要求的引用溯源基础设施，归入组二「异步入库」组末尾，因为 `ingestion_worker`（Task 5）依赖它做按页切分。它在 tasks.md 中无独立编号，是 Task 5（2.1）的实现前置，单列成任务以便独立测试与审查。
- **Task 13**（调整现有测试断言）是 Task 14（6.1 完整回归）的前置准备，单列以避免回归时混杂断言调整与真实失败排查。

**关键依赖（实施顺序提示）**：
- Task 5 的 worker 调用 `parse_document(file_path, file_type, page_aware=True)`，该参数由 **Task 8** 实现。Task 5 的单元测试通过 mock `parse_document` 验证状态机，不依赖真实 `page_aware` 支持；但 worker **真实运行**（端到端）需在 Task 8 完成后才可用。Task 14 完整回归时验证端到端通路。
- Task 7（`split_text_with_pages`）在 Task 5 之后、Task 8 之前；Task 7 完成后 Task 5 的 worker 切换到真实 `split_text_with_pages`（Task 7 Step 5 含此重构）。
- 实施时可按 Task 1→2→3→4→5→7→6→8→9→10→11→12→13→14 顺序以尽早打通端到端通路；若严格按编号顺序，Task 5-7 期间 worker 真实运行依赖 mock，单元测试全绿。

---

## 组一：文本清洗

### Task 1: 新增 `clean_text()` 清洗函数（tasks.md 1.1）

**Files:**
- Create: `framework/upload/text_cleaner.py`
- Test: `tests/test_text_cleaner.py`

**Interfaces:**
- Consumes: 无（纯新增）。
- Produces: `framework/upload/text_cleaner.py`：
  - `clean_text(text: str) -> str`：Unicode NFKC → 去不可见控制字符（保留 `\t \n \r`）→ 合并连续空白（3+ 空白压 2 个、3+ 换行压 2 个）→ 去跨页重复 ≥ 3 次的页眉页脚行 → strip。空文本/None 返回 `""`。
  - `_strip_repeated_header_footer(text: str) -> str`：内部辅助，行数 < 6 原样返回；统计非空行 hash 频次，频次 ≥ 3 的行去除。

- [ ] **Step 1: 编写失败测试** `tests/test_text_cleaner.py`

```python
"""测试文本清洗纯函数。"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from framework.upload.text_cleaner import clean_text


def test_empty_returns_empty():
    assert clean_text("") == ""
    assert clean_text(None) == ""


def test_nfkc_fullwidth_to_halfwidth():
    # 全角字母数字 → 半角
    assert clean_text("ＡＢＣ１２３") == "ABC123"


def test_control_chars_removed():
    # 保留 \t \n \r，去除其他控制字符
    text = "abc\x00def\x07ghi\n\t\r"
    assert clean_text(text) == "abcdefghi\n\t\r"


def test_multi_whitespace_collapsed():
    # 3+ 空白压成 2 个
    assert clean_text("a   b") == "a  b"
    # 3+ 换行压成 2 个
    assert clean_text("a\n\n\n\nb") == "a\n\nb"


def test_repeated_header_footer_removed():
    # 跨页重复 ≥ 3 次的行去除
    header = "第 X 页 共 Y 页"
    text = "\n".join([header, "正文内容一", header, "正文内容二", header, "正文内容三", header])
    result = clean_text(text)
    assert header not in result.split("\n")
    assert "正文内容一" in result
    assert "正文内容二" in result


def test_short_text_passthrough():
    # 行数 < 6 不做页眉页脚处理
    text = "重复行\n重复行\n重复行"
    # 行数 3 < 6，不去重
    assert "重复行" in clean_text(text)


def test_strip_leading_trailing_whitespace():
    assert clean_text("  hello  ") == "hello"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_text_cleaner.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'framework.upload.text_cleaner'`

- [ ] **Step 3: 编写最小实现** `framework/upload/text_cleaner.py`

```python
"""文档解析后文本清洗：NFKC 规范化、去控制字符、合并空白、去重复页眉页脚。"""
from __future__ import annotations
import re
import unicodedata
from collections import Counter

# 不可见控制字符（保留 \t \n \r）
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
# 连续空白（3+ 个）压成 2 个
_MULTI_WS_RE = re.compile(r"[ \t]{3,}")
_MULTI_NL_RE = re.compile(r"\n{3,}")


def clean_text(text: str) -> str:
    """规范化文本：Unicode NFKC → 去控制字符 → 合并空白 → 去重复页眉页脚。

    纯函数，可独立单测。被 document_parser 各 _parse_* 出口调用。
    """
    if not text:
        return ""
    # 1. Unicode NFKC 规范化（全角→半角、兼容字符归一）
    text = unicodedata.normalize("NFKC", text)
    # 2. 去不可见控制字符
    text = _CONTROL_RE.sub("", text)
    # 3. 合并连续空白
    text = _MULTI_WS_RE.sub("  ", text)
    text = _MULTI_NL_RE.sub("\n\n", text)
    # 4. 去重复页眉页脚
    text = _strip_repeated_header_footer(text)
    return text.strip()


def _strip_repeated_header_footer(text: str) -> str:
    """跨页重复 ≥ 3 次的行视为页眉/页脚并去除。

    实现：按 \\n 切行，统计行内容 hash 频率；频次 ≥ 3 的非空行去除。
    保留单页内容（即使恰好与页眉相同也不去除，因为是页眉的话必然多次重复）。
    """
    lines = text.split("\n")
    if len(lines) < 6:
        return text
    freq = Counter(line.strip() for line in lines if line.strip())
    repeated = {h for h, c in freq.items() if c >= 3}
    if not repeated:
        return text
    return "\n".join(line for line in lines if line.strip() not in repeated)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_text_cleaner.py -v`
Expected: PASS（7 项全通过）

- [ ] **Step 5: 提交**

```bash
git add framework/upload/text_cleaner.py tests/test_text_cleaner.py
git commit -m "feat(kb): 新增 clean_text 文本清洗纯函数"
```

---

### Task 2: 在 `document_parser.py` 解析后接入清洗（tasks.md 1.2）

**Files:**
- Modify: `framework/upload/document_parser.py`（各 `_parse_*` return 前调用 `clean_text`；`parse_document` 新增 `page_aware` 参数透传给 PDF；本任务先只接入 clean_text，page_aware 留 Task 5/6）
- Test: `tests/test_document_parser_clean.py`

**Interfaces:**
- Consumes: Task 1 的 `clean_text(text: str) -> str`。
- Produces: `parse_document(file_path, file_type) -> Optional[str]`（签名暂不变，内部接入清洗）；后续 Task 5 扩展 `page_aware` 参数。

- [ ] **Step 1: 编写失败测试** `tests/test_document_parser_clean.py`

```python
"""测试 document_parser 各路径接入 clean_text。"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from framework.upload import document_parser
from framework.upload.document_parser import parse_document, _parse_txt


def test_parse_txt_applies_clean(tmp_path, monkeypatch):
    # 写入含全角字符与控制字符的 txt
    p = tmp_path / "sample.txt"
    p.write_text("ＡＢＣ\x00正文   空白", encoding="utf-8")
    result = _parse_txt(str(p))
    # clean_text 已接入：全角→半角、控制字符去除、空白合并
    assert "ABC" in result
    assert "\x00" not in result
    assert "正文  空白" in result


def test_parse_txt_empty_file(tmp_path):
    p = tmp_path / "empty.txt"
    p.write_text("", encoding="utf-8")
    assert _parse_txt(str(p)) == ""


def test_parse_document_unknown_type_returns_none():
    assert parse_document("/tmp/x.xyz", "xyz") is None
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_document_parser_clean.py -v`
Expected: FAIL，`_parse_txt` 返回未清洗原文（含 `\x00` 与全角字符）

- [ ] **Step 3: 接入 clean_text 到各 `_parse_*` 出口**

修改 `framework/upload/document_parser.py`：

1. 顶部新增导入：
```python
from framework.upload.text_cleaner import clean_text
```

2. `_parse_txt` 末尾 return 前清洗：
```python
def _parse_txt(file_path: str) -> str:
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        return clean_text(f.read())
```

3. `_parse_pdf` 末尾 `return text` 改为 `return clean_text(text)`（含 PyPDF2 兜底分支的 `return text` 与 OCR 分支的 `return ocr_text`）。
4. `_parse_pdf_ocr` 末尾 `return text` 改为 `return clean_text(text)`。
5. `_parse_docx` 末尾 `return text` 改为 `return clean_text(text)`。
6. `_parse_excel` 末尾 `return clean_text(df.to_string())`。

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_document_parser_clean.py -v`
Expected: PASS（3 项全通过）

- [ ] **Step 5: 回归现有解析测试**

Run: `python -m pytest tests/test_document_parser.py -v 2>/dev/null || echo "无现有测试或全部通过"`
Expected: 无新增失败（若现有测试断言原文未清洗文本，按 Design Doc 第 7 节调整断言为清洗后等价语义）

- [ ] **Step 6: 提交**

```bash
git add framework/upload/document_parser.py tests/test_document_parser_clean.py
git commit -m "feat(kb): document_parser 各解析路径接入 clean_text"
```

---

### Task 3: 清洗函数补充边界与回归测试（tasks.md 1.3）

**Files:**
- Modify: `tests/test_text_cleaner.py`（补充 NFKC 兼容字符、混合空白+控制字符叠加、纯空白输入、单页重复行不去重等边界）
- Test: 同上

**Interfaces:**
- Consumes: Task 1 的 `clean_text`。
- Produces: 完整清洗单测覆盖（对应 spec `file-upload-management` 的 `Clean parsed text` 场景全部分支）。

- [ ] **Step 1: 编写补充失败测试**（追加到 `tests/test_text_cleaner.py`）

```python
def test_nfkc_compatibility_chars():
    # 兼容字符归一（如 ﾊ 半角片假名场景的兼容分解，此处用常见全角符号）
    assert clean_text("１２３") == "123"


def test_mixed_whitespace_and_control():
    text = "a\x00   b\n\n\n\nc"
    result = clean_text(text)
    assert "\x00" not in result
    assert "a  b" in result
    assert "b\n\nc" in result


def test_only_whitespace_returns_empty():
    assert clean_text("   \n\n\n\t\t") == ""


def test_single_page_repeated_line_not_removed():
    # 行数 < 6 不去重，即使某行重复 ≥ 3 次
    text = "重复\n重复\n重复\n重复\n重复"
    # 行数 5 < 6，不去重
    result = clean_text(text)
    assert result.count("重复") == 5


def test_header_footer_threshold_exactly_three():
    # 恰好 3 次重复且行数 ≥ 6 → 去除
    header = "页眉行"
    text = "\n".join([header, "正文一", header, "正文二", header, "正文三"])
    result = clean_text(text)
    assert "页眉行" not in result
```

- [ ] **Step 2: 运行测试确认结果**

Run: `python -m pytest tests/test_text_cleaner.py -v`
Expected: 全部 PASS（若 `test_header_footer_threshold_exactly_three` 失败，检查 `_strip_repeated_header_footer` 的 `>= 3` 判定与行数 `>= 6` 判定）

- [ ] **Step 3: 必要时 Refactor**

若 Step 2 有失败，修正 `framework/upload/text_cleaner.py` 中阈值或边界条件；不改动对外签名。

- [ ] **Step 4: 提交**

```bash
git add tests/test_text_cleaner.py framework/upload/text_cleaner.py
git commit -m "test(kb): 补充 clean_text 边界与回归测试"
```

---

### 📋 审查检查点 #1（Task 1-3 完成后，thorough 模式分段审查）

- [ ] 运行 `python -m pytest tests/test_text_cleaner.py tests/test_document_parser_clean.py -v` 全绿
- [ ] 确认 `clean_text` 对 None/空串/纯空白均返回 `""`，不抛异常
- [ ] 确认 `_parse_*` 所有 return 路径都经过 `clean_text`（含 PDF 的 pdfplumber/PyPDF2/OCR 三分支）
- [ ] 确认现有 `test_upload.py` / `test_document_parser.py` 回归无破坏（若有断言依赖未清洗文本，已调整为等价语义）
- [ ] Comet Classic：本段属 Build 阶段普通实现写入，Hook 应放行；若被拒按拒绝信息回到 Build

---

## 组二：异步入库

### Task 4: `Document` 模型新增 STATUS 枚举常量（tasks.md 2.2 前置）

**Files:**
- Modify: `framework/models/document.py`（新增 `STATUS_PENDING/COMPLETED/PROCESSING/FAILED` 类常量；`status` 默认值保持 `1` 不变以兼容现有数据）
- Test: `tests/test_document_status_enum.py`

**Interfaces:**
- Consumes: 无。
- Produces: `Document.STATUS_PENDING=0 / STATUS_COMPLETED=1 / STATUS_PROCESSING=2 / STATUS_FAILED=3`；`status` 列默认仍为 `1`（现有数据语义不变）。

- [ ] **Step 1: 编写失败测试** `tests/test_document_status_enum.py`

```python
"""测试 Document 状态枚举常量。"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from framework.models.document import Document


def test_status_constants():
    assert Document.STATUS_PENDING == 0
    assert Document.STATUS_COMPLETED == 1
    assert Document.STATUS_PROCESSING == 2
    assert Document.STATUS_FAILED == 3


def test_status_default_preserved():
    # 默认值仍为 1（completed），现有数据语义不变
    col = Document.__table__.c.status
    assert col.default.arg == 1
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_document_status_enum.py -v`
Expected: FAIL，`AttributeError: type object 'Document' has no attribute 'STATUS_PENDING'`

- [ ] **Step 3: 新增枚举常量**

修改 `framework/models/document.py`，在 `class Document(db.Model):` 之后、字段定义之前插入：

```python
class Document(db.Model):
    __tablename__ = 'kb_document'

    # 入库生命周期状态：现有 status=1 数据语义不变（表"已完成"），无需迁移
    STATUS_PENDING = 0      # 待处理（新上传，worker 未启动）
    STATUS_COMPLETED = 1    # 已完成（保留现有语义）
    STATUS_PROCESSING = 2   # 处理中（worker 已开始解析/切分/向量化）
    STATUS_FAILED = 3       # 失败（worker 抛异常）

    id = db.Column(db.Integer, primary_key=True, autoincrement=True, comment='文档ID')
    # ...其余字段不变
```

注意：`status = db.Column(db.SmallInteger, default=1, ...)` 保持不变。

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_document_status_enum.py -v`
Expected: PASS（2 项全通过）

- [ ] **Step 5: 提交**

```bash
git add framework/models/document.py tests/test_document_status_enum.py
git commit -m "feat(kb): Document 新增 STATUS 枚举常量（0/1/2/3）"
```

---

### Task 5: 新增 `ingestion_worker.py` 异步 worker 与状态机（tasks.md 2.1 + 2.2）

**Files:**
- Create: `framework/upload/ingestion_worker.py`
- Test: `tests/test_ingestion_worker.py`

**Interfaces:**
- Consumes:
  - Task 4 的 `Document.STATUS_*` 常量。
  - `framework.upload.document_parser.parse_document(file_path, file_type, page_aware=False)`：本任务 worker 调用时传 `page_aware=True`，该参数由 **Task 8** 实现。Task 5 单元测试通过 mock `parse_document` 验证状态机，不依赖真实 `page_aware` 支持；worker 端到端真实运行需在 Task 8 完成后（Task 14 回归时验证）。
  - `framework.upload.chunker.split_text`（Task 7 新增 `split_text_with_pages`，Task 7 Step 5 将 worker 切换到真实 `split_text_with_pages`）。
  - `framework.vector_store.chroma_store.vector_store.add_documents(chunks, metadatas, category=...)`。
  - `framework.models.user.db`、`framework.create_app`。
- Produces: `framework/upload/ingestion_worker.py`：
  - `submit_ingest(document_id, file_path, file_type, doc_name, category, treatment_type) -> None`：非阻塞提交到模块级 `ThreadPoolExecutor(max_workers=2, thread_name_prefix="ingest")`。
  - `_ingest(...)`：worker 主体，状态机 `pending(0) → processing(2) → completed(1)` 或异常 `→ failed(3)`；worker 线程内新建 app context。
  - `_set_status(document_id, status)`：更新文档状态并 commit。

- [ ] **Step 1: 编写失败测试** `tests/test_ingestion_worker.py`

```python
"""测试异步入库 worker 状态机（mock vector_store 与 parse_document）。"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from framework.upload import ingestion_worker
from framework.upload.ingestion_worker import _ingest
from framework.models.document import Document


class _FakeDoc:
    def __init__(self, doc_id):
        self.id = doc_id
        self.status = Document.STATUS_PENDING
        self.chunk_count = 0


def _patch_app_context(monkeypatch):
    # 避免真正创建 Flask app：把 create_app 替换为返回 stub
    class _StubApp:
        def app_context(self):
            class _Ctx:
                def __enter__(self): return self
                def __exit__(self, *a): return False
            return _Ctx()
    monkeypatch.setattr(ingestion_worker, "create_app", lambda: _StubApp())


def test_ingest_success_transitions_pending_to_completed(monkeypatch):
    _patch_app_context(monkeypatch)
    fake = _FakeDoc(1)

    monkeypatch.setattr(ingestion_worker, "_set_status", lambda did, s: setattr(fake, "status", s))
    monkeypatch.setattr(ingestion_worker, "parse_document", lambda fp, ft, page_aware=True: "正文内容" * 100)
    monkeypatch.setattr(ingestion_worker, "split_text", lambda text, size=None, overlap=None: ["c1", "c2"])

    class _FakeVS:
        def add_documents(self, chunks, metadatas, category=None):
            return len(chunks)
    monkeypatch.setattr(ingestion_worker, "vector_store", _FakeVS())

    class _FakeQuery:
        def get(self, did):
            return fake
    monkeypatch.setattr(ingestion_worker.db.session, "query", lambda *a: _FakeQuery())
    monkeypatch.setattr(ingestion_worker.db.session, "commit", lambda: setattr(fake, "_committed", True))

    _ingest(1, "/tmp/x.pdf", "pdf", "x.pdf", "acidification", None)

    assert fake.status == Document.STATUS_COMPLETED
    assert fake.chunk_count == 2


def test_ingest_failure_promotes_to_failed(monkeypatch):
    _patch_app_context(monkeypatch)
    fake = _FakeDoc(2)

    def _boom_set(did, s):
        # pending → processing 正常；后续 parse 抛异常
        fake.status = s

    monkeypatch.setattr(ingestion_worker, "_set_status", _boom_set)

    def _parse_boom(fp, ft, page_aware=True):
        raise RuntimeError("解析爆炸")
    monkeypatch.setattr(ingestion_worker, "parse_document", _parse_boom)

    class _FakeQuery:
        def get(self, did):
            return fake
    monkeypatch.setattr(ingestion_worker.db.session, "query", lambda *a: _FakeQuery())
    monkeypatch.setattr(ingestion_worker.db.session, "commit", lambda: None)

    _ingest(2, "/tmp/bad.pdf", "pdf", "bad.pdf", "other", None)

    assert fake.status == Document.STATUS_FAILED
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_ingestion_worker.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'framework.upload.ingestion_worker'`

- [ ] **Step 3: 编写实现** `framework/upload/ingestion_worker.py`

```python
"""异步入库 worker：fire-and-forget 提交 + 状态机跟踪。

状态机: pending(0) → processing(2) → completed(1) 或 failed(3)。
worker 线程内推送独立 Flask app context（Flask-SQLAlchemy 需要）。
"""
from __future__ import annotations
import concurrent.futures
import traceback

from framework.models.user import db
from framework.models.document import Document
from framework.upload.document_parser import parse_document
from framework.upload.chunker import split_text
from framework.vector_store.chroma_store import vector_store

# 模块级 worker：与 data_trigger.py 的 ThreadPoolExecutor 模式同源
_WORKER = concurrent.futures.ThreadPoolExecutor(
    max_workers=2, thread_name_prefix="ingest"
)


def submit_ingest(document_id, file_path, file_type, doc_name, category, treatment_type):
    """非阻塞提交入库任务；立即返回。

    上传路由调用本函数后立即返回 202，状态机由 worker 内部推进。
    """
    _WORKER.submit(
        _ingest,
        document_id, file_path, file_type, doc_name, category, treatment_type,
    )


def _ingest(document_id, file_path, file_type, doc_name, category, treatment_type):
    """入库 worker 主体。异常时记录 traceback 并推进到 failed，避免文档永久停留 processing。"""
    # 在 worker 线程内推送 app context（Flask-SQLAlchemy 需要）
    from framework import create_app
    app = create_app()
    with app.app_context():
        try:
            _set_status(document_id, Document.STATUS_PROCESSING)
            # 解析（parse_document 内部已调用 clean_text）
            pages = parse_document(file_path, file_type, page_aware=True)
            # 切分：page_aware 返回 List[(chunk, page)]；其他格式返回 str
            if isinstance(pages, list) and pages and isinstance(pages[0], tuple):
                chunks_with_pages = _split_with_pages(pages)
                chunks = [c for c, _ in chunks_with_pages]
                pages_meta = [p for _, p in chunks_with_pages]
            else:
                # 非分页格式（txt/docx/xlsx）回退到普通切分
                chunks = split_text(pages or "")
                pages_meta = [None] * len(chunks)

            metadatas = [{
                "source": doc_name,
                "category": category,
                "treatment_type": treatment_type,
                "chunk_index": i,
                "page": pages_meta[i],
            } for i in range(len(chunks))]

            added_count = 0
            if chunks:
                added_count = vector_store.add_documents(chunks, metadatas, category=category)

            # 更新 chunk_count + 推进到 completed
            doc = Document.query.get(document_id)
            if doc:
                doc.chunk_count = len(chunks)
                doc.status = Document.STATUS_COMPLETED
                db.session.commit()
        except Exception:
            traceback.print_exc()
            try:
                doc = Document.query.get(document_id)
                if doc:
                    doc.status = Document.STATUS_FAILED
                    db.session.commit()
            except Exception:
                traceback.print_exc()


def _split_with_pages(pages):
    """临时包装：Task 7 完成后改为直接调用 chunker.split_text_with_pages。

    本函数在 Task 5 阶段返回 [(chunk, page)] 占位，Task 7 替换为真实切分。
    """
    # 占位：每页整体作为一个 chunk（Task 7 替换为 split_text_with_pages）
    from framework.upload.chunker import split_text
    result = []
    for page_num, page_text in pages:
        for c in split_text(page_text or ""):
            result.append((c, page_num))
    return result


def _set_status(document_id, status):
    doc = Document.query.get(document_id)
    if doc:
        doc.status = status
        db.session.commit()
```

> 注：
> - `_split_with_pages` 为 Task 7 前的占位包装；Task 7 Step 5 将 `_ingest` 切换为直接调用 `chunker.split_text_with_pages`，删除本函数。
> - worker 调用 `parse_document(file_path, file_type, page_aware=True)`，`page_aware` 参数由 Task 8 实现。本任务单元测试 mock `parse_document`，不依赖真实参数支持；worker 端到端运行需在 Task 8 完成后。

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_ingestion_worker.py -v`
Expected: PASS（2 项全通过）

- [ ] **Step 5: 提交**

```bash
git add framework/upload/ingestion_worker.py tests/test_ingestion_worker.py
git commit -m "feat(kb): 新增异步入库 worker 与状态机"
```

---

### Task 6: 上传路由 `/upload` 改异步 fire-and-forget + 202（tasks.md 2.1 + 2.3）

**Files:**
- Modify: `framework/api/routes/docs.py`（`/upload` 文档分支改为：先 `Document(status=PENDING)` → commit → `submit_ingest(...)` → 立即返回 202；数据文件分支保持同步不变）
- Test: `tests/test_upload_async.py`

**Interfaces:**
- Consumes:
  - Task 4 的 `Document.STATUS_PENDING`。
  - Task 5 的 `submit_ingest(document_id, file_path, file_type, doc_name, category, treatment_type)`。
- Produces: `/upload` 对文档类返回 HTTP 202 + `Document.to_dict()`（status=0 pending）；数据文件分支（`category in DATA_CATEGORIES`）保持原 200 同步行为。

- [ ] **Step 1: 编写失败测试** `tests/test_upload_async.py`

```python
"""测试上传接口异步化：文档类返回 202 + status=0，并提交后台 worker。"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from framework.api.routes import docs as docs_route
from framework.upload import ingestion_worker


def test_upload_document_returns_202_and_submits(monkeypatch, tmp_path):
    # 准备：mock 文件保存、查重、worker 提交
    saved_path = tmp_path / "uuid.pdf"
    saved_path.write_bytes(b"%PDF-1.4 fake")

    monkeypatch.setattr(docs_route, "save_uploaded_file",
                       lambda f: ("uuid.pdf", str(saved_path), "hash123"))
    monkeypatch.setattr(docs_route, "get_file_type", lambda name: "pdf")
    monkeypatch.setattr(docs_route, "allowed_file", lambda name: True)

    # 查重：返回 None（不重复）
    class _NoDup:
        def filter_by(self, **kw):
            class _Q:
                def first(self): return None
            return _Q()
    monkeypatch.setattr(docs_route.Document, "query", _NoDup())

    # mock db.session
    class _FakeDoc:
        def __init__(self):
            self.id = 42
            self.status = docs_route.Document.STATUS_PENDING
            self.chunk_count = 0
            self.doc_name = "test.pdf"
            self.file_path = "uuid.pdf"
            self.file_type = "pdf"
            self.file_size = 100
            self.file_hash = "hash123"
            self.category = "acidification"
            self.treatment_type = None
            self.create_by = 1
            self.create_time = None
            self.update_time = None
        def to_dict(self):
            return {"id": self.id, "status": self.status, "chunk_count": self.chunk_count,
                    "doc_name": self.doc_name}

    fake_doc = _FakeDoc()
    monkeypatch.setattr(docs_route.db.session, "add", lambda obj: setattr(obj, "_added", True))
    monkeypatch.setattr(docs_route.db.session, "commit", lambda: None)
    monkeypatch.setattr(docs_route.Document, "__new__", lambda cls: fake_doc, raising=False)

    submitted = {}
    monkeypatch.setattr(ingestion_worker, "submit_ingest",
                        lambda **kw: submitted.update(kw))

    # 构造最小 request/files
    class _File:
        filename = "test.pdf"
        content_length = 100
    class _Req:
        files = {"file": _File()}
        form = {"category": "acidification"}
    monkeypatch.setattr(docs_route, "request", _Req())
    monkeypatch.setattr(docs_route, "get_jwt_identity", lambda: 1)
    monkeypatch.setattr(docs_route.os.path, "getsize", lambda p: 100)

    # 执行
    resp = docs_route.upload_document()
    body = resp[0].get_json()
    code = resp[1]

    assert code == 202
    assert body["data"]["status"] == docs_route.Document.STATUS_PENDING
    assert submitted.get("document_id") == 42
    assert submitted.get("doc_name") == "test.pdf"


def test_upload_data_file_stays_sync(monkeypatch, tmp_path):
    # 数据文件（raw_data/improved_data）保持同步，不调 submit_ingest
    saved_path = tmp_path / "data.csv"
    saved_path.write_text("col\nval")
    monkeypatch.setattr(docs_route, "save_uploaded_file",
                       lambda f: ("data.csv", str(saved_path), "hashcsv"))
    monkeypatch.setattr(docs_route, "get_file_type", lambda name: "csv")
    monkeypatch.setattr(docs_route, "allowed_file", lambda name: True)

    class _NoDup:
        def filter_by(self, **kw):
            class _Q:
                def first(self): return None
            return _Q()
    monkeypatch.setattr(docs_route.Document, "query", _NoDup())

    submitted = {"called": False}
    monkeypatch.setattr(ingestion_worker, "submit_ingest", lambda **kw: submitted.update({"called": True}))

    class _File:
        filename = "data.csv"
        content_length = 100
    class _Req:
        files = {"file": _File()}
        form = {"category": "raw_data"}
    monkeypatch.setattr(docs_route, "request", _Req())
    monkeypatch.setattr(docs_route, "get_jwt_identity", lambda: 1)
    monkeypatch.setattr(docs_route.os.path, "getsize", lambda p: 100)

    class _FakeDataFile:
        def __init__(self, **kw): self.__dict__.update(kw); self.id = 7
        def to_dict(self): return {"id": self.id, "category": self.category}
    monkeypatch.setattr(docs_route.DataFile, "__new__", lambda cls: _FakeDataFile(), raising=False)
    monkeypatch.setattr(docs_route.db.session, "add", lambda obj: None)
    monkeypatch.setattr(docs_route.db.session, "commit", lambda: None)

    resp = docs_route.upload_document()
    assert resp[1] == 200
    assert submitted["called"] is False
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_upload_async.py -v`
Expected: FAIL（当前 `/upload` 同步返回 200 + status=1，未调 `submit_ingest`）

- [ ] **Step 3: 改造 `/upload` 文档分支**

修改 `framework/api/routes/docs.py` 的 `upload_document()`：

将原同步块（`content = parse_document(...)` 到 `db.session.commit()` + `return jsonify(... 文档上传成功)`)替换为：

```python
        # 文档类：异步入库（fire-and-forget）
        document = Document(
            doc_name=file.filename,
            file_path=new_filename,
            file_type=file_type,
            file_size=os.path.getsize(file_path),
            chunk_count=0,
            status=Document.STATUS_PENDING,
            file_hash=file_hash,
            category=category,
            treatment_type=treatment_type,
            create_by=user_id,
        )
        db.session.add(document)
        db.session.commit()
        print(f"[上传接口] 文档已入库排队 - 文档ID: {document.id}, 文件名: {file.filename}", flush=True)

        from framework.upload.ingestion_worker import submit_ingest
        submit_ingest(
            document_id=document.id,
            file_path=file_path,
            file_type=file_type,
            doc_name=file.filename,
            category=category,
            treatment_type=treatment_type,
        )

        return jsonify({
            "status": "ok",
            "data": document.to_dict(),
            "message": "文档已提交，正在后台处理",
        }), 202
```

注意：
- 删除原 `from framework.upload.document_parser import parse_document` / `from framework.upload.chunker import split_text` / `from framework.vector_store.chroma_store import vector_store` 的同步调用（保留 import 或移除均可，worker 内部自行 import）。
- 数据文件分支（`category in DATA_CATEGORIES`）保持原 200 同步行为不变。
- 文件保存 `save_uploaded_file`、查重逻辑保持不变。

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_upload_async.py -v`
Expected: PASS（2 项全通过）

- [ ] **Step 5: 回归现有上传测试**

Run: `python -m pytest tests/test_upload.py -v 2>/dev/null || echo "无现有测试或需调整断言"`
Expected: 若现有 `test_upload.py` 断言 `status==1` / HTTP 200，按 Design Doc 第 7 节调整为：上传立即返回 202 + status=0(pending)，worker 完成后 status=1。调整断言不破坏语义。

- [ ] **Step 6: 提交**

```bash
git add framework/api/routes/docs.py tests/test_upload_async.py
git commit -m "feat(kb): 上传路由文档分支改异步 fire-and-forget + 202"
```

---

### 📋 审查检查点 #2（Task 4-6 完成后，thorough 模式分段审查）

- [ ] 运行 `python -m pytest tests/test_document_status_enum.py tests/test_ingestion_worker.py tests/test_upload_async.py -v` 全绿
- [ ] 确认 `Document.status` 默认值仍为 `1`（现有数据语义不变，无 schema 迁移）
- [ ] 确认 worker 异常路径推进到 `STATUS_FAILED` 且打印 traceback（spec `Worker failure promotes status to failed`）
- [ ] 确认数据文件分支未受影响（仍 200 同步）
- [ ] 确认 worker `max_workers=2` 与 `data_trigger.py` 模式一致，未引入 Celery/Redis
- [ ] Comet Classic：Build 阶段写入；若 Hook 拒绝多文件改动，按拒绝信息回到 Build

---

## 组三：OCR 与表格解析主路径

### Task 7: `chunker.py` 新增 `split_text_with_pages`（tasks.md 4.1 前置 / 引用溯源依赖）

**Files:**
- Modify: `framework/upload/chunker.py`（新增 `split_text_with_pages`；保留 `split_text` 不变）
- Test: `tests/test_chunker_pages.py`

**Interfaces:**
- Consumes: `framework.config.Config.CHUNK_SIZE / CHUNK_OVERLAP`、Task 1 的 `split_text`。
- Produces: `split_text_with_pages(pages: List[Tuple[int, str]], size=None, overlap=None) -> List[Tuple[str, int]]`：
  - 每页独立用 `split_text` 切分，跨页不拼接；
  - 空页跳过；末块不足 size 仍保留；
  - 参数缺省读 `Config.CHUNK_SIZE / CHUNK_OVERLAP`。

> 说明：本任务属于引用溯源的基础设施（chunker 按页切分），放在组三是因为 `ingestion_worker` 与 `document_parser` 的 `page_aware` 都依赖它。tasks.md 4.1 是 chain.py sources 改造，本任务是其前置。

- [ ] **Step 1: 编写失败测试** `tests/test_chunker_pages.py`

```python
"""测试 page-aware 切分：跨页不拼接、空页跳过、参数缺省。"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from framework.upload.chunker import split_text_with_pages, split_text


def test_single_page_multiple_chunks(monkeypatch):
    monkeypatch.setattr("framework.upload.chunker.Config.CHUNK_SIZE", 10)
    monkeypatch.setattr("framework.upload.chunker.Config.CHUNK_OVERLAP", 2)
    pages = [(1, "a" * 25)]
    result = split_text_with_pages(pages)
    assert all(isinstance(c, tuple) for c in result)
    assert all(p == 1 for _, p in result)
    assert len(result) >= 2  # 25 字符 / 10 size 至少 3 块


def test_empty_page_skipped():
    pages = [(1, ""), (2, "正文内容")]
    result = split_text_with_pages(pages)
    assert len(result) == 1
    assert result[0] == ("正文内容", 2)


def test_cross_page_not_concatenated():
    # 跨页不拼接：每页独立切分
    pages = [(1, "页一内容"), (2, "页二内容")]
    result = split_text_with_pages(pages)
    chunks = [c for c, _ in result]
    pages_meta = [p for _, p in result]
    # 不应出现跨页拼接的 chunk
    assert "页一内容页二内容" not in chunks
    assert pages_meta == [1, 2]


def test_explicit_size_overlap():
    pages = [(1, "abcdefghij"), (2, "klmnopqrst")]
    result = split_text_with_pages(pages, size=5, overlap=0)
    # 每页 2 块（5+5），共 4 块
    assert len(result) == 4


def test_empty_pages_returns_empty():
    assert split_text_with_pages([]) == []
    assert split_text_with_pages([(1, None)]) == []
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_chunker_pages.py -v`
Expected: FAIL，`ImportError: cannot import name 'split_text_with_pages'`

- [ ] **Step 3: 实现 `split_text_with_pages`**

在 `framework/upload/chunker.py` 末尾追加：

```python
from typing import List, Tuple


def split_text_with_pages(
    pages: List[Tuple[int, str]],
    size: int = None,
    overlap: int = None,
) -> List[Tuple[str, int]]:
    """按页切分文本，返回 (chunk_text, page_num) 列表。

    - pages: [(page_num, page_text)]，page_num 通常从 1 开始
    - 切分逻辑：把每页文本视为独立段，对每页用 split_text 切，跨页不合并
      （保留页码语义清晰，避免 chunk 跨页导致 page 字段歧义）
    - 跨页 chunk 不拼接：每页独立切分后顺序输出
    - 末块不足 size 仍保留
    """
    if not pages:
        return []
    if size is None:
        size = Config.CHUNK_SIZE
    if overlap is None:
        overlap = Config.CHUNK_OVERLAP
    result: List[Tuple[str, int]] = []
    for page_num, page_text in pages:
        if not page_text:
            continue
        chunks = split_text(page_text, size=size, overlap=overlap)
        for c in chunks:
            result.append((c, page_num))
    return result
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_chunker_pages.py -v`
Expected: PASS（5 项全通过）

- [ ] **Step 5: Refactor worker 调用真实切分**

修改 `framework/upload/ingestion_worker.py`：
- 顶部 import 改为 `from framework.upload.chunker import split_text, split_text_with_pages`。
- `_ingest` 中 `chunks_with_pages = _split_with_pages(pages)` 改为 `chunks_with_pages = split_text_with_pages(pages)`。
- 删除占位函数 `_split_with_pages`。

- [ ] **Step 6: 回归 worker 测试**

Run: `python -m pytest tests/test_ingestion_worker.py -v`
Expected: PASS（worker 测试用 `split_text` mock，不受影响）

- [ ] **Step 7: 提交**

```bash
git add framework/upload/chunker.py framework/upload/ingestion_worker.py tests/test_chunker_pages.py
git commit -m "feat(kb): chunker 新增 split_text_with_pages 按页切分"
```

---

### Task 8: `document_parser.py` 增 `page_aware` + 图片型 PDF 检测 + 表格 Markdown（tasks.md 3.1 + 3.2）

**Files:**
- Modify: `framework/upload/document_parser.py`（`parse_document` 增 `page_aware` 参数；`_parse_pdf` 重写为图片型检测+表格提取+逐页 OCR 兜底；新增 `_detect_avg_chars` / `_table_to_markdown`；`_parse_pdf_ocr` 增 `page_aware` 参数）
- Modify: `framework/config.py`（新增 `PDF_OCR_THRESHOLD = 50`）
- Test: `tests/test_document_parser_pdf.py`

**Interfaces:**
- Consumes: `framework.config.Config.PDF_OCR_THRESHOLD`、Task 2 的 `clean_text`。
- Produces:
  - `parse_document(file_path, file_type, page_aware=False) -> Optional[str | List[Tuple[int, str]]]`：`page_aware=True` 时 PDF 返回 `List[(page_num, text)]`；其他格式始终返回 `str`。
  - `_parse_pdf(file_path, page_aware=False)`：图片型（avg_chars < 阈值）走全本 OCR 主路径；否则逐页文本层+表格 Markdown+空页 OCR 兜底。
  - `_detect_avg_chars(pdf) -> float`：采样前 5 页平均字符数。
  - `_table_to_markdown(rows) -> str`：`List[List[str]]` → Markdown 表格。
  - `_parse_pdf_ocr(file_path, page_aware=False)`：OCR 主路径，`page_aware=True` 返回 `List[(page_num, text)]`。

- [ ] **Step 1: 编写失败测试** `tests/test_document_parser_pdf.py`

```python
"""测试 PDF 解析：图片型检测、表格 Markdown、page_aware 返回结构。"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from framework.upload import document_parser
from framework.upload.document_parser import (
    parse_document, _detect_avg_chars, _table_to_markdown,
)


def test_table_to_markdown_basic():
    rows = [["列A", "列B"], ["1", "2"], ["3", "4"]]
    md = _table_to_markdown(rows)
    assert "| 列A | 列B |" in md
    assert "| --- | --- |" in md
    assert "| 1 | 2 |" in md
    assert "| 3 | 4 |" in md


def test_table_to_markdown_empty():
    assert _table_to_markdown([]) == ""
    assert _table_to_markdown([[]]) == ""


def test_table_to_markdown_handles_none_cells():
    rows = [["a", None], [None, "b"]]
    md = _table_to_markdown(rows)
    assert "| a |  |" in md
    assert "|  | b |" in md


def test_detect_avg_chars_samples_first_five(monkeypatch):
    class _Page:
        def __init__(self, n): self._n = n
        def extract_text(self): return "x" * self._n
    class _Pdf:
        pages = [_Page(100), _Page(200), _Page(50), _Page(80), _Page(120), _Page(999)]
    avg = _detect_avg_chars(_Pdf())
    # 采样前 5 页：(100+200+50+80+120)/5 = 110
    assert avg == 110.0


def test_detect_avg_chars_empty_pdf():
    class _Pdf:
        pages = []
    assert _detect_avg_chars(_Pdf()) == 0.0


def test_parse_document_page_aware_non_pdf_returns_str(tmp_path):
    p = tmp_path / "x.txt"
    p.write_text("正文", encoding="utf-8")
    # 非 PDF 格式忽略 page_aware，仍返回 str
    result = parse_document(str(p), "txt", page_aware=True)
    assert isinstance(result, str)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_document_parser_pdf.py -v`
Expected: FAIL，`ImportError: cannot import name '_detect_avg_chars'` / `page_aware` 参数不存在

- [ ] **Step 3: Config 新增阈值**

修改 `framework/config.py`，在 `Config` 类中（建议紧跟 `CHUNK_OVERLAP` 之后）新增：

```python
    PDF_OCR_THRESHOLD = 50  # 平均字符/页阈值，低于则触发 OCR 主路径
```

- [ ] **Step 4: 重写 `_parse_pdf` 与扩展 `parse_document`**

修改 `framework/upload/document_parser.py`：

1. `parse_document` 增 `page_aware` 参数：

```python
def parse_document(file_path: str, file_type: str, page_aware: bool = False):
    """解析文档。page_aware=True 时 PDF 返回 List[(page_num, text)]；其他格式始终返回 str。

    失败时抛出异常，由调用方捕获并打印日志。
    """
    if file_type == 'txt':
        return _parse_txt(file_path)
    elif file_type == 'md':
        return _parse_txt(file_path)
    elif file_type == 'pdf':
        return _parse_pdf(file_path, page_aware=page_aware)
    elif file_type == 'docx':
        return _parse_docx(file_path)
    elif file_type == 'xlsx':
        return _parse_excel(file_path)
    else:
        return None
```

2. `_parse_pdf` 重写（替换原 pdfplumber + PyPDF2 双路径实现）：

```python
def _parse_pdf(file_path: str, page_aware: bool = False):
    """PDF 解析：先做图片型检测，命中则全本 OCR；否则逐页提取文本+表格。

    page_aware=True 返回 List[(page_num, text)]；False 返回 str（向后兼容）。
    """
    try:
        import pdfplumber
    except ImportError as e:
        raise ImportError(
            f"pdfplumber 未安装，无法解析 PDF。请执行 pip install pdfplumber 错误: {e}"
        )

    from framework.config import Config

    pages_text = []  # List[(page_num, text)]
    with pdfplumber.open(file_path) as pdf:
        total_pages = len(pdf.pages)
        # 1. 图片型检测：平均字符数 < 阈值则全本 OCR
        avg_chars = _detect_avg_chars(pdf)
        if avg_chars < Config.PDF_OCR_THRESHOLD:
            print(f"[Parser] 图片型 PDF 检测命中（avg_chars={avg_chars:.1f} < {Config.PDF_OCR_THRESHOLD}），走 OCR 主路径", flush=True)
            return _parse_pdf_ocr(file_path, page_aware=page_aware)

        # 2. 混合解析：逐页提取文本+表格
        for i, page in enumerate(pdf.pages, start=1):
            try:
                page_text = page.extract_text() or ""
            except Exception as e:
                print(f"[Parser] pdfplumber 第 {i}/{total_pages} 页解析失败：{e}")
                page_text = ""
            tables_md = [_table_to_markdown(t) for t in (page.extract_tables() or [])]
            if tables_md:
                page_text = page_text + "\n\n" + "\n\n".join(tables_md)
            # 单页空文本 → 该页 OCR 兜底
            if not page_text.strip():
                try:
                    from pdf2image import convert_from_path
                    import pytesseract
                    images = convert_from_path(file_path, first_page=i, last_page=i)
                    if images:
                        page_text = pytesseract.image_to_string(images[0], lang="chi_sim+eng")
                except Exception as e:
                    print(f"[Parser] 第 {i} 页 OCR 兜底失败: {e}")
            pages_text.append((i, page_text))

    if page_aware:
        return pages_text
    return clean_text("\n".join(t for _, t in pages_text))


def _detect_avg_chars(pdf) -> float:
    """采样前 5 页（或全部，若不足 5 页）的字符数取平均，避免全本扫描成本。"""
    sample = pdf.pages[:5] if len(pdf.pages) > 5 else pdf.pages
    total = 0
    for page in sample:
        try:
            total += len((page.extract_text() or "").strip())
        except Exception:
            pass
    return total / max(len(sample), 1)


def _table_to_markdown(rows) -> str:
    """pdfplumber.extract_tables() 返回的 List[List[str]] 转 Markdown 表格语法。"""
    if not rows or not rows[0]:
        return ""
    header = rows[0]
    body = rows[1:] if len(rows) > 1 else []
    lines = ["| " + " | ".join((c or "") for c in header) + " |",
             "| " + " | ".join("---" for _ in header) + " |"]
    for row in body:
        lines.append("| " + " | ".join((c or "") for c in row) + " |")
    return "\n".join(lines)
```

3. `_parse_pdf_ocr` 增 `page_aware` 参数（基于 `convert_from_path` 的 images 列表本身就是按页排序）：

```python
def _parse_pdf_ocr(file_path: str, page_aware: bool = False):
    """使用 OCR 识别扫描件/图片型 PDF 中的文字。

    page_aware=True 返回 List[(page_num, text)]；False 返回 str。
    """
    print(f"[Parser] 开始 OCR 识别：{file_path}", flush=True)

    try:
        from pdf2image import convert_from_path
    except ImportError as e:
        raise ImportError(
            f"pdf2image 未安装，无法进行 OCR 识别。请执行: pip install pdf2image 错误: {e}"
        )
    try:
        import pytesseract
    except ImportError as e:
        raise ImportError(
            f"pytesseract 未安装，无法进行 OCR 识别。请执行: pip install pytesseract 错误: {e}"
        )
    try:
        pytesseract.get_tesseract_version()
    except Exception as e:
        raise RuntimeError(
            f"未找到 Tesseract OCR 引擎。请先安装 Tesseract：https://github.com/tesseract-ocr/tesseract  错误: {e}"
        )

    print("[Parser] 正在将 PDF 转换为图片...", flush=True)
    try:
        images = convert_from_path(file_path)
    except Exception as e:
        raise RuntimeError(f"PDF 转图片失败（可能需要安装 poppler）：{e}")

    total_pages = len(images)
    print(f"[Parser] PDF 共 {total_pages} 页，开始 OCR 识别...", flush=True)

    pages_text = []  # List[(page_num, text)]
    for i, image in enumerate(images, start=1):
        try:
            print(f"[Parser] OCR 识别第 {i}/{total_pages} 页...", flush=True)
            page_text = pytesseract.image_to_string(image, lang='chi_sim+eng').strip()
        except Exception as e:
            print(f"[Parser] OCR 第 {i}/{total_pages} 页识别失败：{e}", flush=True)
            page_text = ""
        pages_text.append((i, page_text))

    print(f"[Parser] OCR 识别完成，共 {total_pages} 页", flush=True)
    if page_aware:
        return pages_text
    return clean_text("\n".join(t for _, t in pages_text))
```

> 注意：`clean_text` 已在 Task 2 导入；保持顶部 `from framework.upload.text_cleaner import clean_text`。

- [ ] **Step 5: 运行测试确认通过**

Run: `python -m pytest tests/test_document_parser_pdf.py -v`
Expected: PASS（6 项全通过）

- [ ] **Step 6: 回归现有解析测试**

Run: `python -m pytest tests/test_document_parser.py tests/test_document_parser_clean.py -v 2>/dev/null || echo "检查失败项"`
Expected: 无新增失败（`_parse_pdf` 签名增了 `page_aware=False` 默认参数，向后兼容）

- [ ] **Step 7: 提交**

```bash
git add framework/upload/document_parser.py framework/config.py tests/test_document_parser_pdf.py
git commit -m "feat(kb): PDF 图片型检测主路径 + 表格 Markdown + page_aware"
```

---

### Task 9: 扫描件与含表格 PDF 信息保真验证（tasks.md 3.3）

**Files:**
- Test: `tests/test_document_parser_pdf_fidelity.py`（集成验证：图片型触发 OCR 主路径、表格保留结构、page_aware 返回页码从 1 开始）

**Interfaces:**
- Consumes: Task 8 的 `_parse_pdf` / `_parse_pdf_ocr` / `_table_to_markdown` / `parse_document(page_aware=True)`。
- Produces: 覆盖 spec `Image-type PDF Detection` / `Table Structure Preservation` / `Page-aware Parsing` 三个场景的保真测试。

- [ ] **Step 1: 编写保真测试** `tests/test_document_parser_pdf_fidelity.py`

```python
"""扫描件与含表格 PDF 信息保真集成测试（mock pdfplumber/pdf2image）。"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from framework.upload import document_parser
from framework.upload.document_parser import _parse_pdf, _parse_pdf_ocr, parse_document


def test_image_type_pdf_triggers_ocr_primary(monkeypatch):
    # avg_chars < 阈值 → 走 OCR 主路径
    class _Page:
        def extract_text(self): return "ab"  # 每页 2 字符
        def extract_tables(self): return []
    class _Pdf:
        pages = [_Page() for _ in range(3)]
    class _Ctx:
        def __enter__(self): return self
        def __exit__(self, *a): return False
    class _Pdfplumber:
        @staticmethod
        def open(path):
            class _H:
                def __enter__(self): return _Pdf()
                def __exit__(self, *a): return False
            return _H()
    monkeypatch.setattr(document_parser, "pdfplumber", _Pdfplumber, raising=False)

    ocr_called = {"yes": False}
    def _fake_ocr(fp, page_aware=False):
        ocr_called["yes"] = True
        if page_aware:
            return [(1, "OCR第一页"), (2, "OCR第二页"), (3, "OCR第三页")]
        return "OCR全文"
    monkeypatch.setattr(document_parser, "_parse_pdf_ocr", _fake_ocr)

    result = _parse_pdf("/tmp/scan.pdf", page_aware=True)
    assert ocr_called["yes"] is True
    assert isinstance(result, list)
    assert result[0] == (1, "OCR第一页")


def test_text_pdf_with_table_preserves_structure(monkeypatch):
    # 文本层正常 + 含表格 → 提取文本 + 表格 Markdown
    class _Page:
        def extract_text(self): return "页面正文"
        def extract_tables(self):
            return [[["产品", "数量"], ["A", "10"], ["B", "20"]]]
    class _Pdf:
        pages = [_Page()]
    class _Ctx:
        def __enter__(self): return self
        def __exit__(self, *a): return False
    class _Pdfplumber:
        @staticmethod
        def open(path):
            class _H:
                def __enter__(self): return _Pdf()
                def __exit__(self, *a): return False
            return _H()
    monkeypatch.setattr(document_parser, "pdfplumber", _Pdfplumber, raising=False)

    result = _parse_pdf("/tmp/with_table.pdf", page_aware=True)
    assert isinstance(result, list)
    page_text = result[0][1]
    assert "页面正文" in page_text
    assert "| 产品 | 数量 |" in page_text
    assert "| A | 10 |" in page_text


def test_page_aware_returns_pages_from_one(monkeypatch):
    class _Page:
        def __init__(self, n): self._n = n
        def extract_text(self): return f"第{self._n}页内容"
        def extract_tables(self): return []
    class _Pdf:
        pages = [_Page(i) for i in range(1, 4)]
    class _Ctx:
        def __enter__(self): return self
        def __exit__(self, *a): return False
    class _Pdfplumber:
        @staticmethod
        def open(path):
            class _H:
                def __enter__(self): return _Pdf()
                def __exit__(self, *a): return False
            return _H()
    monkeypatch.setattr(document_parser, "pdfplumber", _Pdfplumber, raising=False)

    result = _parse_pdf("/tmp/multi.pdf", page_aware=True)
    page_nums = [p for p, _ in result]
    assert page_nums == [1, 2, 3]


def test_empty_page_ocr_fallback(monkeypatch):
    # 文本层提取为空 → 该页 OCR 兜底
    class _Page:
        def extract_text(self): return ""
        def extract_tables(self): return []
    class _Pdf:
        pages = [_Page()]
    class _Ctx:
        def __enter__(self): return self
        def __exit__(self, *a): return False
    class _Pdfplumber:
        @staticmethod
        def open(path):
            class _H:
                def __enter__(self): return _Pdf()
                def __exit__(self, *a): return False
            return _H()
    monkeypatch.setattr(document_parser, "pdfplumber", _Pdfplumber, raising=False)
    monkeypatch.setattr(document_parser, "_detect_avg_chars", lambda pdf: 100.0)

    # mock pdf2image + pytesseract
    class _Img: pass
    import types
    fake_pdf2image = types.ModuleType("pdf2image")
    fake_pdf2image.convert_from_path = lambda fp, first_page=None, last_page=None: [_Img()]
    monkeypatch.setitem(sys.modules, "pdf2image", fake_pdf2image)
    fake_pytesseract = types.ModuleType("pytesseract")
    fake_pytesseract.image_to_string = lambda img, lang=None: "OCR兜底文本"
    monkeypatch.setitem(sys.modules, "pytesseract", fake_pytesseract)

    result = _parse_pdf("/tmp/empty_page.pdf", page_aware=True)
    assert result[0][1] == "OCR兜底文本"
```

- [ ] **Step 2: 运行测试确认通过**

Run: `python -m pytest tests/test_document_parser_pdf_fidelity.py -v`
Expected: PASS（4 项全通过；若失败检查 mock 注入是否完整）

- [ ] **Step 3: 提交**

```bash
git add tests/test_document_parser_pdf_fidelity.py
git commit -m "test(kb): 扫描件与含表格 PDF 信息保真集成测试"
```

---

### 📋 审查检查点 #3（Task 7-9 完成后，thorough 模式分段审查）

- [ ] 运行 `python -m pytest tests/test_chunker_pages.py tests/test_document_parser_pdf.py tests/test_document_parser_pdf_fidelity.py -v` 全绿
- [ ] 确认 `split_text_with_pages` 跨页不拼接，page 字段精确（spec `Cross-page chunk boundary`）
- [ ] 确认图片型 PDF（avg_chars < 50）走 OCR 主路径而非兜底（spec `Detect image-type PDF and trigger OCR as primary path`）
- [ ] 确认表格输出 Markdown 含表头分隔行（spec `Extract tables as Markdown`）
- [ ] 确认 `page_aware=True` 时 PDF 返回 `List[Tuple[int, str]]`，page_num 从 1 开始（spec `PDF parsed with page metadata`）
- [ ] 确认 `parse_document(page_aware=True)` 对非 PDF 格式仍返回 str（spec `Page-aware Parsing`）
- [ ] 确认 worker 已切换到真实 `split_text_with_pages`，占位函数已删除
- [ ] Comet Classic：Build 阶段写入放行

---

## 组四：引用溯源

### Task 10: `chain.py` sources 增 `chunk_index`/`page`（tasks.md 4.1）

**Files:**
- Modify: `framework/rag/chain.py`（`chat()` 与 `chat_stream()` 两处 sources 改为按 chunk 输出，含 `chunk_index`/`page`；metadata 缺失时降级为 `None`）
- Test: `tests/test_chain_sources.py`

**Interfaces:**
- Consumes: `retrieval_results["results"]` 中每项的 `metadata`（含 `source`/`chunk_index`/`page`，由 ingestion_worker 写入）。
- Produces: `sources` 列表每项为 `{"doc_name": str, "chunk_index": Optional[int], "page": Optional[int]}`；`chat()` 与 `chat_stream()` 结构一致。

- [ ] **Step 1: 编写失败测试** `tests/test_chain_sources.py`

```python
"""测试 chain.py sources 含 chunk_index/page，且流式与非流式一致。"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from framework.rag import chain as chain_module
from framework.rag.chain import RAGChain


def _make_hit(source, chunk_index, page, content="chunk内容"):
    return {
        "content": content,
        "metadata": {
            "source": source,
            "chunk_index": chunk_index,
            "page": page,
            "category": "acidification",
        },
    }


def test_chat_sources_include_chunk_index_and_page(monkeypatch):
    rag = RAGChain.__new__(RAGChain)
    # mock _retrieve_documents 返回 2 个命中
    rag._retrieve_documents = lambda q, v: {
        "results": [
            _make_hit("doc_a.pdf", 0, 1),
            _make_hit("doc_a.pdf", 1, 5),
            _make_hit("doc_b.pdf", 2, 3),
        ],
        "count": 3,
    }
    rag._query_doc_names = lambda names: {"doc_a.pdf": "文档A.pdf", "doc_b.pdf": "文档B.pdf"}
    rag._build_context = lambda results: "ctx"
    rag._build_prompt = lambda q, ctx: "prompt"
    rag.llm_service = type("_L", (), {"generate": lambda self, p, h=None: {"success": True, "content": "ans", "model": "m"}})()

    result = rag.chat("问题")
    sources = result["sources"]
    # 每个 chunk 一条 source（不再按文档去重）
    assert len(sources) == 3
    assert {"doc_name": "文档A.pdf", "chunk_index": 0, "page": 1} in sources
    assert {"doc_name": "文档A.pdf", "chunk_index": 1, "page": 5} in sources
    assert {"doc_name": "文档B.pdf", "chunk_index": 2, "page": 3} in sources


def test_chat_sources_metadata_missing_degrades_to_none(monkeypatch):
    rag = RAGChain.__new__(RAGChain)
    rag._retrieve_documents = lambda q, v: {
        "results": [
            {"content": "c", "metadata": {"source": "old.pdf"}},  # 旧数据无 chunk_index/page
        ],
        "count": 1,
    }
    rag._query_doc_names = lambda names: {}
    rag._build_context = lambda r: "ctx"
    rag._build_prompt = lambda q, ctx: "p"
    rag.llm_service = type("_L", (), {"generate": lambda self, p, h=None: {"success": True, "content": "ans", "model": "m"}})()

    result = rag.chat("问题")
    assert result["sources"] == [{"doc_name": "old.pdf", "chunk_index": None, "page": None}]


def test_chat_stream_sources_same_structure_as_chat(monkeypatch):
    rag = RAGChain.__new__(RAGChain)
    rag._retrieve_documents = lambda q, v: {
        "results": [_make_hit("x.pdf", 4, 9)],
        "count": 1,
    }
    rag._query_doc_names = lambda names: {"x.pdf": "X.pdf"}
    rag._build_context = lambda r: "ctx"
    rag._build_prompt = lambda q, ctx: "p"
    rag.llm_service = type("_L", (), {
        "generate": lambda self, p, h=None: {"success": True, "content": "ans", "model": "m"},
        "generate_stream": lambda self, p, h=None: iter(["a", "n", "s"]),
    })()

    # chat
    chat_sources = rag.chat("问题")["sources"]
    # chat_stream：收集 meta 事件
    stream_meta = None
    for ev in rag.chat_stream("问题"):
        if ev.get("type") == "meta":
            stream_meta = ev
            break
    assert stream_meta is not None
    assert stream_meta["sources"] == chat_sources
    assert stream_meta["sources"][0] == {"doc_name": "X.pdf", "chunk_index": 4, "page": 9}


def test_chat_no_retrieval_returns_empty_sources(monkeypatch):
    rag = RAGChain.__new__(RAGChain)
    rag._retrieve_documents = lambda q, v: {"results": [], "count": 0}
    rag.llm_service = type("_L", (), {"generate": lambda self, p, h=None: {"success": True, "content": "ans", "model": "m"}})()

    result = rag.chat("问题")
    assert result["sources"] == []
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_chain_sources.py -v`
Expected: FAIL（当前 sources 只含 `doc_name`，按文档去重，无 `chunk_index`/`page`）

- [ ] **Step 3: 改造 `chat()` sources 构造**

修改 `framework/rag/chain.py` 的 `chat()` 方法中 sources 构造块（约 L55-L68）：

```python
        # 收集所有命中 chunk 的 source 元数据
        uuid_names = []
        for result in retrieval_results["results"]:
            metadata = result.get("metadata") or {}
            source = metadata.get("source", "unknown")
            if source not in uuid_names:
                uuid_names.append(source)
        name_mapping = self._query_doc_names(uuid_names)

        sources = []
        for result in retrieval_results["results"]:
            metadata = result.get("metadata") or {}
            source = metadata.get("source", "unknown")
            doc_name = name_mapping.get(source, source)
            sources.append({
                "doc_name": doc_name,
                "chunk_index": metadata.get("chunk_index"),
                "page": metadata.get("page"),
            })
```

- [ ] **Step 4: 改造 `chat_stream()` sources 构造**

修改 `chat_stream()` 中 sources 构造块（约 L96-L112），用与 Step 3 完全相同的逻辑：

```python
        # 收集所有命中 chunk 的 source 元数据
        uuid_names = []
        for result in retrieval_results["results"]:
            metadata = result.get("metadata") or {}
            source = metadata.get("source", "unknown")
            if source not in uuid_names:
                uuid_names.append(source)
        name_mapping = self._query_doc_names(uuid_names)

        sources = []
        for result in retrieval_results["results"]:
            metadata = result.get("metadata") or {}
            source = metadata.get("source", "unknown")
            doc_name = name_mapping.get(source, source)
            sources.append({
                "doc_name": doc_name,
                "chunk_index": metadata.get("chunk_index"),
                "page": metadata.get("page"),
            })

        # 先发送来源元数据，前端可立即展示参考来源
        yield {"type": "meta", "sources": sources}
```

- [ ] **Step 5: 运行测试确认通过**

Run: `python -m pytest tests/test_chain_sources.py -v`
Expected: PASS（4 项全通过）

- [ ] **Step 6: 回归现有 chain 测试**

Run: `python -m pytest tests/test_rag_chain.py tests/test_hybrid_search.py -v 2>/dev/null || echo "检查失败项"`
Expected: 若现有测试断言 `sources == [{"doc_name": ...}]`，按 Design Doc 调整为含 `chunk_index`/`page` 字段（旧数据 fixture 补 `chunk_index=None, page=None`）。

- [ ] **Step 7: 提交**

```bash
git add framework/rag/chain.py tests/test_chain_sources.py
git commit -m "feat(kb): chain sources 增 chunk_index/page，按 chunk 输出"
```

---

### Task 11: chunk 级引用测试补充（tasks.md 4.2）

**Files:**
- Modify: `tests/test_chain_sources.py`（补充边界：多 chunk 同文档页码不同、metadata 完全缺失、source 字段缺失降级）
- Test: 同上

**Interfaces:**
- Consumes: Task 10 的 sources 改造。
- Produces: 覆盖 spec `rag-chain` 全部 5 个场景（含 `Cross-page chunk boundary` 说明性边界、`Streaming and non-streaming consistency`）。

- [ ] **Step 1: 编写补充测试**（追加到 `tests/test_chain_sources.py`）

```python
def test_multiple_chunks_same_doc_different_pages(monkeypatch):
    rag = RAGChain.__new__(RAGChain)
    rag._retrieve_documents = lambda q, v: {
        "results": [
            _make_hit("same.pdf", 0, 1),
            _make_hit("same.pdf", 1, 1),
            _make_hit("same.pdf", 2, 2),
        ],
        "count": 3,
    }
    rag._query_doc_names = lambda names: {"same.pdf": "同文档.pdf"}
    rag._build_context = lambda r: "ctx"
    rag._build_prompt = lambda q, ctx: "p"
    rag.llm_service = type("_L", (), {"generate": lambda self, p, h=None: {"success": True, "content": "ans", "model": "m"}})()

    result = rag.chat("问题")
    # 同文档多 chunk 不合并，每条 source 独立
    assert len(result["sources"]) == 3
    pages = [s["page"] for s in result["sources"]]
    assert pages == [1, 1, 2]


def test_source_field_missing(monkeypatch):
    # metadata 完全缺失 source 字段
    rag = RAGChain.__new__(RAGChain)
    rag._retrieve_documents = lambda q, v: {
        "results": [{"content": "c", "metadata": {}}],
        "count": 1,
    }
    rag._query_doc_names = lambda names: {}
    rag._build_context = lambda r: "ctx"
    rag._build_prompt = lambda q, ctx: "p"
    rag.llm_service = type("_L", (), {"generate": lambda self, p, h=None: {"success": True, "content": "ans", "model": "m"}})()

    result = rag.chat("问题")
    assert result["sources"] == [{"doc_name": "unknown", "chunk_index": None, "page": None}]


def test_metadata_none_entirely(monkeypatch):
    # result.metadata 为 None
    rag = RAGChain.__new__(RAGChain)
    rag._retrieve_documents = lambda q, v: {
        "results": [{"content": "c", "metadata": None}],
        "count": 1,
    }
    rag._query_doc_names = lambda names: {}
    rag._build_context = lambda r: "ctx"
    rag._build_prompt = lambda q, ctx: "p"
    rag.llm_service = type("_L", (), {"generate": lambda self, p, h=None: {"success": True, "content": "ans", "model": "m"}})()

    result = rag.chat("问题")
    assert result["sources"] == [{"doc_name": "unknown", "chunk_index": None, "page": None}]
    # 不抛异常、不丢弃 source
```

- [ ] **Step 2: 运行测试确认通过**

Run: `python -m pytest tests/test_chain_sources.py -v`
Expected: PASS（全部 7 项通过）

- [ ] **Step 3: 提交**

```bash
git add tests/test_chain_sources.py
git commit -m "test(kb): chunk 级引用边界与降级测试补充"
```

---

## 组五：检索质量评估

### Task 12: 新增评估脚本与 fixtures（tasks.md 5.1 + 5.2）

**Files:**
- Create: `scripts/eval_retrieval.py`
- Create: `tests/fixtures/eval_queries.yaml`
- Test: `tests/test_eval_retrieval.py`

**Interfaces:**
- Consumes: `framework.vector_store.chroma_store.vector_store.hybrid_search(query, category=..., top_k=...)`、`framework.rag.category_router.route_category(query)`、PyYAML。
- Produces:
  - `scripts/eval_retrieval.py`：
    - `load_queries(path) -> list[dict]`：读 YAML 返回 `queries` 列表。
    - `evaluate(queries, top_k=5) -> dict`：返回 `{"queries": [...], "summary": {"n", "hit_rate", "mrr"}}`。
    - `main()`：CLI `--queries / --top-k / --out`，输出 JSON + 打印指标。
  - `tests/fixtures/eval_queries.yaml`：约 10 条标注查询，覆盖 `acidification` 与 `organic_matter` 两域。

- [ ] **Step 1: 编写 fixtures** `tests/fixtures/eval_queries.yaml`

```yaml
queries:
  - query: 土壤交换性氢含量如何影响酸度
    expected_doc_ids: ["acidification_overview.pdf"]
  - query: 交换性铝在酸化过程中的作用
    expected_doc_ids: ["acidification_overview.pdf"]
  - query: pH 值下降对作物根系的影响
    expected_doc_ids: ["acidification_overview.pdf"]
  - query: 石灰改良酸性土壤的用量
    expected_doc_ids: ["acidification_remediation.pdf"]
  - query: 有机质提升对土壤团聚体的作用
    expected_doc_ids: ["organic_matter_guide.pdf"]
  - query: 秸秆还田增加有机质的原理
    expected_doc_ids: ["organic_matter_guide.pdf"]
  - query: 腐殖质与土壤保水保肥能力
    expected_doc_ids: ["organic_matter_guide.pdf"]
  - query: 绿肥作物对有机质的贡献
    expected_doc_ids: ["organic_matter_guide.pdf"]
  - query: 土壤板结与有机质缺乏的关系
    expected_doc_ids: ["organic_matter_guide.pdf"]
  - query: 酸化土壤种什么绿肥合适
    expected_doc_ids: ["acidification_remediation.pdf", "organic_matter_guide.pdf"]
```

- [ ] **Step 2: 编写失败测试** `tests/test_eval_retrieval.py`

```python
"""测试检索质量评估指标计算（stub vector_store，不依赖真实向量库）。"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from scripts import eval_retrieval
from scripts.eval_retrieval import load_queries, evaluate


def test_load_queries(tmp_path):
    p = tmp_path / "q.yaml"
    p.write_text("queries:\n  - query: 测试\n    expected_doc_ids: [\"a.pdf\"]\n", encoding="utf-8")
    qs = load_queries(str(p))
    assert len(qs) == 1
    assert qs[0]["query"] == "测试"
    assert qs[0]["expected_doc_ids"] == ["a.pdf"]


def test_evaluate_hit_rate_and_mrr(monkeypatch):
    queries = [
        {"query": "Q1", "expected_doc_ids": ["a.pdf"]},
        {"query": "Q2", "expected_doc_ids": ["b.pdf"]},
    ]

    def _fake_hybrid_search(self_or_query, category=None, top_k=5, **kw):
        # 兼容 vector_store.hybrid_search(query, category=, top_k=) 与 unbound 调用
        query = self_or_query
        if query == "Q1":
            return {"results": [
                {"metadata": {"source": "a.pdf"}},
                {"metadata": {"source": "c.pdf"}},
            ]}
        if query == "Q2":
            return {"results": [
                {"metadata": {"source": "c.pdf"}},
                {"metadata": {"source": "b.pdf"}},  # rank 2 命中
            ]}
        return {"results": []}

    # patch route_category 与 vector_store.hybrid_search
    monkeypatch.setattr(eval_retrieval, "route_category", lambda q: "other")

    class _FakeVS:
        hybrid_search = _fake_hybrid_search
    monkeypatch.setattr(eval_retrieval, "vector_store", _FakeVS())

    result = evaluate(queries, top_k=5)
    # Q1 rank1 命中（rr=1.0），Q2 rank2 命中（rr=0.5）→ mrr=0.75
    # hit_rate=2/2=1.0
    assert result["summary"]["n"] == 2
    assert result["summary"]["hit_rate"] == 1.0
    assert result["summary"]["mrr"] == pytest.approx(0.75)
    assert result["queries"][0]["hit"] is True
    assert result["queries"][0]["reciprocal_rank"] == 1.0
    assert result["queries"][1]["reciprocal_rank"] == 0.5


def test_evaluate_no_hit(monkeypatch):
    queries = [{"query": "QX", "expected_doc_ids": ["z.pdf"]}]

    monkeypatch.setattr(eval_retrieval, "route_category", lambda q: "other")

    class _FakeVS:
        def hybrid_search(self, query, category=None, top_k=5, **kw):
            return {"results": [{"metadata": {"source": "c.pdf"}}]}
    monkeypatch.setattr(eval_retrieval, "vector_store", _FakeVS())

    result = evaluate(queries, top_k=5)
    assert result["summary"]["hit_rate"] == 0.0
    assert result["summary"]["mrr"] == 0.0
    assert result["queries"][0]["hit"] is False
    assert result["queries"][0]["reciprocal_rank"] == 0.0


def test_evaluate_empty_expected(monkeypatch):
    queries = [{"query": "QE", "expected_doc_ids": []}]

    monkeypatch.setattr(eval_retrieval, "route_category", lambda q: "other")

    class _FakeVS:
        def hybrid_search(self, query, category=None, top_k=5, **kw):
            return {"results": [{"metadata": {"source": "a.pdf"}}]}
    monkeypatch.setattr(eval_retrieval, "vector_store", _FakeVS())

    result = evaluate(queries, top_k=5)
    # 空 expected → 无命中
    assert result["summary"]["hit_rate"] == 0.0
    assert result["queries"][0]["hit"] is False
```

- [ ] **Step 3: 运行测试确认失败**

Run: `python -m pytest tests/test_eval_retrieval.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'scripts.eval_retrieval'`

- [ ] **Step 4: 编写评估脚本** `scripts/eval_retrieval.py`

```python
"""检索质量评估：基于标注查询集计算 hit_rate@K 与 MRR。

用法: python scripts/eval_retrieval.py --queries tests/fixtures/eval_queries.yaml --top-k 5 --out eval.json
"""
from __future__ import annotations
import argparse
import json
import yaml

from framework.vector_store.chroma_store import vector_store
from framework.rag.category_router import route_category


def load_queries(path):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)["queries"]


def evaluate(queries, top_k=5):
    results = []
    hits = 0
    reciprocal_ranks = []
    for q in queries:
        normalized = q["query"]
        category = route_category(normalized)
        retrieval = vector_store.hybrid_search(normalized, category=category, top_k=top_k)
        retrieved_doc_names = [r.get("metadata", {}).get("source") for r in retrieval.get("results", [])]
        expected = set(q.get("expected_doc_ids") or [])
        # hit@K: 命中任一 expected
        hit = any(d in expected for d in retrieved_doc_names)
        # MRR: 首个命中的倒数排名
        rr = 0.0
        for rank, d in enumerate(retrieved_doc_names, start=1):
            if d in expected:
                rr = 1.0 / rank
                break
        if hit:
            hits += 1
        reciprocal_ranks.append(rr)
        results.append({
            "query": normalized,
            "expected": list(expected),
            "retrieved": retrieved_doc_names,
            "hit": hit,
            "reciprocal_rank": rr,
        })
    summary = {
        "n": len(queries),
        "hit_rate": hits / max(len(queries), 1),
        "mrr": sum(reciprocal_ranks) / max(len(reciprocal_ranks), 1),
    }
    return {"queries": results, "summary": summary}


def main():
    ap = argparse.ArgumentParser(description="检索质量评估")
    ap.add_argument("--queries", required=True, help="标注查询集 YAML 路径")
    ap.add_argument("--top-k", type=int, default=5, help="Top-K 检索数量")
    ap.add_argument("--out", default="eval.json", help="输出 JSON 路径")
    args = ap.parse_args()

    queries = load_queries(args.queries)
    result = evaluate(queries, top_k=args.top_k)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"[eval] hit_rate={result['summary']['hit_rate']:.2%} mrr={result['summary']['mrr']:.2%}")


if __name__ == "__main__":
    main()
```

> 注：`scripts/` 目录可能无 `__init__.py`；若测试 import 失败，在 `scripts/__init__.py` 建空文件或在测试中改用 `importlib`。本计划默认 `scripts/` 已可作为包导入（项目既有脚本惯例）。

- [ ] **Step 5: 运行测试确认通过**

Run: `python -m pytest tests/test_eval_retrieval.py -v`
Expected: PASS（4 项全通过）

- [ ] **Step 6: 提交**

```bash
git add scripts/eval_retrieval.py tests/fixtures/eval_queries.yaml tests/test_eval_retrieval.py
git commit -m "feat(kb): 检索质量评估脚本 + 标注查询集 fixtures"
```

---

## 组六：验证与回归

### Task 13: 调整现有上传/解析测试断言以适配异步与清洗（tasks.md 6.1 前置）

**Files:**
- Modify: `tests/test_upload.py`（若存在且断言 `status==1` / HTTP 200，调整为 `status==0(pending)` / HTTP 202 + worker 完成后 `status==1` 的等价断言）
- Modify: `tests/test_document_parser.py`（若存在且断言原文未清洗文本，调整为清洗后等价语义）
- Modify: `tests/test_rag_chain.py` / `tests/test_hybrid_search.py`（若断言 sources 仅含 `doc_name`，补 `chunk_index`/`page` 字段或用旧 fixture `None` 降级）

**Interfaces:**
- Consumes: Task 2/6/10 的接口变更。
- Produces: 现有测试套件适配新行为，无语义破坏。

- [ ] **Step 1: 识别需调整的现有测试**

Run: `python -m pytest tests/ -v --co -q 2>&1 | findstr /R "test_upload test_document_parser test_rag_chain test_hybrid_search"`
Expected: 列出现有相关测试节点

- [ ] **Step 2: 运行现有测试套件定位失败**

Run: `python -m pytest tests/test_upload.py tests/test_document_parser.py tests/test_rag_chain.py tests/test_hybrid_search.py -v 2>&1 | tail -50`
Expected: 标记因本变更导致断言不匹配的失败项（非真实回归）

- [ ] **Step 3: 调整断言（不破坏语义）**

对每个失败测试，按 Design Doc 第 7 节策略调整：
- 上传测试：`assert resp.status_code == 200` → `== 202`；`assert data["status"] == 1` → `== Document.STATUS_PENDING`(0)，并补 worker 完成后的等价断言（mock worker 或直接断言提交调用）。
- 解析测试：断言原文 → 断言清洗后等价文本（如全角 `Ａ` → 半角 `A`）。
- sources 测试：`[{"doc_name": "x"}]` → `[{"doc_name": "x", "chunk_index": None, "page": None}]`（旧 fixture）或补真实 chunk_index/page。

- [ ] **Step 4: 运行调整后测试确认通过**

Run: `python -m pytest tests/test_upload.py tests/test_document_parser.py tests/test_rag_chain.py tests/test_hybrid_search.py -v`
Expected: PASS（调整后的断言全通过）

- [ ] **Step 5: 提交**

```bash
git add tests/test_upload.py tests/test_document_parser.py tests/test_rag_chain.py tests/test_hybrid_search.py
git commit -m "test(kb): 现有测试适配异步上传与清洗后断言"
```

---

### Task 14: 完整测试套件回归验证（tasks.md 6.1）

**Files:**
- Test: 全项目 `tests/` 套件

**Interfaces:**
- Consumes: Task 1-13 全部实现。
- Produces: P0+P1+P2 改动无回归的完整测试通过证明。

- [ ] **Step 1: 运行完整测试套件**

Run: `python -m pytest tests/ -v`
Expected: 全部 PASS（或仅剩与本变更无关的既存已知失败，需在报告中列明）

- [ ] **Step 2: 运行评估脚本冒烟（可选，需向量库与 fixtures 就绪）**

Run: `python scripts/eval_retrieval.py --queries tests/fixtures/eval_queries.yaml --top-k 5 --out eval.json`
Expected: 输出 `[eval] hit_rate=XX% mrr=XX%`，生成 `eval.json`（若向量库为空，hit_rate/mrr 可能为 0，属正常；脚本不抛异常即通过）

- [ ] **Step 3: 失败项分类与修复**

若 Step 1 有失败：
- 本变更引入的回归 → 修复实现或测试断言
- 既存无关失败 → 在最终报告中列明，不修复

- [ ] **Step 4: 提交（如有修复）**

```bash
git add -A
git commit -m "test(kb): P2 完整测试套件回归验证通过"
```

> 若无修改则跳过提交。

---

### 📋 最终审查检查点（Task 10-14 完成后，thorough 模式完整审查）

- [ ] 运行 `python -m pytest tests/ -v` 全绿（或仅剩既存无关失败）
- [ ] **Spec 覆盖核对**：
  - `file-upload-management/spec.md`：
    - [ ] Text Cleaning → `test_text_cleaner.py` 全过
    - [ ] Asynchronous Document Processing → `test_upload_async.py` 验证 202 + 状态流转
    - [ ] Status Enum Definition → `test_document_status_enum.py` 验证 0/1/2/3
    - [ ] Image-type PDF Detection → `test_document_parser_pdf.py` + `test_document_parser_pdf_fidelity.py` 验证阈值触发 OCR 主路径
    - [ ] Table Structure Preservation → `test_document_parser_pdf.py` 验证 Markdown 表格
    - [ ] Page-aware Parsing → `test_document_parser_pdf_fidelity.py` 验证 `List[(page, text)]`
  - `rag-chain/spec.md`：
    - [ ] Chunk-level Source Citation → `test_chain_sources.py` 验证 sources 含 chunk_index/page + 流式一致 + metadata 缺失降级
  - `kb-retrieval-evaluation/spec.md`：
    - [ ] Retrieval quality evaluation → `test_eval_retrieval.py` + `scripts/eval_retrieval.py` 输出 JSON 指标
- [ ] **tasks.md 14 项全部勾选**：1.1-1.3 / 2.1-2.3 / 3.1-3.3 / 4.1-4.2 / 5.1-5.2 / 6.1
- [ ] **Design Doc 第 3 节文件改动清单全部落地**（16 项：2 新增模块 + 1 新增脚本 + 1 fixtures + 6 新测试 + 6 修改）
- [ ] **无数据迁移**：status 列类型与默认值未变；现有 status=1 数据语义不变
- [ ] **无依赖新增**：pdfplumber/pytesseract/pdf2image/Pillow/PyYAML 均已在环境
- [ ] **流式与非流式 sources 一致**：`chat()` 与 `chat_stream()` 结构相同
- [ ] **跨页 chunk 不拼接**：page 字段精确，无跨页拼接 chunk
- [ ] Comet Classic Build 阶段写入全程放行；准备进入 Verify 阶段

---

## 附录：执行方式说明

**用户已确认工作方式**：
- **worktree 隔离**：实施前用 `superpowers:using-git-worktrees` 创建隔离 worktree，所有改动在 worktree 内进行。
- **direct 执行**：full workflow 使用 direct 模式（需 `direct_override=true`），不派发子代理串行执行，由当前会话直接逐任务推进。
- **TDD**：每个任务严格 Red（失败测试）→ Green（最小实现）→ Refactor，先测试后实现。
- **thorough 审查**：每完成 3 个任务进行一次分段审查（见 📋 审查检查点 #1/#2/#3），全部完成后进行最终完整审查（见最终审查检查点）。

**Comet 协议**：当前 change `kb-ingestion-quality`，workflow=classic。本计划属 Classic Build 阶段；实施过程中若 Hook 拒绝写入，按拒绝信息回到 Build 阶段对应动作恢复，不绕过 Hook。Build 完成后进入 Verify 阶段（独立验收全部条目）。
