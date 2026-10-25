"""A basket is a final-demand vector. This one is a toy; the real Danish basket is
an open question (docs/OPEN_QUESTIONS.md Q2) and is not encoded here yet."""
from pathlib import Path
from ube_ced import load_system, Basket, basket_ced, monte_carlo

s = load_system(Path(__file__).parent.parent / "data" / "tomato_sixsector_2026-04.yaml")
b = Basket({"Tomato": 20.0, "Water": 36.5, "Electricity": 1000.0})   # per person-year, toy
total, items = basket_ced(s, b)
print(f"Toy basket CED = {total:,.0f} kWh primary / year")
for k, v in items.items():
    print(f"  {k:12s} {v:9.1f}")
mc = monte_carlo(s, b.vector(s), spread=0.25, n=5000)
print("\n±25% triangular on every coefficient:", {k: round(v, 1) if isinstance(v, float) else v for k, v in mc.items()})
