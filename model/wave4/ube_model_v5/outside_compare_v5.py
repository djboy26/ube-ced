"""
outside_compare_v5.py - the outside desk check repeated once on the re-sized floor (E-OD-2)
=========================================================================================

Reads the v4 (before) and v5 (after) results files and writes outside_comparison_v5.csv:
  1. the floor by category in FINAL energy, beside the outside comparators the Physics Validator
     verified (Outside_Desk_Check.md sec 6 and 10.1); the conversion is sec 2.2's: delivered energy
     for metered lines; unmetered lines divided by 1.5 (low final) and by 1.2 on food lines / 1.3 on
     other lines (high final), as E-OD-1 asks;
  2. the re-sized space-heat line beside Eurostat's 4,656 kWh/cap/yr of actual Danish space heat, with
     the gap decomposed into area, set-point, envelope and a remainder (ILLUSTRATIVE);
  3. the decent-living comparison made like for like against Denmark's 15.6 GJ.
Every project figure PROVISIONAL.
"""

from __future__ import annotations

import csv
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
GJ = 0.0036
DK = "CED_DK_2023_1.6_kWh_cap_yr"
CATS = {
    "Food, farm to shop (F_01-F_25)": [f"F_{i:02d}" for i in range(1, 26)],
    "Home energy (H_01-H_03, A_01-A_05, V_01)": ["H_01", "H_02", "H_03", "A_01", "A_02", "A_03", "A_04", "A_05", "V_01"],
    "Dwelling structure, envelope, furnishings (C_01-C_03)": ["C_01", "C_02", "C_03"],
    "Water, wastewater and waste (W_01, W_02, HY_07)": ["W_01", "W_02", "HY_07"],
    "Clothing and bedding (T_01, T_02)": ["T_01", "T_02"],
    "Hygiene goods (HY_01-HY_06)": [f"HY_{i:02d}" for i in range(1, 7)],
    "Mobility in the floor (TR_01E, TR_01L, TR_02, TR_04)": ["TR_01E", "TR_01L", "TR_02", "TR_04"],
    "Communication (CM_01-CM_06)": [f"CM_{i:02d}" for i in range(1, 7)],
}
OUTSIDE = {  # Outside_Desk_Check.md sec 6 (GJ/cap/yr final): decent-living Denmark / poorest fifth / Danish mean
    "Food, farm to shop (F_01-F_25)": (2.7, 2.84, 5.26),
    "Home energy (H_01-H_03, A_01-A_05, V_01)": (2.9, 24.1, 35.9),
    "Dwelling structure, envelope, furnishings (C_01-C_03)": (0.8, None, None),
    "Water, wastewater and waste (W_01, W_02, HY_07)": (0.2, None, None),
    "Clothing and bedding (T_01, T_02)": (0.3, 1.30, 3.73),
    "Hygiene goods (HY_01-HY_06)": (None, None, None),
    "Mobility in the floor (TR_01E, TR_01L, TR_02, TR_04)": (2.3, 7.32, 27.5),
    "Communication (CM_01-CM_06)": (0.5, 1.63, 3.11),
}


def load(path):
    return {r["id"]: r for r in csv.DictReader(open(path, encoding="utf-8")) if r["row_type"] == "LINE"}


def final_band(rows, ids):
    lo = hi = p = 0.0
    for i in ids:
        r = rows.get(i)
        if r is None or float(r["in_floor_total"] or 0) != 1.0:
            continue
        v = float(r[DK]); p += v
        d = r.get("delivered_DK_kWh", "")
        if d:
            lo += float(d); hi += float(d)
        else:
            lo += v / 1.5
            hi += v / (1.2 if i.startswith("F_") else 1.3)
    return p, lo * GJ, hi * GJ


