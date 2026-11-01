from .user import db

class Document(db.Model):
    __tablename__ = 'kb_document'
    __table_args__ = (
        db.UniqueConstraint(
            'create_by', 'idempotency_key',
            name='uq_kb_document_owner_idempotency',
        ),
    )

    # 入库生命周期状态：现有 status=1 数据语义不变（表"已完成"），无需迁移
    STATUS_PENDING = 0      # 待处理（新上传，worker 未启动）
    STATUS_COMPLETED = 1    # 已完成（保留现有语义）
    STATUS_PROCESSING = 2   # 处理中（worker 已开始解析/切分/向量化）
    STATUS_FAILED = 3       # 失败（worker 抛异常）
    STATUS_REJECTED = 4     # 管理员审核驳回

    REVIEW_PENDING = 'pending'
    REVIEW_APPROVED = 'approved'
    REVIEW_REJECTED = 'rejected'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True, comment='文档ID')
    doc_name = db.Column(db.String(255), nullable=False, comment='文档原始文件名')
    file_path = db.Column(db.String(500), nullable=False, comment='文件存储相对路径')
    file_type = db.Column(db.String(20), nullable=False, comment='文件类型')
    file_size = db.Column(db.BigInteger, default=0, comment='文件大小(字节)')
    chunk_count = db.Column(db.Integer, default=0, comment='文本分割后的片段数量')
    status = db.Column(db.SmallInteger, default=1, comment='状态')
    category = db.Column(db.String(30), default='other', comment='文档分类')
    treatment_type = db.Column(db.String(30), nullable=True, comment='治理类型')
    doc_type = db.Column(db.String(30), default='other', comment='展示分类: regulation-规范标准, scheme-方案, report-报告, academic_paper-学术论文, other-其他 (前端列表按此展示; category 保留耕地质量语义)')
    visibility_scope = db.Column(
        db.String(20), nullable=False, default='private', comment='可见范围: public/private'
    )
    file_hash = db.Column(db.String(64), nullable=True, comment='文件内容SHA-256哈希')
    idempotency_key = db.Column(db.String(128), nullable=True, comment='用户范围幂等键')
    document_kind = db.Column(db.String(40), nullable=False, default='other', comment='文献类型')
    title = db.Column(db.String(500), nullable=True, comment='文献标题')
    language = db.Column(db.String(40), nullable=True, comment='文献语言')
    doi_normalized = db.Column(db.String(300), nullable=True, index=True, comment='规范化DOI')
    standard_number_normalized = db.Column(db.String(200), nullable=True, index=True, comment='规范化标准号')
    issuing_authority = db.Column(db.String(300), nullable=True, comment='发布机构')
    authority_status = db.Column(db.String(30), nullable=False, default='unverified', comment='权威状态')
    bibliographic_metadata = db.Column(db.JSON, nullable=True, comment='书目扩展元数据')
    provenance_metadata = db.Column(db.JSON, nullable=True, comment='来源与许可溯源')
    parse_metadata = db.Column(db.JSON, nullable=True, comment='解析/OCR/转换质量元数据')
    processing_stage = db.Column(db.String(40), nullable=True, index=True, comment='可读处理阶段')
    failure_code = db.Column(db.String(80), nullable=True, comment='稳定失败码')
    failure_message = db.Column(db.String(1000), nullable=True, comment='脱敏失败信息')
    retryable = db.Column(db.Boolean, nullable=False, default=False, comment='是否允许重试')
    review_status = db.Column(db.String(20), nullable=False, default=REVIEW_APPROVED, index=True)
    reviewed_by = db.Column(db.Integer, nullable=True, comment='审核人')
    reviewed_at = db.Column(db.DateTime, nullable=True, comment='审核时间')
    review_note = db.Column(db.String(1000), nullable=True, comment='审核意见')
    review_idempotency_key = db.Column(db.String(128), nullable=True, comment='审核幂等键')
    create_by = db.Column(db.Integer, nullable=False, comment='上传者用户ID')
    create_time = db.Column(db.DateTime, default=db.func.current_timestamp(), comment='上传时间')
    update_time = db.Column(db.DateTime, default=db.func.current_timestamp(), onupdate=db.func.current_timestamp(), comment='更新时间')

    labels = db.relationship(
        'DocumentLabel', backref='document', lazy='select',
        cascade='all, delete-orphan', passive_deletes=True,
    )

    def to_dict(self, include_pending: bool = True):
        approved = sorted(
            label.label_code for label in self.labels
            if label.review_status == 'approved'
        )
        data = {
            'id': self.id,
            'doc_name': self.doc_name,
            'file_type': self.file_type,
            'file_size': self.file_size,
            'chunk_count': self.chunk_count,
            'row_count': self.chunk_count,
            'status': self.status,
            'category': self.category,
            'treatment_type': self.treatment_type,
            'visibility_scope': self.visibility_scope,
            'doc_type': self.doc_type,
            'document_kind': self.document_kind,
            'title': self.title,
            'language': self.language,
            'doi': self.doi_normalized,
            'standard_number': self.standard_number_normalized,
            'issuing_authority': self.issuing_authority,
            'authority_status': self.authority_status,
            'bibliographic_metadata': self.bibliographic_metadata or {},
            'provenance_metadata': self.provenance_metadata or {},
            'parse_metadata': self.parse_metadata or {},
            'processing_stage': self.processing_stage,
            'failure_code': self.failure_code,
            'failure_message': self.failure_message,
            'retryable': bool(self.retryable),
            'review_status': self.review_status,
            'reviewed_by': self.reviewed_by,
            'reviewed_at': self.reviewed_at.strftime('%Y-%m-%d %H:%M:%S') if self.reviewed_at else None,
            'review_note': self.review_note,
            'domain_labels': [label for label in approved if '.' not in label],
            'topic_labels': [label for label in approved if '.' in label],
            'file_hash': self.file_hash,
            'create_by': self.create_by,
            'create_time': self.create_time.strftime('%Y-%m-%d %H:%M:%S') if self.create_time else None,
            'update_time': self.update_time.strftime('%Y-%m-%d %H:%M:%S') if self.update_time else None
        }
        if include_pending:
            data['pending_labels'] = [
                label.to_dict() for label in self.labels
                if label.review_status == 'pending'
            ]
        return data
