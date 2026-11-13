"""Store and serve Cd files through the owning conversation."""
import csv
import json
import math
import re
import shutil
import uuid
from pathlib import Path
from tempfile import TemporaryDirectory

from flask import current_app

from framework.models import Conversation, Message


FILES = {
    "map": ("map.jpg", "image/jpeg", "Cd 分布图"),
    "histogram": ("histogram.jpg", "image/jpeg", "Cd 像元直方图"),
    "raster": ("raster.tif", "image/tiff", "Cd GeoTIFF"),
    "csv": ("results.csv", "text/csv", "Cd 查询结果"),
}
MAX_POINTS = 20_000
MAX_ROWS = 100_000
MAX_GRID_CELLS = 16_000_000


class ArtifactError(ValueError):
    pass


def legacy_access(identity):
    from framework.models import User, db

    owner_id = str(identity)
    user = db.session.get(User, int(owner_id)) if owner_id.isdigit() else None
    return {"owner_id": owner_id, "allow_unowned": bool(user and user.status == 1 and user.is_admin())}


def _root():
    default = Path(__file__).resolve().parents[3] / "data" / "cd_chat_artifacts"
    return Path(current_app.config.get("CD_CHAT_ARTIFACT_ROOT", default)).resolve()


def _directory(user_id, conversation_id):
    root = _root()
    directory = root / str(int(user_id)) / str(int(conversation_id))
    if directory.resolve() != directory:
        raise ArtifactError("invalid_path")
    return directory


def _owns(user_id, conversation_id):
    return Conversation.query.filter_by(id=conversation_id, user_id=user_id).first() is not None


def _manifest(directory):
    try:
        path = directory / "manifest.json"
        if path.resolve() != path or directory.resolve() != directory:
            return None
        record = json.loads(path.read_text(encoding="utf-8"))
        return record if isinstance(record, dict) else None
    except (OSError, ValueError):
        return None


def _file(directory, kind):
    if kind not in FILES:
        raise ArtifactError("invalid_kind")
    path = directory / FILES[kind][0]
    if path.resolve() != path or not path.is_file() or path.stat().st_size == 0:
        raise ArtifactError("artifact_not_found")
    return path


def download(user_id, conversation_id, artifact_id, kind):
    if not re.fullmatch(r"[0-9a-f]{32}", artifact_id) or not _owns(user_id, conversation_id):
        raise ArtifactError("artifact_not_found")
    directory = _directory(user_id, conversation_id) / artifact_id
    manifest = _manifest(directory)
    if (not manifest or manifest.get("status") != "ready" or kind not in manifest.get("kinds", ())
        or int(user_id) != manifest.get("owner_id") or conversation_id != manifest.get("conversation_id")):
        raise ArtifactError("artifact_not_found")
    return _file(directory, kind), FILES[kind][1]


def remove_conversation(user_id, conversation_id):
    directory = _directory(user_id, conversation_id)
    if directory.is_dir():
        shutil.rmtree(directory)


def list_owned(user_id, conversation_id):
    if not _owns(user_id, conversation_id):
        raise ArtifactError("artifact_not_found")
    directory = _directory(user_id, conversation_id)
    items = [_manifest(path) for path in directory.iterdir()
             if re.fullmatch(r"[0-9a-f]{32}", path.name)] if directory.is_dir() else []
    return [item["public"] for item in items if item and item.get("status") == "ready"
            and item.get("owner_id") == int(user_id) and item.get("conversation_id") == conversation_id]


def _flux_rows(scope):
    from framework.domain.other_models import cd_flux_v2

    filters = {name: scope[name] for name in ("source", "parcel_id", "region_type", "region_id") if scope.get(name)}
    years = scope.get("years") or [scope.get("year")]
    for year in years:
        yield from cd_flux_v2.results(
            year=year, calculation_version=scope.get("calculation_version", cd_flux_v2.VERSION), **filters,
        )["rows"]


def _prediction_points(scope):
    from framework.domain.other_models import heavy_metal_cd_visualization as viz

    return viz._points(scope["model_id"], source=scope["source"],
                       region_type=scope.get("region_type"), region_id=scope.get("region_id"))


