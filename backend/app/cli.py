"""Command-line entry point for chart calculation.

Usage:
    python -m app.cli --birth '1990-06-15T12:00:00' --tz Asia/Shanghai --city Shanghai
    python -m app.cli --birth-request path/to/birth.json

The CLI is intentionally minimal: it never calls the LLM, never reads RAG, and
never writes to a database. Its sole purpose is to compute and pretty-print
a chart for testing or one-off use.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, cast

from .api.dto import BirthRequest
from .services.chart_service import ChartService, get_default_service


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="bazi-cli", description="Deterministic chart calculation")
    p.add_argument("--birth", help="Local ISO datetime, e.g. 1990-06-15T12:00:00")
    p.add_argument("--tz", "--timezone", dest="timezone", help="IANA timezone, e.g. Asia/Shanghai")
    p.add_argument("--city", help="City name (any string; not geo-resolved)")
    p.add_argument("--country", default="CN")
    p.add_argument("--longitude", type=float, default=None)
    p.add_argument("--latitude", type=float, default=None)
    p.add_argument("--gender", choices=["male", "female", "unspecified"], default="unspecified")
    p.add_argument(
        "--calculation-profile-id",
        default="ziping_standard_v1",
        help="Profile id; must be one of the frozen profiles in contracts/",
    )
    p.add_argument("--idempotency-key", default="cli-default", help="Idempotency key for retries")
    p.add_argument("--out", choices=["json", "text"], default="text")
    p.add_argument("--birth-request", help="Path to a JSON file containing a full BirthRequest")
    return p


def _build_request_from_args(args: argparse.Namespace) -> dict[str, Any]:
    if args.birth_request:
        payload: object = json.loads(Path(args.birth_request).read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise SystemExit("--birth-request must contain a JSON object")
        return cast(dict[str, Any], payload)
    if not (args.birth and args.timezone):
        raise SystemExit("--birth and --tz are required (or pass --birth-request)")
    return {
        "schema_version": "birth-request-v1",
        "gender": args.gender,
        "birth_datetime_local": args.birth,
        "timezone": args.timezone,
        "birthplace": {
            "country": args.country,
            "city": args.city or "Unknown",
            "longitude": args.longitude,
            "latitude": args.latitude,
        },
        "calculation_profile_id": args.calculation_profile_id,
    }


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    req = _build_request_from_args(args)
    br = BirthRequest.model_validate(req)
    svc: ChartService = get_default_service()
    dto, _chart_id, _created = svc.create_chart(request=br, idempotency_key=args.idempotency_key)
    if args.out == "json":
        print(dto.model_dump_json(ensure_ascii=False, indent=2))
    else:
        print(f"chart_id: {dto.chart_id}")
        print(f"status:   {dto.calculation_status}")
        print(f"profile:  {dto.calculation_profile_id}")
        print(f"day_master: {dto.day_master}")
        print("pillars:")
        for p in dto.pillars:
            print(f"  {p.position}: {p.ganzhi} (stem {p.stem}, branch {p.branch})")
        print("engines:")
        for ev in dto.engine_versions:
            print(f"  {ev.engine} v{ev.version} ({ev.took_ms:.2f}ms)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
