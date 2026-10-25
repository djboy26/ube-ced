"""
verify_results_v5.py - check a v5 results file against ITSELF, without the model
================================================================================

Port of Wave 2's verify_results.py to the standard library.  It deliberately
does NOT import the model.  It asks the Wave 1 audit's three questions of the
results file (do sector totals equal their lines? does the floor equal the
sectors? is there a hidden constant multiplier?) and then recomputes every
line-by-scenario cell from the basket, the parameter file and the IO findings
with a SECOND implementation of the conversion rules, including v4's
construction-C healthcare line:

  base            = quantity x intensity
  primary_at_ref  = base x ((1 - s) + s x PEF / PEF_ref)
  io_construction_C (healthcare) = F + E x PEF + H x DH factor, from the IO findings
  delivered_electrical  = base x PEF
  delivered_thermal_low = base x (DH_share x DH_factor + HP_share x PEF / COP)
  delivered_liquid_fuel = base x well-to-tank
  delivered_mixed       = base x (s x PEF + (1 - s) x non-electric factor)
  then x the line's food-loss factor, and x the depth factor if it is B2.

Run:  python verify_results_v4.py [results file]   (default: construction C)
Exit code 0 if the file reconciles, 1 if it does not.
"""

from __future__ import annotations

import csv
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(HERE, "survival_goods_results_v5.csv")
BASKET = os.path.join(HERE, "basket_denmark_v5.csv")
PARAMS = os.path.join(HERE, "parameters_denmark_v5.json")
FINDINGS = os.path.join(HERE, "io_findings_v5.json")
COLS = ["CED_Fossil_2.5_kWh_cap_yr", "CED_DK_2023_1.6_kWh_cap_yr", "CED_Renewable_1.0_kWh_cap_yr"]
LABEL_COL = dict(zip(["Fossil_2.5", "DK_2023_1.6", "Renewable_1.0"], COLS))


def recompute_lines() -> dict:
    """Construction C (the adopted construction) from the raw inputs."""
    with open(PARAMS, encoding="utf-8") as fh:
        par = json.load(fh)
    with open(FINDINGS, encoding="utf-8") as fh:
        fnd = json.load(fh)
    with open(BASKET, encoding="utf-8", newline="") as fh:
        b = list(csv.DictReader(fh))
    comp = fnd["carrier_composition"]["C"]["by_industry"]
    hcC = fnd["healthcare"]["C"]["components_kWh"]["central"]
    pef_ref = par["pef_reference"]
    hc = par["heat_carrier"]
    dh = hc["district_heat_factor_variants"][hc["district_heat_factor_default"]]
    wtt = par["liquid_fuel_well_to_tank"]["central"]
    nef = par["non_electric_delivered_to_primary_factor"]["central"]
    losses = par["food_loss_regimes"][par["food_loss_default"]]
    depth = par["boundary_depth"]["factors_relative_to_B2"][par["boundary_depth"]["default"]]
    modal = par["modal_split"]["variants"][par["modal_split"]["default"]]
    tom = par["tomato"]["variants"][par["tomato"]["default"]]
    cook = par["cooking"]["variants"][par["cooking"]["default"]]

    D = par["dwelling"]
    area_v5 = D["floor_area_net_m2_per_cap_R32"] * D["net_to_gross"]["central"]
    cal = D["calibration_R48"]["central"]
    vshare = D["vulnerable_share_R50"]["central"]
    with open(os.path.join(HERE, "dwelling_findings_v5.json"), encoding="utf-8") as fh:
        dref = json.load(fh)["costing"]
    dw_std = dref["standard_R33"]["frame"]["reference_mix_kWh_m2"]
    dw_vul = dref["vulnerable_R50"]["frame"]["reference_mix_kWh_m2"]
    with open(os.path.join(HERE, "food_findings_v5.json"), encoding="utf-8") as fh:
        food_q = json.load(fh)["central"]["line_kg_cap_yr"]
    qty, inten, share = {}, {}, {}
    for r in b:
        lid = r["line_id"]
        q = None if r["quantity"] == "DERIVED_FOOD_MASS" else float(r["quantity"])
        i = float(r["intensity"])
        s_raw = r["share_electric"]
        s = comp[s_raw.split(":")[1]]["electric_share_of_primary_at_pef_ref"] if s_raw.startswith("IO:") else float(s_raw)
        if lid == "F_04":
            i = tom["kWh_per_kg"]
        elif lid == "A_01":
            q, i = cook["kWh_per_cap_yr"], 1.0
        elif lid == "TR_01E":
            q = modal["propulsion_electric_kWh"]
        elif lid == "TR_01L":
            q = modal["propulsion_liquid_kWh"]
        elif lid == "TR_02":
            i = modal["vehicle_manufacture_kWh"]
        # v5, resolved independently from the raw findings files (never from the rounded basket values):
        #   C_01, V_01, C_03: area = R-32 net x the central net-to-gross ratio
        #   H_01: q_standard x calibration x area;  H_03: (q_vulnerable - q_standard) x calibration x area x share
        #   food lines: food_findings_v5.json, central rule
        if lid in ("C_01", "V_01", "C_03"):
            q = area_v5
        elif lid == "H_01":
            q = dw_std * cal * area_v5
        elif lid == "H_03":
            q = (dw_vul - dw_std) * cal * area_v5 * vshare
        elif lid in food_q:
            q = food_q[lid]
        qty[lid], inten[lid], share[lid] = q, i, s
    qty["F_25"] = sum(qty[r["line_id"]] for r in b
                      if r["sector"] == "S1_Food" and r["line_id"] != "F_25"
                      and r["loss_regime"] != "inline" and r["unit"] == "kg/cap/yr")
    out = {}
    for r in b:
        lid = r["line_id"]
        base = qty[lid] * inten[lid]
        s = share[lid]
        for label, pef in par["pef_scenarios"].items():
            basis = r["energy_basis"]
            if basis == "primary_at_ref":
                v = base * ((1.0 - s) + s * pef / pef_ref)
            elif basis == "io_construction_C":
                v = qty[lid] * (hcC["F"] + hcC["E"] * pef + hcC["H"] * dh)
            elif basis == "delivered_electrical":
                v = base * pef
            elif basis == "delivered_thermal_low":
                v = base * (hc["district_heat_share"] * dh + hc["heat_pump_share"] * pef / hc["heat_pump_cop"])
            elif basis == "delivered_liquid_fuel":
                v = base * wtt
            elif basis == "delivered_mixed":
                v = base * (s * pef + (1.0 - s) * nef)
            else:
                raise SystemExit(f"{lid}: unknown basis {basis}")
            v *= losses[r["loss_regime"]]
            if r["boundary_depth"] == "B2":
                v *= depth
            out[(lid, label)] = v
    return out


