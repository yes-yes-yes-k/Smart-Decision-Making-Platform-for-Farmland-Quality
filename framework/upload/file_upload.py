import os
import uuid
import hashlib
from framework.config import Config

ALLOWED_EXTENSIONS = {'txt', 'md', 'pdf', 'caj', 'docx', 'xlsx', 'xls', 'csv', 'dat'}

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
    os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)

    filename = file.filename
    extension = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
    new_filename = f"{uuid.uuid4().hex}.{extension}"
    file_path = os.path.join(Config.UPLOAD_FOLDER, new_filename)

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
