"""Idempotent schema upgrade for per-conversation acidification records."""

from sqlalchemy import inspect

from framework.models import AcidificationMeasurement


def ensure_acidification_measurement_table(connection):
    table = AcidificationMeasurement.__table__
    table.create(connection, checkfirst=True)
    existing_indexes = {
        item["name"] for item in inspect(connection).get_indexes(table.name)
    }
    for index in table.indexes:
        if index.name not in existing_indexes:
            index.create(connection, checkfirst=True)