def main(argv) -> int:
    path = argv[0] if argv else RESULTS
    with open(path, encoding="utf-8", newline="") as fh:
        d = list(csv.DictReader(fh))
    lines = [r for r in d if r["row_type"] == "LINE" and float(r["in_floor_total"] or 0) == 1]
    sectors = {r["id"]: r for r in d if r["row_type"] == "SECTOR_TOTAL"}
    floor = [r for r in d if r["row_type"] == "FLOOR_TOTAL" and r["id"] == "FLOOR_kWh"][0]
    ok = True
    counts = {}
    for r in d:
        counts[r["row_type"]] = counts.get(r["row_type"], 0) + 1
    print(path)
    print("  " + ", ".join(f"{k} {v}" for k, v in counts.items()))
    print(f"  {len(lines)} line rows are inside the floor total\n")
    for c in COLS:
        by_sector = {}
        for r in lines:
            by_sector[r["sector"]] = by_sector.get(r["sector"], 0.0) + float(r[c])
        for sec, v in by_sector.items():
            diff = abs(float(sectors[sec][c]) - v)
            if diff > 0.01:
                ok = False
                print(f"  FAIL  sector {sec} {c}: off by {diff:.3f}")
        tot = sum(by_sector.values())
        diff = abs(float(floor[c]) - tot)
        if diff > 0.01:
            ok = False
            print(f"  FAIL  floor total {c}: off by {diff:.3f}")
        print(f"  {c:<32} lines {tot:>10.2f}   floor {float(floor[c]):>10.2f}   ratio {float(floor[c]) / tot:.6f}")
    ratios = [float(floor[c]) / sum(float(r[c]) for r in lines) for c in COLS]
    if all(abs(x - 1.0) < 1e-6 for x in ratios):
        print("\n  No multiplier of any kind stands between the line rows and the reported floor.")
    else:
        ok = False
        print(f"\n  FAIL  a multiplier is present: {ratios}")
    if not all(r.get("v5_figure_status") == "PROVISIONAL" for r in d):
        ok = False
        print("  FAIL  a row is not tagged PROVISIONAL")
    else:
        print(f"  All {len(d)} rows carry v5_figure_status = PROVISIONAL.")

    if os.path.basename(path) == os.path.basename(RESULTS):
        rec = recompute_lines()
        line_rows = {r["id"]: r for r in d if r["row_type"] == "LINE"}
        worst, cell, n = 0.0, None, 0
        for (lid, label), v in rec.items():
            got = float(line_rows[lid][LABEL_COL[label]])
            diff = abs(got - v)
            n += 1
            if diff > worst:
                worst, cell = diff, (lid, label, got, v)
        print(f"\n  Recomputed all {n} line-by-scenario cells (v5, all steps) from the basket, the parameter "
              f"file and the IO findings with a second implementation of the rules.")
        print(f"  Maximum disagreement: {worst:.6f} kWh/cap/yr"
              + (f" (worst cell {cell[0]} {cell[1]}: file {cell[2]:.4f}, recomputed {cell[3]:.4f})" if cell else ""))
        if worst > 0.0002:
            ok = False
            print("  FAIL  a cell does not reproduce from the raw inputs")
    print("\nRESULT:", "the file reconciles with itself" if ok else "THE FILE DOES NOT RECONCILE")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
