"""Cd 结果可视化：栅格化、可选空间插值、分级地图、直方图与产物导出（阶段 4）。

数据来源（design 决策 1）：直接读两张 Cd 结果表 + ``parcel_info`` 质心坐标，
``exp(ln)`` 还原 mg/kg，不重新调用预测模型。区域过滤复用阶段 3 的归属依据：
自有地块取面积最大归属（``farmland_region_parcel_area``），移植地块取点面判断
（``cd_ported_parcel_township``）。

栅格网格（design 决策 2）：以迁移自原系统的 ``template.tif`` 为基准，
``resolution_factor`` 相对模板像元放大；模板范围外的点会被丢弃，若一个点都不在
范围内则返回 ``no_data_in_template``，不产出空白图。

产物（design 决策 6）::

    data/cd_visualization/<model_id>/<artifact_id>/
        map.jpg            # 分级地图（JPG, dpi 300）
        histogram.jpg      # 直方图
        raster.tif         # 可选（save_raster=True）
        meta.json          # 请求参数、图例、统计摘要、文件清单、generated_at
"""
from __future__ import annotations

import json
import logging
import math
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

import matplotlib

matplotlib.use("Agg")  # 服务端渲染；必须在 pyplot 之前设置

import matplotlib.pyplot as plt
import numpy as np

LOG = logging.getLogger(__name__)

_ROUTER_MODELS = ("crop_cd", "effective_cd")
_ROOT = Path(__file__).resolve().parents[3]
TEMPLATE_PATH = _ROOT / "data" / "model_artifacts" / "heavy_metal_cd" / "visualization" / "template.tif"
TEMPLATE_MANIFEST = _ROOT / "data" / "model_artifacts" / "heavy_metal_cd" / "visualization" / "manifest.json"
VISUALIZATION_ROOT = _ROOT / "data" / "cd_visualization"

REGION_TYPES: tuple[str, ...] = ("province", "city", "county", "township", "zone", "village")
INTERPOLATION_METHODS: tuple[str, ...] = ("nearest", "linear", "cubic")
KINDS: dict[str, str] = {"map": "map.jpg", "histogram": "histogram.jpg", "raster": "raster.tif"}

ARTIFACT_ID_RE = re.compile(r"^[0-9a-f]{32}$")
DEFAULT_RESOLUTION_FACTOR = 4.0
MIN_RESOLUTION_FACTOR = 1.0
MAX_RESOLUTION_FACTOR = 16.0
DEFAULT_FIGSIZE = (10.0, 8.0)
DEFAULT_DPI = 300

# 与原系统 VISUALIZATION_CONFIG / COLORMAPS 对齐（design 决策 4）
CROP_CD_BOUNDS: tuple[float, ...] = (0.0, 0.2, 0.3, float("inf"))
CROP_CD_LABELS: tuple[str, ...] = ("0.0 ~ 0.2 mg/kg", "0.2 ~ 0.3 mg/kg", "≥ 0.3 mg/kg")
CROP_CD_COLORS: tuple[str, ...] = ("#15B392", "#FFEB55", "#D91656")
EFFECTIVE_CD_COLORS: tuple[str, ...] = (
    "#15B392",
    "#73EC8B",
    "#FFEB55",
    "#EE66A6",
    "#D91656",
    "#640D5F",
)
EFFECTIVE_CD_QUANTILES: tuple[float, ...] = (0, 20, 40, 60, 80, 90, 100)


class CdVisualizationError(ValueError):
    """可视化输入或数据错误；``code`` 是机器可读的问题码。"""

    def __init__(self, code: str, message: str = ""):
        super().__init__(message or code)
        self.code = code


def _require_app_context() -> None:
    from flask import has_app_context

    if not has_app_context():
        raise CdVisualizationError("no_app_context")


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _statistics():
    from framework.domain.other_models import heavy_metal_cd_statistics as statistics

    return statistics


def _spatial():
    from framework.domain.other_models import heavy_metal_cd_spatial as spatial

    return spatial


# ----------------------------- 参数校验 -----------------------------