def _prediction_rows(scope):
    from framework.domain.other_models import heavy_metal_cd_spatial as spatial
    from framework.domain.other_models import heavy_metal_cd_statistics as stats
    from framework.models import db

    model = scope["model_id"]
    table = stats._result_table(model)
    value = getattr(table, stats._COLUMNS[model])
    query = stats.source_filter(db.session.query(table.parcel_id, table.sample_id, value),
                                table, scope["source"])
    if scope.get("region_type"):
        mapping, _ = spatial._mapping_for(scope["region_type"], scope["source"])
        parcels = [parcel for parcel, region in mapping.items() if region == str(scope["region_id"])]
        query = query.filter(table.parcel_id.in_(parcels))
    for parcel, sample, log_value in query.order_by(table.parcel_id, table.sample_id).yield_per(2000):
        try:
            concentration = math.exp(float(log_value))
        except (TypeError, ValueError, OverflowError):
            continue
        if math.isfinite(concentration):
            yield parcel, sample, concentration, stats.UNIT_STATUS


def _csv_value(value):
    # Prevent spreadsheet formula execution when identifiers come from imports.
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def _write_csv(directory, scope):
    count = 0
    with (directory / FILES["csv"][0]).open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.writer(file)
        if scope["category"] == "flux":
            writer.writerow(["source", "accounting_year", "parcel_id", "sample_id",
                             "calculation_version", "unit_status", "in_cd_g_ha_a",
                             "out_cd_g_ha_a", "net_cd_g_ha_a", "end_cd_mg_kg"])
            for row in _flux_rows(scope):
                count += 1
                if count > MAX_ROWS:
                    raise ArtifactError("too_many_rows")
                result = row["output"] or {}
                writer.writerow([_csv_value(value) for value in (
                    row["source"], row["accounting_year"], row["parcel_id"], row["sample_id"],
                    result.get("calculation_version"), (result.get("unit_status") or {}).get("status"),
                    *(result.get(name) for name in ("in_cd", "out_cd", "net_cd", "end_cd")),
                )])
        else:
            writer.writerow(["parcel_id", "sample_id", "prediction_mg_kg", "unit_status"])
            for parcel, sample, value, unit_status in _prediction_rows(scope):
                count += 1
                if count > MAX_ROWS:
                    raise ArtifactError("too_many_rows")
                writer.writerow([_csv_value(parcel), _csv_value(sample), value, unit_status])
    if count == 0:
        raise ArtifactError("no_data")
    return ["csv"], {"row_count": count}


def _flux_points(scope):
    from framework.models import ParcelInfo, db

    field = scope["field"]
    rows = [row for row in _flux_rows(scope) if row.get("output") and row["output"].get(field) is not None]
    if len({row["accounting_year"] for row in rows}) > 1:
        raise ArtifactError("choose_single_year")
    records = [(row["parcel_id"], row["output"][field]) for row in rows]
    parcels = sorted({parcel for parcel, _ in records})
    coordinates = {}
    for start in range(0, len(parcels), 2000):
        batch = parcels[start:start + 2000]
        for parcel, lon, lat in db.session.query(
            ParcelInfo.parcel_id, ParcelInfo.centroid_lon, ParcelInfo.centroid_lat,
        ).filter(ParcelInfo.parcel_id.in_(batch)):
            if lon is not None and lat is not None and math.isfinite(lon) and math.isfinite(lat):
                coordinates[parcel] = (lon, lat)
    return [(parcel, *coordinates[parcel], value) for parcel, value in records
            if parcel in coordinates and math.isfinite(value)], len(records)


