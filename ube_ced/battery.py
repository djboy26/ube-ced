"""Section 7: input mutations the core must catch (load/solve refuses) or must change the output hash."""
from __future__ import annotations
import copy, hashlib, json, tempfile
from pathlib import Path
import numpy as np
import yaml
from .system import load_system, load_basket, basket_vector
from .records import ValidationError
from .solve import solve, NotProductive


def _run_hash(sys_dict: dict, basket_dict: dict | None) -> str:
    with tempfile.TemporaryDirectory() as td:
        sp = Path(td) / "s.yaml"; sp.write_text(yaml.safe_dump(sys_dict, sort_keys=False), encoding="utf-8")
        s = load_system(sp)
        if basket_dict:
            bp = Path(td) / "b.yaml"; bp.write_text(yaml.safe_dump(basket_dict, sort_keys=False), encoding="utf-8")
            f = basket_vector(s, load_basket(bp, s))
        else:
            fu = s.declaration.functional_unit
            f = s.unit_demand(fu["process"], float(fu["quantity"]))
        sol = solve(s, f)
        payload = {"ced": round(sol.ced, 12), "eps": [round(float(v), 12) for v in sol.epsilon]}
        return hashlib.sha256(json.dumps(payload).encode()).hexdigest()


def _mutations(d: dict):
    """Yield (name, mutated dict, expectation) where expectation in {'refuse', 'differ'}."""
    procs = d["processes"]; coefs = d["coefficients"]; ext = d["external"]
    def m(fn):
        dd = copy.deepcopy(d); fn(dd); return dd
    # --- must refuse at load/solve ---
    yield "transpose A (swap input/output on every coefficient)", m(lambda dd: [c.update(input=c["output"], output=c["input"]) for c in dd["coefficients"]]), "refuse_or_differ"
    yield "negate one coefficient value", m(lambda dd: dd["coefficients"][0].update(value=-abs(dd["coefficients"][0]["value"]))), "refuse"
    yield "swap two process units", m(lambda dd: (dd["processes"][0].update(unit="ZZZ"))), "refuse"
    yield "non-productive sub-block (self-consumption 1.5)", m(lambda dd: dd["coefficients"].append({"input": procs[0]["name"], "output": procs[0]["name"], "value": 1.5, "low": 1.4, "high": 1.6, "unit": f"{procs[0]['unit']}/{procs[0]['unit']}", "status": "ASSUMED"})), "refuse"
    yield "drop a status", m(lambda dd: dd["coefficients"][0].pop("status")), "refuse"
    yield "drop source on a DATABASE record", m(lambda dd: [c.update(status="DATABASE", source=None) for c in dd["coefficients"][:1]]), "refuse"
    yield "bounds do not bracket value", m(lambda dd: dd["coefficients"][0].update(low=dd["coefficients"][0]["value"] * 2, high=dd["coefficients"][0]["value"] * 3)), "refuse"
    yield "duplicate process name", m(lambda dd: dd["processes"].append(dict(dd["processes"][0]))), "refuse"
    yield "mismatched coefficient unit", m(lambda dd: dd["coefficients"][0].update(unit="banana/kg")), "refuse"
    yield "missing declaration field", m(lambda dd: dd["declaration"].pop("instant")), "refuse"
    yield "external energy not in kWh", m(lambda dd: dd["external"][0].update(unit="MJ/kg")), "refuse"
    # --- must change the output hash ---
    yield "alter one coefficient by +10%", m(lambda dd: dd["coefficients"][0].update(value=dd["coefficients"][0]["value"] * 1.1, high=max(dd["coefficients"][0]["high"], dd["coefficients"][0]["value"] * 1.1))), "differ"
    yield "alter one external value by +10%", m(lambda dd: dd["external"][0].update(value=dd["external"][0]["value"] * 1.1, high=max(dd["external"][0]["high"], dd["external"][0]["value"] * 1.1))), "differ"


def battery(system_path: str | Path, basket_path: str | Path | None = None) -> list[dict]:
    d = yaml.safe_load(Path(system_path).read_text(encoding="utf-8"))
    b = yaml.safe_load(Path(basket_path).read_text(encoding="utf-8")) if basket_path else None
    base = _run_hash(d, b)
    results = []
    for name, dd, expect in _mutations(d):
        try:
            h = _run_hash(dd, b)
            outcome = "accepted_same" if h == base else "accepted_differs"
        except (ValidationError, NotProductive, ValueError, KeyError) as ex:
            outcome = "refused"; h = type(ex).__name__
        if expect == "refuse":
            ok = outcome == "refused"
        elif expect == "differ":
            ok = outcome == "accepted_differs"
        else:
            ok = outcome in ("refused", "accepted_differs")
        results.append({"mutation": name, "expected": expect, "outcome": outcome, "pass": ok, "detail": h})
    return results
