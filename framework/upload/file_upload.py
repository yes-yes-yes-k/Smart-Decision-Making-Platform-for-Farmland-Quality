import os
import uuid
from framework.config import Config

ALLOWED_EXTENSIONS = {'txt', 'md', 'pdf', 'docx', 'xlsx', 'xls'}

def allowed_file(filename: str) -> bool:
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

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