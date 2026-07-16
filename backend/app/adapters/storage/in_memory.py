"""In-memory chart store — B3 default. Process-local; not for multi-instance deployments.

The single source of truth for charts during development. A real deployment
swaps this for a Postgres-backed implementation; the `ChartStore` interface
ensures the application code is unchanged.
"""
from __future__ import annotations

import threading
from datetime import UTC, datetime

from ...domain.chart import ChartResult
from .base import ChartStore, StoredChart


class InMemoryChartStore(ChartStore):
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._by_id: dict[str, StoredChart] = {}
        self._by_idem: dict[str, str] = {}  # idempotency_key -> chart_id

    def save(self, chart: ChartResult, owner_id: str = "anonymous") -> StoredChart:
        with self._lock:
            existing = self._by_id.get(chart.chart_id)
            if existing:
                return existing
            stored = StoredChart(
                chart_id=chart.chart_id,
                owner_id=owner_id,
                calculation_status=chart.calculation_status,
                chart=chart,
                created_at=datetime.now(UTC),
            )
            self._by_id[chart.chart_id] = stored
            return stored

    def get(self, chart_id: str) -> StoredChart | None:
        with self._lock:
            return self._by_id.get(chart_id)

    def list_for_owner(self, owner_id: str) -> list[StoredChart]:
        with self._lock:
            return [s for s in self._by_id.values() if s.owner_id == owner_id and not s.deleted]

    def delete(self, chart_id: str) -> bool:
        with self._lock:
            s = self._by_id.get(chart_id)
            if not s or s.deleted:
                return False
            # soft delete so we never lose audit data
            self._by_id[chart_id] = StoredChart(
                chart_id=s.chart_id,
                owner_id=s.owner_id,
                calculation_status=s.calculation_status,
                chart=s.chart,
                created_at=s.created_at,
                deleted=True,
                note=s.note,
            )
            return True

    def find_by_idempotency_key(self, key: str) -> StoredChart | None:
        with self._lock:
            chart_id = self._by_idem.get(key)
            if not chart_id:
                return None
            return self._by_id.get(chart_id)

    def remember_idempotency_key(self, key: str, chart_id: str) -> None:
        with self._lock:
            self._by_idem[key] = chart_id

    def set_note(self, chart_id: str, note: str) -> StoredChart | None:
        with self._lock:
            current = self._by_id.get(chart_id)
            if current is None or current.deleted:
                return None
            updated = StoredChart(
                chart_id=current.chart_id,
                owner_id=current.owner_id,
                calculation_status=current.calculation_status,
                chart=current.chart,
                created_at=current.created_at,
                deleted=current.deleted,
                note=note,
            )
            self._by_id[chart_id] = updated
            return updated


# Module-level singleton (B3 default; production swaps via DI).
_DEFAULT = InMemoryChartStore()


def get_default_store() -> ChartStore:
    return _DEFAULT
