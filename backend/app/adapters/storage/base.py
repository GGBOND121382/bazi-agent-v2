"""Storage interface — keeps persistence details out of services."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime

from ...domain.chart import ChartResult


@dataclass(frozen=True, slots=True)
class StoredChart:
    chart_id: str
    owner_id: str  # currently 'anonymous'
    calculation_status: str
    chart: ChartResult
    created_at: datetime
    deleted: bool = False
    note: str = ""


class ChartStore(ABC):
    @abstractmethod
    def save(self, chart: ChartResult, owner_id: str = "anonymous") -> StoredChart: ...

    @abstractmethod
    def get(self, chart_id: str) -> StoredChart | None: ...

    @abstractmethod
    def list_for_owner(self, owner_id: str) -> list[StoredChart]: ...

    @abstractmethod
    def delete(self, chart_id: str) -> bool: ...

    @abstractmethod
    def find_by_idempotency_key(self, key: str) -> StoredChart | None: ...

    @abstractmethod
    def remember_idempotency_key(self, key: str, chart_id: str) -> None: ...

    @abstractmethod
    def set_note(self, chart_id: str, note: str) -> StoredChart | None: ...
