"""Entrypoint for uvicorn.

Usage:
    uvicorn app.main:app --reload
"""
from __future__ import annotations

from .api.app_factory import create_app

app = create_app()