def _check_model(model_id: str) -> str:
    model_id = str(model_id or "").strip()
    if model_id not in _ROUTER_MODELS:
        raise CdVisualizationError("unknown_model")
    return model_id


def _check_region(region_type: str | None, region_id: str | None) -> tuple[str | None, str | None]:
    region_type = (region_type or "").strip() or None
    region_id = (region_id or "").strip() or None
    if bool(region_type) != bool(region_id):
        raise CdVisualizationError("invalid_region")
    if region_type is not None and region_type not in REGION_TYPES:
        raise CdVisualizationError("invalid_region_type")
    return region_type, region_id


def _check_interpolation(enable: bool, method: str) -> tuple[bool, str]:
    method = str(method or "nearest").strip().lower()
    if method not in INTERPOLATION_METHODS:
        raise CdVisualizationError("invalid_interpolation_method")
    return bool(enable), method


def _check_resolution(value: Any) -> float:
    try:
        factor = float(value)
    except (TypeError, ValueError) as exc:
        raise CdVisualizationError("invalid_resolution_factor") from exc
    if not math.isfinite(factor) or not MIN_RESOLUTION_FACTOR <= factor <= MAX_RESOLUTION_FACTOR:
        raise CdVisualizationError("invalid_resolution_factor")
    return factor


# ----------------------------- 数据取数 -----------------------------


def _region_mapping(region_type: str | None, source: str) -> tuple[dict[str, str], dict[str, Any]]:
    """按来源取「地块 → 区域」映射；语义与阶段 3 的 ``_mapping_for`` 一致。

    自有地块取面积最大归属；移植地块只有 township 级归属（点面判断）。
    """
    spatial = _spatial()
    statistics = _statistics()
    source = statistics.normalize_source(source)
    mapping: dict[str, str] = {}
    meta: dict[str, Any] = {"source": source, "assignment_sources": {}, "ported_unavailable_for_region_type": False}
    if region_type is None:
        return mapping, meta
    if source in ("native", "all"):
        native_map = spatial.parcel_region_map(region_type)
        mapping.update(native_map)
        if native_map:
            meta["assignment_sources"]["native"] = "farmland_region_parcel_area"
    if source in ("ported", "all"):
        if region_type == "township":
            ported_map = spatial.ported_region_map()
            mapping.update(ported_map)
            if ported_map:
                meta["assignment_sources"]["ported"] = "cd_ported_parcel_township"
        else:
            meta["ported_unavailable_for_region_type"] = True
    return mapping, meta


def _points(
    model_id: str,
    *,
    source: str = "all",
    region_type: str | None = None,
    region_id: str | None = None,
) -> list[tuple[str, float, float, float]]:
    """取 (parcel_id, lon, lat, value_mgkg) 列表，按来源与区域过滤。"""
    _require_app_context()
    from sqlalchemy import select

    from framework.models import ParcelInfo
    from framework.models.cd_prediction import CdCropPredictionResult, CdEffectivePredictionResult
    from framework.models.user import db

    statistics = _statistics()
    table = CdCropPredictionResult if model_id == "crop_cd" else CdEffectivePredictionResult
    column = getattr(table, statistics._COLUMNS[model_id])  # noqa: SLF001 - 同包统计口径
    query = select(
        table.parcel_id,
        table.sample_id,
        column,
        ParcelInfo.centroid_lon,
        ParcelInfo.centroid_lat,
    ).join(ParcelInfo, ParcelInfo.parcel_id == table.parcel_id)
    query = statistics.source_filter(query, table, source)

    wanted: set[str] | None = None
    if region_type is not None:
        mapping, _meta = _region_mapping(region_type, source)
        wanted = {parcel_id for parcel_id, rid in mapping.items() if rid == str(region_id)}
        if not wanted:
            return []
        query = query.where(table.parcel_id.in_(wanted))

    payload: list[tuple[str, float, float, float]] = []
    for parcel_id, _sample_id, log_value, lon, lat in db.session.execute(query).all():
        if log_value is None or lon is None or lat is None:
            continue
        try:
            value = math.exp(float(log_value))
        except (OverflowError, ValueError):
            continue
        if math.isfinite(value):
            payload.append((str(parcel_id), float(lon), float(lat), value))
    return payload


