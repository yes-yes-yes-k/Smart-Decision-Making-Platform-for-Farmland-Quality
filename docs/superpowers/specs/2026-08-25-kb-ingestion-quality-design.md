---
comet_change: kb-ingestion-quality
role: technical-design
canonical_spec: openspec
archived-with: 2026-08-25-kb-ingestion-quality
status: final
---

# kb-ingestion-quality — Technical Design Doc

> 上游事实源：`openspec/changes/kb-ingestion-quality/{proposal.md,design.md,tasks.md,specs/*/spec.md}`。本文档是对 OpenSpec `design.md` 的深度技术细化，不替代或重写需求 spec。

## 1. 背景与目标

在 P0（hybrid retrieval：向量+BM25+RRF+rerank）与 P1（同义词预处理 + chunk metadata + 分领域 collection）基础上，补齐入库质量治理与可观测性。本次变更覆盖 5 项能力：

1. 解析后文本清洗（合并空白/页眉页脚/控制字符/Unicode NFKC）
2. 上传管线异步化（fire-and-forget + 状态机跟踪）
3. OCR 主路径化（图片型/扫描件 PDF 优先 OCR）+ 表格结构保留
4. 答案引用溯源到 chunk/页码
5. 检索质量评估脚本（hit_rate@K + MRR）

### 关键 Non-Goals（沿用 OpenSpec design.md）

- 不改 P0/P1 检索策略与元数据设计
- 不引入完整 RAGAS 平台或图形化 UI
- 不引入 Celery/Redis（与项目 Non-Goals 一致）

## 2. 实施方案：最小侵入式（方案 A）

总原则：每项能力做最小侵入改动，保留现有函数签名向后兼容；新增能力以独立模块/脚本形式提供，避免影响已有调用方。

### 2.1 文本清洗

**新增模块**：`framework/upload/text_cleaner.py`

```python
import re
import unicodedata

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

    实现：按 \n 切行，统计行内容 hash 频率；频次 ≥ 3 的非空行去除。
    保留单页内容（即使恰好与页眉相同也不去除，因为是页眉的话必然多次重复）。
    """
    lines = text.split("\n")
    if len(lines) < 6:
        return text
    from collections import Counter
    freq = Counter(line.strip() for line in lines if line.strip())
    repeated = {h for h, c in freq.items() if c >= 3}
    if not repeated:
        return text
    return "\n".join(line for line in lines if line.strip() not in repeated)
```

**接入点**：`framework/upload/document_parser.py` 各 `_parse_*` 函数 return 前调用 `clean_text(text)`；`_parse_pdf_ocr` 同样在最后 return 前调用。

**测试**：`tests/test_text_cleaner.py`，覆盖 NFKC 转换、控制字符、空白合并、重复页眉（3+ 次）去除、空文本/短文本边界。

### 2.2 异步入库

**新增模块**：`framework/upload/ingestion_worker.py`

```python
import concurrent.futures
import traceback
from flask import current_app
from framework.models.user import db
from framework.models.document import Document
from framework.upload.document_parser import parse_document
from framework.upload.chunker import split_text_with_pages, split_text
from framework.vector_store.chroma_store import vector_store

# 模块级 worker：与 data_trigger.py 的 ThreadPoolExecutor 模式同源
_WORKER = concurrent.futures.ThreadPoolExecutor(
    max_workers=2, thread_name_prefix="ingest"
)


def submit_ingest(document_id, file_path, file_type, doc_name, category, treatment_type):
    """非阻塞提交入库任务；立即返回 future。

    上传路由调用本函数后立即返回 202，状态机由 worker 内部推进。
    """
    _WORKER.submit(
        _ingest,
        document_id, file_path, file_type, doc_name, category, treatment_type,
    )


def _ingest(document_id, file_path, file_type, doc_name, category, treatment_type):
    """入库 worker 主体。状态机: pending(0) → processing(2) → completed(1) 或 failed(3)。

    异常时记录 traceback 并推进到 failed，避免文档永久停留 processing。
    """
    # 在 worker 线程内推送 app context（Flask-SQLAlchemy 需要）
    from framework import create_app
    app = create_app()
    with app.app_context():
        try:
            _set_status(document_id, Document.STATUS_PROCESSING)
            # 解析（parse_document 内部已调用 clean_text）
            pages = parse_document(file_path, file_type, page_aware=True)
            # 切分：page_aware 返回 List[(chunk, page)]
            if isinstance(pages, list) and pages and isinstance(pages[0], tuple):
                chunks_with_pages = split_text_with_pages(pages)
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
            doc.chunk_count = len(chunks)
            doc.status = Document.STATUS_COMPLETED
            db.session.commit()
        except Exception as e:
            traceback.print_exc()
            try:
                doc = Document.query.get(document_id)
                if doc:
                    doc.status = Document.STATUS_FAILED
                    db.session.commit()
            except Exception:
                traceback.print_exc()


def _set_status(document_id, status):
    doc = Document.query.get(document_id)
    if doc:
        doc.status = status
        db.session.commit()
```

