"""
regression_tests.py - so that this class of error cannot return silently
=======================================================================

Runs offline from ``_dsdata/``.  Exit code 0 only if every test passes.

  0. DATA INTEGRITY  every cached extract still has the SHA-256 recorded in
     _dsdata/fetch_log.json when it was downloaded.
  1. ORIENTATION     the two-sector worked example (A[i][j] = input of i per
     unit of output of j) gives 0.5, and its transpose gives 0.
  2. WAVE 2 REPRODUCTION  with the correction switched off, this engine
     reproduces Wave 2's healthcare figures (640.28 / 999.25 / 2,194.80) and
     its 1,446.2 PJ energy extension.  A correction is only meaningful if the
     uncorrected model is reproduced first.
  3. TEST (a)  GROSS ENERGY  the industries' direct-energy extension plus the
     households' direct fuel must reconcile with Danmarks Statistik's ENE3H
     gross energy consumption for the same year (1,175.6 PJ for 2023) within
     2%.  NEGATIVE CONTROL: the Wave 2 extension must FAIL it (it is +35%).
  4. TEST (b)  DST MULTIPLIERS  domestic-closure multipliers computed from
     DST's own direct-energy vector must reproduce DST's published ENE2MU1N
     multipliers to a median within 3%, with no industry off by more than
     10%, after undoing ENE2MU1N's seven-label permutation.  NEGATIVE
     CONTROLS: the naive labels and the transposed A matrix must both FAIL.

  5. TEST (c)  DWELLING REPRODUCTION (v5; Dwelling_Data_Requests.md sec 1.8 rule 1, sec 6.2 point 2)
     Run BEFORE calibration, on the TABULA 2007-2011 geometries with 5 W/m2 gains:
       - the method reproduces TABULA's own calculated space heat (SBi 2012:01 Table 20) within 20%;
       - the frame-compliant envelope is solved to the BR18 frame-implied space heat, and its U-values
         lie within 0.5-1.5x the TABULA 2007-2011 examples' own (a plausibility check);
       - the temperature sensitivity lies inside Kragh's 8-12% per K for new houses (SBi 2016:08, on his
         basis: space heat plus hot water).
     Reported, and EXPECTED TO FAIL: BR18 sec 257's minimum element values do not by themselves meet
     the energy frame (they give 1.2-2.3x the frame-implied heat).
  6. TEST (d)  v4 REPRODUCTION  ube_model_v5.py --upto 1 reproduces every deterministic LINE, SECTOR,
     FLOOR and SCENARIO cell of v4's post-verification results file that both files carry.

Tests (a) and (b) are the two the Physics Validator asked for
(IO_Double_Count_Check.md sec 7, step 7).  Test (a) would have caught the Wave 2
double count the first time the model ran.  Test (b) guards the machinery (the
orientation, the IO table, the industry labels) rather than the energy vector,
because it runs on DST's own vector.

Run:  python regression_tests.py
"""

from __future__ import annotations

import hashlib
import json
import os
import sys

import dst_data as dd
import io_model_v5 as iom
import dwelling_v5 as dwm
from linalg import orientation_worked_example

HERE = os.path.dirname(os.path.abspath(__file__))


def data_integrity() -> tuple[bool, str]:
    path = os.path.join(dd.DATA, "fetch_log.json")
    with open(path, encoding="utf-8") as fh:
        log = json.load(fh)["extracts"]
    bad = []
    for fname, rec in log.items():
        with open(os.path.join(dd.DATA, fname), "rb") as fh:
            if hashlib.sha256(fh.read()).hexdigest() != rec["sha256"]:
                bad.append(fname)
    return (not bad), (f"{len(log)} extracts match their recorded SHA-256" if not bad
                       else f"CHANGED since download: {bad}")