def _region_boundary(region_type: str | None, region_id: str | None) -> Any | None:
    """从区域目录取边界几何（GeoJSON → shapely）。SQLite 或缺失时返回 None。"""
    if region_type is None or region_id is None:
        return None
    _require_app_context()
    try:
        from sqlalchemy import func, select
        from shapely.geometry import shape

        from framework.models import SpatialRegionCatalog
        from framework.models.user import db

        row = db.session.execute(
            select(func.ST_AsGeoJSON(SpatialRegionCatalog.geom)).where(
                SpatialRegionCatalog.object_type == region_type,
                SpatialRegionCatalog.object_id == str(region_id),
                SpatialRegionCatalog.enabled.is_(True),
                SpatialRegionCatalog.geom.isnot(None),
            )
        ).first()
        if row is None or row[0] is None:
            return None
        return shape(json.loads(row[0]))
    except Exception as exc:  # PostGIS 函数缺失（如 SQLite 测试库）时退回凸包
        LOG.warning("区域边界读取失败，回退凸包: %s", exc)
        return None


# ----------------------------- 栅格化 -----------------------------


def load_template() -> dict[str, Any]:
    """读取模板栅格元数据；文件缺失时报错。"""
    if not TEMPLATE_PATH.exists():
        raise CdVisualizationError("template_missing")
    import rasterio

    with rasterio.open(TEMPLATE_PATH) as src:
        return {
            "path": str(TEMPLATE_PATH),
            "crs": src.crs,
            "transform": src.transform,
            "width": src.width,
            "height": src.height,
            "bounds": tuple(src.bounds),
            "nodata": src.nodata,
        }


def _scaled_grid(template: dict[str, Any], resolution_factor: float) -> tuple[Any, tuple[int, int]]:
    """按分辨率因子放大模板网格，返回 (transform, (height, width))。"""
    import rasterio

    base = template["transform"]
    height = max(1, int(round(template["height"] * resolution_factor)))
    width = max(1, int(round(template["width"] * resolution_factor)))
    transform = rasterio.Affine(
        base.a / resolution_factor,
        base.b,
        base.c,
        base.d,
        base.e / resolution_factor,
        base.f,
    )
    return transform, (height, width)


def _rasterize(
    points: Sequence[tuple[str, float, float, float]],
    *,
    template: dict[str, Any],
    resolution_factor: float,
    boundary,
    enable_interpolation: bool,
    interpolation_method: str,
) -> tuple[np.ndarray, Any, str, int]:
    """点集 → 栅格数组；返回 (raster, transform, boundary_source, 丢弃点数)。"""
    from rasterio.features import geometry_mask, rasterize
    from rasterio.windows import from_bounds
    from shapely.geometry import MultiPoint, Point

    transform, (height, width) = _scaled_grid(template, resolution_factor)

    # 模板范围过滤（design：范围外点丢弃，但完全不落入则报错）
    min_x, min_y, max_x, max_y = template["bounds"]
    kept = [p for p in points if min_x <= p[1] <= max_x and min_y <= p[2] <= max_y]
    dropped = len(points) - len(kept)
    if not kept:
        raise CdVisualizationError("no_data_in_template")

    shapes = ((Point(lon, lat), value) for _pid, lon, lat, value in kept)
    raster = rasterize(
        shapes=shapes,
        out_shape=(height, width),
        transform=transform,
        fill=np.nan,
        dtype="float32",
    )

    # 掩膜：优先行政区边界（支持 MultiPolygon / 多要素合并），否则凸包
    boundary_source = "convex_hull"
    mask_geom = boundary
    if mask_geom is not None:
        boundary_source = "catalog"
    else:
        mask_geom = MultiPoint([(p[1], p[2]) for p in kept]).convex_hull
    if mask_geom is not None and not mask_geom.is_empty:
        inside = geometry_mask([mask_geom], out_shape=(height, width), transform=transform, invert=True)
        raster = np.where(inside, raster, np.nan)

        # 裁剪到边界 bbox（原系统 mask(crop=True) 的等价效果）
        try:
            window = from_bounds(*mask_geom.bounds, transform=transform)
            col0 = max(0, int(math.floor(window.col_off)))
            row0 = max(0, int(math.floor(window.row_off)))
            col1 = min(width, int(math.ceil(window.col_off + window.width)))
            row1 = min(height, int(math.ceil(window.row_off + window.height)))
            if col1 > col0 and row1 > row0 and (col1 - col0) * (row1 - row0) < height * width:
                raster = raster[row0:row1, col0:col1]
                transform = transform @ rasterio_affine_translation(col0, row0)
        except Exception as exc:  # 裁剪失败不致命
            LOG.warning("边界 bbox 裁剪失败，保留整幅栅格: %s", exc)

    if enable_interpolation and np.isnan(raster).any():
        interpolated, effective_method = _interpolate_nan(raster, interpolation_method)
        raster = interpolated
        if mask_geom is not None and not mask_geom.is_empty:
            inside = geometry_mask(
                [mask_geom], out_shape=raster.shape, transform=transform, invert=True
            )
            raster = np.where(inside, raster, np.nan)
    else:
        effective_method = None

    return raster, transform, boundary_source, dropped, effective_method


