"""测试 Document 状态枚举常量。"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from framework.models.document import Document


def test_status_constants():
    assert Document.STATUS_PENDING == 0
    assert Document.STATUS_COMPLETED == 1
    assert Document.STATUS_PROCESSING == 2
    assert Document.STATUS_FAILED == 3
    assert Document.STATUS_REJECTED == 4


def test_status_default_preserved():
    # 默认值仍为 1（completed），现有数据语义不变
    col = Document.__table__.c.status
    assert col.default.arg == 1
