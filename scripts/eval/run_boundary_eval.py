"""Physically isolated H1 evaluation reader.

Production modules must never import this script. It reports aggregate schema
health only and never copies evaluation rows into RAG or application storage.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def evaluate(path: Path) -> dict[str, int]:
    if path.parent.name != "evaluation":
        raise ValueError("only the isolated evaluation directory is accepted")
    total = 0
    valid_json = 0
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                continue
            total += 1
            payload = json.loads(line)
            if isinstance(payload, dict):
                valid_json += 1
    return {"total": total, "valid_json": valid_json}


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        type=Path,
        default=root / "contracts" / "evaluation" / "boundary_test_inputs.jsonl",
    )
    args = parser.parse_args()
    print(json.dumps(evaluate(args.input.resolve()), ensure_ascii=False))


if __name__ == "__main__":
    main()

