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
            'row_count': self.chunk_count,
            'status': self.status,
            'category': self.category,
            'treatment_type': self.treatment_type,
            'file_hash': self.file_hash,
            'create_by': self.create_by,
            'create_time': self.create_time.strftime('%Y-%m-%d %H:%M:%S') if self.create_time else None,
            'update_time': self.update_time.strftime('%Y-%m-%d %H:%M:%S') if self.update_time else None
        }