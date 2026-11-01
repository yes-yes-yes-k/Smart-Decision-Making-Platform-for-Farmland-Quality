"""Read-only audit of stored parcel grades versus the live Model-2 engine."""

from __future__ import annotations

import json
import os
import sys
from collections import Counter
from pathlib import Path

import psycopg2


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
for path in (PROJECT_ROOT, PROJECT_ROOT / "src"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

env_path = PROJECT_ROOT / ".env"
if env_path.exists():
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())

from framework.domain.calculations.grade_calculation import evaluate_land_quality  # noqa: E402
from framework.domain.calculations.region_mapping_service import refresh_region_cache  # noqa: E402
from framework.domain.data.parcel_data_accessor import ParcelDataAccessor  # noqa: E402


def _connection():
    return psycopg2.connect(
        host=os.environ.get("DB_HOST", "localhost"),
        port=int(os.environ.get("DB_PORT", "5432")),
        user=os.environ.get("DB_USER", "postgres"),
        password=os.environ.get("DB_PASSWORD", ""),
        dbname=os.environ.get("DB_NAME", "db_enterprise_qa"),
    )


def audit() -> dict:
    with _connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT parcel_id, area_code, soil_indicators "
            "FROM parcel_info ORDER BY parcel_id"
        )
        rows = cursor.fetchall()

    # Force the service to reload DB mappings in the current process. Missing DB
    # entries still use the complete, source-verified hardcoded mapping table.
    refresh_region_cache()
    accessor = ParcelDataAccessor()
    mismatch_by_area: Counter[str] = Counter()
    mismatch_samples: list[dict] = []
    index_differences: list[float] = []
    evaluable = 0
    grade_mismatches = 0

    for parcel_id, area_code, indicators in rows:
        indicators = indicators or {}
        mapped = accessor._map_indicators_to_inputs(indicators, "model-2")
        if not area_code or any(value is None for value in mapped.values()):
            continue
        evaluable += 1
        computed_index, computed_grade, _memberships = evaluate_land_quality(
            mapped, area_code
        )
        stored_grade = str(indicators.get("quality_grade") or "").removesuffix("等")
        stored_index = indicators.get("composite_index")
        if stored_index is not None:
            index_differences.append(abs(float(stored_index) - computed_index))
        if stored_grade and stored_grade != computed_grade:
            grade_mismatches += 1
            mismatch_by_area[str(area_code)] += 1
            if len(mismatch_samples) < 20:
                mismatch_samples.append({
                    "parcelId": str(parcel_id),
                    "areaCode": str(area_code),
                    "storedGrade": stored_grade,
                    "computedGrade": computed_grade,
                    "storedIndex": stored_index,
                    "computedIndex": round(computed_index, 6),
                })

    return {
        "totalParcels": len(rows),
        "evaluableParcels": evaluable,
        "gradeMismatchCount": grade_mismatches,
        "gradeMismatchPercent": round(grade_mismatches * 100 / evaluable, 2) if evaluable else 0,
        "meanAbsoluteIndexDifference": (
            round(sum(index_differences) / len(index_differences), 6)
            if index_differences else None
        ),
        "maxAbsoluteIndexDifference": (
            round(max(index_differences), 6) if index_differences else None
        ),
        "gradeMismatchesByArea": dict(sorted(mismatch_by_area.items())),
        "samples": mismatch_samples,
    }


if __name__ == "__main__":
    print(json.dumps(audit(), ensure_ascii=False, indent=2))
