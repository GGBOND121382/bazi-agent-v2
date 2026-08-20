from __future__ import annotations

import os
import tempfile

_TEST_RUNTIME = tempfile.mkdtemp(prefix="bazi-agent-tests-")
os.environ.setdefault("BAZI_RUNTIME_DIR", _TEST_RUNTIME)
os.environ.setdefault("BAZI_AUTH_DISABLED", "true")

"""Backend pytest configuration.

- Ensure the `app` package is importable when running `pytest` from the
  repo root (`handoff_v2/`).
- Add the workspace root to sys.path so `app` and `contracts` resolve.
- Define a session-scoped fixture for the calculation profile.
"""
import sys
from pathlib import Path

import pytest

# Make `backend/` importable when pytest is invoked from anywhere.
_BACKEND = Path(__file__).resolve().parent
_REPO = _BACKEND.parent
for p in (_BACKEND, _REPO):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))


@pytest.fixture(scope="session")
def profile():
    from app.domain.profile import load_profile

    return load_profile()