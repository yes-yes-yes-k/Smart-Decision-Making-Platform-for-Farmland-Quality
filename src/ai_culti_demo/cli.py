from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from .diagnosis import diagnose_county
from .overview import get_county_overview
from .report import build_report_summary
from .runtime import verify_standalone_runtime
from .thematic_models import list_thematic_models, run_thematic_model


def _print_json(value: dict[str, Any]) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="乐昌市基础能力接口 CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    overview_parser = subparsers.add_parser("overview")
    overview_parser.add_argument("--area-code", default="lechang")

    diagnosis_parser = subparsers.add_parser("diagnose")
    diagnosis_parser.add_argument("--topic", default="quality")
    diagnosis_parser.add_argument("--area-code", default="lechang")
    diagnosis_parser.add_argument("--longitude", type=float)
    diagnosis_parser.add_argument("--latitude", type=float)

    report_parser = subparsers.add_parser("report")
    report_parser.add_argument("--topic", default="quality")

    models_parser = subparsers.add_parser("models")
    models_parser.add_argument("--area-code", default="lechang")

    model_parser = subparsers.add_parser("model")
    model_parser.add_argument("--model-id", required=True)
    model_parser.add_argument("--area-code", default="lechang")
    model_parser.add_argument("--longitude", type=float)
    model_parser.add_argument("--latitude", type=float)
    model_parser.add_argument(
        "--indicators",
        nargs="*",
        default=None,
        help="可选指标列表，例如 pH organic_matter nutrient",
    )

    subparsers.add_parser("verify")

    args = parser.parse_args(argv)
    if args.command == "overview":
        _print_json(get_county_overview(args.area_code))
        return 0
    if args.command == "diagnose":
        payload = {
            "topic": args.topic,
            "area_code": args.area_code,
        }
        if args.longitude is not None:
            payload["longitude"] = args.longitude
        if args.latitude is not None:
            payload["latitude"] = args.latitude
        _print_json(diagnose_county(payload))
        return 0
    if args.command == "report":
        diagnosis = diagnose_county({"topic": args.topic, "area_code": "lechang"})
        _print_json(build_report_summary(diagnosis))
        return 0
    if args.command == "models":
        _print_json(list_thematic_models(args.area_code))
        return 0
    if args.command == "model":
        payload = {
            "model_id": args.model_id,
            "area_code": args.area_code,
        }
        if args.longitude is not None:
            payload["longitude"] = args.longitude
        if args.latitude is not None:
            payload["latitude"] = args.latitude
        if args.indicators:
            payload["indicators"] = args.indicators
        _print_json(run_thematic_model(payload))
        return 0
    if args.command == "verify":
        _print_json(verify_standalone_runtime())
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
