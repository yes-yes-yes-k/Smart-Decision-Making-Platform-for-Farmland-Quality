from datetime import datetime
from .user import db

class Message(db.Model):
    __tablename__ = 'kb_message'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True, comment='消息ID')
    conversation_id = db.Column(db.Integer, db.ForeignKey('kb_conversation.id'), nullable=False, comment='所属对话ID')
    role = db.Column(db.String(20), nullable=False, comment='消息角色: user/assistant')
    content = db.Column(db.Text, nullable=False, comment='消息内容')
    sources = db.Column(db.JSON, default=None, comment='AI回答的引用来源')
    create_time = db.Column(db.DateTime, default=db.func.current_timestamp(), comment='发送时间')

    def to_dict(self):
        return {
            'id': self.id,
            'conversation_id': self.conversation_id,
            'role': self.role,
            'content': self.content,
            'sources': self.sources,
            'create_time': self.create_time.strftime('%Y-%m-%d %H:%M:%S') if self.create_time else None
        }