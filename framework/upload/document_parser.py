from __future__ import annotations
import os
from typing import Optional

def parse_document(file_path: str, file_type: str) -> Optional[str]:
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
    elif file_type == 'csv':
        return _parse_csv(file_path)
    elif file_type == 'dat':
        return _parse_dat(file_path)
    else:
        return None

def _parse_txt(file_path: str) -> str:
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        return f.read()

def _parse_pdf(file_path: str) -> str:
    try:
        from PyPDF2 import PdfReader
        reader = PdfReader(file_path)
        text = ""
        for page in reader.pages:
            text += page.extract_text() + "\n"
        return text
    except Exception:
        return ""

def _parse_docx(file_path: str) -> str:
    try:
        from docx import Document
        doc = Document(file_path)
        return "\n".join([para.text for para in doc.paragraphs])
    except Exception:
        return ""

def _parse_excel(file_path: str) -> str:
    try:
        import pandas as pd
        df = pd.read_excel(file_path)
        return df.to_string()
    except Exception:
        return ""

def _parse_csv(file_path: str) -> str:
    try:
        import pandas as pd
        df = pd.read_csv(file_path)
        return df.to_string()
    except Exception:
        return ""

def _parse_dat(file_path: str) -> str:
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            return f.read()
    except Exception:
        return ""