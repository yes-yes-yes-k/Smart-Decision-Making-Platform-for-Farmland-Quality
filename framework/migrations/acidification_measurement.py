"""Idempotent schema upgrade for per-conversation acidification records."""

from sqlalchemy import inspect

from framework.models import AcidificationMeasurement


def ensure_acidification_measurement_table(connection):
    table = AcidificationMeasurement.__table__
    inspector = inspect(connection)
    # 全新库上 init_db.py 先 create_app 再 create_all，父表可能还没建；
    # 此时建表会因外键指向不存在的表报 UndefinedTable，留给 create_all 统一处理。
    parents = {fk.target_fullname.split(".", 1)[0] for fk in table.foreign_keys}
    if any(not inspector.has_table(name) for name in parents):
        return
    table.create(connection, checkfirst=True)
    existing_indexes = {
        item["name"] for item in inspector.get_indexes(table.name)
    }
    for index in table.indexes:
        if index.name not in existing_indexes:
            index.create(connection, checkfirst=True)
