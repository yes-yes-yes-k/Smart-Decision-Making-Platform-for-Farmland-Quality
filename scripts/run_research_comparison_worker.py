"""Finite, restartable M1 comparison consumer; no model calls or migrations."""
import argparse
import json
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
import sqlalchemy as sa
from framework.knowledge_graph.research_service import ResearchService
from framework.knowledge_graph.research_store import ResearchStore
from framework.knowledge_graph.research_sources import PublishedResearchSources


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--max-jobs", type=int, default=1)
    args = parser.parse_args()
    allowed = (REPO/"artifacts/knowledge_platform/evidence-m1-v1/runtime").resolve()
    path = args.database.resolve()
    if allowed not in path.parents or not path.is_file() or not 1 <= args.max_jobs <= 20:
        raise ValueError("explicit_M1_database_and_one_to_twenty_jobs_required")
    from dotenv import load_dotenv
    load_dotenv(REPO/".env")
    from framework.config import Config
    engine = sa.create_engine(sa.URL.create("sqlite", database=str(path)))
    store = ResearchStore(engine); store.require_schema()
    source = PublishedResearchSources(Config.SQLALCHEMY_DATABASE_URI, Config.UPLOAD_FOLDER)
    try:
        service = ResearchService(store, source)
        for _ in range(args.max_jobs):
            result = service.run_once()
            print(json.dumps(result), flush=True)
            if result["state"] == "idle":
                break
    finally:
        source.close(); engine.dispose()


if __name__ == "__main__":
    main()
