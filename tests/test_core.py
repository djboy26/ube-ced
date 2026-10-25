import numpy as np, pytest
from pathlib import Path
from ube_ced import (System, load_system, leontief_inverse, ced, ced_vector,
                     tier_decomposition, sector_decomposition, spectral_radius, hawkins_simon_ok,
                     Basket, basket_ced, monte_carlo)

DATA = Path(__file__).parent.parent / "data" / "tomato_sixsector_2026-04.yaml"

@pytest.fixture
def tomato():
    return load_system(DATA)

def test_scalar_case_matches_geometric_series():
    # one sector consuming r of its own output: CED = e / (1 - r)
    for r in (0.0, 0.1, 0.5, 0.9):
        s = System(["x"], ["u"], np.array([[r]]), np.array([3.0]))
        assert ced(s, np.array([1.0])) == pytest.approx(3.0 / (1 - r))

def test_inverse_equals_power_series(tomato):
    L = leontief_inverse(tomato.A)
    S, Ak = np.zeros_like(L), np.eye(tomato.n)
    for _ in range(60):
        S += Ak; Ak = Ak @ tomato.A
    assert np.allclose(L, S, atol=1e-10)

def test_tiers_sum_to_total(tomato):
    f = tomato.unit_demand("Tomato")
    assert sum(tier_decomposition(tomato, f, max_tier=60, tol=0)) == pytest.approx(ced(tomato, f), rel=1e-9)

def test_sectors_sum_to_total(tomato):
    f = tomato.unit_demand("Tomato")
    assert sum(sector_decomposition(tomato, f).values()) == pytest.approx(ced(tomato, f))

def test_tomato_pinned_values(tomato):
    # Pinned to the matrix as transcribed from the April 2026 note. NOT the note's
    # printed 8.74; see docs/ERRATA.md. If the matrix changes these must change.
    f = tomato.unit_demand("Tomato")
    assert spectral_radius(tomato.A) == pytest.approx(0.19352, abs=1e-4)
    assert ced(tomato, f) == pytest.approx(9.0210, abs=1e-3)
    t = tier_decomposition(tomato, f)
    assert t[0] == 0.0
    assert t[1] == pytest.approx(7.715, abs=1e-3)
    assert t[2] == pytest.approx(0.9853, abs=1e-3)

def test_productivity_check():
    bad = System(["a", "b"], ["u", "u"], np.array([[0.0, 2.0], [2.0, 0.0]]), np.array([1.0, 1.0]))
    assert not hawkins_simon_ok(bad.A)
    with pytest.raises(ValueError):
        leontief_inverse(bad.A)

def test_linearity_in_demand(tomato):
    f1, f2 = tomato.unit_demand("Tomato", 2.0), tomato.unit_demand("Steel", 3.0)
    assert ced(tomato, f1 + f2) == pytest.approx(ced(tomato, f1) + ced(tomato, f2))

def test_basket_matches_vector(tomato):
    b = Basket({"Tomato": 20.0, "Steel": 1.5})
    total, _ = basket_ced(tomato, b)
    assert total == pytest.approx(ced(tomato, b.vector(tomato)))

def test_monte_carlo_brackets_point(tomato):
    f = tomato.unit_demand("Tomato")
    mc = monte_carlo(tomato, f, spread=0.2, n=2000, seed=1)
    assert mc["p05"] < ced(tomato, f) < mc["p95"]
    assert mc["n_accepted"] == 2000

def test_with_changes_is_a_copy(tomato):
    s2 = tomato.with_changes(e_d={"Electricity": 1.0})
    assert tomato.e_d[tomato.index("Electricity")] == 2.5
    assert s2.e_d[s2.index("Electricity")] == 1.0
