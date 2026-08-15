from datetime import datetime
from .user import db


class Report(db.Model):
    __tablename__ = 'kb_report'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True, comment='报告ID')
    title = db.Column(db.String(255), nullable=False, comment='报告标题')
    report_type = db.Column(db.String(50), nullable=False, comment='报告类型')
    area_code = db.Column(db.String(50), nullable=False, comment='区域代码')
    content = db.Column(db.Text, nullable=True, comment='报告内容（HTML格式）')
    status = db.Column(db.String(20), default='completed', comment='状态: completed/processing/failed')
    create_by = db.Column(db.Integer, nullable=False, comment='创建者用户ID')
    create_time = db.Column(db.DateTime, default=db.func.current_timestamp(), comment='创建时间')
    update_time = db.Column(db.DateTime, default=db.func.current_timestamp(), onupdate=db.func.current_timestamp(), comment='更新时间')

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'report_type': self.report_type,
            'area_code': self.area_code,
            'content': self.content,
            'status': self.status,
            'create_by': self.create_by,
            'create_time': self.create_time.strftime('%Y-%m-%d %H:%M:%S') if self.create_time else None,
            'update_time': self.update_time.strftime('%Y-%m-%d %H:%M:%S') if self.update_time else None,
        }