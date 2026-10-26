"""Scenario table from the technical note §6.1, recomputed from the matrix."""
from pathlib import Path
from ube_ced_v01 import load_system, ced

s0 = load_system(Path(__file__).parent.parent.parent / "data" / "tomato_sixsector_2026-04.yaml")
f = s0.unit_demand("Tomato")
base = ced(s0, f)

scen = {
    "Baseline":                 s0,
    "100% renewable grid":      s0.with_changes(e_d={"Electricity": 1.0}),
    "Heat pump heating (COP 3)": s0.with_changes(A={("Electricity", "Tomato"): 1.0}),
    "Green ammonia":            s0.with_changes(A={("Diesel", "Fertiliser"): 0.0}),
    "Spanish open-field":       s0.with_changes(A={("Electricity", "Tomato"): 0.1, ("Diesel", "Tomato"): 0.15}),
    "Vertical farm (LEDs)":     s0.with_changes(A={("Electricity", "Tomato"): 20.0}),
}
print(f"{'Scenario':28s} {'kWh/kg':>8s} {'vs base':>9s}")
for name, s in scen.items():
    v = ced(s, f)
    print(f"{name:28s} {v:8.3f} {100*(v/base-1):+8.1f}%")
