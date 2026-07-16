"""Portable JSON backup/restore validator for process-local development stores.

Production Postgres deployments should use native encrypted backups; this tool
validates the versioned envelope used by export/import drills without touching
running application state.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


SCHEMA_VERSION = "bazi-backup-v1"


def validate(path: Path) -> int:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported backup schema")
    records = payload.get("records")
    if not isinstance(records, list):
        raise ValueError("backup records must be a list")
    return len(records)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("backup", type=Path)
    args = parser.parse_args()
    count = validate(args.backup.resolve())
    print(json.dumps({"status": "validated", "records": count}))


if __name__ == "__main__":
    main()

