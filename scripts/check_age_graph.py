"""Check the configured dedicated Apache AGE instance without exposing its URI."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

def main():
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[1] / '.env')
    from framework.config import Config
    from sqlalchemy import create_engine
    from framework.knowledge_graph.stores import AgeGraphStore, SqlAlchemyAgeExecutor
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dsn', default=None, help='Optional override; prefer KG_AGE_DATABASE_URI')
    args = parser.parse_args()
    uri = args.dsn or Config.KG_AGE_DATABASE_URI or Config.SQLALCHEMY_DATABASE_URI
    engine = create_engine(uri, pool_pre_ping=True)
    try:
        health = dict(AgeGraphStore(SqlAlchemyAgeExecutor(engine), graph_name=Config.KG_AGE_GRAPH_NAME).health())
        print(json.dumps(health, ensure_ascii=False, indent=2))
        return 0 if health.get('ready') else 1
    except Exception as exc:
        print(json.dumps({'ready': False, 'failure': type(exc).__name__}))
        return 1
    finally:
        engine.dispose()

if __name__ == '__main__':
    raise SystemExit(main())
