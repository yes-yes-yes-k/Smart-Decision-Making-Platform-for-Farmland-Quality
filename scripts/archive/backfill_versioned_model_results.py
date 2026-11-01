"""Precompute the shared versioned result layer for Model-1 through Model-6.

Run after deploying the additive schema and before enabling calculated map
colouring.  Existing imported quality fields are not modified.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    env_path = ROOT / ".env"
    if env_path.exists():
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())

from flask import Flask  # noqa: E402
from sqlalchemy import text as sa_text  # noqa: E402
from framework.agents.manager import AgentManager  # noqa: E402
from framework.config import config_map  # noqa: E402
from framework.domain.assessment.versioned_results import (  # noqa: E402
    business_result,
    execute_versioned,
)
from framework.domain.calculations.stability_calculation import calculate_stability  # noqa: E402
from framework.domain.data.parcel_data_accessor import ParcelDataAccessor  # noqa: E402
from framework.models import (  # noqa: E402
    ParcelHistorySnapshot,
    ParcelInfo,
    VersionedModelResult,
    db,
)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--models",
        nargs="+",
        # Model-1 consumes the published Model-2 row, so quality is populated
        # first even when all models are requested.
        default=["model-2", "model-3", "model-4", "model-5", "model-1", "model-6"],
        choices=[f"model-{number}" for number in range(1, 7)],
    )
    parser.add_argument("--parcel-id", action="append", help="只处理指定地块，可重复")
    parser.add_argument("--limit", type=int, help="最多处理的地块数")
    parser.add_argument("--progress-every", type=int, default=100)
    return parser.parse_args()


def _preload_model1_inputs(parcel_ids: list[str]) -> tuple[dict, dict, dict]:
    """Load Model-1 history, Model-2 grades and 1 km neighbours in bulk."""
    history_by_parcel: dict[str, list[dict]] = {}
    for row in ParcelHistorySnapshot.query.order_by(
        ParcelHistorySnapshot.parcel_id,
        ParcelHistorySnapshot.survey_year,
    ).all():
        history_by_parcel.setdefault(str(row.parcel_id), []).append({
            "survey_year": row.survey_year,
            "soil_indicators": row.soil_indicators,
            "quality_grade": row.quality_grade,
            "composite_index": row.composite_index,
        })

    grade_rows = VersionedModelResult.query.filter_by(
        agent_id="model-2", subject_type="parcel", is_current=True,
    ).all()
    grades_by_parcel = {
        str(row.subject_id): business_result(row)
        for row in grade_rows
    }

    # The former implementation issued one query per parcel; a single global
    # join can create an oversized intermediate set.  Fixed-size source batches
    # preserve the exact predicate while bounding query memory.
    neighbours_by_parcel = {parcel_id: [] for parcel_id in parcel_ids}
    neighbour_sql = sa_text("""
        SELECT source.parcel_id,
               ARRAY_REMOVE(
                   ARRAY_AGG(result.result_payload -> 'result' ->> 'quality_grade'),
                   NULL
               ) AS neighbour_grades
        FROM parcel_info AS source
        LEFT JOIN parcel_info AS neighbour
          ON neighbour.parcel_id <> source.parcel_id
         AND source.geom IS NOT NULL
         AND neighbour.geom IS NOT NULL
         AND neighbour.geom && ST_Expand(source.geom, 0.02)
         AND ST_DWithin(source.geom::geography, neighbour.geom::geography, 1000)
        LEFT JOIN versioned_model_result AS result
          ON result.agent_id = 'model-2'
         AND result.subject_type = 'parcel'
         AND result.subject_id = neighbour.parcel_id
         AND result.is_current = TRUE
        WHERE source.parcel_id = ANY(:source_ids)
        GROUP BY source.parcel_id
    """)
    batch_size = 100
    for offset in range(0, len(parcel_ids), batch_size):
        source_ids = parcel_ids[offset:offset + batch_size]
        rows = db.session.execute(
            neighbour_sql, {"source_ids": source_ids}
        ).mappings().all()
        for row in rows:
            neighbours_by_parcel[str(row["parcel_id"])] = [
                {"quality_grade": grade}
                for grade in (row["neighbour_grades"] or [])
            ]
        completed = min(offset + batch_size, len(parcel_ids))
        if completed % 500 == 0 or completed == len(parcel_ids):
            print(f"model-1 neighbour preload={completed}/{len(parcel_ids)}", flush=True)
    return history_by_parcel, grades_by_parcel, neighbours_by_parcel


def _backfill_model1_optimized(
    manager: AgentManager,
    parcels: list[tuple[str, str | None, dict]],
    progress_every: int,
) -> dict[str, int]:
    history, grades, neighbours = _preload_model1_inputs(
        [parcel_id for parcel_id, _area_code, _indicators in parcels]
    )
    accessor = ParcelDataAccessor()
    agent = manager.agents["model-1"]
    counters = {"ok": 0, "failed": 0, "cache": 0}

    for index, (parcel_id, area_code, indicators) in enumerate(parcels, start=1):
        try:
            quality = grades.get(str(parcel_id)) or {}
            if quality.get("quality_grade") is None or quality.get("composite_index") is None:
                raise RuntimeError("Model-2 版本化质量结果未就绪")
            mapped = accessor._map_indicators_to_inputs(indicators or {}, "model-1")
            stability = calculate_stability(
                {
                    "indicators": mapped,
                    "quality_index": quality["composite_index"],
                    "quality_grade": quality["quality_grade"],
                    "area_code": area_code or "440281",
                },
                history.get(str(parcel_id), []),
                neighbours.get(str(parcel_id), []),
            )
            outputs = {"parcel_id": str(parcel_id), "stability_modules": stability}
            persisted = agent._persist_result(
                agent_id="model-1",
                parcel_id=str(parcel_id),
                inputs={**(indicators or {}), "parcel_id": str(parcel_id), "area_code": area_code, "data_source": "db"},
                outputs=outputs,
                status="ok",
            )
            execution = execute_versioned(
                agent,
                {"parcel_id": str(parcel_id), "area_code": area_code},
                lambda: {
                    "status": "ok",
                    "simulated": False,
                    "result": outputs,
                    "data_source": "db",
                    "persisted": persisted,
                },
            )
            counters["ok"] += 1
            if (execution.get("versioned_result") or {}).get("cacheHit"):
                counters["cache"] += 1
        except Exception as exc:
            counters["failed"] += 1
            print(f"FAILED model=model-1 parcel={parcel_id}: {exc}", flush=True)
        if index % max(progress_every, 1) == 0:
            print(f"processed={index} counters={{'model-1': {counters}}}", flush=True)
    return counters


def main() -> int:
    args = _arguments()
    app = Flask(__name__)
    app.config.from_object(config_map[os.getenv("FLASK_CONFIG", "default")])
    db.init_app(app)
    manager = AgentManager()
    counters = {model: {"ok": 0, "failed": 0, "cache": 0} for model in args.models}

    with app.app_context():
        VersionedModelResult.__table__.create(bind=db.engine, checkfirst=True)
        if db.engine.dialect.name == "postgresql":
            db.session.execute(sa_text(
                "ALTER TABLE model_execution_log "
                "ALTER COLUMN model_version TYPE VARCHAR(128)"
            ))
            db.session.execute(sa_text(
                "CREATE INDEX IF NOT EXISTS idx_parcel_info_geom_geography "
                "ON parcel_info USING GIST ((geom::geography)) "
                "WHERE geom IS NOT NULL"
            ))
            db.session.execute(sa_text(
                "CREATE UNIQUE INDEX IF NOT EXISTS "
                "uk_versioned_model_result_one_current "
                "ON versioned_model_result (agent_id, subject_type, subject_id) "
                "WHERE is_current = TRUE"
            ))
            db.session.commit()
        query = ParcelInfo.query.order_by(ParcelInfo.parcel_id)
        if args.parcel_id:
            query = query.filter(ParcelInfo.parcel_id.in_(args.parcel_id))
        if args.limit:
            query = query.limit(args.limit)

        # Materialise only identifiers before model executions commit.  A
        # server-side ``yield_per`` cursor is invalidated by those commits on
        # PostgreSQL.
        parcel_rows = query.with_entities(
            ParcelInfo.parcel_id,
            ParcelInfo.area_code,
            ParcelInfo.soil_indicators,
        ).all()
        if args.models == ["model-1"]:
            counters["model-1"] = _backfill_model1_optimized(
                manager,
                [(str(pid), area, indicators or {}) for pid, area, indicators in parcel_rows],
                args.progress_every,
            )
        else:
            for index, (parcel_id, area_code, _indicators) in enumerate(parcel_rows, start=1):
                payload = {"parcel_id": parcel_id, "area_code": area_code}
                for model in args.models:
                    try:
                        execution = manager.agents[model].execute(payload)
                        status = str(execution.get("status") or "error")
                        if status in {"ok", "success", "rejected"}:
                            counters[model]["ok"] += 1
                        else:
                            counters[model]["failed"] += 1
                        if (execution.get("versioned_result") or {}).get("cacheHit"):
                            counters[model]["cache"] += 1
                    except Exception as exc:  # continue batch; report exact parcel
                        counters[model]["failed"] += 1
                        print(f"FAILED model={model} parcel={parcel_id}: {exc}")
                if index % max(args.progress_every, 1) == 0:
                    print(f"processed={index} counters={counters}")

        publication_audit = {}
        for model in args.models:
            current_count = VersionedModelResult.query.filter_by(
                agent_id=model, subject_type="parcel", is_current=True,
            ).count()
            duplicate_current = (
                db.session.query(VersionedModelResult.subject_id)
                .filter_by(agent_id=model, subject_type="parcel", is_current=True)
                .group_by(VersionedModelResult.subject_id)
                .having(db.func.count(VersionedModelResult.id) > 1)
                .count()
            )
            publication_audit[model] = {
                "currentParcelRows": current_count,
                "duplicateCurrentParcels": duplicate_current,
            }

    print(f"completed counters={counters} publication_audit={publication_audit}")
    return 0 if all(value["failed"] == 0 for value in counters.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
