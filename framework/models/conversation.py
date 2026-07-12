from datetime import datetime
from .user import db

class Conversation(db.Model):
    __tablename__ = 'kb_conversation'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True, comment='对话ID')
    user_id = db.Column(db.Integer, nullable=False, comment='创建者用户ID')
    title = db.Column(db.String(255), default='新对话', comment='对话标题')
    create_time = db.Column(db.DateTime, default=db.func.current_timestamp(), comment='创建时间')
    update_time = db.Column(db.DateTime, default=db.func.current_timestamp(), onupdate=db.func.current_timestamp(), comment='更新时间')

    messages = db.relationship(
        'Message',
        backref='conversation',
        lazy=True,
        cascade='all, delete-orphan',
        order_by='Message.create_time'
    )

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'title': self.title,
            'create_time': self.create_time.strftime('%Y-%m-%d %H:%M:%S') if self.create_time else None,
            'update_time': self.update_time.strftime('%Y-%m-%d %H:%M:%S') if self.update_time else None
        }