def main() -> int:
    results = []

    ok, msg = data_integrity()
    results.append(("0. Data integrity", ok, msg))

    ot = orientation_worked_example()
    results.append(("1. A-matrix orientation", ot["passes"],
                    f"stated convention {ot['energy_with_stated_convention']}, transpose "
                    f"{ot['energy_with_transpose']}, true answer 0.5"))

    model = iom.IOModel()
    model.multipliers()

    w2 = iom.test_wave2_reproduction(model)
    results.append(("2. Wave 2 reproduction", w2["passes"],
                    f"healthcare {w2['reproduced']['low_health_domestic_only']:.2f} / "
                    f"{w2['reproduced']['central_health_domestic_technology']:.2f} / "
                    f"{w2['reproduced']['high_health_plus_care_domestic_technology']:.2f} kWh/cap/yr "
                    f"(max gap {w2['max_abs_gap_kWh']:.1e}); extension {w2['sum_extension_PJ']:.1f} PJ"))

    a = iom.test_a_gross_energy(model)
    results.append(("3. Test (a): extension + household fuel vs DST ENE3H", a["passes"],
                    f"corrected {a['A']['total_GJ'] / 1e6:.1f} PJ vs DST {a['reference_ENE3H_total_GJ'] / 1e6:.1f} PJ "
                    f"({a['A']['gap_pct']:+.2f}%); fuels outside the conversion plants "
                    f"{a['fuels_outside_conversion_plants']['gap_pct']:+.2f}%"))
    results.append(("   negative control: Wave 2 extension must fail (a)", a["catches_wave2_error"],
                    f"Wave 2 {a['W2']['total_GJ'] / 1e6:.1f} PJ ({a['W2']['gap_pct']:+.1f}%)"))

    b = iom.test_b_dst_multipliers(model)
    results.append(("4. Test (b): our multipliers vs DST ENE2MU1N", b["passes"],
                    f"median gap {b['median_abs_gap_pct']:.2f}%, max {b['max_abs_gap_pct']:.2f}%, "
                    f"{100 * b['share_within_3pct']:.0f}% of {b['n_industries_compared']} industries within 3%; "
                    f"human health {b['human_health']['ours']:.2f} vs DST {b['human_health']['DST_published']:.2f} "
                    f"GJ/m DKK; labels remapped: {b['remap_published_label_to_true_industry']}"))
    results.append(("   negative control: naive ENE2MU1N labels must fail (b)",
                    b["negative_control_naive_labels"]["fails_as_it_should"],
                    f"human health off by {b['negative_control_naive_labels']['human_health_gap_pct']:.0f}%"))
    results.append(("   negative control: transposed A must fail (b)",
                    b["negative_control_transposed_A"]["fails_as_it_should"],
                    f"median gap {b['negative_control_transposed_A']['median_abs_gap_pct']:.1f}%"))

    d = dwm.run(write=False)
    tt = d["tests"]
    t1 = d["test1_method_vs_TABULA_table20"]
    fr = d["frame_compliant_envelope"]
    results.append(("5. Test (c): dwelling reproduction (before calibration)", tt["reproduction_test_passes"],
                    "TABULA check ratios " + ", ".join(f"{k} {v['ratio']:.2f} ({v['ratio_with_infiltration']:.2f} with 0.1/h infiltration)"
                                                       for k, v in t1.items())
                    + "; sensitivity per K on Kragh's basis " + ", ".join(f"{k} {v['sensitivity_pct_per_K_on_heat_plus_DHW_Kragh_basis']:.1f}%"
                                                                     for k, v in fr.items())))
    t2 = d["test2_BR18_elements_vs_frame"]
    results.append(("   reported, expected to fail: BR18 sec 257 elements meet the frame", True,
                    ("confirmed that they do NOT: " if not tt["test2_BR18_elements_reproduce_frame"] else "UNEXPECTEDLY they do: ")
                    + ", ".join(f"{k} {v['ratio']:.2f}x the frame" for k, v in t2.items())))

    import csv as _csv
    import ube_model_v5 as M
    pr = M.load_parameters()
    cfg = M.prepare_config(pr, M.load_findings(), 1)
    P = M.effective_params(pr, cfg)
    rows, _, _, _ = M.build_results(P, M.load_basket(cfg), cfg, with_mc=False)
    v4 = {(r["row_type"], r["id"]): r for r in _csv.DictReader(open(os.path.join(HERE, "..", "ube_model_v4",
                                                                                 "survival_goods_results_v4.csv"), encoding="utf-8"))}
    cols = M.COLS3 + ("quantity", "intensity", "share_electric", "delivered_DK_kWh")
    n = bad = 0
    for r in rows:
        k = (r["row_type"], r["id"])
        if r["row_type"] not in ("LINE", "SECTOR_TOTAL", "FLOOR_TOTAL", "SCENARIO") or k not in v4:
            continue
        for c in cols:
            a, b = M._cell(c, r.get(c, "")), v4[k].get(c, "")
            if a == "" and b == "":
                continue
            n += 1
            if (a == "") != (b == "") or abs(float(a) - float(b)) > 0.0001:
                bad += 1
    results.append(("6. Test (d): v5 step 1 reproduces v4", bad == 0 and n > 400, f"{n} cells compared, {bad} differ"))

    width = max(len(r[0]) for r in results)
    allok = True
    for name, ok, msg in results:
        allok &= bool(ok)
        print(f"{'PASS' if ok else 'FAIL'}  {name:<{width}}  {msg}")
    print("\nALL REGRESSION TESTS PASS" if allok else "\nREGRESSION FAILURE")
    return 0 if allok else 1


if __name__ == "__main__":
    sys.exit(main())
