"""D2, D3, D5, D7, D9: the coefficient record. Never a bare float."""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum


class Status(str, Enum):
    MEASURED = "MEASURED"
    DATABASE = "DATABASE"
    DERIVED = "DERIVED"
    ASSUMED = "ASSUMED"

    @property
    def rank(self) -> int:           # weakest-link ordering for DERIVED
        return {"MEASURED": 0, "DATABASE": 1, "DERIVED": 2, "ASSUMED": 3}[self.value]


class ValidationError(Exception):
    """Raised by loaders with ALL violations at once (spec section 4)."""
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("\n".join(f"  - {e}" for e in errors))


EXTERNAL = "EXTERNAL"
_FIXED_OK = {"fixed"}


def _check_common(d: dict, where: str, errors: list[str], needs_source: bool = True):
    for k in ("value", "unit", "status"):
        if k not in d:
            errors.append(f"{where}: missing '{k}'")
    if "value" in d:
        try:
            v = float(d["value"])
            if v < 0:
                errors.append(f"{where}: value {v} < 0")
        except (TypeError, ValueError):
            errors.append(f"{where}: value {d['value']!r} is not a number")
    st = d.get("status")
    if st is not None and st not in Status.__members__:
        errors.append(f"{where}: status {st!r} not in {list(Status.__members__)}")
    if st == "ASSUMED" and "source" in d and d["source"]:
        pass  # allowed: a note on why it was assumed
    if st and st != "ASSUMED" and needs_source and not d.get("source"):
        errors.append(f"{where}: status {st} requires a 'source'")
    dist = d.get("distribution", "triangular")
    if dist not in {"triangular"} | _FIXED_OK:
        errors.append(f"{where}: distribution {dist!r} not supported (triangular | fixed)")
    if dist == "triangular":
        for k in ("low", "high"):
            if k not in d:
                errors.append(f"{where}: missing '{k}' (triangular needs low/high; use distribution: fixed only for definitional constants)")
        if all(k in d for k in ("low", "value", "high")):
            try:
                lo, v, hi = float(d["low"]), float(d["value"]), float(d["high"])
                if not (lo <= v <= hi):
                    errors.append(f"{where}: bounds do not bracket value: low={lo} value={v} high={hi}")
                if lo < 0:
                    errors.append(f"{where}: low {lo} < 0")
            except (TypeError, ValueError):
                pass
    tags = d.get("tags", {}) or {}
    if not isinstance(tags, dict) or any(not isinstance(k, str) or not isinstance(v, (str, int, float)) for k, v in tags.items()):
        errors.append(f"{where}: tags must be a mapping of string -> scalar")


@dataclass(frozen=True)
class Record:
    """a_ij: units of `input` consumed per unit of `output`."""
    input: str
    output: str
    value: float
    unit: str
    status: Status
    low: float
    high: float
    source: dict = field(default_factory=dict)
    tags: dict = field(default_factory=dict)
    distribution: str = "triangular"
    note: str = ""

    @staticmethod
    def from_dict(d: dict, i: int, errors: list[str]) -> "Record | None":
        where = f"coefficients[{i}]"
        for k in ("input", "output"):
            if k not in d:
                errors.append(f"{where}: missing '{k}'")
        _check_common(d, where, errors)
        if errors:
            return None
        dist = d.get("distribution", "triangular")
        v = float(d["value"])
        lo = float(d.get("low", v)) if dist == "fixed" else float(d["low"])
        hi = float(d.get("high", v)) if dist == "fixed" else float(d["high"])
        return Record(d["input"], d["output"], v, str(d["unit"]), Status(d["status"]), lo, hi,
                      dict(d.get("source") or {}), dict(d.get("tags") or {}), dist, str(d.get("note", "")))


@dataclass(frozen=True)
class ExternalRecord:
    """D3: external energy, kWh per unit of `process` output. Several per process allowed; they sum."""
    process: str
    value: float
    unit: str
    status: Status
    low: float
    high: float
    source: dict = field(default_factory=dict)
    tags: dict = field(default_factory=dict)
    distribution: str = "triangular"
    note: str = ""

    @staticmethod
    def from_dict(d: dict, i: int, errors: list[str]) -> "ExternalRecord | None":
        where = f"external[{i}]"
        if "process" not in d:
            errors.append(f"{where}: missing 'process'")
        _check_common(d, where, errors)
        if d.get("unit") not in (None,) and not str(d.get("unit", "")).startswith("kWh"):
            errors.append(f"{where}: external energy unit must be kWh per process unit, got {d.get('unit')!r}")
        if errors:
            return None
        dist = d.get("distribution", "triangular")
        v = float(d["value"])
        lo = float(d.get("low", v)) if dist == "fixed" else float(d["low"])
        hi = float(d.get("high", v)) if dist == "fixed" else float(d["high"])
        return ExternalRecord(d["process"], v, str(d["unit"]), Status(d["status"]), lo, hi,
                              dict(d.get("source") or {}), dict(d.get("tags") or {}), dist, str(d.get("note", "")))


@dataclass(frozen=True)
class BasketItem:
    """D9: one line of final demand, itself a record of the functional unit."""
    process: str
    quantity: float
    unit: str
    status: Status
    low: float
    high: float
    source: dict = field(default_factory=dict)
    tags: dict = field(default_factory=dict)
    distribution: str = "triangular"
    note: str = ""

    @staticmethod
    def from_dict(d: dict, i: int, errors: list[str]) -> "BasketItem | None":
        where = f"basket.items[{i}]"
        if "process" not in d:
            errors.append(f"{where}: missing 'process'")
        dd = dict(d)
        if "quantity" in dd and "value" not in dd:
            dd["value"] = dd["quantity"]
        _check_common(dd, where, errors)
        if errors:
            return None
        dist = dd.get("distribution", "triangular")
        v = float(dd["value"])
        lo = float(dd.get("low", v)) if dist == "fixed" else float(dd["low"])
        hi = float(dd.get("high", v)) if dist == "fixed" else float(dd["high"])
        return BasketItem(dd["process"], v, str(dd["unit"]), Status(dd["status"]), lo, hi,
                          dict(dd.get("source") or {}), dict(dd.get("tags") or {}), dist, str(dd.get("note", "")))
