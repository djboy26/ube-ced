import numpy as np, pytest, yaml, tempfile
from pathlib import Path
from ube_ced import (load_system, load_basket, solve, stress, propagate, scenario, battery, conform,
                     build_report, write_report, ValidationError, Status)
from ube_ced.system import basket_vector
from ube_ced.solve import leontief_inverse, tier_series, NotProductive, hawkins_simon

EX = Path(__file__).parent.parent / "examples" / "reference_condition"

@pytest.fixture
def sysx():
    return load_system(EX / "system.yaml")

def fu_vec(s):
    fu = s.declaration.functional_unit
    return s.unit_demand(fu["process"], float(fu["quantity"]))

# ---- C1/C2: scalar case and productivity
def test_scalar_geometric_series():
    for r in (0.0, 0.3, 0.9):
        A = np.array([[r]]); L = leontief_inverse(A)
        assert L[0, 0] == pytest.approx(1 / (1 - r))

def test_hawkins_simon_refuses():
    assert not hawkins_simon(np.array([[0.0, 2.0], [2.0, 0.0]]))[0]
    with pytest.raises(NotProductive):
        leontief_inverse(np.array([[1.2]]))

# ---- C3/C4/C5/C6/C7 on the example
def test_tiers_sectors_tags_sum_to_total(sysx):
    f = fu_vec(sysx); sol = solve(sysx, f)
    assert sum(sol.tiers) == pytest.approx(sol.ced, rel=1e-9)
    assert sum(sol.by_sector.values()) == pytest.approx(sol.ced, rel=1e-9)
    for key, parts in sol.by_tag.items():
        assert sum(parts.values()) == pytest.approx(sol.ced, rel=1e-9), key
    assert sol.reconciliation_gap < 1e-9

def test_linearity(sysx):
    f1, f2 = sysx.unit_demand("Bread", 2.0), sysx.unit_demand("Steel", 0.5)
    assert solve(sysx, f1 + f2).ced == pytest.approx(solve(sysx, f1).ced + solve(sysx, f2).ced)

def test_inverse_equals_series(sysx):
    L = leontief_inverse(sysx.A); S, Ak = np.zeros_like(L), np.eye(sysx.n)
    for _ in range(80): S += Ak; Ak = Ak @ sysx.A
    assert np.allclose(L, S, atol=1e-10)

# ---- D2/D4 validation: all errors at once
def test_validation_lists_all_errors(tmp_path):
    d = yaml.safe_load((EX / "system.yaml").read_text())
    d["declaration"].pop("place"); d["coefficients"][0].pop("status"); d["coefficients"][1]["unit"] = "x/y"
    p = tmp_path / "bad.yaml"; p.write_text(yaml.safe_dump(d))
    with pytest.raises(ValidationError) as ei:
        load_system(p)
    msg = str(ei.value)
    assert "declaration: missing 'place'" in msg and "missing 'status'" in msg and "must be" in msg

def test_basket_unit_mismatch_refused(sysx, tmp_path):
    p = tmp_path / "b.yaml"; p.write_text(yaml.safe_dump({"items": [{"process": "Bread", "quantity": 1, "low": 0.5, "high": 2, "unit": "tonne", "status": "ASSUMED"}]}))
    with pytest.raises(ValidationError):
        load_basket(p, sysx)

# ---- C8 stress
def test_stress_sorted_and_brackets(sysx):
    rows = stress(sysx, fu_vec(sysx))
    assert rows and all(rows[i]["swing"] >= rows[i + 1]["swing"] for i in range(len(rows) - 1))
    r = rows[0]; assert r["x0.5"] <= r["base"] <= r["x2"]

# ---- C9 propagation
def test_propagate_floor_and_interval(sysx):
    f = fu_vec(sysx)
    with pytest.raises(ValueError):
        propagate(sysx, f, draws=100)
    mc = propagate(sysx, f, draws=10_000, seed=3)
    c = solve(sysx, f).ced
    assert mc["p05"] < c < mc["p95"] and mc["rejected"] == 0 and "diesel_chain" in mc["correlation_groups"]

def test_propagate_deterministic(sysx):
    f = fu_vec(sysx)
    a, b = propagate(sysx, f, draws=10_000, seed=7), propagate(sysx, f, draws=10_000, seed=7)
    assert a["median"] == b["median"] and a["p95"] == b["p95"]

# ---- D10 scenario leaves the original untouched
def test_scenario_is_a_copy(sysx):
    s2 = scenario(sysx, "cheap heat", external={"SpaceHeat": 1.0})
    assert sysx.e[sysx.index("SpaceHeat")] == 1.25 and s2.e[s2.index("SpaceHeat")] == 1.0
    assert solve(s2, fu_vec(s2)).ced < solve(sysx, fu_vec(sysx)).ced

# ---- section 7 battery, section 6 conformance
def test_battery_all_pass():
    res = battery(EX / "system.yaml", EX / "basket_vulnerable_day.yaml")
    assert all(r["pass"] for r in res), [r for r in res if not r["pass"]]

def test_example_conforms():
    assert conform(EX)["pass"]

# ---- section 5 report
def test_report_writes_three_files(sysx, tmp_path):
    rep = build_report(sysx, None, draws=10_000)
    paths = write_report(rep, tmp_path)
    assert all(Path(p).exists() for p in paths.values())
    html = Path(paths["html"]).read_text(encoding="utf-8")
    assert "Backward-opening chain" in html and "loop a tree cannot draw" in html and "<svg" in html
    assert rep["headline"]["interval"]["p05"] < rep["headline"]["central"] < rep["headline"]["interval"]["p95"]
