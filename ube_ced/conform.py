"""Section 6: a specific model reproduces its published results through the core."""
from __future__ import annotations
from pathlib import Path
import re
import yaml
from .system import load_system, load_basket, basket_vector
from .solve import solve

CONFORM_TOL = 1e-6   # S2, settled 26 Oct 2026
_SOLVER_PATTERNS = re.compile(r"linalg\.(inv|solve)\s*\(|np\.linalg|numpy\.linalg|scipy\.linalg|def\s+leontief", re.I)


def conform(model_dir: str | Path) -> dict:
    model_dir = Path(model_dir)
    cfg = yaml.safe_load((model_dir / "conformance.yaml").read_text(encoding="utf-8"))
    out = {"model": str(model_dir), "cases": [], "second_solver_hits": [], "pass": True}
    # S1 heuristic scan (S2 is the real enforcement)
    for py in model_dir.rglob("*.py"):
        if _SOLVER_PATTERNS.search(py.read_text(encoding="utf-8", errors="ignore")):
            out["second_solver_hits"].append(str(py.relative_to(model_dir)))
    for case in cfg.get("cases", []):
        s = load_system(model_dir / case["system"])
        if case.get("basket"):
            f = basket_vector(s, load_basket(model_dir / case["basket"], s))
        else:
            fu = s.declaration.functional_unit
            f = s.unit_demand(fu["process"], float(fu["quantity"]))
        got = solve(s, f).ced
        exp = float(case["expected_kwh"])
        rel = abs(got - exp) / exp if exp else abs(got - exp)
        ok = rel <= cfg.get("tolerance", CONFORM_TOL)
        out["cases"].append({"name": case.get("name", case["system"]), "expected": exp, "got": got, "rel_gap": rel, "pass": ok})
        out["pass"] &= ok
    if out["second_solver_hits"]:
        out["pass"] = False
    return out
