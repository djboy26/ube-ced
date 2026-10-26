"""C8: every ASSUMED record at x0.5 and x2; report the swing, largest first."""
from __future__ import annotations
from dataclasses import replace
import numpy as np
from .system import System
from .records import Status
from .solve import solve, NotProductive


def stress(system: System, f: np.ndarray) -> list[dict]:
    base = solve(system, f).ced
    rows = []
    for i, r in enumerate(system.records):
        if r.status != Status.ASSUMED:
            continue
        res = {"kind": "coefficient", "key": f"{r.input} -> {r.output}", "value": r.value, "unit": r.unit}
        for k, lab in ((0.5, "x0.5"), (2.0, "x2")):
            s = system.copy()
            s.records = [replace(rr, value=rr.value * k) if j == i else rr for j, rr in enumerate(system.records)]
            try:
                res[lab] = solve(s, f).ced
            except NotProductive:
                res[lab] = float("nan")
        rows.append(res)
    for i, x in enumerate(system.external):
        if x.status != Status.ASSUMED:
            continue
        res = {"kind": "external", "key": f"EXTERNAL -> {x.process}" + (f" {x.tags}" if x.tags else ""), "value": x.value, "unit": x.unit}
        for k, lab in ((0.5, "x0.5"), (2.0, "x2")):
            s = system.copy()
            s.external = [replace(xx, value=xx.value * k) if j == i else xx for j, xx in enumerate(system.external)]
            res[lab] = solve(s, f).ced
        rows.append(res)
    for r in rows:
        r["base"] = base
        r["swing"] = max(abs(r["x2"] - base), abs(r["x0.5"] - base)) if not any(np.isnan(v) for v in (r["x2"], r["x0.5"])) else float("inf")
        r["swing_pct"] = 100 * r["swing"] / base if base else float("nan")
    rows.sort(key=lambda r: -r["swing"])
    return rows
