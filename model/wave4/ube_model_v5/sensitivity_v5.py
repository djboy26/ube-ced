"""
sensitivity_v5.py - escalation E-RS-3: the floor-mix depth factor with the service-provider lines treated as fully
captured (B1 0.862, B3 1.065) instead of at the services part's measured factor (B1 0.803, B3 1.087).
Both R-8 intervals, same seed and draws; writes sensitivity_v5.csv.  Every figure PROVISIONAL.
"""
import csv, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import ube_model_v5 as M
pr = M.load_parameters(); f = M.load_findings()
cfg = M.prepare_config(pr, f, 7)
v = cfg["floor_mix"]["variant_service_lines_fully_captured"]
cfg["B1"], cfg["B3"] = round(v["B1"], 3), round(v["B3"], 3)
P = M.effective_params(pr, cfg); B = M.load_basket(cfg); base = M.default_scenario(P, cfg)
rows = []
for tag, scen in (("EXCL_HEALTHCARE", base), ("WITH_HEALTHCARE_B3", {**base, "healthcare": "eeio_service_footprint"})):
    mc = M.monte_carlo(P, B, cfg, scen, variance_for=())
    for q in ("p05", "median", "p95"):
        rows.append([f"service lines fully captured (B1 {cfg['B1']}, B3 {cfg['B3']})", tag, q] +
                    [f"{mc[l][q]:.1f}" for l in ("Fossil_2.5", "DK_2023_1.6", "Renewable_1.0")] + ["PROVISIONAL"])
with open(os.path.join(HERE, "sensitivity_v5.csv"), "w", encoding="utf-8", newline="") as fh:
    w = csv.writer(fh, lineterminator="\n")
    w.writerow(["case", "interval", "percentile", "Fossil_2.5", "DK_2023_1.6", "Renewable_1.0", "figure_status"])
    w.writerows(rows)
for r in rows: print(r)
