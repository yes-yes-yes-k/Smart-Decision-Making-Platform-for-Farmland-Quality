from __future__ import annotations
import os
import hashlib
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, UTC
from typing import Optional

from framework.upload.text_cleaner import clean_text


class ParsedPages(list):
    """Page-aware parse result carrying non-indexed quality metadata."""

    def __init__(self, values=(), *, parse_metadata=None):
        super().__init__(values)
        self.parse_metadata = dict(parse_metadata or {})


def _attach_parse_metadata(result, updates):
    if isinstance(result, ParsedPages):
        result.parse_metadata.update(updates)
    return result

def parse_document(file_path: str, file_type: str, page_aware: bool = False, *, pdf_profile: str = "legacy"):
    """解析文档。page_aware=True 时 PDF 返回 List[(page_num, text)]；其他格式始终返回 str。

    失败时抛出异常，由调用方捕获并打印日志。
    """
    if pdf_profile != "legacy":
        if pdf_profile != "pdf-layout-v2":
            raise ValueError("unknown_pdf_parse_profile")
        with Path(file_path).open("rb") as stream:
            is_pdf = stream.read(5) == b"%PDF-"
        if file_type not in {"pdf", "caj"} or not is_pdf:
            raise ValueError("layout_v2_requires_PDF_payload_native_CAJ_conversion_separate")
        from framework.upload.pdf_layout import parse_layout_pdf
        document = parse_layout_pdf(file_path)
        result = ParsedPages([(p["page"], p["text"]) for p in document["pages"]],
                             parse_metadata={"parser_profile": pdf_profile, "parse_version": document["parse_version"],
                                             "page_count": len(document["pages"]), "ocr_pages": 0})
        result.layout_document = document
        return result if page_aware else "\n".join(text for _, text in result)
    if file_type == 'txt':
        return _parse_txt(file_path)
    elif file_type == 'md':
        return _parse_txt(file_path)
    elif file_type == 'pdf':
        return _parse_pdf(file_path, page_aware=page_aware)
    elif file_type == 'caj':
        return _parse_caj(file_path, page_aware=page_aware)
    elif file_type == 'docx':
        return _parse_docx(file_path)
    elif file_type == 'xlsx':
        return _parse_excel(file_path)
    elif file_type in {'csv', 'dat'}:
        return _parse_delimited(file_path)
    else:
        return None


def _parse_caj(file_path: str, page_aware: bool = False):
    """将 CAJ 转换为临时 PDF，并复用已有的 PDF/OCR 解析链路。

    CAJ 是专有容器，不能可靠地按纯文本直接读取。转换后的 PDF 只存在于临时
    目录中，入库仍保存原始 CAJ 文件。部分扩展名为 .caj 的文件实际是 PDF，
    此时根据文件头直接解析，避免不必要的外部进程调用。
    """
    source = Path(file_path)
    try:
        with source.open("rb") as stream:
            if stream.read(5) == b"%PDF-":
                result = _parse_pdf(str(source), page_aware=page_aware)
                return _attach_parse_metadata(result, {
                    'conversion': 'pdf_payload',
                    'derived_pdf_retained': False,
                })
    except OSError as exc:
        raise RuntimeError(f"无法读取 CAJ 文件: {exc}") from exc

    from framework.config import Config

    converter = _resolve_caj_converter(Config.CAJ_CONVERTER_PATH)
    timeout = Config.CAJ_CONVERTER_TIMEOUT
    with tempfile.TemporaryDirectory(prefix="caj_parse_") as temp_dir:
        output_pdf = Path(temp_dir) / f"{source.stem}.pdf"
        command = _caj_converter_command(converter, source, output_pdf)
        try:
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                errors="replace",
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"CAJ 转换超时（{timeout} 秒）") from exc
        except OSError as exc:
            raise RuntimeError(f"无法启动 CAJ 转换器 {converter}: {exc}") from exc

        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "未提供错误信息").strip()
            raise RuntimeError(
                f"CAJ 转换失败（退出码 {completed.returncode}）: {detail[:1000]}"
            )
        if not output_pdf.is_file() or output_pdf.stat().st_size == 0:
            raise RuntimeError("CAJ 转换器未生成 PDF 文件")
        with output_pdf.open("rb") as stream:
            if stream.read(5) != b"%PDF-":
                raise RuntimeError("CAJ 转换器输出的文件不是有效 PDF")

        hasher = hashlib.sha256()
        with output_pdf.open('rb') as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                hasher.update(chunk)
        digest = hasher.hexdigest()
        managed_pdf = None
        if Config.LITERATURE_RETAIN_DERIVED_PDF:
            derived_dir = Path(Config.UPLOAD_FOLDER) / "derived"
            derived_dir.mkdir(parents=True, exist_ok=True)
            managed_pdf = derived_dir / f"{digest}.pdf"
            if not managed_pdf.exists():
                shutil.copy2(output_pdf, managed_pdf)

        result = _parse_pdf(str(output_pdf), page_aware=page_aware)
        return _attach_parse_metadata(result, {
            'conversion': 'caj_to_pdf',
            'converter': Path(converter).name,
            'converted_at': datetime.now(UTC).isoformat(),
            'derived_pdf_hash': digest,
            'derived_pdf_retained': bool(managed_pdf),
            'derived_pdf_name': managed_pdf.name if managed_pdf else None,
        })