**上传路由改造**（`framework/api/routes/docs.py` 的 `/upload`）：

```python
# 原: parse_document + split_text + add_documents + Document(status=1) 同步执行
# 改: Document(status=0 pending) → commit → submit_ingest(...) → 立即返回 202

document = Document(
    doc_name=file.filename,
    file_path=new_filename,
    file_type=file_type,
    file_size=os.path.getsize(file_path),
    chunk_count=0,
    status=Document.STATUS_PENDING,  # 0=pending
    file_hash=file_hash,
    category=category,
    treatment_type=treatment_type,
    create_by=user_id,
)
db.session.add(document)
db.session.commit()

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

**status 枚举**（`framework/models/document.py`）：

```python
class Document(db.Model):
    __tablename__ = 'kb_document'

    STATUS_PENDING = 0
    STATUS_COMPLETED = 1   # 保留现有语义：现有数据 status=1 表"完成"
    STATUS_PROCESSING = 2
    STATUS_FAILED = 3
    # ...其余字段不变
```

**风险与缓解**：
- worker 异常未推进 status → 用 try/except 包裹 + traceback 打印 + finally 推进 failed
- worker 线程内 db session 隔离 → 重新创建 app context（如上）
- 进程崩溃时未完成文档停留 processing → 后续可在 Verify 阶段补充"启动时清理 stale processing 文档"工具脚本（本期不做，留待 P3）

### 2.3 OCR/表格解析主路径

**图片型 PDF 检测**（`document_parser.py::_parse_pdf`）：

```python
def _parse_pdf(file_path: str, page_aware: bool = False):
    """PDF 解析：先做图片型检测，命中则全本 OCR；否则逐页提取+表格。

    page_aware=True 返回 List[(page_num, text)]；False 返回 str（向后兼容）。
    """
    import pdfplumber
    pages_text = []   # List[(page_num, text)]
    with pdfplumber.open(file_path) as pdf:
        total_pages = len(pdf.pages)
        # 1. 图片型检测：平均字符数 < 阈值则全本 OCR
        avg_chars = _detect_avg_chars(pdf)
        if avg_chars < Config.PDF_OCR_THRESHOLD:  # 默认 50
            return _parse_pdf_ocr(file_path, page_aware=page_aware)
        # 2. 混合解析：逐页提取文本+表格
        for i, page in enumerate(pdf.pages, start=1):
            page_text = page.extract_text() or ""
            tables_md = [_table_to_markdown(t) for t in (page.extract_tables() or [])]
            if tables_md:
                page_text = page_text + "\n\n" + "\n\n".join(tables_md)
            # 单页空文本 → 该页 OCR 兜底
            if not page_text.strip():
                try:
                    from PIL import Image
                    import pytesseract
                    from pdf2image import convert_from_path
                    images = convert_from_path(file_path, first_page=i, last_page=i)
                    if images:
                        page_text = pytesseract.image_to_string(images[0], lang="chi_sim+eng")
                except Exception as e:
                    print(f"[Parser] 第 {i} 页 OCR 兜底失败: {e}")
            pages_text.append((i, page_text))

    if page_aware:
        return pages_text
    return "\n".join(t for _, t in pages_text).strip()


