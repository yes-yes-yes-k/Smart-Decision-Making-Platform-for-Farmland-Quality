from __future__ import annotations
import os
from typing import Optional

def parse_document(file_path: str, file_type: str) -> Optional[str]:
    """解析文档，返回纯文本。失败时抛出异常，由调用方捕获并打印日志。"""
    if file_type == 'txt':
        return _parse_txt(file_path)
    elif file_type == 'md':
        return _parse_txt(file_path)
    elif file_type == 'pdf':
        return _parse_pdf(file_path)
    elif file_type == 'docx':
        return _parse_docx(file_path)
    elif file_type == 'xlsx':
        return _parse_excel(file_path)
    else:
        return None

def _parse_txt(file_path: str) -> str:
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        return f.read()

def _parse_pdf(file_path: str) -> str:
    """PDF 解析：优先 pdfplumber（中文支持好、自动处理加密），失败时回退 PyPDF2。"""

    # ---- 方案一：pdfplumber（推荐，中文支持好）----
    try:
        import pdfplumber
    except ImportError:
        pdfplumber = None

    if pdfplumber:
        try:
            text_parts = []
            with pdfplumber.open(file_path) as pdf:
                total_pages = len(pdf.pages)
                for i, page in enumerate(pdf.pages):
                    try:
                        page_text = page.extract_text() or ""
                    except Exception as e:
                        print(f"[Parser] pdfplumber 第 {i+1}/{total_pages} 页解析失败：{e}")
                        page_text = ""
                    text_parts.append(page_text)

            text = "\n".join(text_parts).strip()
            if text:
                return text
            # pdfplumber 解析出空内容，回退 PyPDF2
            print("[Parser] pdfplumber 解析结果为空，回退 PyPDF2")
        except Exception as e:
            print(f"[Parser] pdfplumber 解析异常，回退 PyPDF2：{e}")

    # ---- 方案二：PyPDF2 兜底 ----
    try:
        from PyPDF2 import PdfReader
    except ImportError as e:
        raise ImportError(
            f"PDF 解析失败：pdfplumber 不可用且 PyPDF2 也未安装。"
            f"请执行 pip install pdfplumber PyPDF2 pycryptodome  错误: {e}"
        )

    reader = PdfReader(file_path)
    total_pages = len(reader.pages)

    # 先用第一页探测加密问题，避免全量跑完才发现
    if total_pages > 0:
        try:
            reader.pages[0].extract_text()
        except Exception as e:
            err_msg = str(e)
            if 'PyCryptodome' in err_msg:
                raise ImportError(
                    f"PDF 使用了 AES 加密，缺少 pycryptodome 库。"
                    f"请执行: pip install pycryptodome  错误详情: {e}"
                )
            if 'is encrypted' in err_msg.lower() or 'encrypt' in err_msg.lower():
                raise ValueError(f"PDF 已加密且无法解密（可能需要密码）：{e}")

    text_parts = []
    empty_pages = 0
    for i, page in enumerate(reader.pages):
        try:
            page_text = page.extract_text() or ""
        except Exception as e:
            print(f"[Parser] PyPDF2 第 {i+1}/{total_pages} 页解析失败，跳过：{e}")
            page_text = ""
        if not page_text.strip():
            empty_pages += 1
        text_parts.append(page_text)

    text = "\n".join(text_parts).strip()

    if not text:
        if total_pages == 0:
            raise ValueError("PDF 无任何页面")
        if empty_pages == total_pages:
            raise ValueError(
                f"PDF 共 {total_pages} 页均未提取到文本，"
                "可能是扫描件/图片型 PDF（需 OCR）、或中文字体编码问题、或 PDF 内容为空"
            )

    return text

def _parse_docx(file_path: str) -> str:
    try:
        from docx import Document
    except ImportError as e:
        raise ImportError(f"python-docx 未安装，无法解析 DOCX：{e}。请执行 pip install python-docx")

    doc = Document(file_path)
    text = "\n".join([para.text for para in doc.paragraphs]).strip()
    if not text:
        # 尝试表格内容
        table_text = []
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    if cell.text:
                        table_text.append(cell.text)
        text = "\n".join(table_text).strip()
    return text

def _parse_excel(file_path: str) -> str:
    try:
        import pandas as pd
    except ImportError as e:
        raise ImportError(f"pandas 未安装，无法解析 Excel：{e}。请执行 pip install pandas openpyxl")

    df = pd.read_excel(file_path)
    return df.to_string()