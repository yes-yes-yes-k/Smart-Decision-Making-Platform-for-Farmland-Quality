from __future__ import annotations
import os
from typing import Optional

from framework.upload.text_cleaner import clean_text

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
        return clean_text(f.read())

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
                return clean_text(text)
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
            print(f"[Parser] PDF 共 {total_pages} 页均未提取到文本，触发 OCR 识别", flush=True)
            try:
                ocr_text = _parse_pdf_ocr(file_path)
                if ocr_text:
                    return clean_text(ocr_text)
            except Exception as e:
                print(f"[Parser] OCR 识别失败：{e}", flush=True)
                raise ValueError(
                    f"PDF 共 {total_pages} 页均未提取到文本，且 OCR 识别失败。"
                    f"可能是中文字体编码问题、或 PDF 内容为空。OCR 错误：{e}"
                )

    return clean_text(text)


def _parse_pdf_ocr(file_path: str) -> str:
    """使用 OCR 识别扫描件/图片型 PDF 中的文字。"""
    print(f"[Parser] 开始 OCR 识别：{file_path}", flush=True)

    try:
        from pdf2image import convert_from_path
    except ImportError as e:
        raise ImportError(
            f"pdf2image 未安装，无法进行 OCR 识别。"
            f"请执行: pip install pdf2image  错误: {e}"
        )

    try:
        import pytesseract
    except ImportError as e:
        raise ImportError(
            f"pytesseract 未安装，无法进行 OCR 识别。"
            f"请执行: pip install pytesseract  错误: {e}"
        )

    # 探测 Tesseract 可执行文件
    try:
        pytesseract.get_tesseract_version()
    except Exception as e:
        raise RuntimeError(
            f"未找到 Tesseract OCR 引擎。"
            f"请先安装 Tesseract：https://github.com/tesseract-ocr/tesseract  错误: {e}"
        )

    try:
        from PIL import Image
    except ImportError as e:
        raise ImportError(
            f"Pillow 未安装，无法进行 OCR 识别。"
            f"请执行: pip install Pillow  错误: {e}"
        )

    # 将 PDF 转为图片
    print("[Parser] 正在将 PDF 转换为图片...", flush=True)
    try:
        images = convert_from_path(file_path)
    except Exception as e:
        raise RuntimeError(f"PDF 转图片失败（可能需要安装 poppler）：{e}")

    total_pages = len(images)
    print(f"[Parser] PDF 共 {total_pages} 页，开始 OCR 识别...", flush=True)

    text_parts = []
    for i, image in enumerate(images):
        try:
            print(f"[Parser] OCR 识别第 {i+1}/{total_pages} 页...", flush=True)
            page_text = pytesseract.image_to_string(image, lang='chi_sim+eng')
            text_parts.append(page_text.strip())
        except Exception as e:
            print(f"[Parser] OCR 第 {i+1}/{total_pages} 页识别失败：{e}", flush=True)
            text_parts.append("")

    text = "\n".join(text_parts).strip()
    print(f"[Parser] OCR 识别完成，提取到 {len(text)} 个字符", flush=True)
    return clean_text(text)

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
    return clean_text(text)

def _parse_excel(file_path: str) -> str:
    try:
        import pandas as pd
    except ImportError as e:
        raise ImportError(f"pandas 未安装，无法解析 Excel：{e}。请执行 pip install pandas openpyxl")

    df = pd.read_excel(file_path)
    return clean_text(df.to_string())