def _resolve_caj_converter(configured_path: str = "") -> str:
    """解析 caj2pdf 路径；配置优先，否则从 PATH 查找。"""
    if configured_path:
        configured = Path(configured_path).expanduser()
        if not configured.is_file():
            raise RuntimeError(f"CAJ_CONVERTER_PATH 指向的文件不存在: {configured}")
        return str(configured)

    discovered = shutil.which("caj2pdf") or shutil.which("caj2pdf.exe")
    if discovered:
        return discovered
    raise RuntimeError(
        "未找到 CAJ 转换器。请安装 caj2pdf 并加入 PATH，或设置 "
        "CAJ_CONVERTER_PATH 指向 caj2pdf 可执行文件/caj2pdf.py"
    )


def caj_converter_is_available(configured_path: str = "") -> bool:
    try:
        _resolve_caj_converter(configured_path)
        return True
    except RuntimeError:
        return False


def _caj_converter_command(converter: str, source: Path, output_pdf: Path):
    """构造 caj2pdf 的参数列表，不经过 shell，避免文件名命令注入。"""
    prefix = [sys.executable, converter] if converter.lower().endswith(".py") else [converter]
    return [*prefix, "convert", str(source), "-o", str(output_pdf)]

def _parse_txt(file_path: str) -> str:
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        return clean_text(f.read())

def _parse_pdf(file_path: str, page_aware: bool = False):
    """Parse a PDF, repairing a readable damaged catalog/xref when needed."""
    try:
        return _parse_pdf_impl(file_path, page_aware=page_aware)
    except Exception as original_exc:
        repaired_path = None
        try:
            import fitz

            with tempfile.NamedTemporaryFile(
                suffix='.pdf', prefix='pdf_repaired_', delete=False,
            ) as temp_file:
                repaired_path = Path(temp_file.name)
            with fitz.open(file_path) as document:
                if document.needs_pass or len(document) == 0:
                    raise original_exc
                document.save(
                    repaired_path, garbage=4, clean=True, deflate=True,
                )
            result = _parse_pdf_impl(str(repaired_path), page_aware=page_aware)
            metadata = getattr(result, 'parse_metadata', None)
            if metadata is not None:
                metadata['pdf_repaired'] = True
            return result
        except Exception:
            raise original_exc
        finally:
            if repaired_path is not None:
                repaired_path.unlink(missing_ok=True)


def _parse_pdf_impl(file_path: str, page_aware: bool = False):
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

    pages_text = ParsedPages()  # List[(page_num, text)]
    text_layer_pages = 0
    ocr_pages = 0
    empty_pages = 0
    error_pages = 0
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
                error_pages += 1
            if len(page_text.strip()) >= Config.PDF_OCR_THRESHOLD:
                text_layer_pages += 1
            else:
                try:
                    from pdf2image import convert_from_path
                    import pytesseract
                    images = convert_from_path(file_path, first_page=i, last_page=i)
                    if images:
                        ocr_text = pytesseract.image_to_string(
                            images[0], lang="chi_sim+eng"
                        )
                        if ocr_text.strip():
                            page_text = ocr_text
                        ocr_pages += 1
                except Exception as e:
                    print(f"[Parser] 第 {i} 页 OCR 兜底失败: {e}")
                    error_pages += 1
            try:
                tables_md = [_table_to_markdown(t) for t in (page.extract_tables() or [])]
            except Exception as e:
                print(f"[Parser] 第 {i} 页表格提取失败: {e}")
                tables_md = []
                error_pages += 1
            if tables_md:
                page_text = page_text + "\n\n" + "\n\n".join(tables_md)
            cleaned = clean_text(page_text)
            if not cleaned:
                empty_pages += 1
            pages_text.append((i, cleaned))

    pages_text.parse_metadata.update({
        'page_count': total_pages,
        'text_layer_pages': text_layer_pages,
        'ocr_pages': ocr_pages,
        'empty_pages': empty_pages,
        'error_pages': error_pages,
    })

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