def _detect_avg_chars(pdf) -> float:
    """采样前 5 页（或全部）的字符数取平均，避免全本扫描成本。"""
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
    if not rows:
        return ""
    header = rows[0]
    body = rows[1:] if len(rows) > 1 else []
    lines = ["| " + " | ".join(c or "" for c in header) + " |",
             "| " + " | ".join("---" for _ in header) + " |"]
    for row in body:
        lines.append("| " + " | ".join(c or "" for c in row) + " |")
    return "\n".join(lines)
```

**`parse_document` 入口扩展**：

```python
def parse_document(file_path: str, file_type: str, page_aware: bool = False):
    """解析文档。page_aware=True 时 PDF 返回 List[(page, text)]；其他格式始终返回 str。"""
    # ...各分支调用，PDF 透传 page_aware
    if file_type == 'pdf':
        result = _parse_pdf(file_path, page_aware=page_aware)
        return result
    # txt/md/docx/xlsx 仍返回 str（已通过 clean_text 清洗）
```

**`_parse_pdf_ocr` 也增加 page_aware 参数**：基于 `convert_from_path` 的 images 列表本身就是按页排序，返回 `[(i, ocr_text)]`。

**Config 新增**：

```python
class Config:
    PDF_OCR_THRESHOLD = 50  # 平均字符/页阈值，低于则触发 OCR 主路径
```

### 2.4 引用溯源

**chunker 改造**（`framework/upload/chunker.py`）：

```python
def split_text(text: str, size: int = None, overlap: int = None) -> List[str]:
    """原签名保留，向后兼容。"""
    # ...原实现不变


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
    size = size if size is not None else Config.CHUNK_SIZE
    overlap = overlap if overlap is not None else Config.CHUNK_OVERLAP
    result = []
    for page_num, page_text in pages:
        if not page_text:
            continue
        chunks = split_text(page_text, size=size, overlap=overlap)
        for c in chunks:
            result.append((c, page_num))
    return result
```

**关键决策**：跨页不拼接。理由：拼接后 chunk 的 page 字段取何页都有歧义；不拼接时 page 字段精确表示该 chunk 来自第 N 页。代价是 chunk 数量略多（页末块可能小于 size），但溯源精确度优先。

**metadata 写入 chroma**：`ingestion_worker._ingest` 中已包含：

```python
metadatas = [{
    "source": doc_name,
    "category": category,
    "treatment_type": treatment_type,
    "chunk_index": i,
    "page": pages_meta[i],
} for i in range(len(chunks))]
```

**chain.py sources 改造**（`framework/rag/chain.py` L55-L68 和 L96-L112）：

```python
# 原 sources 构造（伪代码）:
# for src in metadata.source: doc_name = lookup(doc); sources.append({"doc_name": doc_name})

# 改为（同时保留 doc_name，新增 chunk_index 和 page）:
sources = []
for hit in retrieval_hits:
    meta = hit.get("metadata", {})
    doc_name = _lookup_doc_name(meta.get("source"))
    sources.append({
        "doc_name": doc_name,
        "chunk_index": meta.get("chunk_index"),
        "page": meta.get("page"),
    })
```

`chat()` 与 `chat_stream()` 两处都按此模式改造，确保流式与非流式行为一致。

**测试**：
- `tests/test_chunker_pages.py`：单页多 chunk、空页跳过、跨页不拼接的边界
- `tests/test_chain_sources.py`：sources 字段完整性、metadata 缺失时降级（chunk_index/page 为 None）

### 2.5 检索质量评估

**新增脚本**：`scripts/eval_retrieval.py`

```python
"""检索质量评估：基于标注查询集计算 hit_rate@K 与 MRR。

用法: python scripts/eval_retrieval.py --queries tests/fixtures/eval_queries.yaml --top-k 5 --out eval.json
"""
import argparse, json, yaml
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
        retrieved_doc_names = [r.get("metadata", {}).get("source") for r in retrieval]
        expected = set(q["expected_doc_ids"] or [])
        # hit@K: 命中任一 expected
        hit = any(d in expected for d in retrieved_doc_names)
        # MRR: 首个命中的倒数排名
        rr = 0.0
        for rank, d in enumerate(retrieved_doc_names, start=1):
            if d in expected:
                rr = 1.0 / rank
                break
        if hit: hits += 1
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
    ap = argparse.ArgumentParser()
    ap.add_argument("--queries", required=True)
    ap.add_argument("--top-k", type=int, default=5)
    ap.add_argument("--out", default="eval.json")
    args = ap.parse_args()
    queries = load_queries(args.queries)
    result = evaluate(queries, top_k=args.top_k)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"[eval] hit_rate={result['summary']['hit_rate']:.2%} mrr={result['summary']['mrr']:.2%}")


