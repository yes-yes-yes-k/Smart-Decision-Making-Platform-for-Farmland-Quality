"""HTTP endpoints for farmland statistics and map parcel interaction."""

from __future__ import annotations

import logging
from collections import defaultdict, deque
from threading import Lock
from time import monotonic

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from framework.api.services.farmland_statistics import (
    StatisticsError,
    aggregate_statistics,
    get_parcel_summary,
    indicator_quality_audit,
    list_boundaries,
    list_regions,
    list_viewport_parcels,
    metric_metadata,
    pick_parcel,
)


logger = logging.getLogger(__name__)
farmland_statistics_bp = Blueprint("farmland_statistics", __name__)


class _SlidingWindowLimiter:
    def __init__(self, limit: int, window_seconds: float):
        self.limit = limit
        self.window_seconds = window_seconds
        self._requests: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def allow(self, key: str) -> bool:
        now = monotonic()
        cutoff = now - self.window_seconds
        with self._lock:
            timestamps = self._requests[key]
            while timestamps and timestamps[0] <= cutoff:
                timestamps.popleft()
            if len(timestamps) >= self.limit:
                return False
            timestamps.append(now)
            return True


_PICK_LIMITER = _SlidingWindowLimiter(limit=120, window_seconds=60)
_VIEWPORT_LIMITER = _SlidingWindowLimiter(limit=60, window_seconds=60)


def _request_key() -> str:
    identity = get_jwt_identity()
    return f"user:{identity}" if identity is not None else f"ip:{request.remote_addr or 'unknown'}"


def _success(data):
    return jsonify({"status": "ok", "data": data})


def _handle_error(error: StatisticsError):
    response = jsonify({
        "status": "error",
        "code": error.code,
        "message": error.message,
    })
    if error.http_status == 429:
        response.headers["Retry-After"] = "1"
    return response, error.http_status


def _internal_error():
    return jsonify({
        "status": "error",
        "code": "internal_error",
        "message": "统计服务内部错误",
    }), 500


@farmland_statistics_bp.route("/metrics", methods=["GET"])
@jwt_required()
def get_metrics():
    return _success(metric_metadata())


@farmland_statistics_bp.route("/regions", methods=["GET"])
@jwt_required()
def get_regions():
    try:
        include_disputes = request.args.get("include_disputes", "false").lower() == "true"
        return _success(list_regions(
            parent_type=request.args.get("parent_type"),
            parent_id=request.args.get("parent_id"),
            include_disputes=include_disputes,
        ))
    except StatisticsError as error:
        return _handle_error(error)
    except Exception:
        logger.exception("Unexpected farmland region-list failure")
        return _internal_error()


@farmland_statistics_bp.route("/boundaries", methods=["GET"])
@jwt_required()
def get_boundaries():
    try:
        return _success(list_boundaries(
            region_type=request.args.get("region_type"),
            parent_type=request.args.get("parent_type"),
            parent_id=request.args.get("parent_id"),
            bbox=request.args.get("bbox"),
            zoom=request.args.get("zoom"),
        ))
    except StatisticsError as error:
        return _handle_error(error)
    except Exception:
        logger.exception("Unexpected farmland boundary-list failure")
        return _internal_error()


@farmland_statistics_bp.route("/aggregate", methods=["POST"])
@jwt_required()
def aggregate():
    try:
        return _success(aggregate_statistics(request.get_json(silent=True)))
    except StatisticsError as error:
        return _handle_error(error)
    except Exception:
        logger.exception("Unexpected farmland statistics failure")
        return _internal_error()


@farmland_statistics_bp.route("/parcels/<parcel_id>", methods=["GET"])
@jwt_required()
def get_parcel(parcel_id):
    try:
        return _success(get_parcel_summary(parcel_id))
    except StatisticsError as error:
        return _handle_error(error)
    except Exception:
        logger.exception("Unexpected parcel-summary failure")
        return _internal_error()


@farmland_statistics_bp.route("/parcels/pick", methods=["POST"])
@jwt_required()
def pick():
    body = request.get_json(silent=True) or {}
    try:
        if not _PICK_LIMITER.allow(_request_key()):
            raise StatisticsError("rate_limited", "点选请求过于频繁，请稍后重试", 429)
        return _success(pick_parcel(
            body.get("longitude"),
            body.get("latitude"),
            metric_key=body.get("metric", body.get("metric_key")),
            tolerance_meters=body.get("toleranceMeters", body.get("tolerance_meters", 0)),
        ))
    except StatisticsError as error:
        return _handle_error(error)
    except Exception:
        logger.exception("Unexpected parcel-pick failure")
        return _internal_error()


@farmland_statistics_bp.route("/parcels/viewport", methods=["GET"])
@jwt_required()
def viewport_parcels():
    try:
        if not _VIEWPORT_LIMITER.allow(_request_key()):
            raise StatisticsError("rate_limited", "视口地块请求过于频繁，请稍后重试", 429)
        return _success(list_viewport_parcels(
            bbox=request.args.get("bbox"),
            metric_key=request.args.get("metric"),
            geometry_mode=request.args.get("geometry", "centroid"),
            zoom=request.args.get("zoom"),
            limit=request.args.get("limit", "2000"),
        ))
    except StatisticsError as error:
        return _handle_error(error)
    except Exception:
        logger.exception("Unexpected viewport-parcel failure")
        return _internal_error()


@farmland_statistics_bp.route("/quality/audit", methods=["GET"])
@jwt_required()
def quality_audit():
    try:
        return _success(indicator_quality_audit())
    except StatisticsError as error:
        return _handle_error(error)
    except Exception:
        logger.exception("Unexpected indicator-quality audit failure")
        return _internal_error()
