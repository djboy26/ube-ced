# UBE model v5: the floor re-size (Wave 4 cycle 4)

**Every figure this folder produces is PROVISIONAL** until the Physics Validator checks this run. Basis throughout:
**primary cumulative energy demand, lower heating value, kWh per person per year, Denmark 2023**, unless a line
says otherwise (space heat and hot water are also given as **delivered** heat). Electricity-dependent figures are
the triple **fossil 2.5 / DK-2023 1.6 / renewable 1.0**. The narrative is `..\Floor_Resize.md`.

## What this is

The run that replaces R-8 once (R-52). v5 is v4 (the double-count correction, as cleared by the Physics Validator),
plus the rulings made since R-8, applied as **seven cumulative steps**, so that each effect is visible on its own:

| Step | Ruling | Change |
|---|---|---|
| 1 | R-38, R-39 | v4, post-verification. `--upto 1` reproduces v4 exactly (regression test (d)) |
| 2 | R-61 | Depth factors re-measured on the floor's own mix (B1 0.803, B3 1.087). R-42's statuses for CM_01/CM_02 |
| 3 | R-32, R-33, R-49, R-34 | Area 19.54 m² net × 1.175 gross; zoned set-points; new-build mix 21/24/55; monthly balance-point method; new lines V_01 (fans) and C_03 (envelope uplift) |
| 4 | R-48 | Space heat × 1.5; the range 1.0–2.5 as a Monte Carlo axis |
| 5 | R-50 | Vulnerable +2 °C line H_03 (share 40%, ILLUSTRATIVE) |
| 6 | R-51 | Hot water 20 L (no change to the central); 41 L as a sensitivity |
| 7 | R-64 | Food quantities from the Danish dietary guidelines, by age band |

v4 is not modified. Standard library only (Python 3.9 or later). No network, except for the optional re-downloads.

## Run it

From this folder:

```
python io_model_v5.py          # 1 s.  Input-output layer (v4 + the floor-mix parts) -> io_findings_v5.json
python dwelling_v5.py          # 1 s.  Heat model and its reproduction tests -> dwelling_findings_v5.json
python food_v5.py              # 1 s.  Guideline quantities by age band -> food_findings_v5.json
python regression_tests.py     # 20 s. Data integrity; orientation; Wave 2 reproduction; tests (a), (b),
                               #       (c) dwelling reproduction, (d) v4 reproduction
python ube_model_v5.py         # ~15 min.  All seven steps -> survival_goods_results_v5.csv
python waterfall_v5.py         # ~6 min (7 processes).  The waterfall -> waterfall_v5.csv
python outside_compare_v5.py   # 1 s.  Desk-check comparison on the re-sized floor -> outside_comparison_v5.csv
python verify_results_v5.py    # 1 s.  Independent reconciliation of the results file
```

Other switches: `ube_model_v5.py --upto k` (the model after step k); `--check` (confirms byte-for-byte
reproduction); `--self-test` (assertions and the 39-case corruption battery); `--draws N` (a quick look,
written to a separate `_quickN` file).

Re-download the data: `python dst_data.py --refetch` (Statistics Denmark) and `python climate_fetch_v5.py` (PVGIS).
Their URLs and checksums are in `_dsdata\fetch_log.json`, which `regression_tests.py` checks.

## The files

| File | What it is |
|---|---|
| `dwelling_v5.py` | Monthly balance-point space heat (EN ISO 13790 family) on the TABULA 2007–2011 geometries (SBi 2012:01); BR18 §257 element values; each type's envelope solved to meet its BR18 energy frame; R-33 zoned set-points; the +2 K case; reproduction tests |
| `food_v5.py` | DTU 2020 model 2 by age band (NNR 2023 reference energy; the Fødevarestyrelsen dairy amounts by age); line mapping; reproduction of the Till author's paired cost |
| `io_model_v5.py` | v4's input-output model, plus tier series for goods, services and household energy (R-61) |
| `ube_model_v5.py` | The basket model: v4 with the seven steps as switches, the calibration axis, new scenario, benchmark and diagnostic rows |
| `waterfall_v5.py`, `outside_compare_v5.py` | The step table and the outside comparison |
| `sensitivity_v5.py` | Escalation E-RS-3: both intervals with the service-provider lines treated as fully captured in the depth factor -> `sensitivity_v5.csv` |
| `climate_fetch_v5.py` | Re-downloads and aggregates the PVGIS climate (network needed) |
| `basket_denmark_v5.csv` | The final (all-steps) basket: H_01 and H_03 resolved from the dwelling model; C_01, V_01, C_03 on the R-32 gross area; food lines at the guideline quantities; CM_01/CM_02 statuses per R-42. The model checks every resolved value against its findings file |
| `parameters_denmark_v5.json` | Adds `dwelling`, `v5` and `outside_references`; `boundary_depth` holds the floor-mix factors; `decent_living_benchmark` corrected per E-OD-1 (Denmark 15.6 GJ; 1.2 on food lines) |
| `_dsdata\` | v4's extracts, plus PVGIS monthly climate, FAM55N and FOLK1A (2023) |
| `survival_goods_results_v5.csv` | **The v5 results** (all steps). Columns as v4, with `v5_figure_status` and `construction` |
| `waterfall_v5.csv` | Step by step: interval with and without healthcare (triple), central triple, food term against the outside range, heating's share |
| `outside_comparison_v5.csv` | The desk-check categories in final energy before and after; heat against Eurostat; decent-living comparison like for like |

## Judgements this run makes (each quantified; escalated in the narrative)

- **E-RS-1.** The reference envelope is the **frame-compliant** one. BR18 §257's minimum element values do not meet
  the energy frame (1.2–2.3× the frame-implied heat), and calibrating them ×1.5 would count the performance gap twice.
- **E-RS-2.** The net-to-gross ratio is 1.175, the midpoint of the ASSUMED 1.10–1.25.
- **E-RS-3.** Service-provider lines take the services part's measured depth factor, not "fully captured".
- **E-RS-4.** Food: adults receive the official flat amounts; children are energy-scaled.
