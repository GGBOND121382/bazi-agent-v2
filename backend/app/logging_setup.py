"""Persistent rotating logs for the local application."""
from __future__ import annotations

import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from .persistence import log_dir

_CONFIGURED = False


def configure_logging() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    directory = log_dir()
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s", datefmt="%Y-%m-%dT%H:%M:%S%z"
    )
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    handler = RotatingFileHandler(
        directory / "application.log", maxBytes=10 * 1024 * 1024, backupCount=10, encoding="utf-8"
    )
    handler.setFormatter(formatter)
    root.addHandler(handler)
    error_handler = RotatingFileHandler(
        directory / "error.log", maxBytes=10 * 1024 * 1024, backupCount=10, encoding="utf-8"
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)
    root.addHandler(error_handler)
    _CONFIGURED = True


def append_llm_trace(trace: dict[str, Any]) -> None:
    path: Path = log_dir() / "llm_calls.jsonl"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(trace, ensure_ascii=False, default=str) + "\n")
