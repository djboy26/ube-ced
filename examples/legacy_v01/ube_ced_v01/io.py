"""YAML loading. The file is the unit of provenance: every number carries its source there."""
from __future__ import annotations
from pathlib import Path
import numpy as np
import yaml
from .core import System


def load_system(path: str | Path) -> System:
    d = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    procs = d["processes"]
    names = [p["name"] for p in procs]
    units = [p["unit"] for p in procs]
    n = len(names)
    A = np.zeros((n, n))
    for entry in d.get("coefficients", []):
        i, j = names.index(entry["input"]), names.index(entry["output"])
        A[i, j] = float(entry["value"])
    e_d = np.array([float(p.get("e_d", 0.0)) for p in procs])
    meta = {k: v for k, v in d.items() if k not in ("processes", "coefficients")}
    return System(names, units, A, e_d, meta)


def load_scenarios(path: str | Path) -> dict:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))
