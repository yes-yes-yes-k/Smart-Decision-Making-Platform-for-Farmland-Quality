"""Create the Cd trial table or roll back an empty installation."""

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect, select, text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from framework.config import Config
from framework.models.cd_trial import CdTrial


def migrate(engine, *, drop: bool = False) -> None:
    table = CdTrial.__table__
    with engine.begin() as connection:
        if not drop:
            table.create(connection, checkfirst=True)
            return
        if not inspect(connection).has_table(table.name):
            return
        if connection.dialect.name == "postgresql":
            connection.execute(text("LOCK TABLE cd_conversation_trial IN ACCESS EXCLUSIVE MODE"))
        if connection.execute(select(table.c.id).limit(1)).first():
            raise RuntimeError("Cd trial table contains records. Preserve them before a database rollback.")
        table.drop(connection)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--drop", action="store_true", help="Roll back the empty Cd trial table")
    args = parser.parse_args()
    migrate(create_engine(Config.SQLALCHEMY_DATABASE_URI), drop=args.drop)
    print("Cd trial migration complete.")
