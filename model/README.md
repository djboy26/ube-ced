# model/

Directory layout mirrors the UBE research tree so the v5 model's relative references resolve unchanged.
Nothing in `wave4/ube_model_v5` has been edited for publication.

| Path | Role |
|---|---|
| `wave4/ube_model_v5/` | The Danish survival-floor model, v5 (19 Sep 2026). Run `regression_tests.py`, `ube_model_v5.py`, `verify_results_v5.py`. |
| `wave4/ube_model_v4/survival_goods_results_v4.csv` | Reference output; v5 step 1 must reproduce it cell for cell (regression test 6). |
| `wave2/ube_model/ube_sector_io_findings.json` | Wave-2 IO findings; v5 must reproduce its healthcare figures (regression test 2). |
| `wave2/survival_goods_results_v3.csv` | Wave-2 results; used by `waterfall_v5.py` as the "before" column. |
