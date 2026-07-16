"""Storage adapters — abstract the persistence boundary.

The application code talks to the `ChartStore` interface; concrete impls
include `InMemoryChartStore` (B3 default) and a future Postgres-backed
implementation (added in a later milestone).
"""
from .base import ChartStore, StoredChart
from .in_memory import InMemoryChartStore

__all__ = ["ChartStore", "InMemoryChartStore", "StoredChart"]