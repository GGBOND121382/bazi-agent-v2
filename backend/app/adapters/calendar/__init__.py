"""Calendar adapter package — wraps lunar_python, sxtwl, reference, and pure domain rules.

Adapter contracts:
- CalendarAdapter: returns (pillars, facts, warnings, engine_version).
- CrossEngineComparer: compares two adapters' pillar outputs and reports drift.

SxtwlAdapter is the canonical 复核 engine per the architecture doc; on
environments without a working sxtwl build (Windows without MSVC), the
reference_v1 engine acts as a stand-in 复核. Both implementations live here
so the comparison can be swapped via dependency injection.
"""
from .base import CalendarAdapter, CalendarResult, SolarTermAdapter, SolarTermResult
from .compare import ConflictReport, CrossEngineComparer
from .lunar_python_adapter import LunarPythonAdapter
from .reference_adapter import ReferenceAdapter
from .sxtwl_adapter import SxtwlAdapter

__all__ = [
    "CalendarAdapter",
    "CalendarResult",
    "ConflictReport",
    "CrossEngineComparer",
    "LunarPythonAdapter",
    "ReferenceAdapter",
    "SolarTermAdapter",
    "SolarTermResult",
    "SxtwlAdapter",
]