"""D1, D4, D8: the System, its declaration, YAML loading with all-at-once validation, input hashing."""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
import hashlib
import numpy as np
import yaml
from .records import Record, ExternalRecord, BasketItem, Status, ValidationError, EXTERNAL

REQUIRED_DECL = ("functional_unit", "place", "instant", "boundary_notes", "conventions")


@dataclass(frozen=True)
class Declaration:
    functional_unit: dict          # {process, quantity, unit}
    place: str
    instant: str
    boundary_notes: str
    conventions: tuple            # tuple of {name, value, reason} dicts

    def as_dict(self) -> dict:
        return {"functional_unit": dict(self.functional_unit), "place": self.place, "instant": self.instant,
                "boundary_notes": self.boundary_notes, "conventions": [dict(c) for c in self.conventions]}

    def differs_from(self, other: "Declaration") -> list[str]:
        a, b = self.as_dict(), other.as_dict()
        return [k for k in a if a[k] != b[k]]


@dataclass
class System:
    name: str
    processes: list[str]
    units: list[str]
    records: list[Record]
    external: list[ExternalRecord]
    declaration: Declaration
    correlation_groups: dict = field(default_factory=dict)   # name -> list of record ids
    source_files: dict = field(default_factory=dict)          # path -> sha256
    frozen: bool = False

    # ---- derived arrays -------------------------------------------------
    @property
    def n(self) -> int:
        return len(self.processes)

    def index(self, name: str) -> int:
        return self.processes.index(name)

    @property
    def A(self) -> np.ndarray:
        A = np.zeros((self.n, self.n))
        for r in self.records:
            A[self.index(r.input), self.index(r.output)] += r.value
        return A

    @property
    def e(self) -> np.ndarray:
        e = np.zeros(self.n)
        for x in self.external:
            e[self.index(x.process)] += x.value
        return e

    def e_by_tag(self, key: str) -> dict[str, np.ndarray]:
        """C5: external vector split by the value of tag `key`. Untagged records go to '(untagged)'."""
        out: dict[str, np.ndarray] = {}
        for x in self.external:
            val = str(x.tags.get(key, "(untagged)"))
            out.setdefault(val, np.zeros(self.n))[self.index(x.process)] += x.value
        return out

    @property
    def tag_keys(self) -> list[str]:
        keys = set()
        for x in self.external:
            keys.update(x.tags.keys())
        return sorted(keys)

    def unit_demand(self, name: str, amount: float = 1.0) -> np.ndarray:
        f = np.zeros(self.n); f[self.index(name)] = amount; return f

    def zero_count(self) -> int:
        return int((self.A == 0).sum())

    def copy(self) -> "System":
        return System(self.name, list(self.processes), list(self.units), list(self.records), list(self.external),
                      self.declaration, dict(self.correlation_groups), dict(self.source_files), False)


# ---- loading -------------------------------------------------------------

def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_system(path: str | Path) -> System:
    path = Path(path)
    d = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    errors: list[str] = []

    name = d.get("name") or path.stem
    procs = d.get("processes") or []
    if not procs:
        errors.append("processes: empty")
    names, units = [], []
    for i, p in enumerate(procs):
        if not isinstance(p, dict) or "name" not in p or "unit" not in p:
            errors.append(f"processes[{i}]: needs 'name' and 'unit'"); continue
        if p["name"] in names:
            errors.append(f"processes[{i}]: duplicate process name {p['name']!r}")
        if p["name"] == EXTERNAL:
            errors.append(f"processes[{i}]: {EXTERNAL!r} is reserved")
        names.append(p["name"]); units.append(str(p["unit"]))
    unit_of = dict(zip(names, units))

    # declaration (D4)
    decl_d = d.get("declaration") or {}
    for k in REQUIRED_DECL:
        if k not in decl_d:
            errors.append(f"declaration: missing '{k}' (spec D4)")
    fu = decl_d.get("functional_unit") or {}
    if isinstance(fu, dict):
        for k in ("process", "quantity", "unit"):
            if k not in fu:
                errors.append(f"declaration.functional_unit: missing '{k}'")
        if fu.get("process") and names and fu["process"] not in names:
            errors.append(f"declaration.functional_unit.process {fu['process']!r} is not a process")
    else:
        errors.append("declaration.functional_unit must be a mapping {process, quantity, unit}")
    conv = decl_d.get("conventions")
    if conv is not None:
        if not isinstance(conv, list):
            errors.append("declaration.conventions must be a list of {name, value, reason}")
        else:
            for i, c in enumerate(conv):
                if not isinstance(c, dict) or not all(k in c for k in ("name", "value", "reason")):
                    errors.append(f"declaration.conventions[{i}]: needs name, value, reason")

    # coefficients (D2)
    records: list[Record] = []
    for i, cd in enumerate(d.get("coefficients") or []):
        sub: list[str] = []
        r = Record.from_dict(cd, i, sub)
        errors.extend(sub)
        if r is None:
            continue
        if r.input not in unit_of:
            errors.append(f"coefficients[{i}]: input {r.input!r} is not a process")
        if r.output not in unit_of:
            errors.append(f"coefficients[{i}]: output {r.output!r} is not a process")
        if r.input in unit_of and r.output in unit_of:
            expect = f"{unit_of[r.input]}/{unit_of[r.output]}"
            if r.unit != expect:
                errors.append(f"coefficients[{i}] ({r.input} -> {r.output}): unit {r.unit!r} must be {expect!r}")
        records.append(r)

    # external (D3)
    external: list[ExternalRecord] = []
    for i, xd in enumerate(d.get("external") or []):
        sub = []
        x = ExternalRecord.from_dict(xd, i, sub)
        errors.extend(sub)
        if x is None:
            continue
        if x.process not in unit_of:
            errors.append(f"external[{i}]: process {x.process!r} is not a process")
        else:
            expect = f"kWh/{unit_of[x.process]}"
            if x.unit != expect:
                errors.append(f"external[{i}] ({x.process}): unit {x.unit!r} must be {expect!r}")
        external.append(x)

    groups = d.get("correlation_groups") or {}
    if not isinstance(groups, dict):
        errors.append("correlation_groups must be a mapping name -> list of record keys")

    if errors:
        raise ValidationError(errors)

    decl = Declaration(dict(fu), str(decl_d["place"]), str(decl_d["instant"]), str(decl_d["boundary_notes"]),
                       tuple(dict(c) for c in (conv or [])))
    s = System(name, names, units, records, external, decl, dict(groups), {str(path): _sha(path)})
    return s


def load_basket(path: str | Path, system: System) -> list[BasketItem]:
    path = Path(path)
    d = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    errors: list[str] = []
    items: list[BasketItem] = []
    for i, it in enumerate(d.get("items") or []):
        sub = []
        b = BasketItem.from_dict(it, i, sub)
        errors.extend(sub)
        if b is None:
            continue
        if b.process not in system.processes:
            errors.append(f"basket.items[{i}]: process {b.process!r} not in system")
        elif b.unit != system.units[system.index(b.process)]:
            errors.append(f"basket.items[{i}] ({b.process}): unit {b.unit!r} must be {system.units[system.index(b.process)]!r}")
        items.append(b)
    if not items:
        errors.append("basket: no items")
    if errors:
        raise ValidationError(errors)
    system.source_files[str(path)] = _sha(path)
    return items


def basket_vector(system: System, items: list[BasketItem]) -> np.ndarray:
    f = np.zeros(system.n)
    for b in items:
        f[system.index(b.process)] += b.quantity
    return f


def freeze_hashes(system: System) -> dict:
    """C11: the hashes recorded at load, for the report."""
    return dict(system.source_files)