def main():
    before = load(os.path.join(HERE, "..", "ube_model_v4", "survival_goods_results_v4.csv"))
    after = load(os.path.join(HERE, "survival_goods_results_v5.csv"))
    P = json.load(open(os.path.join(HERE, "parameters_denmark_v5.json"), encoding="utf-8"))
    o = P["outside_references"]
    out = []
    tot = {"before": [0, 0, 0], "after": [0, 0, 0]}
    for name, ids in CATS.items():
        b = final_band(before, ids); a = final_band(after, ids)
        for k, v in (("before", b), ("after", a)):
            tot[k] = [x + y for x, y in zip(tot[k], v)]
        mh, q1, mean = OUTSIDE[name]
        pos = ""
        if q1 is not None and a[1] > q1:
            pos = f"ABOVE the poorest fifth ({a[1] / q1:.1f}-{a[2] / q1:.1f}x)"
        elif mh is not None and a[2] < mh:
            pos = f"BELOW decent-living ({a[1] / mh:.2f}-{a[2] / mh:.2f}x)"
        elif mh is not None:
            pos = f"INSIDE ({a[1] / mh:.1f}-{a[2] / mh:.1f}x decent-living" + (f"; {100 * a[2] / q1:.0f}% of the poorest fifth)" if q1 else ")")
        out.append({"section": "1 category, final GJ/cap/yr", "item": name,
                    "v4_primary_DK": round(b[0]), "v4_final_GJ": f"{b[1]:.2f}-{b[2]:.2f}",
                    "v5_primary_DK": round(a[0]), "v5_final_GJ": f"{a[1]:.2f}-{a[2]:.2f}",
                    "decent_living_DK_GJ": mh, "poorest_fifth_GJ": q1, "danish_mean_GJ": mean, "v5_position": pos})
    for k in ("before", "after"):
        out.append({"section": "1 category, final GJ/cap/yr", "item": f"FLOOR without healthcare ({'v4' if k == 'before' else 'v5'})",
                    ("v4" if k == "before" else "v5") + "_primary_DK": round(tot[k][0]),
                    ("v4" if k == "before" else "v5") + "_final_GJ": f"{tot[k][1]:.2f}-{tot[k][2]:.2f}"})
    # 2. heat against Eurostat
    D = P["dwelling"]; dw = json.load(open(os.path.join(HERE, "dwelling_findings_v5.json")))
    area = D["floor_area_net_m2_per_cap_R32"] * D["net_to_gross"]["central"]
    h01 = float(after["H_01"]["delivered_DK_kWh"]); h03 = float(after["H_03"]["delivered_DK_kWh"])
    actual = o["eurostat_2023_household_space_heat_kWh_cap"]; stock_area = o["stock_floor_area_m2_cap_LABY46"]
    f_total = actual / h01
    f_area = stock_area / area
    f_perm2 = (actual / stock_area) / (h01 / area)
    c = dw["costing"]
    f_setpoint = c["flat_20C"]["frame"]["reference_mix_kWh_m2"] / c["standard_R33"]["frame"]["reference_mix_kWh_m2"]
    ref20_cal = c["flat_20C"]["frame"]["reference_mix_kWh_m2"] * D["calibration_R48"]["central"]
    f_env = [x / ref20_cal for x in o["stock_space_heat_kWh_m2_ODYSSEE"]]
    f_rest = [f_perm2 / (f_setpoint * e) for e in f_env]
    for item, val, note in [
        ("Space heat H_01, v5, delivered kWh/cap/yr", f"{h01:.0f}", "plus the vulnerable line H_03 %.0f (population average)" % h03),
        ("Wave 2 / v4 space heat, delivered kWh/cap/yr", "553", ""),
        ("Actual Danish household space heat 2023 (Eurostat nrg_d_hhq)", f"{actual}", "VERIFIED (Outside_Desk_Check.md sec 10.1)"),
        ("Gap: actual / floor", f"{f_total:.2f}x", ""),
        ("  x area: 53.6 m2/cap actual (LABY46) / %.2f m2 gross floor" % area, f"{f_area:.2f}x", "VERIFIED inputs"),
        ("  x heat per m2: actual %.1f / floor %.1f kWh/m2" % (actual / stock_area, h01 / area), f"{f_perm2:.2f}x", "of which:"),
        ("      set-points: whole dwelling at 20 C vs R-33's 20/18 zoning (reference envelope)", f"{f_setpoint:.2f}x", "ILLUSTRATIVE (the model)"),
        ("      envelope: stock 75-82 kWh/m2 (ODYSSEE, LOCKED_FACTS sec 3) / reference at 20 C calibrated %.1f" % ref20_cal,
         f"{f_env[0]:.2f}-{f_env[1]:.2f}x", "ILLUSTRATIVE"),
        ("      remainder: behaviour above 20 C, definitions of area and heat, climate year", f"{f_rest[1]:.2f}-{f_rest[0]:.2f}x", "ILLUSTRATIVE (residual)"),
    ]:
        out.append({"section": "2 space heat vs Eurostat", "item": item, "v5_final_GJ": val, "v5_position": note})
    # 3. decent-living like for like (from the v5 results BENCHMARK rows)
    bench = {r["id"]: r for r in csv.DictReader(open(os.path.join(HERE, "survival_goods_results_v5.csv"), encoding="utf-8"))
             if r["row_type"] == "BENCHMARK"}
    for rid in ("FLOOR_FINAL_GJ_ratio_high", "FLOOR_FINAL_GJ_ratio_low", "FLOOR_AT_DLS_SCOPE_FINAL_GJ", "DLS_DENMARK_GJ",
                "DLS_DENMARK_EX_HEALTH_EDU_INFRA_GJ"):
        r = bench[rid]
        out.append({"section": "3 decent-living like for like", "item": r["name"], "v5_final_GJ": r[DK], "v5_position": r["notes"]})
    keys = ["section", "item", "v4_primary_DK", "v4_final_GJ", "v5_primary_DK", "v5_final_GJ", "decent_living_DK_GJ",
            "poorest_fifth_GJ", "danish_mean_GJ", "v5_position"]
    with open(os.path.join(HERE, "outside_comparison_v5.csv"), "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=keys, lineterminator="\n", extrasaction="ignore")
        w.writeheader()
        for r in out:
            w.writerow({k: ("" if r.get(k) is None else r.get(k, "")) for k in keys})
    for r in out:
        print(" | ".join(str(r.get(k, "")) for k in ("item", "v4_final_GJ", "v5_primary_DK", "v5_final_GJ", "v5_position")))


if __name__ == "__main__":
    main()
