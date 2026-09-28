import sqlalchemy as sa
import pytest

from scripts.precompute_farmland_region_parcels import (
    _region_type_clause,
    ensure_schema,
)


def test_precompute_schema_creation_is_idempotent(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'precompute.db'}")

    ensure_schema(engine)
    ensure_schema(engine)

    inspector = sa.inspect(engine)
    assert inspector.has_table("farmland_region_parcel_area")
    assert inspector.has_table("farmland_region_precompute_state")
    assert {
        "region_type", "region_id", "parcel_id", "area_mu", "computed_at",
    } == {
        column["name"]
        for column in inspector.get_columns("farmland_region_parcel_area")
    }
    assert "idx_farmland_region_parcel_area_parcel" in {
        index["name"]
        for index in inspector.get_indexes("farmland_region_parcel_area")
    }


def test_region_type_clause_rejects_empty_or_unknown_types():
    with pytest.raises(ValueError, match="at least one"):
        _region_type_clause(())
    with pytest.raises(ValueError, match="unsupported"):
        _region_type_clause(("district",))


def test_region_type_clause_uses_bound_parameters():
    clause, params = _region_type_clause(("county", "village"))

    assert clause == ":region_type_0, :region_type_1"
    assert params == {"region_type_0": "county", "region_type_1": "village"}