def _parse_pdf_ocr(file_path: str, page_aware: bool = False):
    """使用 OCR 识别扫描件/图片型 PDF 中的文字。

    page_aware=True 返回 List[(page_num, text)]；False 返回 str。
    """
    print(f"[Parser] 开始 OCR 识别：{file_path}", flush=True)

    try:
        from pdf2image import convert_from_path
    except ImportError as e:
        raise ImportError(
            f"pdf2image 未安装，无法进行 OCR 识别。请执行: pip install pdf2image  错误: {e}"
        )
    try:
        import pytesseract
    except ImportError as e:
        raise ImportError(
            f"pytesseract 未安装，无法进行 OCR 识别。请执行: pip install pytesseract  错误: {e}"
        )
    try:
        pytesseract.get_tesseract_version()
    except Exception as e:
        raise RuntimeError(
            f"未找到 Tesseract OCR 引擎。请先安装 Tesseract：https://github.com/tesseract-ocr/tesseract  错误: {e}"
        )

    try:
        import pdfplumber
        with pdfplumber.open(file_path) as pdf:
            total_pages = len(pdf.pages)
    except Exception as e:
        raise RuntimeError(f"无法读取 PDF 页数: {e}") from e
    print(f"[Parser] PDF 共 {total_pages} 页，开始 OCR 识别...", flush=True)

    pages_text = ParsedPages()  # List[(page_num, text)]
    empty_pages = 0
    error_pages = 0
    for i in range(1, total_pages + 1):
        try:
            print(f"[Parser] OCR 识别第 {i}/{total_pages} 页...", flush=True)
            images = convert_from_path(file_path, first_page=i, last_page=i)
            if not images:
                raise RuntimeError("未生成页面图片")
            page_text = pytesseract.image_to_string(
                images[0], lang='chi_sim+eng'
            ).strip()
        except Exception as e:
            print(f"[Parser] OCR 第 {i}/{total_pages} 页识别失败：{e}", flush=True)
            page_text = ""
            error_pages += 1
        cleaned = clean_text(page_text)
        if not cleaned:
            empty_pages += 1
        pages_text.append((i, cleaned))

    pages_text.parse_metadata.update({
        'page_count': total_pages,
        'text_layer_pages': 0,
        'ocr_pages': total_pages,
        'empty_pages': empty_pages,
        'error_pages': error_pages,
    })

    print(f"[Parser] OCR 识别完成，共 {total_pages} 页", flush=True)
    if page_aware:
        return pages_text
    return clean_text("\n".join(t for _, t in pages_text))

def _parse_docx(file_path: str) -> str:
    try:
        from docx import Document
    except ImportError as e:
        raise ImportError(f"python-docx 未安装，无法解析 DOCX：{e}。请执行 pip install python-docx")

    doc = Document(file_path)
    parts = [para.text for para in doc.paragraphs if para.text]
    for table in doc.tables:
        for row in table.rows:
            values = [cell.text.strip() for cell in row.cells]
            if any(values):
                parts.append(" | ".join(values))
    return clean_text("\n".join(parts))

def _parse_excel(file_path: str) -> str:
    try:
        import pandas as pd
    except ImportError as e:
        raise ImportError(f"pandas 未安装，无法解析 Excel：{e}。请执行 pip install pandas openpyxl")

    sheets = pd.read_excel(file_path, sheet_name=None)
    parts = []
    for sheet_name, df in sheets.items():
        parts.append(f"工作表: {sheet_name}\n{df.to_string(index=False)}")
    return clean_text("\n\n".join(parts))


def _parse_delimited(file_path: str) -> str:
    try:
        import pandas as pd
    except ImportError as e:
        raise ImportError(f"pandas 未安装，无法解析 CSV/DAT：{e}。请执行 pip install pandas")

    last_error = None
    for encoding in ("utf-8-sig", "gb18030"):
        try:
            df = pd.read_csv(file_path, sep=None, engine="python", encoding=encoding)
            return clean_text(df.to_string(index=False))
        except Exception as exc:
            last_error = exc
    raise ValueError(f"无法解析分隔文本文件: {last_error}")
