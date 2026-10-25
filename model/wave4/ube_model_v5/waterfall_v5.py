"""
waterfall_v5.py - R-8 replaced once, one step at a time (R-52)
=============================================================

For each cumulative step 1..7 of ube_model_v5.py, the central triple and the
5th-95th percentile interval (200,000 draws, seed 20260907, the same method),
with and without healthcare; plus, at every step, the food term against the
outside range (E-OD-2, F-1) and heating's share of the floor.

  python waterfall_v5.py            # runs the seven steps in parallel, writes waterfall_v5.csv
  python waterfall_v5.py --step 3   # one step (what the driver launches)

Step 0 is the ruling as it stands (R-8, 6,482-9,389 with healthcare; 5,428-8,194
without), read from Wave 2's results file.  Every figure PROVISIONAL.
"""

from __future__ import annotations

import csv
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
LABS = ["Fossil_2.5", "DK_2023_1.6", "Renewable_1.0"]
NAMES = {0: "R-8 as ruled (Wave 2; known overstated, R-38)",
         1: "1. double count removed (v4, post-verification)",
         2: "2. depth factor on the floor's own mix (R-61)",
         3: "3. dwelling standard (R-32 area, R-33 set-points, R-49 mix, R-34 method, fans, envelope)",
         4: "4. calibration x1.5, range 1.0-2.5 (R-48)",
         5: "5. vulnerable +2 K line (R-50)",
         6: "6. hot water 20 L (R-51)",
         7: "7. food at the dietary guidelines (R-64)"}


def one_step(k: int, draws=None) -> dict:
    sys.path.insert(0, HERE)
    import ube_model_v5 as M
    pr = M.load_parameters()
    f = M.load_findings()
    cfg = M.prepare_config(pr, f, k)
    P = M.effective_params(pr, cfg)
    B = M.load_basket(cfg)
    base = M.default_scenario(P, cfg)
    run = M.run_once(P, B, cfg, base)
    hc = M.run_once(P, B, cfg, {**base, "healthcare": "eeio_service_footprint"})
    out = {"step": k, "name": NAMES[k], "B1": cfg["B1"], "B3": cfg["B3"],
           "central_excl": run["totals"], "central_with": hc["totals"],
           "sectors_DK": {s: v for s, v in run["sector_totals"]["DK_2023_1.6"].items()},
           "sectors": run["sector_totals"]}
    lines = {l["line_id"]: l for l in run["lines"]}
    out["space_heat_delivered"] = lines["H_01"]["delivered_DK"]
    out["F25"] = {"delivered": lines["F_25"]["delivered_DK"], "primary_DK": lines["F_25"]["primary_DK_2023_1.6"]}
    out["heat_lines_delivered"] = sum(lines[i]["delivered_DK"] for i in ("H_01", "H_02", "H_03")
                                      if lines[i]["in_floor"])
    # food term with the loss cascade removed (E-OD-2: the cascade as its own step)
    nl = M.run_once(P, B, cfg, {**base, "food_loss": "household_only"})
    out["food_household_losses_only"] = nl["sector_totals"]
    mc_ex = M.monte_carlo(P, B, cfg, base, draws=draws, variance_for=())
    mc_hc = M.monte_carlo(P, B, cfg, {**base, "healthcare": "eeio_service_footprint"}, draws=draws, variance_for=())
    out["mc_excl"] = {lab: {q: mc_ex[lab][q] for q in ("p05", "median", "p95")} for lab in LABS}
    out["mc_with"] = {lab: {q: mc_hc[lab][q] for q in ("p05", "median", "p95")} for lab in LABS}
    json.dump(out, open(os.path.join(HERE, f"_waterfall_step{k}.json"), "w"), indent=1)
    return out


