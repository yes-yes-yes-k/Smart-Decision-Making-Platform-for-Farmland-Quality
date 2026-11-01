from pathlib import Path

import geopandas as gpd
import pytest
from shapely.geometry import Polygon

from scripts import import_lechang_boundaries as boundaries


def test_scope_where_selects_parents_and_descendants():
    assert boundaries._scope_where("PXZQDM", 2, "440281") == "PXZQDM = '44'"
    assert boundaries._scope_where("CXZQDM", 4, "440281") == "CXZQDM = '4402'"
    assert boundaries._scope_where("FXZQDM", 6, "440281") == "FXZQDM = '440281'"
    assert boundaries._scope_where("TXZQDM", 9, "440281") == "TXZQDM LIKE '440281%'"


def test_best_boundary_name_ignores_enclave_suffix():
    assert boundaries._best_boundary_name(["三水区飞地", "三水区"]) == "三水区"


def test_invalid_geometry_requires_explicit_repair(tmp_path, monkeypatch):
    source = tmp_path / "boundary.shp"
    source.touch()
    bow_tie = Polygon([(0, 0), (1, 1), (1, 0), (0, 1), (0, 0)])
    frame = gpd.GeoDataFrame(
        {"OBJECTID": [7], "XZQDM": ["440281001001"], "geometry": [bow_tie]},
        crs="EPSG:4490",
    )
    monkeypatch.setattr(boundaries.gpd, "read_file", lambda *args, **kwargs: frame.copy())

    with pytest.raises(RuntimeError, match=r"OBJECTID=\[7\]"):
        boundaries._read_scoped_level(
            Path(tmp_path), source.name, "XZQDM", 12, "440281",
        )

    repaired = boundaries._read_scoped_level(
        Path(tmp_path), source.name, "XZQDM", 12, "440281", repair_invalid=True,
    )
    assert repaired.geometry.is_valid.all()
    assert repaired.attrs["repaired_invalid_count"] == 1


def test_missing_direct_admin_parents_are_synthesized():
    polygon = Polygon([(0, 0), (1, 0), (1, 1), (0, 0)])
    records = [
        boundaries._record("province", "44", "广东省", "44", None, polygon, {}),
        boundaries._record("city", "4413", "惠州市", "4413", ("province", "44"), polygon, {}),
        boundaries._record(
            "village",
            "441300000001",
            "示例直属区域",
            "441300000001",
            ("township", "441300000"),
            polygon,
            {"sourceCountyName": "惠州市", "sourceParentName": "惠州市直属区域"},
        ),
    ]

    counts = boundaries._add_synthetic_region_parents(records)

    assert counts == {"county": 1, "township": 1}
    synthetic = {(item["object_type"], item["object_id"]): item for item in records}
    assert synthetic[("county", "441300")]["parent_id"] == "4413"
    assert synthetic[("township", "441300000")]["parent_id"] == "441300"
    assert synthetic[("county", "441300")]["metadata"]["selectable"] is False