def _charts(directory, scope, *, raster, interpolation):
    import numpy as np

    from framework.domain.other_models import cd_flux
    from framework.domain.other_models import heavy_metal_cd_visualization as viz

    is_flux = scope["category"] == "flux"
    if is_flux and (interpolation or raster):
        raise ArtifactError("unsupported_flux_chart_option")
    if is_flux and len(scope.get("years") or []) > 1:
        raise ArtifactError("choose_single_year")
    if is_flux:
        points, records = _flux_points(scope)
        title = {
            "in_cd": "Cd Input Flux", "out_cd": "Cd Output Flux",
            "net_cd": "Cd Net Flux", "end_cd": "Cd End Concentration",
        }[scope["field"]]
        unit = cd_flux.FIELDS[scope["field"]]["unit"]
    else:
        points = _prediction_points(scope)
        records = len(points)
        title, _ = viz._title_for(scope["model_id"])
        unit = "mg/kg"
    available = len(points)
    if not available:
        raise ArtifactError("no_data")
    points = sorted(points)[:MAX_POINTS]
    template = viz.load_template()
    _, (height, width) = viz._scaled_grid(template, viz.DEFAULT_RESOLUTION_FACTOR)
    if height * width > MAX_GRID_CELLS:
        raise ArtifactError("grid_too_large")
    boundary = viz._region_boundary(scope.get("region_type"), scope.get("region_id"))
    grid, transform, boundary_source, dropped, effective = viz._rasterize(
        points, template=template, resolution_factor=viz.DEFAULT_RESOLUTION_FACTOR,
        boundary=boundary, enable_interpolation=bool(interpolation),
        interpolation_method=interpolation or "nearest",
    )
    if not np.isfinite(grid).any():
        raise ArtifactError("no_data_in_template")
    legend = cd_flux._legend(scope["field"], grid) if is_flux else viz._legend_for(scope["model_id"], grid)
    render_legend = {**legend, "labels": ["< -5", "-5 to 5", "> 5"]} if is_flux and scope["field"] == "net_cd" else legend
    viz._render_map(grid, transform, boundary, render_legend, title=title, out_path=directory / FILES["map"][0])
    viz._render_histogram(grid, title=title, xlabel=unit, out_path=directory / FILES["histogram"][0])
    kinds = ["map", "histogram"]
    if raster:
        viz._render_raster_tif(grid, transform, template, directory / FILES["raster"][0])
        kinds.append("raster")
    return kinds, {
        "records": records, "available_points": available, "used_points": len(points),
        "truncated": available > len(points), "outside_template": dropped,
        "boundary_source": boundary_source, "statistics_basis": "raster_pixels",
        "pixel_statistics": viz._stats_for(scope.get("model_id"), grid),
        "legend": {**legend, "bounds": [x if math.isfinite(x) else None for x in legend["bounds"]]},
        "unit": unit, "unit_status": "explicit_v2_contract" if is_flux else "unverified",
        "interpolation_requested": interpolation, "interpolation_effective": effective,
        "interpolated": effective is not None,
        "display_only": True,
    }


def generate(user_id, conversation_id, revision, scope, *, export=False, raster=False, interpolation=None):
    user_id, conversation_id, revision = int(user_id), int(conversation_id), int(revision)
    if not _owns(user_id, conversation_id) or not Message.query.filter_by(
        id=revision, conversation_id=conversation_id, role="user",
    ).first():
        raise ArtifactError("artifact_not_found")
    if interpolation not in (None, "nearest", "linear", "cubic"):
        raise ArtifactError("invalid_interpolation")
    options = dict(export=export, raster=raster, interpolation=interpolation)
    fingerprint = json.dumps([user_id, conversation_id, revision, scope, options], sort_keys=True)
    artifact_id = uuid.uuid5(uuid.NAMESPACE_URL, fingerprint).hex
    parent = _directory(user_id, conversation_id)
    directory = parent / artifact_id
    existing = _manifest(directory)
    if existing and existing["status"] == "ready":
        for kind in existing["kinds"]:
            _file(directory, kind)
        return existing["public"]
    parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".pending-", dir=parent) as temporary:
        staging = Path(temporary) / "bundle"
        staging.mkdir()
        kinds, metadata = _write_csv(staging, scope) if export else _charts(
            staging, scope, raster=raster, interpolation=interpolation,
        )
        attachments = []
        for kind in kinds:
            path = _file(staging, kind)
            attachments.append({
                "artifact_id": artifact_id, "kind": kind, "mime_type": FILES[kind][1],
                "title": FILES[kind][2], "size_bytes": path.stat().st_size,
                "url": f"/api/v1/chat/conversations/{conversation_id}/attachments/{artifact_id}/{kind}",
            })
        public = {"status": "ready", "attachments": attachments, "scope": scope,
                  "query_revision": revision, "metadata": metadata}
        manifest = {"status": "ready", "owner_id": user_id, "conversation_id": conversation_id,
                    "revision": revision, "kinds": kinds, "public": public}
        (staging / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, allow_nan=False), encoding="utf-8")
        if not _owns(user_id, conversation_id):
            raise ArtifactError("artifact_not_found")
        try:
            staging.rename(directory)
        except OSError:
            concurrent = _manifest(directory)
            if concurrent and concurrent["status"] == "ready":
                return concurrent["public"]
            raise
        return public
