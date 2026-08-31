"""Seed authoritative county objects from enabled area-code mappings."""
from __future__ import annotations

import argparse
from collections.abc import Sequence

from framework.models import AreaCodeRegionMap, SpatialRegionCatalog, db


def seed_spatial_region_catalog() -> dict[str, int]:
    counts = {"inserted": 0, "updated": 0, "skipped": 0}
    rows = AreaCodeRegionMap.query.filter_by(enabled=True).all()
    for row in rows:
        existing = SpatialRegionCatalog.query.filter_by(
            object_type="county", object_id=row.area_code
        ).one_or_none()
        values = {
            "display_name": row.region_name or row.area_code,
            "area_code": row.area_code,
            "source": "area_code_region_map",
            "enabled": True,
        }
        if existing is None:
            db.session.add(SpatialRegionCatalog(
                object_type="county", object_id=row.area_code, **values
            ))
            counts["inserted"] += 1
        elif any(getattr(existing, key) != value for key, value in values.items()):
            for key, value in values.items():
                setattr(existing, key, value)
            counts["updated"] += 1
        else:
            counts["skipped"] += 1
    db.session.commit()
    return counts


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="default")
    args = parser.parse_args(argv)
    from framework.api.app import create_app
    app = create_app(args.config)
    with app.app_context():
        print(seed_spatial_region_catalog())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