def rasterio_affine_translation(col: int, row: int):
    """返回像元偏移的仿射变换（避免在多处重复 import rasterio.Affine）。"""
    import rasterio

    return rasterio.Affine.translation(col, row)


def _interpolate_nan(raster: np.ndarray, method: str) -> tuple[np.ndarray, str]:
    """用 scipy.griddata 填充 NaN；剩余 NaN 用最近邻填充（原系统同款兜底）。

    返回 (栅格, 实际使用的插值方法)。有效像元不足以构造三角剖分（linear/cubic 需要
    至少 4 个非共线点）时 MUST 降级为 nearest，而不是让整个请求失败。
    """
    from scipy.interpolate import griddata
    from scipy.ndimage import distance_transform_edt

    if not np.isnan(raster).any():
        return raster, method
    valid = ~np.isnan(raster)
    rows, cols = raster.shape
    grid_x, grid_y = np.mgrid[0:rows, 0:cols]
    points = np.column_stack(np.where(valid))
    values = raster[valid]
    effective = method
    interpolated = None
    if method != "nearest":
        try:
            interpolated = griddata(points, values, (grid_x, grid_y), method=method, fill_value=np.nan)
        except Exception as exc:  # QhullError：点数不足/共线，降级 nearest
            LOG.warning("插值方法 %s 不可用（有效点不足），降级 nearest: %s", method, exc)
            interpolated = None
    if interpolated is None:
        effective = "nearest"
        interpolated = griddata(points, values, (grid_x, grid_y), method="nearest", fill_value=np.nan)
    if np.isnan(interpolated).any():
        remaining = np.isnan(interpolated)
        _dist, indices = distance_transform_edt(remaining, return_distances=True, return_indices=True)
        interpolated[remaining] = raster[indices[0][remaining], indices[1][remaining]]
    return interpolated, effective


def _legend_for(model_id: str, raster: np.ndarray) -> dict[str, Any]:
    """构造图例（作物三档 / 有效态分位数 6 级）。"""
    valid = raster[~np.isnan(raster)]
    if valid.size == 0:
        return {"mode": "empty", "bounds": [], "colors": [], "labels": []}
    if model_id == "crop_cd":
        bounds = [float(b) for b in CROP_CD_BOUNDS]
        return {
            "mode": "threshold",
            "bounds": bounds,
            "colors": list(CROP_CD_COLORS),
            "labels": list(CROP_CD_LABELS),
            "note": "展示分级（阈值 0.2/0.3 mg/kg），不是统计分箱或安全判定",
        }
    quantiles = np.nanpercentile(valid, EFFECTIVE_CD_QUANTILES)
    unique = np.unique(quantiles)
    if unique.size < len(EFFECTIVE_CD_QUANTILES):
        quantiles = np.linspace(float(np.nanmin(valid)), float(np.nanmax(valid)), len(EFFECTIVE_CD_QUANTILES))
    bounds = [float(v) for v in quantiles]
    labels = [f"{bounds[i]:.4g} ~ {bounds[i + 1]:.4g}" for i in range(len(bounds) - 1)]
    return {
        "mode": "quantile",
        "bounds": bounds,
        "colors": list(EFFECTIVE_CD_COLORS),
        "labels": labels,
        "note": "展示分级（按有效像元分位数），不是统计分箱或超标判定",
    }


