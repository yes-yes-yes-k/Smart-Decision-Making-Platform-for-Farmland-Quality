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


# 前端区域筛选传中文名，首版 demo 仅乐昌有完整数据，这里统一归并
# 空字符串代表"全省"，以下别名均映射到 lechang
_LECHANG_ALIASES = {
    "",
    "lechang",
    "Lechang",
    "乐昌",
    "乐昌市",
    # 韶关市及下属区县
    "韶关市", "韶关", "Shaoguan",
    "浈江区", "武江区", "曲江区", "乐昌市", "南雄市",
    "始兴县", "仁化县", "翁源县", "新丰县", "乳源瑶族自治县",
    # 广东省及其他地市（前端可选择，但后端当前仅返回乐昌数据）
    "广东省", "Guangdong",
    "广州市", "深圳市", "珠海市", "佛山市", "东莞市",
    "中山市", "惠州市", "江门市", "肇庆市", "茂名市",
    "湛江市", "清远市", "梅州市", "河源市", "揭阳市",
    "汕头市", "潮州市", "汕尾市", "阳江市", "云浮市",
}


def _normalize_area_code(area_code: str | None) -> str:
    """把前端传入的中文/空/code 统一归一到 lechang（首版 demo 仅乐昌完整）。"""
    code = (area_code or "").strip()
    if code in _LECHANG_ALIASES:
        return "lechang"
    # 兜底：任何非空输入也先给 lechang，后续可扩展真实多区域支持
    return "lechang" if code else "lechang"


def get_county_overview(area_code: str = "lechang") -> dict[str, Any]:
    """返回未来 Agent 和前端都可直接消费的县域总览结构。"""

    catalog = load_catalog()
    normalized = _normalize_area_code(area_code)
    if normalized != catalog["area"]["code"]:
        msg = f"当前基础能力仅支持 {catalog['area']['name']}"
        return {
            "status": "error",
            "message": msg,
            "error": {
                "code": "UNSUPPORTED_AREA",
                "message": msg,
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
