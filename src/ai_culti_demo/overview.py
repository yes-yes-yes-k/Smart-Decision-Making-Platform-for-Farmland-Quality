from __future__ import annotations

from typing import Any

from .catalog import get_asset, load_catalog


BASE_LAYER_ASSETS = {
    "boundary": ["lechang-county-boundary", "lechang-town-boundary"],
    "cropland": ["guangdong-cropland-mask"],
    "soil_points": [
        "third-survey-topsoil-points",
        "second-survey-points",
        "formula-fertilization-points",
    ],
}


def _source_for_assets(catalog: dict[str, Any], asset_ids: list[str]) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    for asset_id in asset_ids:
        asset = get_asset(catalog, asset_id)
        if not asset:
            continue
        sources.append(
            {
                "asset_id": asset["asset_id"],
                "name": asset["name"],
                "type": asset["type"],
                "path": asset["path"],
                "source_kind": asset["source_kind"],
            }
        )
    return sources


def get_county_overview(area_code: str = "lechang") -> dict[str, Any]:
    """返回未来 Agent 和前端都可直接消费的县域总览结构。"""

    catalog = load_catalog()
    if area_code != catalog["area"]["code"]:
        return {
            "status": "error",
            "error": {
                "code": "UNSUPPORTED_AREA",
                "message": f"当前基础能力仅支持 {catalog['area']['name']}",
            },
        }

    layers = [
        {
            "id": "boundary",
            "name": "行政边界",
            "kind": "base",
            "display_order": 10,
            "source": _source_for_assets(catalog, BASE_LAYER_ASSETS["boundary"]),
        },
        {
            "id": "cropland",
            "name": "耕地范围",
            "kind": "base",
            "display_order": 20,
            "source": _source_for_assets(catalog, BASE_LAYER_ASSETS["cropland"]),
        },
        {
            "id": "soil_points",
            "name": "土壤样点",
            "kind": "base",
            "display_order": 30,
            "source": _source_for_assets(catalog, BASE_LAYER_ASSETS["soil_points"]),
        },
    ]

    for layer in catalog.get("derived_layers", []):
        layers.append(
            {
                "id": layer["layer_id"],
                "name": layer["name"],
                "kind": "derived",
                "display_order": 100 + len(layers),
                "status": layer["status"],
                "source": _source_for_assets(catalog, layer["source_assets"]),
                "notes": layer["notes"],
            }
        )

    return {
        "status": "ok",
        "area": catalog["area"],
        "layers": sorted(layers, key=lambda item: item["display_order"]),
        "lineage": {
            "catalog": "data/lechang/catalog.json",
            "source_root": catalog["source_root"],
            "privacy": catalog["privacy"],
        },
        "reliability": {
            "level": "demo_stub",
            "message": "当前结果用于基础接口验证，专题图层可在后续替换为真实模型输出。",
        },
    }