# ----------------------------- 渲染 -----------------------------


def _render_map(
    raster: np.ndarray,
    transform: Any,
    boundary,
    legend: dict[str, Any],
    *,
    title: str,
    out_path: Path,
) -> None:
    from matplotlib.colors import BoundaryNorm, ListedColormap
    from rasterio.plot import show

    colors = legend["colors"]
    if not colors:
        raise CdVisualizationError("no_data")
    valid = raster[~np.isnan(raster)]
    if valid.size == 0:
        raise CdVisualizationError("no_data")

    cmap = ListedColormap(list(colors))
    bounds = [float(b) for b in legend["bounds"]]
    valid = raster[~np.isnan(raster)]
    if valid.size == 0:
        raise CdVisualizationError("no_data")
    data_min = float(np.nanmin(valid))
    data_max = float(np.nanmax(valid))
    # 末档上界：inf / 非递增时抬到数据最大值之上（保证 BoundaryNorm 严格单调）
    if not math.isfinite(bounds[-1]) or bounds[-1] <= bounds[-2]:
        bounds[-1] = max(data_max, bounds[-2] + 1e-6)
    # 首档下界：保证覆盖数据最小值
    if bounds[0] > data_min:
        bounds[0] = math.nextafter(data_min, -math.inf)
    for i in range(1, len(bounds)):
        if bounds[i] <= bounds[i - 1]:
            bounds[i] = bounds[i - 1] + 1e-6
    norm = BoundaryNorm(bounds, ncolors=len(colors))

    fig, ax = plt.subplots(figsize=DEFAULT_FIGSIZE)
    show(raster, transform=transform, ax=ax, cmap=cmap, norm=norm)
    if boundary is not None and not boundary.is_empty:
        try:
            import geopandas as gpd

            gpd.GeoSeries([boundary], crs="EPSG:4326").boundary.plot(
                ax=ax, color="black", linewidth=1
            )
        except Exception as exc:  # 描边失败不致命
            LOG.warning("边界描边失败: %s", exc)

    ax.set_title(title, fontsize=20)
    ax.set_xlabel("Longitude", fontsize=18)
    ax.set_ylabel("Latitude", fontsize=18)
    ax.grid(True, linestyle="--", color="gray", alpha=0.5)
    ax.tick_params(axis="y", labelrotation=90)

    ticks = [(bounds[i] + bounds[i + 1]) / 2 for i in range(len(bounds) - 1)]
    tick_labels = list(legend["labels"])
    if len(tick_labels) != len(ticks):
        data_max = float(np.nanmax(valid))
        if data_max < 0.01:
            tick_labels = [f"{v:.2e}" for v in ticks]
        elif data_max < 1:
            tick_labels = [f"{v:.4f}" for v in ticks]
        elif data_max < 10:
            tick_labels = [f"{v:.2f}" for v in ticks]
        else:
            tick_labels = [f"{v:.1f}" for v in ticks]
    cbar = plt.colorbar(
        plt.cm.ScalarMappable(norm=norm, cmap=cmap), ax=ax, ticks=ticks, shrink=0.6, aspect=15
    )
    cbar.ax.set_yticklabels(tick_labels)
    cbar.set_label("Cd Content Level" if legend["mode"] == "threshold" else "Values")

    plt.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out_path, dpi=DEFAULT_DPI, format="jpg", bbox_inches="tight")
    plt.close("all")


