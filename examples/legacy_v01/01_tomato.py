"""Reproduce the six-sector tomato CED and its tier decomposition."""
from pathlib import Path
from ube_ced_v01 import load_system, ced_vector, ced, tier_decomposition, sector_decomposition, spectral_radius

s = load_system(Path(__file__).parent.parent.parent / "data" / "tomato_sixsector_2026-04.yaml")
f = s.unit_demand("Tomato", 1.0)

print(f"rho(A) = {spectral_radius(s.A):.4f}  (converges iff < 1)")
print(f"CED of 1 kg tomato = {ced(s, f):.3f} kWh primary\n")

print("By tier (e_d A^k f):")
for k, t in enumerate(tier_decomposition(s, f)):
    print(f"  tier {k}: {t:8.4f}")

print("\nBy originating sector (e_d[i] * (L f)[i]):")
for n, v in sector_decomposition(s, f).items():
    print(f"  {n:12s} {v:8.4f}")

print("\nepsilon for every process:")
for n, u, e in zip(s.names, s.units, ced_vector(s)):
    print(f"  {n:12s} {e:9.3f} kWh per {u}")