def main(argv):
    if "--step" in argv:
        one_step(int(argv[argv.index("--step") + 1]))
        return 0
    procs = [subprocess.Popen([sys.executable, __file__, "--step", str(k)], cwd=HERE) for k in range(1, 8)]
    for p in procs:
        if p.wait() != 0:
            raise SystemExit("a step failed")
    steps = [json.load(open(os.path.join(HERE, f"_waterfall_step{k}.json"))) for k in range(1, 8)]
    w2 = {(r["row_type"], r["id"]): r for r in csv.DictReader(open(os.path.normpath(os.path.join(
        HERE, "..", "..", "wave2", "survival_goods_results_v3.csv")), encoding="utf-8"))}
    cols = {"Fossil_2.5": "CED_Fossil_2.5_kWh_cap_yr", "DK_2023_1.6": "CED_DK_2023_1.6_kWh_cap_yr",
            "Renewable_1.0": "CED_Renewable_1.0_kWh_cap_yr"}
    P = json.load(open(os.path.join(HERE, "parameters_denmark_v5.json"), encoding="utf-8"))
    o = P["outside_references"]
    rows = []
    s0 = {"step": 0, "name": NAMES[0],
          "mc_with": {l: {q: float(w2[("INTERVAL", f"{Q}_WITH_HEALTHCARE_B3")][cols[l]]) for q, Q in
                          (("p05", "P05"), ("median", "MEDIAN"), ("p95", "P95"))} for l in LABS},
          "mc_excl": {l: {q: float(w2[("INTERVAL", f"{Q}_EXCL_HEALTHCARE")][cols[l]]) for q, Q in
                          (("p05", "P05"), ("median", "MEDIAN"), ("p95", "P95"))} for l in LABS},
          "central_excl": {l: float(w2[("FLOOR_TOTAL", "FLOOR_kWh")][cols[l]]) for l in LABS},
          "central_with": {l: float(w2[("SCENARIO", "HEALTHCARE_eeio_B3")][cols[l]]) for l in LABS},
          "sectors": {l: {"S1_Food": float(w2[("SECTOR_TOTAL", "S1_Food")][cols[l]]),
                          "S3_Heating": float(w2[("SECTOR_TOTAL", "S3_Heating")][cols[l]])} for l in LABS}}
    prev = None
    f25_w2 = next(r for r in csv.DictReader(open(os.path.normpath(os.path.join(HERE, "..", "..", "wave2",
                  "survival_goods_results_v3.csv")), encoding="utf-8")) if r["row_type"] == "LINE" and r["id"] == "F_25")
    s0["F25"] = {"delivered": float(f25_w2["delivered_DK_kWh"]), "primary_DK": float(f25_w2[cols["DK_2023_1.6"]])}
    for s in [s0] + steps:
        food = s["sectors"]["DK_2023_1.6"]["S1_Food"]
        # the desk check's conversion (Outside_Desk_Check.md sec 2.2): the retail node is metered, so it enters as
        # delivered energy; the other food lines are divided by 1.5 (low final) and 1.2 (high final)
        fz = food - s["F25"]["primary_DK"]
        f_lo = (fz / 1.5 + s["F25"]["delivered"]) * 0.0036
        f_hi = (fz / 1.2 + s["F25"]["delivered"]) * 0.0036
        rec = {"step": s["step"], "name": s["name"], "B1": s.get("B1", 0.833), "B3": s.get("B3", 1.066)}
        for tag in ("with", "excl"):
            for l in LABS:
                for q in ("p05", "median", "p95"):
                    rec[f"{tag}_{q}_{l}"] = round(s[f"mc_{tag}"][l][q], 1)
            rec[f"{tag}_central_" + "_".join(["F", "DK", "R"])] = " / ".join(f"{s[f'central_{tag}'][l]:.0f}" for l in LABS)
            if prev is not None:
                rec[f"{tag}_change_DK_p05_p95"] = (f"{s[f'mc_{tag}']['DK_2023_1.6']['p05'] - prev[f'mc_{tag}']['DK_2023_1.6']['p05']:+.0f} / "
                                                   f"{s[f'mc_{tag}']['DK_2023_1.6']['p95'] - prev[f'mc_{tag}']['DK_2023_1.6']['p95']:+.0f}")
        rec["food_term_F_DK_R"] = " / ".join(f"{s['sectors'][l]['S1_Food']:.0f}" for l in LABS)
        rec["food_final_GJ"] = f"{f_lo:.2f}-{f_hi:.2f}"
        rec["food_vs_poorest_fifth_2.84GJ"] = f"{f_lo / o['oswald_2011_poorest_fifth_food_GJ']:.2f}-{f_hi / o['oswald_2011_poorest_fifth_food_GJ']:.2f}x"
        rec["food_vs_decent_living_DK_2.7GJ"] = f"{f_lo / o['mh_denmark_food_GJ']:.2f}-{f_hi / o['mh_denmark_food_GJ']:.2f}x"
        rec["food_vs_danish_mean_5.26GJ"] = f"{f_lo / o['oswald_2011_mean_food_GJ']:.2f}-{f_hi / o['oswald_2011_mean_food_GJ']:.2f}x"
        if "food_household_losses_only" in s:
            rec["food_term_without_loss_cascade_DK"] = round(s["food_household_losses_only"]["DK_2023_1.6"]["S1_Food"], 0)
        heat = s["sectors"]["DK_2023_1.6"].get("S3_Heating", 0.0)
        rec["heating_share_pct_DK"] = round(100 * heat / s["central_excl"]["DK_2023_1.6"], 1)
        rec["space_heat_delivered_kWh"] = round(s.get("space_heat_delivered", 553.0), 1)
        rec["figure_status"] = "PUBLISHED (R-8), known overstated" if s["step"] == 0 else "PROVISIONAL"
        rows.append(rec)
        prev = s
    keys = list(rows[-1].keys())
    for r in rows:
        for k in keys:
            r.setdefault(k, "")
    with open(os.path.join(HERE, "waterfall_v5.csv"), "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=keys, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    for k in range(1, 8):
        os.remove(os.path.join(HERE, f"_waterfall_step{k}.json"))
    for r in rows:
        print(f"{r['step']}  with {r['with_p05_DK_2023_1.6']:>7.0f}-{r['with_p95_DK_2023_1.6']:<7.0f} "
              f"excl {r['excl_p05_DK_2023_1.6']:>7.0f}-{r['excl_p95_DK_2023_1.6']:<7.0f} food {r['food_term_F_DK_R']:>18} "
              f"heat {r['heating_share_pct_DK']:>5}%  {r['name'][:60]}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
