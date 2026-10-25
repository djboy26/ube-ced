"""ube-ced <system.yaml> [--demand NAME=QTY ...] [--tiers] [--sectors] [--mc]"""
from __future__ import annotations
import argparse, json
from .io import load_system
from .core import ced, ced_vector, spectral_radius
from .decompose import tier_decomposition, sector_decomposition
from .montecarlo import monte_carlo


def main(argv=None):
    p = argparse.ArgumentParser(prog="ube-ced", description=__doc__)
    p.add_argument("system")
    p.add_argument("--demand", action="append", default=[], help="NAME=QTY, repeatable")
    p.add_argument("--tiers", action="store_true")
    p.add_argument("--sectors", action="store_true")
    p.add_argument("--mc", action="store_true")
    p.add_argument("--json", action="store_true")
    a = p.parse_args(argv)

    s = load_system(a.system)
    eps = ced_vector(s)
    out = {"spectral_radius": spectral_radius(s.A),
           "epsilon_kwh_per_unit": {n: float(e) for n, e in zip(s.names, eps)}}
    if a.demand:
        f = s.unit_demand(s.names[0], 0.0)
        for d in a.demand:
            k, v = d.split("=")
            f[s.index(k)] = float(v)
        out["ced_kwh"] = ced(s, f)
        if a.tiers:
            out["tiers_kwh"] = tier_decomposition(s, f)
        if a.sectors:
            out["by_sector_kwh"] = sector_decomposition(s, f)
        if a.mc:
            out["monte_carlo"] = monte_carlo(s, f)
    if a.json:
        print(json.dumps(out, indent=2))
    else:
        print(f"rho(A) = {out['spectral_radius']:.4f}")
        for n, e in out["epsilon_kwh_per_unit"].items():
            print(f"  epsilon[{n}] = {e:.4f} kWh per {s.units[s.index(n)]}")
        if "ced_kwh" in out:
            print(f"CED(demand) = {out['ced_kwh']:.4f} kWh")
            if "tiers_kwh" in out:
                for k, t in enumerate(out["tiers_kwh"]):
                    print(f"  tier {k}: {t:.4f}")
            if "by_sector_kwh" in out:
                for n, v in out["by_sector_kwh"].items():
                    print(f"  {n}: {v:.4f}")
            if "monte_carlo" in out:
                print("  MC:", out["monte_carlo"])


if __name__ == "__main__":
    main()
