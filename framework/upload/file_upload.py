import os
import uuid
import hashlib
from flask import current_app, has_app_context
from framework.config import Config

ALLOWED_EXTENSIONS = {'txt', 'md', 'pdf', 'caj', 'docx', 'xlsx', 'xls', 'csv', 'dat'}


class UploadValidationError(ValueError):
    def __init__(self, error_code: str, message: str, status_code: int = 422):
        super().__init__(message)
        self.error_code = error_code
        self.status_code = status_code

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

def save_uploaded_file(file) -> tuple[str, str, str]:
    upload_folder = (
        current_app.config.get('UPLOAD_FOLDER', Config.UPLOAD_FOLDER)
        if has_app_context() else Config.UPLOAD_FOLDER
    )
    os.makedirs(upload_folder, exist_ok=True)

    filename = file.filename
    extension = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
    new_filename = f"{uuid.uuid4().hex}.{extension}"
    file_path = os.path.join(upload_folder, new_filename)

    file.save(file_path)
    file_hash = compute_file_hash(file_path)

    return new_filename, file_path, file_hash

def get_file_type(filename: str) -> str:
    extension = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
    type_map = {
        'txt': 'txt',
        'md': 'md',
        'pdf': 'pdf',
        'caj': 'caj',
        'docx': 'docx',
        'xlsx': 'xlsx',
        'xls': 'xlsx',
        'csv': 'csv',
        'dat': 'dat',
    }
    return type_map.get(extension, 'other')


def validate_file_content(file_path: str, file_type: str) -> None:
    """Validate lightweight file signatures before creating an ingestion task."""
    with open(file_path, 'rb') as stream:
        header = stream.read(16)

    if file_type == 'pdf' and not header.startswith(b'%PDF-'):
        raise UploadValidationError(
            'content_type_mismatch', '文件扩展名为 PDF，但内容不是有效 PDF'
        )
    if file_type == 'caj' and not header.startswith(
        (b'%PDF-', b'CAJ', b'HN\x00', b'KDH ', b'C8')
    ):
        raise UploadValidationError(
            'content_type_mismatch', '文件扩展名为 CAJ，但内容签名不受支持'
        )
    if file_type in {'docx', 'xlsx'} and not header.startswith(b'PK'):
        raise UploadValidationError(
            'content_type_mismatch', 'Office 文件扩展名与内容签名不匹配'
        )

    if file_type == 'pdf':
        try:
            import pdfplumber
            with pdfplumber.open(file_path) as pdf:
                len(pdf.pages)
        except UploadValidationError:
            raise
        except Exception as exc:
            detail = str(exc).lower()
            if 'password' in detail or 'encrypt' in detail:
                raise UploadValidationError(
                    'encrypted_document', '暂不支持需要密码的 PDF'
                ) from exc
            # Some otherwise readable PDFs have a damaged xref/catalog that
            # pdfminer rejects.  PyMuPDF can safely repair these into a
            # temporary derivative during parsing, so accept only when it can
            # open every page without a password.
            try:
                import fitz
                with fitz.open(file_path) as document:
                    if document.needs_pass or len(document) == 0:
                        raise ValueError('PDF requires a password or has no pages')
                    for page in document:
                        page.get_text()
            except Exception as repair_exc:
                raise UploadValidationError(
                    'content_type_mismatch', 'PDF 结构校验失败'
                ) from repair_exc
