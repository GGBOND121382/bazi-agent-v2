"""Durable SQLite chart store used by the local application."""
from __future__ import annotations

import pickle
from datetime import datetime

from ...domain.chart import ChartResult
from ...persistence import connect
from .base import ChartStore, StoredChart


class SQLiteChartStore(ChartStore):
    def save(self, chart: ChartResult, owner_id: str = "anonymous") -> StoredChart:
        from datetime import UTC

        created_at = datetime.now(UTC)
        with connect() as conn:
            conn.execute(
                """INSERT OR IGNORE INTO charts
                (chart_id, owner_id, calculation_status, chart_blob, created_at)
                VALUES (?, ?, ?, ?, ?)""",
                (
                    chart.chart_id,
                    owner_id,
                    chart.calculation_status,
                    pickle.dumps(chart, protocol=pickle.HIGHEST_PROTOCOL),
                    created_at.isoformat(),
                ),
            )
        stored = self.get(chart.chart_id)
        assert stored is not None
        return stored

    def get(self, chart_id: str) -> StoredChart | None:
        with connect() as conn:
            row = conn.execute("SELECT * FROM charts WHERE chart_id=?", (chart_id,)).fetchone()
        if row is None:
            return None
        return StoredChart(
            chart_id=str(row["chart_id"]),
            owner_id=str(row["owner_id"]),
            calculation_status=str(row["calculation_status"]),
            chart=pickle.loads(row["chart_blob"]),
            created_at=datetime.fromisoformat(str(row["created_at"])),
            deleted=bool(row["deleted"]),
            note=str(row["note"]),
        )

    def list_for_owner(self, owner_id: str) -> list[StoredChart]:
        query = "SELECT chart_id FROM charts WHERE deleted=0"
        params: tuple[object, ...] = ()
        if owner_id != "*":
            query += " AND owner_id=?"
            params = (owner_id,)
        query += " ORDER BY created_at DESC"
        with connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [item for row in rows if (item := self.get(str(row["chart_id"]))) is not None]

    def delete(self, chart_id: str) -> bool:
        with connect() as conn:
            result = conn.execute(
                "UPDATE charts SET deleted=1 WHERE chart_id=? AND deleted=0", (chart_id,)
            )
        return result.rowcount > 0

    def find_by_idempotency_key(self, key: str) -> StoredChart | None:
        with connect() as conn:
            row = conn.execute(
                "SELECT chart_id FROM chart_idempotency WHERE idempotency_key=?", (key,)
            ).fetchone()
        return self.get(str(row["chart_id"])) if row else None

    def remember_idempotency_key(self, key: str, chart_id: str) -> None:
        with connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO chart_idempotency(idempotency_key, chart_id) VALUES (?, ?)",
                (key, chart_id),
            )

    def set_note(self, chart_id: str, note: str) -> StoredChart | None:
        with connect() as conn:
            result = conn.execute(
                "UPDATE charts SET note=? WHERE chart_id=? AND deleted=0", (note, chart_id)
            )
        return self.get(chart_id) if result.rowcount else None
