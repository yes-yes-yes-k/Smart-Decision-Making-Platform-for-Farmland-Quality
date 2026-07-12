from __future__ import annotations

import json
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CATALOG_PATH = PROJECT_ROOT / "data" / "lechang" / "catalog.json"


def load_catalog(path: Path | None = None) -> dict[str, Any]:
    """读取本仓库维护的乐昌市基础数据目录。"""

    catalog_path = path or DEFAULT_CATALOG_PATH
    with catalog_path.open("r", encoding="utf-8") as fp:
        return json.load(fp)


def get_asset(catalog: dict[str, Any], asset_id: str) -> dict[str, Any] | None:
    for asset in catalog.get("assets", []):
        if asset.get("asset_id") == asset_id:
            return asset
    return None


def get_layer(catalog: dict[str, Any], layer_id: str) -> dict[str, Any] | None:
    for layer in catalog.get("derived_layers", []):
        if layer.get("layer_id") == layer_id:
            return layer
    return None