if __name__ == "__main__":
    main()
```

**fixtures**：`tests/fixtures/eval_queries.yaml`

```yaml
queries:
  - query: 土壤交换性氢含量如何影响酸度
    expected_doc_ids: ["acidification_overview.pdf"]
  - query: 有机质提升对土壤团聚体的作用
    expected_doc_ids: ["organic_matter_guide.pdf"]
  # ...约 10 条，覆盖 acidification 与 organic_matter 两域
```

> 注：`expected_doc_ids` 用 `metadata.source`（即上传时的 `doc_name`）。后续 KB 扩充时可补充更多查询。

**测试**：`tests/test_eval_retrieval.py`：用 stub `vector_store.hybrid_search`（返回固定 retrieval）验证 hit_rate/MRR 计算正确性，不依赖真实向量库。

## 3. 文件改动清单

| 路径 | 类型 | 说明 |
|---|---|---|
| `framework/upload/text_cleaner.py` | 新增 | `clean_text()` 纯函数 |
| `framework/upload/ingestion_worker.py` | 新增 | 异步 worker + 状态机 |
| `framework/upload/document_parser.py` | 修改 | `clean_text` 接入 + 图片型检测 + 表格提取 + `page_aware` 参数 |
| `framework/upload/chunker.py` | 修改 | 新增 `split_text_with_pages()`，保留 `split_text()` |
| `framework/models/document.py` | 修改 | 新增 STATUS_* 类常量 |
| `framework/api/routes/docs.py` | 修改 | `/upload` 改异步 fire-and-forget + 202 |
| `framework/rag/chain.py` | 修改 | sources 增补 `chunk_index`/`page` |
| `framework/config.py` | 修改 | 新增 `PDF_OCR_THRESHOLD=50` |
| `scripts/eval_retrieval.py` | 新增 | 评估脚本 |
| `tests/fixtures/eval_queries.yaml` | 新增 | 标注查询集 |
| `tests/test_text_cleaner.py` | 新增 | 清洗单测 |
| `tests/test_chunker_pages.py` | 新增 | page-aware 切分单测 |
| `tests/test_ingestion_worker.py` | 新增 | 异步 worker 状态机单测 |
| `tests/test_upload_async.py` | 新增 | 上传异步集成测试 |
| `tests/test_eval_retrieval.py` | 新增 | 评估指标计算单测 |
| `tests/test_chain_sources.py` | 新增 | sources 字段完整性测试 |

## 4. Spec Patch（已回写）

参见 OpenSpec delta spec：
- `openspec/changes/kb-ingestion-quality/specs/file-upload-management/spec.md`：补 status 枚举、状态迁移场景、图片型 PDF 检测阈值、表格 Markdown 验收场景
- `openspec/changes/kb-ingestion-quality/specs/rag-chain/spec.md`：补 sources 字段结构示例与跨页边界说明

## 5. 测试策略

| 层级 | 文件 | 覆盖点 |
|---|---|---|
| 单测 | `test_text_cleaner.py` | NFKC、控制字符、空白合并、重复页眉去除、空/短文本边界 |
| 单测 | `test_chunker_pages.py` | page-aware 切分、空页跳过、跨页不拼接、参数缺省回退 |
| 单测 | `test_ingestion_worker.py` | mock vector_store + status 状态机：0→2→1 / 0→2→3、异常路径推进 failed |
| 单测 | `test_eval_retrieval.py` | stub retrieval 验证 hit_rate/MRR 计算、空 expected、无命中 |
| 单测 | `test_chain_sources.py` | sources 字段完整性、metadata 缺失降级 |
| 集成 | `test_upload_async.py` | 上传立即返回 202 + status 流转 + mock `vector_store.add_documents` |
| 回归 | `test_upload.py` 现有 | 现有上传测试若依赖同步 status=1，需调整为 status=1 的等价断言（不破坏断言语义） |
| 回归 | `test_collection_routing.py` | P1 分领域路由不破坏 |
| 回归 | `test_hybrid_search.py` | P0 hybrid 检索不破坏 |

## 6. 边界条件与已知限制

1. **跨页 chunk 不拼接**：page 字段精确表示 chunk 所属页，但页末块可能小于 chunk_size。
2. **OCR 阈值 50 字符/页**：经验值；含图扫描件可能误判，后续可在 Config 暴露微调。
3. **worker 异常推进 failed 的 best-effort**：进程崩溃时未捕获异常会留下 stale processing 文档；P2 不做启动时清理脚本，留待 P3。
4. **chunk 跨页边界溯源粒度**：用户看到 chunk 的 page 是 chunk 起始所属页，不展示 chunk 跨页边界（本期不拼接，无该问题）。
5. **评估 fixtures ~10 条**：覆盖 acidification/organic_matter 两域；后续 KB 扩充时补更多查询。
6. **流式与非流式 sources 一致**：`chat()` 与 `chat_stream()` 都要改造，避免前端两套格式。
7. **现有 status=1 数据语义不变**：枚举重定义为 0/1/2/3 后，1 仍表"completed"，无需数据迁移。

## 7. 风险与缓解

| 风险 | 影响 | 缓解 |
|---|---|---|
| worker 异常未推进 status | 文档永久停留 processing | try/except 包裹 + finally 推进 failed + traceback 打印 |
| 上传路由依赖同步 status=1 的旧测试 | 回归测试失败 | 调整测试断言：上传立即返回 status=0(pending)，worker 完成后 status=1 |
| 图片型 PDF 检测误判 | 含图但文本层正常的 PDF 误触发 OCR | 阈值 50 较保守；可在 Config 暴露后续调整 |
| page-aware chunker 接口新增 | 调用方未升级仍走旧接口 | 保留 `split_text(text)` 向后兼容；只有 worker 用新接口 |
| 流式 sources 改造遗漏 | 前端格式不一致 | 单测 `test_chain_sources.py` 同时覆盖 chat 与 chat_stream |
| 评估 fixtures 量小 | 指标波动大 | ~10 条覆盖两域；后续 P3 扩充 |

## 8. 部署与迁移

1. 新增 `framework/upload/text_cleaner.py` 与 `framework/upload/ingestion_worker.py` 模块。
2. 修改 `framework/upload/document_parser.py`、`chunker.py`、`framework/api/routes/docs.py`、`framework/rag/chain.py`、`framework/models/document.py`、`framework/config.py`。
3. 新增 `scripts/eval_retrieval.py` 与 `tests/fixtures/eval_queries.yaml`。
4. 新增测试文件 6 个。
5. 无数据库 schema 变更（status 字段类型不变，仅枚举语义重定义）。
6. 无依赖新增（pdfplumber/pytesseract/pdf2image/Pillow 已在 P0 引入）。

## 9. 验收场景对应 OpenSpec spec

- `file-upload-management/spec.md`：
  - Text Cleaning → `test_text_cleaner.py` 全部通过
  - Asynchronous Document Processing → `test_upload_async.py` 验证 202 + 状态流转
  - 新增 Image-type PDF Detection → `test_document_parser.py` 验证阈值触发 OCR 主路径
  - 新增 Table Preservation → `test_document_parser.py` 验证 Markdown 表格输出
  - 新增 Status Lifecycle → `test_ingestion_worker.py` 验证 0→2→1/3 状态迁移
- `rag-chain/spec.md`：
  - Chunk-level Source Citation → `test_chain_sources.py` 验证 sources 含 chunk_index/page
- `kb-retrieval-evaluation/spec.md`：
  - Retrieval quality evaluation → `test_eval_retrieval.py` + `scripts/eval_retrieval.py` 输出 JSON 指标
