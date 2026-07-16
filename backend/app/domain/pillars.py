"""Stem / Branch / Pillar / FourPillars — pure data types for the four 柱.

Built from the contracts/core_tables seed; no I/O.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Final, cast

CORE_TABLES = Path(__file__).resolve().parents[3] / "contracts" / "core_tables"


@lru_cache(maxsize=1)
def _stems() -> tuple[str, ...]:
    raw = _read_json_object(CORE_TABLES / "heavenly_stems.json")
    # Schema: {version, items: [{name, index, yin_yang, element}]}
    items = cast(list[dict[str, object]], raw["items"])
    return tuple(str(item["name"]) for item in items)


@lru_cache(maxsize=1)
def _branches() -> tuple[str, ...]:
    raw = _read_json_object(CORE_TABLES / "earthly_branches.json")
    items = cast(list[dict[str, object]], raw["items"])
    return tuple(str(item["name"]) for item in items)


@lru_cache(maxsize=1)
def _hidden_stems_table() -> dict[str, list[dict[str, object]]]:
    raw = _read_json_object(CORE_TABLES / "hidden_stems.json")
    return cast(dict[str, list[dict[str, object]]], raw["items"])


@lru_cache(maxsize=1)
def _ten_gods_matrix() -> dict[str, dict[str, str]]:
    raw = _read_json_object(CORE_TABLES / "ten_gods_matrix.json")
    return cast(dict[str, dict[str, str]], raw["items"])


@lru_cache(maxsize=1)
def _stem_branch_relations() -> dict[str, Any]:
    return _read_json_object(CORE_TABLES / "stem_branch_relations.json")


@lru_cache(maxsize=1)
def _five_elements() -> dict[str, str]:
    """Map character → 五行.

    Derived from heavenly_stems.json and earthly_branches.json (each carries
    an `element` field). five_elements.json is supplementary (it documents
    the 五行 generate/control cycles); we don't depend on it for the lookup.
    """
    stems_raw = _read_json_object(CORE_TABLES / "heavenly_stems.json")
    branches_raw = _read_json_object(CORE_TABLES / "earthly_branches.json")
    mapping: dict[str, str] = {}
    for item in cast(list[dict[str, object]], stems_raw.get("items", [])):
        mapping[str(item["name"])] = str(item["element"])
    for item in cast(list[dict[str, object]], branches_raw.get("items", [])):
        mapping[str(item["name"])] = str(item["element"])
    return mapping


def _read_json_object(path: Path) -> dict[str, Any]:
    payload: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise PillarError(f"core table root must be an object: {path.name}")
    return cast(dict[str, Any], payload)


class PillarError(ValueError):
    """Raised when a stem/branch pair is invalid (out of 60 甲子 cycle)."""


# The 60 甲子 cycle as (stem_index, branch_index) pairs (both 0-indexed).
# A pillar is valid iff (stem_index - branch_index) % 12 == 0.
HEAVENLY_STEMS: Final[tuple[str, ...]] = _stems()
EARTHLY_BRANCHES: Final[tuple[str, ...]] = _branches()


@dataclass(frozen=True, slots=True)
class Stem:
    char: str

    def __post_init__(self) -> None:
        if self.char not in HEAVENLY_STEMS:
            raise PillarError(f"not a heavenly stem: {self.char!r}")

    @property
    def index(self) -> int:
        return HEAVENLY_STEMS.index(self.char)

    @property
    def element(self) -> str:
        return _five_elements()[self.char]

    @property
    def yin_yang(self) -> str:
        return "yang" if self.index % 2 == 0 else "yin"

    def __str__(self) -> str:
        return self.char


@dataclass(frozen=True, slots=True)
class Branch:
    char: str

    def __post_init__(self) -> None:
        if self.char not in EARTHLY_BRANCHES:
            raise PillarError(f"not an earthly branch: {self.char!r}")

    @property
    def index(self) -> int:
        return EARTHLY_BRANCHES.index(self.char)

    @property
    def element(self) -> str:
        return _five_elements()[self.char]

    @property
    def zodiac(self) -> str:
        rel = cast(dict[str, str], _stem_branch_relations().get("zodiac", {}))
        return rel.get(self.char, "")

    def __str__(self) -> str:
        return self.char


@dataclass(frozen=True, slots=True)
class HiddenStem:
    stem: Stem
    ten_god: str  # resolved against day master (None means: resolver will fill)

    @classmethod
    def from_dict(cls, raw: dict[str, object], day_master: Stem | None = None) -> HiddenStem:
        s = Stem(str(raw["stem"]))
        tg = raw.get("ten_god")
        if tg is None and day_master is not None:
            tg = ten_god_of(day_master, s)
        elif tg is None:
            tg = ""
        return cls(stem=s, ten_god=str(tg))


@dataclass(frozen=True, slots=True)
class Pillar:
    """One of the four 柱: e.g. 甲子."""

    stem: Stem
    branch: Branch

    def __post_init__(self) -> None:
        # 60-甲子 cycle: stem and branch both advance together, with stem wrapping
        # every 10 and branch every 12. The resulting sequence satisfies
        # (stem_index - branch_index) % 2 == 0 (i.e. stem and branch share parity).
        if (self.stem.index - self.branch.index) % 2 != 0:
            raise PillarError(
                f"invalid pillar: {self.stem.char}{self.branch.char} "
                f"(stem idx={self.stem.index}, branch idx={self.branch.index})"
            )

    @property
    def ganzhi(self) -> str:
        return f"{self.stem}{self.branch}"

    @property
    def nayin(self) -> str:
        """纳音 — 60-year cycle, two-character 五行 assignment."""
        # The 60 nayin pairs are indexed by the 甲子 cycle position.
        # We compute that from the stem index (since stems and branches move in lock-step).
        pos = self.stem.index  # since stem-branch are aligned in 60 甲子
        rel = cast(list[str], _stem_branch_relations().get("nayin", []))
        if not rel:
            return ""
        return rel[pos % len(rel)]

    def hidden_stems(self) -> list[Stem]:
        return [Stem(str(h["stem"])) for h in _hidden_stems_table()[self.branch.char]]

    def ten_god_of_stem(self, day_master: Stem) -> str:
        return ten_god_of(day_master, self.stem)

    def __str__(self) -> str:
        return self.ganzhi


def ten_god_of(day_master: Stem, other: Stem) -> str:
    """Resolve 十神 given day master and target stem (pure lookup)."""
    matrix = _ten_gods_matrix()
    dm_char = day_master.char
    o_char = other.char
    if dm_char not in matrix:
        return ""
    row = matrix[dm_char]
    return row.get(o_char, "")


@dataclass(frozen=True, slots=True)
class FourPillars:
    """The four 柱 in canonical order: year, month, day, hour."""

    year: Pillar
    month: Pillar
    day: Pillar
    hour: Pillar

    @property
    def day_master(self) -> Stem:
        return self.day.stem

    def as_list(self) -> list[Pillar]:
        return [self.year, self.month, self.day, self.hour]

    def to_dict(self) -> dict[str, dict[str, str]]:
        return {
            "year": {"ganzhi": str(self.year), "stem": str(self.year.stem), "branch": str(self.year.branch)},
            "month": {"ganzhi": str(self.month), "stem": str(self.month.stem), "branch": str(self.month.branch)},
            "day": {"ganzhi": str(self.day), "stem": str(self.day.stem), "branch": str(self.day.branch)},
            "hour": {"ganzhi": str(self.hour), "stem": str(self.hour.stem), "branch": str(self.hour.branch)},
        }
