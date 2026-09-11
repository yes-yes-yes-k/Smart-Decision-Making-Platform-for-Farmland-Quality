"""HTTP endpoints for farmland statistics and map parcel interaction."""

from __future__ import annotations

import logging

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required

from framework.api.services.farmland_statistics import (
    StatisticsError,
    aggregate_statistics,
    get_parcel_summary,
    list_regions,
    metric_metadata,
    pick_parcel,
)


logger = logging.getLogger(__name__)
farmland_statistics_bp = Blueprint("farmland_statistics", __name__)


def _success(data):
    return jsonify({"status": "ok", "data": data})


def _handle_error(error: StatisticsError):
    return jsonify({
        "status": "error",
        "code": error.code,
        "message": error.message,
    }), error.http_status


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
        return _success(pick_parcel(body.get("longitude"), body.get("latitude")))
    except StatisticsError as error:
        return _handle_error(error)
    except Exception:
        logger.exception("Unexpected parcel-pick failure")
        return _internal_error()