def _render_histogram(raster: np.ndarray, *, title: str, xlabel: str, out_path: Path) -> None:
    import seaborn as sns

    valid = raster[~np.isnan(raster)].astype("float64")
    if valid.size == 0:
        raise CdVisualizationError("no_data")
    data_min, data_max = float(valid.min()), float(valid.max())

    plt.figure(figsize=(10, 6))
    if data_min == data_max:
        plt.bar(
            [data_min],
            [int(valid.size)],
            width=0.1 * abs(data_min) if data_min != 0 else 0.1,
            color="steelblue",
            alpha=0.7,
            edgecolor="black",
        )
        plt.axvline(
            x=data_min,
            color="red",
            linewidth=2,
            linestyle="--",
            label=f"Fixed Value: {data_min:.6f}",
        )
        plt.legend()
    else:
        sns.set(style="ticks")
        sns.histplot(valid, bins=100, color="steelblue", alpha=0.7, edgecolor="black", stat="density")
        try:
            sns.kdeplot(valid, color="red", linewidth=2)
        except Exception as exc:  # 密度估计失败不致命
            LOG.warning("KDE 绘制失败，仅保留直方图: %s", exc)

    plt.xlabel(xlabel, fontsize=14)
    plt.ylabel("Frequency", fontsize=14)
    plt.title(title, fontsize=16)
    plt.grid(True, linestyle="--", alpha=0.5)
    plt.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out_path, dpi=DEFAULT_DPI, format="jpg", bbox_inches="tight")
    plt.close("all")


def _render_raster_tif(raster: np.ndarray, transform: Any, template: dict[str, Any], out_path: Path) -> None:
    import rasterio

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(
        out_path,
        "w",
        driver="GTiff",
        height=raster.shape[0],
        width=raster.shape[1],
        count=1,
        dtype="float32",
        crs=template["crs"],
        transform=transform,
        nodata=np.nan,
        compress="deflate",
    ) as dst:
        dst.write(raster.astype("float32"), 1)


# ----------------------------- 生成与产物 -----------------------------


def _title_for(model_id: str) -> tuple[str, str]:
    if model_id == "crop_cd":
        return ("Crop Cd Prediction", "Crop Cd Content (mg/kg)")
    return ("Effective Cd Prediction", "Effective Cd Content (mg/kg)")


def _stats_for(model_id: str, raster: np.ndarray) -> dict[str, Any]:
    valid = raster[~np.isnan(raster)].astype("float64")
    if valid.size == 0:
        return {"valid_pixels": 0}
    return {
        "valid_pixels": int(valid.size),
        "min": float(valid.min()),
        "max": float(valid.max()),
        "mean": float(valid.mean()),
        "median": float(np.median(valid)),
    }


