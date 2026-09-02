import json

from datetime import datetime
from .user import db


class Report(db.Model):
    __tablename__ = 'kb_report'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True, comment='报告ID')
    title = db.Column(db.String(255), nullable=False, comment='报告标题')
    report_type = db.Column(db.String(50), nullable=False, comment='报告类型')
    area_code = db.Column(db.String(50), nullable=False, comment='区域代码')
    scope_json = db.Column(db.Text, nullable=True, comment='范围 scope 序列化 JSON: {"type":"parcel"|"region","id":str}')
    content = db.Column(db.Text, nullable=True, comment='报告内容（HTML格式）')
    status = db.Column(db.String(20), default='completed', comment='状态: completed/processing/failed')
    create_by = db.Column(db.Integer, nullable=False, comment='创建者用户ID')
    create_time = db.Column(db.DateTime, default=db.func.current_timestamp(), comment='创建时间')
    update_time = db.Column(db.DateTime, default=db.func.current_timestamp(), onupdate=db.func.current_timestamp(), comment='更新时间')

    @property
    def scope(self):
        """反序列化 scope_json 为 dict，失败返回 None。"""
        if not self.scope_json:
            return None
        try:
            return json.loads(self.scope_json)
        except (TypeError, ValueError):
            return None

    @scope.setter
    def scope(self, value):
        """设置 scope：dict 序列化为 JSON 字符串；同时回填 area_code 维持历史列表查询。"""
        if isinstance(value, dict) and value.get('type') and value.get('id'):
            self.scope_json = json.dumps({'type': str(value['type']), 'id': str(value['id'])}, ensure_ascii=False)
            # region 范围仍写 area_code 维持历史列表查询；parcel 范围留空字符串（满足 NOT NULL 约束）
            self.area_code = str(value['id']) if value['type'] == 'region' else ''
        else:
            self.scope_json = None

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'report_type': self.report_type,
            'area_code': self.area_code,
            'scope': self.scope,
            'content': self.content,
            'status': self.status,
            'create_by': self.create_by,
            'create_time': self.create_time.strftime('%Y-%m-%d %H:%M:%S') if self.create_time else None,
            'update_time': self.update_time.strftime('%Y-%m-%d %H:%M:%S') if self.update_time else None,
        }