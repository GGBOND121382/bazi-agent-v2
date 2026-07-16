#!/usr/bin/env python3
"""Download registered external sources into isolated buckets.

This utility intentionally does not approve any downloaded corpus. Every non-evaluation
source is placed in quarantine. Run from a networked environment after reviewing the
manifest and each source's terms.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import urllib.request
import zipfile
from pathlib import Path
from typing import Any


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def safe_extract_zip(zip_path: Path, dest: Path) -> None:
    dest_resolved = dest.resolve()
    with zipfile.ZipFile(zip_path) as zf:
        for member in zf.infolist():
            target = (dest / member.filename).resolve()
            if dest_resolved not in target.parents and target != dest_resolved:
                raise ValueError(f"Unsafe archive member: {member.filename}")
        zf.extractall(dest)


def download_github(source: dict[str, Any], target: Path) -> dict[str, Any]:
    archive_url = source["archive_url"]
    target.mkdir(parents=True, exist_ok=True)
    archive = target / "source.zip"
    urllib.request.urlretrieve(archive_url, archive)
    extract_dir = target / "repository"
    safe_extract_zip(archive, extract_dir)
    return {"archive": str(archive), "sha256": sha256_file(archive)}


def download_huggingface(source: dict[str, Any], target: Path) -> dict[str, Any]:
    try:
        from huggingface_hub import snapshot_download
    except ImportError as exc:
        raise RuntimeError("Install huggingface_hub before downloading HF datasets") from exc

    target.mkdir(parents=True, exist_ok=True)
    local = snapshot_download(
        repo_id=source["download_id"],
        repo_type="dataset",
        local_dir=target / "snapshot",
    )
    return {"snapshot": str(local)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--dest", type=Path, required=True)
    parser.add_argument("--source-id")
    parser.add_argument("--usage")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    selected = manifest["sources"]
    if args.source_id:
        selected = [s for s in selected if s["source_id"] == args.source_id]
    if args.usage:
        selected = [s for s in selected if s["intended_use"] == args.usage]
    if not selected:
        raise SystemExit("No sources selected")

    args.dest.mkdir(parents=True, exist_ok=True)
    run_log: list[dict[str, Any]] = []

    for source in selected:
        bucket = source["default_bucket"]
        safe_name = source["name"].replace("/", "__").replace("《", "").replace("》", "")
        target = args.dest / bucket / safe_name
        if target.exists():
            if not args.overwrite:
                run_log.append({"source_id": source["source_id"], "status": "skipped_exists"})
                continue
            shutil.rmtree(target)

        try:
            if source["source_type"] == "huggingface_dataset":
                details = download_huggingface(source, target)
            elif source["source_type"] == "github_repository":
                details = download_github(source, target)
            else:
                run_log.append({
                    "source_id": source["source_id"],
                    "status": "manual_required",
                    "url": source["url"],
                })
                continue

            (target / "SOURCE_METADATA.json").write_text(
                json.dumps(source, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            run_log.append({"source_id": source["source_id"], "status": "downloaded", **details})
        except Exception as exc:  # preserve partial run results
            run_log.append({"source_id": source["source_id"], "status": "failed", "error": repr(exc)})

    log_path = args.dest / "download_run.json"
    log_path.write_text(json.dumps(run_log, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(log_path)


if __name__ == "__main__":
    main()