def generate(
    model_id: str,
    *,
    region_type: str | None = None,
    region_id: str | None = None,
    source: str = "all",
    enable_interpolation: bool = False,
    interpolation_method: str = "nearest",
    resolution_factor: float = DEFAULT_RESOLUTION_FACTOR,
    save_raster: bool = False,
) -> dict[str, Any]:
    """生成一份可视化产物，返回元信息（含下载相对路径）。"""
    model_id = _check_model(model_id)
    region_type, region_id = _check_region(region_type, region_id)
    enable_interpolation, interpolation_method = _check_interpolation(
        enable_interpolation, interpolation_method
    )
    resolution_factor = _check_resolution(resolution_factor)
    statistics = _statistics()
    source = statistics.normalize_source(source)

    if region_type is not None:
        spatial = _spatial()
        if spatial.region_catalog_entry(region_type, region_id) is None:  # type: ignore[arg-type]
            raise CdVisualizationError("region_not_found")

    points = _points(
        model_id, source=source, region_type=region_type, region_id=region_id
    )
    if not points:
        raise CdVisualizationError("no_data")

    template = load_template()
    boundary = _region_boundary(region_type, region_id)
    raster, transform, boundary_source, dropped, interpolation_effective = _rasterize(
        points,
        template=template,
        resolution_factor=resolution_factor,
        boundary=boundary,
        enable_interpolation=enable_interpolation,
        interpolation_method=interpolation_method,
    )
    legend = _legend_for(model_id, raster)
    title, xlabel = _title_for(model_id)

    artifact_id = uuid.uuid4().hex
    out_dir = VISUALIZATION_ROOT / model_id / artifact_id
    out_dir.mkdir(parents=True, exist_ok=True)

    map_path = out_dir / KINDS["map"]
    hist_path = out_dir / KINDS["histogram"]
    raster_path = out_dir / KINDS["raster"] if save_raster else None

    try:
        _render_map(raster, transform, boundary, legend, title=title, out_path=map_path)
        _render_histogram(raster, title=f"{title} Frequency", xlabel=xlabel, out_path=hist_path)
        if raster_path is not None:
            _render_raster_tif(raster, transform, template, raster_path)
    except Exception:
        shutil.rmtree(out_dir, ignore_errors=True)
        raise

    files = {
        "map": f"{model_id}/{artifact_id}/{KINDS['map']}",
        "histogram": f"{model_id}/{artifact_id}/{KINDS['histogram']}",
    }
    if raster_path is not None:
        files["raster"] = f"{model_id}/{artifact_id}/{KINDS['raster']}"

    meta: dict[str, Any] = {
        "artifact_id": artifact_id,
        "model_id": model_id,
        "request": {
            "region_type": region_type,
            "region_id": region_id,
            "source": source,
            "enable_interpolation": enable_interpolation,
            "interpolation_method": interpolation_method,
            "resolution_factor": resolution_factor,
            "save_raster": save_raster,
        },
        "template": {
            "file": TEMPLATE_PATH.name,
            "sha256_manifest": TEMPLATE_MANIFEST.exists(),
            "bounds": [float(v) for v in template["bounds"]],
            "grid": [int(raster.shape[1]), int(raster.shape[0])],
        },
        "data": {
            "row_count": len(points),
            "points_in_template": len(points) - dropped,
            "points_dropped_out_of_template": dropped,
            "unit": statistics.UNIT,
            "unit_status": statistics.UNIT_STATUS,
            "coordinate_source": "parcel_centroid",
        },
        "legend": legend,
        "boundary_source": boundary_source,
        "interpolated": enable_interpolation,
        "interpolation_effective": interpolation_effective,
        "statistics": _stats_for(model_id, raster),
        "files": files,
        "generated_at": _now_iso(),
    }
    (out_dir / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return meta


def list_artifacts(
    *,
    model_id: str | None = None,
    region_type: str | None = None,
    region_id: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """列出已有产物（读取 meta.json），按生成时间降序。"""
    if model_id:
        model_id = _check_model(model_id)
    try:
        limit = int(limit)
    except (TypeError, ValueError) as exc:
        raise CdVisualizationError("invalid_limit") from exc
    if limit < 1 or limit > 200:
        raise CdVisualizationError("invalid_limit")

    items: list[dict[str, Any]] = []
    if VISUALIZATION_ROOT.exists():
        for meta_file in VISUALIZATION_ROOT.glob("*/*/meta.json"):
            try:
                meta = json.loads(meta_file.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if model_id and meta.get("model_id") != model_id:
                continue
            request = meta.get("request") or {}
            if region_type and request.get("region_type") != region_type:
                continue
            if region_id and request.get("region_id") != region_id:
                continue
            items.append(meta)
    items.sort(key=lambda m: str(m.get("generated_at") or ""), reverse=True)
    return {"count": len(items), "items": items[:limit]}


def artifact_path(artifact_id: str, kind: str) -> tuple[Path, str]:
    """校验并返回产物文件路径与 MIME；越界或非法请求一律拒绝。"""
    artifact_id = str(artifact_id or "").strip()
    kind = str(kind or "").strip().lower()
    if not ARTIFACT_ID_RE.match(artifact_id):
        raise CdVisualizationError("invalid_artifact_id")
    if kind not in KINDS:
        raise CdVisualizationError("invalid_kind")

    root = VISUALIZATION_ROOT.resolve()
    candidates = list(root.glob(f"*/{artifact_id}/{KINDS[kind]}"))
    if not candidates:
        raise CdVisualizationError("artifact_not_found")
    path = candidates[0].resolve()
    if root not in path.parents:
        raise CdVisualizationError("invalid_artifact_id")
    if not path.exists():
        raise CdVisualizationError("artifact_not_found")
    mime = "image/jpeg" if kind != "raster" else "image/tiff"
    return path, mime
