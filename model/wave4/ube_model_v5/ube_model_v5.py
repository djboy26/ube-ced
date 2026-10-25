#!/usr/bin/env python3
"""
UBE survival-floor model, v5 - Denmark.  Standard library only.
================================================================

v5 is the Wave 4 cycle 4 floor re-size, the run that replaces R-8 once (R-52).
It is v4 (the double-count correction, R-38/R-39, as cleared by the Physics
Validator) plus the dwelling standard and the food guidelines, applied as
SEPARATE STEPS so that each step's effect can be shown on its own:

  step 1  double count (v4, post-verification)            --upto 1 reproduces v4
  step 2  depth factors re-measured on the floor's own mix (R-61, E-RV-2 (b));
          R-42's statuses for the network and router lines are applied here too
  step 3  the dwelling standard: R-32 area (net, costed gross), R-33 set-points,
          R-49 reference mix, the monthly balance-point method (R-34), and the
          two new lines V_01 (fans) and C_03 (envelope uplift) (MC-1 to MC-4)
  step 4  the calibration x1.5, range 1.0-2.5 through the Monte Carlo (R-48)
  step 5  the vulnerable +2 K line H_03 (R-50)
  step 6  hot water at 20 L/person/day (R-51): no change to the central; 41 L as
          a sensitivity
  step 7  the food lines' quantities from the dietary guidelines (R-64)

  python ube_model_v5.py                 # all seven steps: the v5 results
  python ube_model_v5.py --upto 3        # the model after step 3 (waterfall)
  python ube_model_v5.py --check / --self-test / --draws N

The inputs the steps resolve against are computed by dwelling_v5.py,
food_v5.py and io_model_v5.py; none is hand-entered.  Everything v4 did
(loader taxonomy, corruption battery, determinism, B3 exemption, T4 rule) is
kept.  Every output row carries v5_figure_status = PROVISIONAL.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import os
import random
import re
import sys
import tempfile

from linalg import orientation_worked_example

HERE = os.path.dirname(os.path.abspath(__file__))
BASKET_CSV = os.path.join(HERE, "basket_denmark_v5.csv")
PARAM_JSON = os.path.join(HERE, "parameters_denmark_v5.json")
IO_FINDINGS = os.path.join(HERE, "io_findings_v5.json")
DWELL_FINDINGS = os.path.join(HERE, "dwelling_findings_v5.json")
FOOD_FINDINGS = os.path.join(HERE, "food_findings_v5.json")
RESULTS_BASE = os.path.join(HERE, "survival_goods_results_v5")
STEPS = ["double_count", "depth_floor_mix", "dwelling", "calibration", "vulnerable", "hot_water", "food"]
STEP_LINES = {"dwelling": ("V_01", "C_03"), "vulnerable": ("H_03",)}
CALIBRATED_LINES = ("H_01", "H_03")
HOUSEHOLD_METERED = {"H_01", "H_02", "H_03", "V_01", "A_01", "A_02", "A_03", "A_04", "A_05", "CM_02", "CM_03", "CM_05"}
SERVICE_DELIVERED = {"W_01", "W_02", "TR_01E", "TR_01L", "CM_01", "F_25"}

NAN = float("nan")
KWH_PER_GJ = 1000.0 / 3.6
CONSTRUCTIONS = ("W2", "A", "B", "C")

SECTOR_ORDER = [
    "S1_Food", "S2_Water", "S3_Heating", "S4_Appliances", "S5_Shelter",
    "S6_Clothing", "S7_Hygiene", "S8_Healthcare", "S9_Transport",
    "T4_collective",
]


def isnan(v) -> bool:
    return isinstance(v, float) and v != v


# ===========================================================================
# 1.  The failure taxonomy (unchanged from Wave 2 except one new basis token)
# ===========================================================================

REQUIRED_FIELDS = [
    "line_id", "sector", "service", "quantity", "unit", "intensity",
    "intensity_low", "intensity_high", "intensity_unit", "energy_basis",
    "source_energy_basis", "basis_reconciliation",
    "carrier", "share_electric", "share_electric_status", "exergy_factor",
    "allocation_tier", "scales_with_floor_area", "loss_regime", "boundary_depth",
    "in_floor_total", "status", "confidence", "source",
    "delivery_temperature_C", "contains", "excludes", "substitution_class", "notes",
]


class BasketError(Exception):
    """Raised when the basket file violates a structural rule."""


VOCAB = {
    "energy_basis": {
        "primary_at_ref", "delivered_electrical", "delivered_thermal_low",
        "delivered_liquid_fuel", "delivered_mixed",
        "io_construction_C",   # NEW in v4: fuels + electricity x PEF + heat x DH factor
    },
    "source_energy_basis": {
        "primary_CED", "final_energy", "delivered_energy", "project_internal",
        "derived_in_model",
    },
    "basis_reconciliation": {"same_basis", "converted", "CONTESTED_UNCONVERTED"},
    "carrier": {"electric", "thermal_low", "liquid_fuel", "embodied", "mixed"},
    "allocation_tier": {"T1_person", "T2_household", "T3_dwelling", "T4_population"},
    "boundary_depth": {"B1", "B2", "B3"},
    "loss_regime": {"storable", "perishable", "retail_shelf", "inline", "none"},
    "status": {"VERIFIED", "DERIVED", "ACCEPTABLE", "ESTIMATED", "PROVISIONAL",
               "ASSUMED", "UNSOURCED", "ILLUSTRATIVE", "UNREPRODUCIBLE"},
    "confidence": {"High", "Med", "Low"},
    "share_electric_status": {"DEFINITIONAL", "DERIVED_IO", "DERIVED",
                              "ESTIMATED", "ASSUMED"},
    "sector": set(SECTOR_ORDER),
}
STATUS_FORBIDDEN_WHEN_CONTESTED = {"VERIFIED", "DERIVED", "ACCEPTABLE"}
UNIT_PAIRS = {
    ("kg/cap/yr", "kWh/kg"): "kWh/cap/yr",
    ("m3/cap/yr", "kWh/m3"): "kWh/cap/yr",
    ("m2/cap", "kWh/m2/yr"): "kWh/cap/yr",
    ("cap/yr", "kWh/cap/yr"): "kWh/cap/yr",
    ("kWh/cap/yr", "dimensionless"): "kWh/cap/yr",
}
QUANTITY_ENVELOPE = {
    "kg/cap/yr": (0.01, 500.0), "m3/cap/yr": (0.1, 200.0), "m2/cap": (1.0, 100.0),
    "cap/yr": (1.0, 1.0), "kWh/cap/yr": (0.5, 1500.0),
}
INTENSITY_ENVELOPE = {
    "kWh/kg": (0.01, 100.0), "kWh/m3": (0.01, 20.0), "kWh/m2/yr": (0.5, 500.0),
    "kWh/cap/yr": (0.1, 3000.0), "dimensionless": (1.0, 1.0),
}
MAX_LINE_BASE_KWH = 1500.0
MIN_LINE_BASE_KWH = 0.05
MAX_BAND_RATIO = 30.0
CARRIER_RULES = {
    "electric": ({"delivered_electrical"}, (1.0, 1.0)),
    "thermal_low": ({"delivered_thermal_low", "primary_at_ref"}, (0.0, 0.0)),
    "liquid_fuel": ({"delivered_liquid_fuel"}, (0.0, 0.0)),
    "embodied": ({"primary_at_ref"}, (0.0, 1.0)),
    "mixed": ({"primary_at_ref", "delivered_mixed", "io_construction_C"}, (0.0, 1.0)),
}
BASIS_COMPATIBLE = {
    "primary_at_ref": {"primary_CED", "project_internal", "derived_in_model"},
    "delivered_electrical": {"delivered_energy", "final_energy", "project_internal", "derived_in_model"},
    "delivered_thermal_low": {"delivered_energy", "final_energy", "project_internal", "derived_in_model"},
    "delivered_liquid_fuel": {"delivered_energy", "final_energy", "project_internal", "derived_in_model"},
    "delivered_mixed": {"delivered_energy", "final_energy", "project_internal", "derived_in_model"},
    "io_construction_C": {"derived_in_model"},
}
IO_SHARE_BASES = {"primary_at_ref", "io_construction_C"}
SERVICE_STOPWORDS = {"and", "or", "the", "of", "for", "per", "a", "an", "in",
                     "with", "to", "at", "on", "from"}
SERVICE_SYNONYMS = {
    "heating": "heat", "heated": "heat", "warming": "heat", "warmth": "heat",
    "electricity": "electric", "electrical": "electric", "power": "electric",
    "dwelling": "home", "house": "home", "housing": "home", "household": "home",
    "residence": "home", "residential": "home", "domicile": "home",
    "auto": "vehicle", "car": "vehicle", "automobile": "vehicle",
    "mobile": "phone", "smartphone": "phone", "handset": "phone",
    "notebook": "laptop", "computer": "laptop",
    "washing": "laundry", "wash": "laundry",
    "refrigeration": "cold", "refrigerated": "cold", "chilled": "cold",
    "cooking": "cook", "cookery": "cook", "cuisine": "cook",
    "lighting": "light", "illumination": "light",
    "clothes": "clothing", "garments": "clothing", "apparel": "clothing",
    "shop": "retail", "store": "retail", "grocery": "retail",
    "usage": "use", "operational": "use", "operating": "use",
    "manufacture": "embodied", "manufacturing": "embodied",
    "construction": "embodied", "production": "embodied",
}
SERVICE_SIMILARITY_LIMIT = 0.60
BARE_DATABASE_NAMES = {
    "ecoinvent", "ecoinvent 3", "ecoinvent 3.x", "gabi", "simapro",
    "exiobase", "eora", "idemat", "ökobaudat", "oekobaudat",
}
DERIVED_QUANTITY_TOKEN = "DERIVED_FOOD_MASS"
IO_SHARE_PREFIX = "IO:"


def _norm_tokens(text: str) -> set:
    words = re.split(r"[^a-z0-9]+", str(text).lower())
    out = set()
    for w in words:
        if not w or w in SERVICE_STOPWORDS:
            continue
        if len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
            w = w[:-1]
        out.add(SERVICE_SYNONYMS.get(w, w))
    return out


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _as_float(value, field, lid, problems):
    try:
        return float(value)
    except (TypeError, ValueError):
        problems.append(f"{lid}: field '{field}' is not a number: {value!r} (T3)")
        return None


def validate_basket(rows: list, columns: list) -> list:
    """The whole taxonomy over a raw (all-string) basket.  Every check rejects."""
    problems: list[str] = []
    missing = [c for c in REQUIRED_FIELDS if c not in columns]
    if missing:
        return [f"basket file is missing required columns: {missing} (T1)"]

    ids = [r["line_id"] for r in rows]
    dups = sorted({i for i in ids if ids.count(i) > 1})
    if dups:
        problems.append(f"duplicate line_id values: {dups} (T1)")

    never_empty = ("line_id", "sector", "service", "quantity", "unit", "intensity",
                   "intensity_low", "intensity_high", "intensity_unit",
                   "energy_basis", "source_energy_basis", "basis_reconciliation",
                   "carrier", "share_electric", "share_electric_status",
                   "exergy_factor", "allocation_tier", "loss_regime",
                   "boundary_depth", "in_floor_total", "status", "confidence", "source")
    for r in rows:
        lid = r["line_id"] or "<no line_id>"
        for f in never_empty:
            if not str(r[f]).strip():
                problems.append(f"{lid}: field '{f}' is empty (T1)")

    # T2
    for r in rows:
        for field, allowed in VOCAB.items():
            val = str(r[field]).strip()
            if val and val not in allowed:
                problems.append(
                    f"{r['line_id']}: field '{field}' carries '{val}', which is not in the "
                    f"controlled vocabulary {sorted(allowed)} (T2)")

    # T3/T4
    for r in rows:
        lid = r["line_id"]
        qty_raw = str(r["quantity"]).strip()
        if qty_raw != DERIVED_QUANTITY_TOKEN:
            q = _as_float(qty_raw, "quantity", lid, problems)
            if q is not None:
                if q < 0:
                    problems.append(f"{lid}: negative quantity {q} (T3)")
                env = QUANTITY_ENVELOPE.get(str(r["unit"]).strip())
                if env and not (env[0] <= q <= env[1]):
                    problems.append(
                        f"{lid}: quantity {q} {r['unit']} is outside the plausible "
                        f"envelope {env} for that unit — a decimal slip or a unit error (T6)")
        i = _as_float(r["intensity"], "intensity", lid, problems)
        lo = _as_float(r["intensity_low"], "intensity_low", lid, problems)
        hi = _as_float(r["intensity_high"], "intensity_high", lid, problems)
        if None not in (i, lo, hi):
            if i <= 0 or lo < 0 or hi <= 0:
                problems.append(f"{lid}: intensity or band is zero or negative ({lo}, {i}, {hi}) (T3)")
            if not (lo <= i <= hi):
                problems.append(f"{lid}: band [{lo}, {hi}] does not bracket the central value {i} (T3)")
            if lo > 0 and hi / lo > MAX_BAND_RATIO:
                problems.append(
                    f"{lid}: band spans a factor of {hi / lo:.0f}, beyond the limit of "
                    f"{MAX_BAND_RATIO:.0f} — that is not an uncertainty band, it is two "
                    f"different quantities (T3)")
            env = INTENSITY_ENVELOPE.get(str(r["intensity_unit"]).strip())
            if env and not (env[0] <= i <= env[1]):
                problems.append(
                    f"{lid}: intensity {i} {r['intensity_unit']} is outside the plausible "
                    f"envelope {env} for that unit — a decimal slip or a unit error (T6)")
        for f, dom in (("exergy_factor", (0.0, 1.0)), ("scales_with_floor_area", (0.0, 1.0)),
                       ("in_floor_total", (0.0, 1.0))):
            v = _as_float(r[f], f, lid, problems)
            if v is not None and not (dom[0] <= v <= dom[1]):
                problems.append(f"{lid}: {f} = {v} is outside {dom} (T4)")
        for f in ("scales_with_floor_area", "in_floor_total"):
            v = _as_float(r[f], f, lid, problems)
            if v is not None and v not in (0.0, 1.0):
                problems.append(f"{lid}: {f} = {v} is a flag and must be 0 or 1 (T4)")
        s_raw = str(r["share_electric"]).strip()
        s_stat = str(r["share_electric_status"]).strip()
        if s_raw.startswith(IO_SHARE_PREFIX):
            if s_stat != "DERIVED_IO":
                problems.append(f"{lid}: share_electric is IO-derived but its status says '{s_stat}' (T2)")
            if str(r["energy_basis"]).strip() not in IO_SHARE_BASES:
                problems.append(
                    f"{lid}: an IO-derived electric share is a share of PRIMARY CED and may only "
                    f"be used on a {sorted(IO_SHARE_BASES)} line, not on '{r['energy_basis']}' (T7)")
        else:
            if s_stat == "DERIVED_IO":
                problems.append(
                    f"{lid}: share_electric_status is DERIVED_IO but the value '{s_raw}' is not an "
                    f"{IO_SHARE_PREFIX}<industry> token (T2)")
            s = _as_float(s_raw, "share_electric", lid, problems)
            if s is not None and not (0.0 <= s <= 1.0):
                problems.append(f"{lid}: share_electric = {s} is outside [0, 1]; an electric share is a fraction (T4)")

    # T5
    for r in rows:
        pair = (str(r["unit"]).strip(), str(r["intensity_unit"]).strip())
        if pair not in UNIT_PAIRS:
            problems.append(
                f"{r['line_id']}: quantity unit '{pair[0]}' times intensity unit '{pair[1]}' "
                f"does not resolve to kWh/cap/yr. Allowed pairs: {sorted(UNIT_PAIRS)} (T5)")

    # T6 line magnitude
    for r in rows:
        lid = r["line_id"]
        if str(r["quantity"]).strip() == DERIVED_QUANTITY_TOKEN:
            continue
        try:
            base = float(r["quantity"]) * float(r["intensity"])
        except (TypeError, ValueError):
            continue
        if base > MAX_LINE_BASE_KWH:
            problems.append(
                f"{lid}: quantity x intensity = {base:.1f} kWh/cap/yr exceeds the plausibility "
                f"ceiling of {MAX_LINE_BASE_KWH:.0f} for a single survival-basket line (T6)")
        if 0 < base < MIN_LINE_BASE_KWH:
            problems.append(
                f"{lid}: quantity x intensity = {base:.4f} kWh/cap/yr is below "
                f"{MIN_LINE_BASE_KWH} — too small to be a line rather than a rounding artefact (T6)")

    # T7
    for r in rows:
        lid = r["line_id"]
        carrier = str(r["carrier"]).strip()
        basis = str(r["energy_basis"]).strip()
        rule = CARRIER_RULES.get(carrier)
        if rule is None:
            continue
        allowed_bases, share_dom = rule
        if basis not in allowed_bases:
            problems.append(
                f"{lid}: carrier '{carrier}' with energy_basis '{basis}'. A '{carrier}' line may "
                f"only be {sorted(allowed_bases)}. This is the silent-basis-change signature (T7)")
        s_raw = str(r["share_electric"]).strip()
        if not s_raw.startswith(IO_SHARE_PREFIX):
            try:
                s = float(s_raw)
            except (TypeError, ValueError):
                s = None
            if s is not None and not (share_dom[0] <= s <= share_dom[1]):
                problems.append(
                    f"{lid}: carrier '{carrier}' requires an electric share in {share_dom}; the "
                    f"line declares {s} (T7)")
        if carrier == "thermal_low" and not str(r["delivery_temperature_C"]).strip():
            problems.append(f"{lid}: thermal carrier without delivery_temperature_C (T1)")
        if str(r["delivery_temperature_C"]).strip():
            t = _as_float(r["delivery_temperature_C"], "delivery_temperature_C", lid, problems)
            if t is not None and not (5.0 <= t <= 95.0):
                problems.append(
                    f"{lid}: delivery temperature {t} C is outside 5-95 C for a low-temperature service (T6)")

    # T8
    for r in rows:
        lid = r["line_id"]
        basis = str(r["energy_basis"]).strip()
        src_basis = str(r["source_energy_basis"]).strip()
        recon = str(r["basis_reconciliation"]).strip()
        compatible = BASIS_COMPATIBLE.get(basis, set())
        if src_basis and src_basis not in compatible and recon == "same_basis":
            problems.append(
                f"{lid}: declares energy_basis '{basis}' on a source whose basis is "
                f"'{src_basis}', and declares them the same basis. Either convert "
                f"(basis_reconciliation=converted) or say so (CONTESTED_UNCONVERTED). This is the "
                f"error class that put 410 kWh of the Wave 2 floor on a basis the project's own "
                f"register denies (T8)")
        if src_basis in compatible and recon == "CONTESTED_UNCONVERTED":
            problems.append(f"{lid}: basis marked contested but '{src_basis}' is already compatible with '{basis}' (T8)")
        if recon == "CONTESTED_UNCONVERTED" and str(r["status"]).strip() in STATUS_FORBIDDEN_WHEN_CONTESTED:
            problems.append(
                f"{lid}: status '{r['status']}' on a line whose energy basis is contested. A figure "
                f"whose basis is unresolved is not verified, derived or acceptable (T8)")

    # T9
    services = [r["service"] for r in rows]
    dup_s = sorted({s for s in services if services.count(s) > 1})
    if dup_s:
        problems.append(f"duplicate service values (rule R1): {dup_s} (T9)")
    toks = {r["line_id"]: _norm_tokens(r["service"]) for r in rows}
    by_id = {r["line_id"]: r for r in rows}
    for a in range(len(rows)):
        for b in range(a + 1, len(rows)):
            ia, ib = rows[a]["line_id"], rows[b]["line_id"]
            j = _jaccard(toks[ia], toks[ib])
            if j >= SERVICE_SIMILARITY_LIMIT:
                problems.append(
                    f"{ia} and {ib}: service names '{rows[a]['service']}' and '{rows[b]['service']}' "
                    f"normalise to {j:.0%} the same tokens. A semantic duplicate is still a double count (T9)")
    fingerprint = {}
    for r in rows:
        key = (str(r["substitution_class"]).strip(), str(r["unit"]).strip(),
               str(r["intensity_unit"]).strip(), str(r["quantity"]).strip(),
               str(r["intensity"]).strip())
        fingerprint.setdefault(key, []).append(r["line_id"])
    for key, members in fingerprint.items():
        if len(members) > 1:
            problems.append(
                f"{members}: identical quantity, intensity and units inside one substitution class "
                f"'{key[0]}'. Two names, one measurement (T9)")
    id_pat = re.compile(r"\b([A-Z]{1,3}_[0-9]{2}[A-Z]?)\b")
    id_set = set(ids)
    for r in rows:
        lid = r["line_id"]
        contains_txt = str(r["contains"])
        for ref in id_pat.findall(contains_txt):
            if ref in id_set and ref != lid:
                problems.append(
                    f"{lid}: contains[] names another basket line {ref} — that component is counted "
                    f"twice (rule R2) (T9)")
        ctoks = _norm_tokens(contains_txt)
        if ctoks:
            for other in ids:
                if other == lid:
                    continue
                otoks = toks[other]
                if len(otoks) >= 2 and otoks <= ctoks:
                    problems.append(
                        f"{lid}: contains[] describes the whole of {other} "
                        f"('{by_id[other]['service']}') by name rather than by id. Naming it "
                        f"differently does not stop it being counted twice (T9)")
        for ref in id_pat.findall(str(r["excludes"])):
            if ref == lid:
                problems.append(f"{lid}: excludes[] names itself (T9)")

    # T10
    for r in rows:
        if str(r["allocation_tier"]).strip() == "T4_population" and \
                str(r["in_floor_total"]).strip() not in ("0", "0.0"):
            problems.append(
                f"{r['line_id']}: allocation_tier T4_population with in_floor_total=1. CED Framework "
                f"Spec v3 sec 2.2 reports population-level items alongside the floor, not inside it (T10)")
        if str(r["boundary_depth"]).strip() == "B3" and \
                str(r["in_floor_total"]).strip() not in ("0", "0.0"):
            problems.append(
                f"{r['line_id']}: a B3 (complete-boundary) line may not sit inside a B2 floor total "
                f"without a declared truncation adjustment (T10)")

    # T11
    for r in rows:
        src = str(r["source"]).strip()
        if src.lower() in BARE_DATABASE_NAMES:
            problems.append(
                f"{r['line_id']}: source '{src}' is a bare database name with no process, version, "
                f"geography or system model — not a citation (T11)")
    return problems


# ===========================================================================
# 2.  Parameters, IO findings and the construction switches
# ===========================================================================

def load_parameters() -> dict:
    with open(PARAM_JSON, encoding="utf-8") as fh:
        return json.load(fh)


def load_findings() -> dict:
    if not os.path.exists(IO_FINDINGS):
        raise BasketError(f"{os.path.basename(IO_FINDINGS)} is absent; run io_model_v4.py first. "
                          "The model will not default the IO-derived quantities")
    with open(IO_FINDINGS, encoding="utf-8") as fh:
        return json.load(fh)


def load_json(path, what):
    if not os.path.exists(path):
        raise BasketError(f"{os.path.basename(path)} is absent; run {what} first")
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def construction_config(params, findings, shares="C", depth="C", healthcare="C") -> dict:
    """Resolve the three switches into concrete shares, depth factors and HC_02."""
    for x in (shares, depth, healthcare):
        if x not in CONSTRUCTIONS:
            raise BasketError(f"unknown construction '{x}'; use one of {CONSTRUCTIONS}")
    cfg = {"shares": shares, "depth": depth, "healthcare": healthcare}
    cfg["composition"] = findings["carrier_composition"][shares]["by_industry"]
    if depth == "W2":
        ref = params["wave2_reference"]["depth"]
        cfg["B1"], cfg["B3"] = ref["B1"], ref["B3_measured"]
    else:
        tr = findings["truncation"][depth]
        cfg["B1"], cfg["B3"] = round(tr["B1"], 3), round(tr["B3_measured"], 3)
    hc_comp = findings["carrier_composition"][healthcare]["by_industry"]["86000"]
    cfg["hc_share"] = hc_comp["electric_share_of_primary_at_pef_ref"]
    if healthcare == "W2":
        ref = params["wave2_reference"]["healthcare_HC_02_kWh"]
        cfg["hc"] = {"mode": "device", "low": ref["low"], "central": ref["central"], "high": ref["high"]}
    elif healthcare in ("A", "B"):
        h = findings["healthcare"][healthcare]
        cfg["hc"] = {"mode": "device", "low": h["low_health_domestic_only"],
                     "central": h["central_health_domestic_technology"],
                     "high": h["high_health_plus_care_domestic_technology"]}
    else:
        cfg["hc"] = {"mode": "C", "components": findings["healthcare"]["C"]["components_kWh"]}
    cfg["hc_C_components"] = findings["healthcare"]["C"]["components_kWh"]
    return cfg


def v5_config(params, findings, upto=7) -> dict:
    """Construction C (v4, post-verification) plus the v5 steps 2..upto."""
    cfg = construction_config(params, findings, "C", "C", "C")
    cfg["upto"] = upto
    cfg["steps"] = set(STEPS[:upto])
    cfg["dwell"] = load_json(DWELL_FINDINGS, "dwelling_v5.py")
    cfg["food"] = load_json(FOOD_FINDINGS, "food_v5.py")
    cfg["excluded"] = set()
    for step, lines in STEP_LINES.items():
        if step not in cfg["steps"]:
            cfg["excluded"].update(lines)
    # R-42 statuses are applied with step 2; step 1 keeps v4's exactly
    cfg["status_override"] = {} if "depth_floor_mix" in cfg["steps"] else {"CM_01": "DERIVED", "CM_02": "ASSUMED"}
    cfg["depth_source"] = "like-for-like (fossil only), v4" if upto < 2 else "floor's own mix (R-61)"
    return cfg


def floor_mix_depth(params, findings, basket, cfg_final) -> dict:
    """
    R-61 / E-RV-2 (b): one depth factor for every line, measured with each part
    of the economy weighted as the floor weights it.  Weights are the floor's own
    B2 primary energy (DK-2023, central, depth 1.0) in three parts: household-
    metered energy lines, service-provider delivered-energy lines, and life-cycle
    (goods) lines.  The part factors are io_model_v5.py's tier series on the
    matching COICOP classes (construction C; option 1 household energy at tier 0).
    THE MAPPING OF FLOOR LINES ONTO PARTS IS A JUDGEMENT, stated here and in the
    narrative; it is the Physics Validator's (Rerun_Verification.md sec 3.5).
    """
    run = run_once(params, basket, cfg_final, default_scenario(params, cfg_final))
    w = {"energy": 0.0, "services": 0.0, "goods": 0.0}
    for l in run["lines"]:
        if not l["in_floor"] or l["boundary_depth"] != "B2":
            continue
        part = "energy" if l["line_id"] in HOUSEHOLD_METERED else (
            "services" if l["line_id"] in SERVICE_DELIVERED else "goods")
        w[part] += l["primary_DK_2023_1.6"]
    tot = sum(w.values())
    pc = findings["truncation"]["parts_C"]
    b1 = sum(w[p] * pc[p]["B1"] for p in w) / tot
    b3 = sum(w[p] * pc[p]["B3_measured"] for p in w) / tot
    b1_svc1 = (w["energy"] * pc["energy"]["B1"] + w["services"] + w["goods"] * pc["goods"]["B1"]) / tot
    b3_svc1 = (w["energy"] * pc["energy"]["B3_measured"] + w["services"] + w["goods"] * pc["goods"]["B3_measured"]) / tot
    return {"weights_kWh": w, "weights_share": {p: v / tot for p, v in w.items()},
            "part_factors": {p: {"B1": pc[p]["B1"], "B3": pc[p]["B3_measured"]} for p in w},
            "B1": b1, "B3": b3, "B1_rounded": round(b1, 3), "B3_rounded": round(b3, 3),
            "variant_service_lines_fully_captured": {"B1": b1_svc1, "B3": b3_svc1}}


def effective_params(params: dict, cfg: dict) -> dict:
    """A copy of the parameters with the construction's depth factors applied."""
    p = json.loads(json.dumps(params))
    bd = p["boundary_depth"]
    bd["factors_relative_to_B2"]["B1"] = cfg["B1"]
    bd["factors_relative_to_B2"]["B3_measured"] = cfg["B3"]
    bd["monte_carlo_range"] = [cfg["B1"], bd["monte_carlo_range"][1]]
    return p


def read_basket_raw(path=None):
    path = path or BASKET_CSV
    with open(path, encoding="utf-8", newline="") as fh:
        rd = csv.DictReader(fh)
        rows = [dict(r) for r in rd]
        cols = list(rd.fieldnames or [])
    for r in rows:
        for k in cols:
            if r.get(k) is None:
                r[k] = ""
    return rows, cols


def load_basket(cfg: dict, path=None) -> list:
    rows, cols = read_basket_raw(path)
    problems = validate_basket(rows, cols)
    if problems:
        raise BasketError("basket REJECTED:\n  - " + "\n  - ".join(problems))
    comp = cfg["composition"]
    out = []
    for r in rows:
        r = dict(r)
        r["share_electric_raw"] = r["share_electric"]
        v = str(r["share_electric"]).strip()
        if v.startswith(IO_SHARE_PREFIX):
            code = v[len(IO_SHARE_PREFIX):]
            if r["line_id"] == "HC_02":
                r["share_electric"] = cfg["hc_share"]
            else:
                if code not in comp:
                    raise BasketError(f"share_electric {v}: Danish industry {code} is not in the "
                                      f"measured carrier-composition table")
                r["share_electric"] = comp[code]["electric_share_of_primary_at_pef_ref"]
        else:
            r["share_electric"] = float(v)
        if not (0.0 <= r["share_electric"] <= 1.0):
            raise BasketError("a resolved electric share is outside [0, 1]")
        r["quantity"] = NAN if r["quantity"] == DERIVED_QUANTITY_TOKEN else float(r["quantity"])
        for c in ("intensity", "intensity_low", "intensity_high", "exergy_factor",
                  "scales_with_floor_area", "in_floor_total"):
            r[c] = float(r[c])
        if r["line_id"] in cfg.get("status_override", {}):
            r["status"] = cfg["status_override"][r["line_id"]]
        if "dwell" in cfg and r["line_id"] in ("H_01", "H_03"):
            want = dwelling_quantity({**cfg, "steps": set(STEPS)}, r["line_id"], v5_defaults(cfg))
            if abs(want - r["quantity"]) > 0.01:
                raise BasketError(f"{r['line_id']} quantity {r['quantity']} in the basket, but dwelling_findings_v5.json "
                                  f"gives {want:.4f}. The dwelling lines are resolved from the dwelling model, never hand-entered")
        if "food" in cfg and r["line_id"] in cfg["food"]["central"]["line_kg_cap_yr"]:
            want = cfg["food"]["central"]["line_kg_cap_yr"][r["line_id"]]
            if abs(want - r["quantity"]) > 0.001:
                raise BasketError(f"{r['line_id']} quantity {r['quantity']} in the basket, but food_findings_v5.json gives {want:.4f}")
        if r["line_id"] == "HC_02" and r["energy_basis"] == "io_construction_C":
            # The basket always carries construction C (ruled, R-39); whatever
            # construction this run uses, those numbers must match the IO model.
            comps = cfg["hc_C_components"]
            for band, col in (("central", "intensity"), ("low", "intensity_low"),
                              ("high", "intensity_high")):
                c = comps[band]
                ref = c["F"] + 1.6 * c["E"] + 1.08 * c["H"]
                if abs(ref - r[col]) > 0.001:
                    raise BasketError(
                        f"HC_02 {col} = {r[col]} in the basket, but construction C in "
                        f"io_findings_v4.json gives {ref:.4f}. The healthcare line is resolved "
                        f"from the IO model, never hand-entered")
            r["effective_basis"] = "io_construction_C" if cfg["hc"]["mode"] == "C" else "primary_at_ref"
        else:
            r["effective_basis"] = r["energy_basis"]
        out.append(r)
    return out


# ===========================================================================
# 3.  Carrier conversion
# ===========================================================================

def heat_primary_factor(pef: float, params: dict, dh_variant: str | None = None) -> float:
    hc = params["heat_carrier"]
    name = dh_variant or hc["district_heat_factor_default"]
    dh = hc["district_heat_factor_variants"][name]
    return hc["district_heat_share"] * dh + hc["heat_pump_share"] * (pef / hc["heat_pump_cop"])


def hc_C_value(comp: dict, pef: float, dhf: float) -> float:
    return comp["F"] + comp["E"] * pef + comp["H"] * dhf


def line_delivered_and_primary(row, pef, params, ctx):
    lid = row["line_id"]
    qty = ctx["quantities"][lid]
    intensity = ctx["intensities"][lid]
    base = qty * intensity
    basis = row["effective_basis"]
    s_el = row["share_electric"]
    pef_ref = params["pef_reference"]
    if basis == "primary_at_ref":
        primary = base * ((1.0 - s_el) + s_el * pef / pef_ref)
        delivered = NAN
    elif basis == "io_construction_C":
        dhf = params["heat_carrier"]["district_heat_factor_variants"][
            ctx.get("dh_variant") or params["heat_carrier"]["district_heat_factor_default"]]
        primary = qty * hc_C_value(ctx["hc_components"]["central"], pef, dhf)
        delivered = NAN
    elif basis == "delivered_electrical":
        primary = base * pef
        delivered = base
    elif basis == "delivered_thermal_low":
        primary = base * heat_primary_factor(pef, params, ctx.get("dh_variant"))
        delivered = base
    elif basis == "delivered_liquid_fuel":
        primary = base * ctx["wtt"]
        delivered = base
    elif basis == "delivered_mixed":
        nef = ctx["non_electric_factor"]
        primary = base * (s_el * pef + (1.0 - s_el) * nef)
        delivered = base
    else:
        raise BasketError(f"{lid}: unknown energy_basis '{basis}'")
    exergy = (delivered * row["exergy_factor"]) if not isnan(delivered) else NAN
    return delivered, primary, exergy


# ===========================================================================
# 4.  One deterministic run
# ===========================================================================

def make_context(params, basket, cfg, *, scenario) -> dict:
    quantities, intensities, lows, highs = {}, {}, {}, {}
    floor_area = scenario["floor_area"]
    area_ref = params["floor_area_m2_per_person"]["central"]
    modal = params["modal_split"]["variants"][scenario["modal_split"]]
    phi = scenario["fleet_electrification"]
    tom = params["tomato"]["variants"][scenario["tomato"]]
    cook = params["cooking"]["variants"][scenario["cooking"]]
    el_0, liq_0 = modal["propulsion_electric_kWh"], modal["propulsion_liquid_kWh"]
    el_1 = params["fleet_electrification"]["fully_electrified_propulsion_electric_kWh"]
    liq_1 = params["fleet_electrification"]["fully_electrified_propulsion_liquid_kWh"]
    steps = cfg.get("steps", set())
    food_q = food_quantities(cfg, scenario)
    for r in basket:
        lid = r["line_id"]
        q = r["quantity"]
        i, lo, hi = r["intensity"], r["intensity_low"], r["intensity_high"]
        if lid == "F_04":
            i, lo, hi = tom["kWh_per_kg"], tom["low"], tom["high"]
        elif lid == "TR_01E":
            q = (el_0 + phi * (el_1 - el_0)) * scenario.get("pkm_scale", 1.0)
        elif lid == "TR_01L":
            q = (liq_0 + phi * (liq_1 - liq_0)) * scenario.get("pkm_scale", 1.0)
        elif lid == "TR_02":
            i, lo, hi = (modal["vehicle_manufacture_kWh"], modal["vehicle_manufacture_low"],
                         modal["vehicle_manufacture_high"])
            q = r["quantity"] * scenario.get("pkm_scale", 1.0)
        elif lid == "A_01":
            q = cook["kWh_per_cap_yr"]
            i, lo, hi = 1.0, cook["low"] / q, cook["high"] / q
        elif lid in ("C_01", "V_01", "C_03"):
            q = floor_area
        elif lid == "H_01":
            if "dwelling" in steps:
                q = dwelling_quantity(cfg, "H_01", scenario)
                if "calibration" in steps:
                    i, lo, hi = 1.0, 1.0, 1.0
                else:
                    i, lo, hi = 1.0, *params["v5"]["H01_uncalibrated_relative_band"]
            else:
                q = params["v5"]["wave2_H01_kWh"] * floor_area / params["v5"]["wave2_floor_area"]
                i, lo, hi = 1.0, *params["v5"]["H01_uncalibrated_relative_band"]
        elif lid == "H_03":
            q = dwelling_quantity(cfg, "H_03", scenario)
        elif lid == "H_02":
            q = r["quantity"] * scenario["hot_water_L"] / 20.0
        elif lid in food_q:
            q = food_q[lid]
        elif lid == "HC_02" and cfg["hc"]["mode"] == "device":
            i, lo, hi = cfg["hc"]["central"], cfg["hc"]["low"], cfg["hc"]["high"]
        quantities[lid], intensities[lid], lows[lid], highs[lid] = q, i, lo, hi
    food_mass = 0.0
    losses = params["food_loss_regimes"][scenario["food_loss"]]
    for r in basket:
        if r["sector"] != "S1_Food" or r["line_id"] == "F_25":
            continue
        if r["loss_regime"] == "inline" or r["unit"] != "kg/cap/yr":
            continue
        food_mass += quantities[r["line_id"]]
    quantities["F_25"] = food_mass
    return {
        "quantities": quantities, "intensities": intensities, "lows": lows, "highs": highs,
        "losses": losses, "wtt": scenario["wtt"], "dh_variant": scenario["dh_variant"],
        "non_electric_factor": params["non_electric_delivered_to_primary_factor"]["central"],
        "food_retail_mass_kg": quantities["F_25"],
        "food_retail_throughput_kg": quantities["F_25"] * losses["retail_shelf"],
        "hc_components": cfg["hc"].get("components"),
    }


def v5_defaults(cfg) -> dict:
    P = json.load(open(PARAM_JSON, encoding="utf-8"))
    D = P["dwelling"]
    return {"calibration": D["calibration_R48"]["central"], "vuln_share": D["vulnerable_share_R50"]["central"],
            "floor_area": D["floor_area_net_m2_per_cap_R32"] * D["net_to_gross"]["central"],
            "envelope": "frame", "hot_water_L": 20.0, "food_rule": "guidelines"}


def dwelling_quantity(cfg, lid, scenario) -> float:
    """H_01 / H_03, kWh/cap/yr delivered heat, from dwelling_findings_v5.json."""
    c = cfg["dwell"]["costing"]
    env = scenario.get("envelope", "frame")
    q_std = c["standard_R33"][env]["reference_mix_kWh_m2"]
    q_vul = c["vulnerable_R50"][env]["reference_mix_kWh_m2"]
    cal = scenario["calibration"] if "calibration" in cfg.get("steps", STEPS) else 1.0
    if lid == "H_01":
        return q_std * cal * scenario["floor_area"]
    return (q_vul - q_std) * cal * scenario["floor_area"] * scenario["vuln_share"]


def food_quantities(cfg, scenario) -> dict:
    if "food" not in cfg:
        return {}
    f = cfg["food"]
    if "food" not in cfg.get("steps", STEPS) or scenario.get("food_rule") == "modelled":
        return dict(f["modelled_kg_cap_yr"])
    if scenario.get("food_rule") == "scaled":
        return dict(f["sensitivity_all_energy_scaled"]["line_kg_cap_yr"])
    return dict(f["central"]["line_kg_cap_yr"])


def default_scenario(params, cfg=None) -> dict:
    v5 = {}
    if cfg is not None and "dwell" in cfg:
        v5 = v5_defaults(cfg)
        if "dwelling" not in cfg["steps"]:
            v5["floor_area"] = params["v5"]["wave2_floor_area"]
    return {
        **v5,
        "floor_area": v5.get("floor_area", params["floor_area_m2_per_person"]["central"]),
        "modal_split": params["modal_split"]["default"],
        "fleet_electrification": params["fleet_electrification"]["default"],
        "tomato": params["tomato"]["default"],
        "cooking": params["cooking"]["default"],
        "food_loss": params["food_loss_default"],
        "healthcare": params["healthcare"]["default"],
        "boundary_depth": params["boundary_depth"]["default"],
        "dh_variant": params["heat_carrier"]["district_heat_factor_default"],
        "wtt": params["liquid_fuel_well_to_tank"]["central"],
    }


def run_once(params, basket, cfg, scenario) -> dict:
    ctx = make_context(params, basket, cfg, scenario=scenario)
    depth = params["boundary_depth"]["factors_relative_to_B2"][scenario["boundary_depth"]]
    hc_line = params["healthcare"]["variants"][scenario["healthcare"]]
    labels = list(params["pef_scenarios"])
    lines = []
    for r in basket:
        lid = r["line_id"]
        in_floor = bool(r["in_floor_total"]) and lid not in cfg.get("excluded", ())
        if lid in ("HC_01", "HC_02"):
            in_floor = (lid == hc_line)
        loss = ctx["losses"][r["loss_regime"]]
        rec = {"line_id": lid, "sector": r["sector"], "service": r["service"],
               "in_floor": in_floor, "boundary_depth": r["boundary_depth"]}
        for label, pef in params["pef_scenarios"].items():
            delivered, primary, exergy = line_delivered_and_primary(r, pef, params, ctx)
            primary *= loss
            if r["boundary_depth"] == "B2":
                primary *= depth
            rec[f"primary_{label}"] = primary
            if label == "DK_2023_1.6":
                rec["delivered_DK"] = delivered * loss if not isnan(delivered) else NAN
                rec["exergy_DK"] = exergy * loss if not isnan(exergy) else NAN
        lines.append(rec)
    floor = [l for l in lines if l["in_floor"]]
    totals = {lab: sum(l[f"primary_{lab}"] for l in floor) for lab in labels}
    sector_totals = {lab: {} for lab in labels}
    for lab in labels:
        for l in floor:
            sector_totals[lab][l["sector"]] = sector_totals[lab].get(l["sector"], 0.0) + l[f"primary_{lab}"]
    return {
        "lines": lines, "totals": totals, "sector_totals": sector_totals, "context": ctx,
        "scenario": scenario,
        "delivered_exergy_DK": sum(l["exergy_DK"] for l in floor if not isnan(l["exergy_DK"])),
        "delivered_energy_DK": sum(l["delivered_DK"] for l in floor if not isnan(l["delivered_DK"])),
    }


# ===========================================================================
# 5.  Monte Carlo (same seed, draws, distribution and structure as Wave 2)
# ===========================================================================

def pert_draws(rng, low, mode, high, n, lam=4.0) -> list:
    span = high - low
    if span <= 0:
        return [mode] * n
    a = 1.0 + lam * (mode - low) / span
    b = 1.0 + lam * (high - mode) / span
    bv = rng.betavariate
    return [low + bv(a, b) * span for _ in range(n)]


def widen(central, low, high, factor):
    return central - (central - low) * factor, central + (high - central) * factor


def percentile(sorted_vals, p) -> float:
    """numpy's default ('linear') percentile on an already-sorted list."""
    n = len(sorted_vals)
    pos = (p / 100.0) * (n - 1)
    lo = int(math.floor(pos))
    hi = min(lo + 1, n - 1)
    frac = pos - lo
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * frac


def monte_carlo(params, basket, cfg, scenario, *, draws=None, seed=None,
                depth_range=None, correlated=False, variance_for=("DK_2023_1.6",), cal_fixed=None):
    """
    Wave 2's Monte Carlo, ported.  Per draw: one boundary-depth factor (PERT),
    one food-loss regime, one CHP convention for district heat, one
    well-to-tank factor, shared by every line; then, for each grid column
    separately, an independent PERT draw on every in-floor line's band widened
    by its source status (or, if ``correlated``, one shared draw per status
    class).  Normative axes DJ has ruled on are scenarios, never sampled.

    v4 addition: under construction C the healthcare line's band is computed
    per draw from its fuel, electricity and heat components at that column's
    PEF and that draw's CHP convention, so its district heat follows the same
    convention as household heat.
    """
    mc = params["monte_carlo"]
    draws = draws or mc["draws"]
    rng = random.Random(seed if seed is not None else mc["seed"])
    widening = params["status_uncertainty_widening"]
    ctx = make_context(params, basket, cfg, scenario=scenario)

    bd = params["boundary_depth"]
    d_lo, d_hi = depth_range or bd["monte_carlo_range"]
    d_mode = min(max(bd["monte_carlo_mode"], d_lo), d_hi)
    depth = pert_draws(rng, d_lo, d_mode, d_hi, draws)

    regimes = list(params["food_loss_regimes"])
    reg_pick = [rng.randrange(len(regimes)) for _ in range(draws)]
    loss_draw = {k: [params["food_loss_regimes"][regimes[j]][k] for j in reg_pick]
                 for k in ("storable", "perishable", "retail_shelf", "inline", "none")}

    dh_names = ["energistyrelsen_1_08", "br18_regulatory_0_85",
                "energistatistik_200pct_0_78", "energy_allocation_1_43"]
    dh_vals = [params["heat_carrier"]["district_heat_factor_variants"][n] for n in dh_names]
    dh_idx = [rng.randrange(len(dh_names)) for _ in range(draws)]
    dh_pick = [dh_vals[j] for j in dh_idx]

    w = params["liquid_fuel_well_to_tank"]
    wtt = pert_draws(rng, w["low"], w["central"], w["high"], draws)

    # v5 (R-48): one calibration factor per draw, shared by H_01 and H_03
    cal_ratio = None
    if "calibration" in cfg.get("steps", set()):
        if cal_fixed is not None:
            scenario = {**scenario, "calibration": cal_fixed}
            ctx = make_context(params, basket, cfg, scenario=scenario)
        else:
            cb = json.load(open(PARAM_JSON, encoding="utf-8"))["dwelling"]["calibration_R48"]
            cal = pert_draws(rng, cb["low"], cb["central"], cb["high"], draws)
            cal_ratio = [c / scenario["calibration"] for c in cal]

    hc_line = params["healthcare"]["variants"][scenario["healthcare"]]
    statuses = sorted({r["status"] for r in basket})
    shared = {}
    if correlated:
        for st in statuses:
            shared[st] = pert_draws(rng, -1.0, 0.0, 1.0, draws)

    out = {}
    hp = params["heat_carrier"]
    for label, pef in params["pef_scenarios"].items():
        total = [0.0] * draws
        keep = label in variance_for
        contrib = {}
        heat_factor = [hp["district_heat_share"] * d + hp["heat_pump_share"] * (pef / hp["heat_pump_cop"])
                       for d in dh_pick]
        for r in basket:
            lid = r["line_id"]
            in_floor = bool(r["in_floor_total"]) and lid not in cfg.get("excluded", ())
            if lid in ("HC_01", "HC_02"):
                in_floor = (lid == hc_line)
            if not in_floor:
                continue
            f = widening.get(r["status"], 1.0)
            qty = ctx["quantities"][lid]
            basis = r["effective_basis"]
            if basis == "io_construction_C":
                comps = ctx["hc_components"]
                prim = [0.0] * draws
                # one band per CHP convention; each draw uses its own convention
                bands = []
                for dv in dh_vals:
                    cen = hc_C_value(comps["central"], pef, dv)
                    lo, hi = widen(cen, hc_C_value(comps["low"], pef, dv),
                                   hc_C_value(comps["high"], pef, dv), f)
                    bands.append((max(lo, 0.0), cen, hi))
                if correlated:
                    z = shared[r["status"]]
                    for i in range(draws):
                        lo, cen, hi = bands[dh_idx[i]]
                        zi = z[i]
                        prim[i] = qty * (cen + zi * (cen - lo) if zi < 0 else cen + zi * (hi - cen))
                else:
                    bv = rng.betavariate
                    pars = []
                    for lo, cen, hi in bands:
                        span = hi - lo
                        pars.append((lo, span, 1.0 + 4.0 * (cen - lo) / span, 1.0 + 4.0 * (hi - cen) / span))
                    for i in range(draws):
                        lo, span, a, b = pars[dh_idx[i]]
                        prim[i] = qty * (lo + bv(a, b) * span)
            else:
                cen = ctx["intensities"][lid]
                lo, hi = widen(cen, ctx["lows"][lid], ctx["highs"][lid], f)
                lo = max(lo, 0.0)
                if correlated:
                    z = shared[r["status"]]
                    inten = [cen + zi * (cen - lo) if zi < 0 else cen + zi * (hi - cen) for zi in z]
                else:
                    inten = pert_draws(rng, lo, cen, hi, draws)
                if basis == "primary_at_ref":
                    s = r["share_electric"]
                    k = qty * ((1 - s) + s * pef / params["pef_reference"])
                    prim = [k * v for v in inten]
                elif basis == "delivered_electrical":
                    k = qty * pef
                    prim = [k * v for v in inten]
                elif basis == "delivered_thermal_low":
                    prim = [qty * v * h for v, h in zip(inten, heat_factor)]
                elif basis == "delivered_liquid_fuel":
                    prim = [qty * v * t for v, t in zip(inten, wtt)]
                elif basis == "delivered_mixed":
                    s = r["share_electric"]
                    k = qty * (s * pef + (1 - s) * ctx["non_electric_factor"])
                    prim = [k * v for v in inten]
                else:
                    raise BasketError(f"{lid}: unknown basis")
            if cal_ratio is not None and lid in CALIBRATED_LINES:
                prim = [p * c for p, c in zip(prim, cal_ratio)]
            ld = loss_draw[r["loss_regime"]]
            if r["boundary_depth"] == "B2":
                prim = [p * l * d for p, l, d in zip(prim, ld, depth)]
            else:
                prim = [p * l for p, l in zip(prim, ld)]
            total = [t + p for t, p in zip(total, prim)]
            if keep:
                contrib[lid] = prim
        s_tot = sorted(total)
        n = float(draws)
        mean = sum(total) / n
        var = sum((t - mean) ** 2 for t in total) / n
        res = {"mean": mean, "median": percentile(s_tot, 50), "p05": percentile(s_tot, 5),
               "p95": percentile(s_tot, 95), "p25": percentile(s_tot, 25),
               "p75": percentile(s_tot, 75), "sd": math.sqrt(var)}
        if keep:
            cov = {}
            for lid, v in contrib.items():
                mv = sum(v) / n
                cov[lid] = sum((a - mv) * (t - mean) for a, t in zip(v, total)) / (n - 1)
            res["variance_share"] = {k: c / var for k, c in sorted(cov.items(), key=lambda kv: -kv[1])}
        out[label] = res
    return out


# ===========================================================================
# 6.  Sensitivity ranking (unchanged method)
# ===========================================================================

def sensitivity_ranking(params, basket, cfg) -> tuple:
    base = default_scenario(params, cfg)
    central = run_once(params, basket, cfg, base)["totals"]["DK_2023_1.6"]

    def total(**over):
        s = dict(base)
        s.update(over)
        return run_once(params, basket, cfg, s)["totals"]["DK_2023_1.6"]

    tr_c = cfg
    axes = []
    lo, hi = total(boundary_depth="B1"), total(boundary_depth="B3_measured")
    axes.append((f"Accounting boundary depth (B1 to B3, MEASURED on Danish IO, construction {tr_c['depth']})",
                 lo, hi,
                 f"Methodological. No physical answer. Both ends measured by tier expansion on the Danish "
                 f"EE-IO model, construction {tr_c['depth']}: B1 = {tr_c['B1']}, B3 = {tr_c['B3']}. "
                 f"This is the ranked version", True))
    lo_lit, hi_lit = total(boundary_depth="B1"), total(boundary_depth="B3_literature_high")
    axes.append(("MEMO Accounting boundary depth (B1 to B3 literature high, ASSUMED)", lo_lit, hi_lit,
                 f"NOT RANKED and NOT CONFIRMED. CED Framework Spec v3 sec 3.2 flags the +25% to +50% B3 "
                 f"bracket as ASSUMED. The measured B2-to-B3 gap is +{100 * (tr_c['B3'] - 1):.1f}%, not "
                 f"+50%. Reported so the disagreement is visible, excluded from the ranking so that an "
                 f"assumption cannot outrank a measurement", False))
    lo, hi = total(healthcare="excluded"), total(healthcare="eeio_service_footprint")
    axes.append((f"Healthcare (excluded to full service footprint, construction {cfg['healthcare']})", lo, hi,
                 "Evidence, corrected in v4 for the oil and gas double count (R-38) and built as "
                 "construction C (R-39)" if cfg["healthcare"] == "C" else
                 f"Healthcare built as construction {cfg['healthcare']}", True))
    grid = run_once(params, basket, cfg, base)["totals"]
    axes.append(("Grid scenario (the mandated triple)", grid["Renewable_1.0"], grid["Fossil_2.5"],
                 f"Physical, and the project's mandated reporting convention. Embodied lines carry the "
                 f"cumulative electric share of their Danish producing industry, construction {cfg['shares']}",
                 True))
    lo, hi = total(fleet_electrification=0.0), total(fleet_electrification=1.0)
    axes.append(("Fleet electrification (2023 fleet to fully electrified)", min(lo, hi), max(lo, hi),
                 "Technology scenario. OPEN - DJ has not ruled. Invisible in the mandated triple", True))
    lo, hi = total(food_loss="household_only"), total(food_loss="cascade_high")
    axes.append(("Food loss cascade (household share only to full cascade high)", lo, hi,
                 "Unresolved evidence. Location-of-recipient puts these losses inside the boundary", True))
    lo, hi = total(modal_split="dls_public_transport"), total(modal_split="danish_actual")
    axes.append(("Mobility modal split (public transport to Danish actual)", lo, hi,
                 "Normative - DJ has RULED (R-6). Reported as a scenario, not carried in the interval", True))
    lo, hi = total(dh_variant="energistatistik_200pct_0_78"), total(dh_variant="energy_allocation_1_43")
    axes.append(("CHP allocation convention for district heat (0.78 to 1.43)", lo, hi,
                 "Conventional. No physical answer. Excludes the 0.19 exergy-allocation end, which would "
                 "widen it further", True))
    steps = cfg.get("steps", set())
    D = json.load(open(PARAM_JSON, encoding="utf-8"))["dwelling"]
    net = D["floor_area_net_m2_per_cap_R32"]
    if "dwelling" in steps:
        g = D["net_to_gross"]
        lo, hi = total(floor_area=net * g["low"]), total(floor_area=net * g["high"])
        axes.append(("Net-to-gross area ratio (1.10 to 1.25; R-32 area costed gross)", lo, hi,
                     "Measurement convention, ASSUMED range; R-32 fixes the net schedule but not the ratio (E-RS-2)", True))
    else:
        lo, hi = total(floor_area=15.0), total(floor_area=22.5)
        axes.append(("Floor area (15 to 22.5 m2/person)", lo, hi, "Normative (pre-R-32 axis)", True))
    if "calibration" in steps:
        c = D["calibration_R48"]
        lo, hi = total(calibration=c["low"]), total(calibration=c["high"])
        axes.append(("Space-heat calibration factor (R-48: 1.0 to 2.5)", lo, hi,
                     "Evidence: measured-to-calculated space heat in new Danish homes; DJ RULED 1.5 with the range "
                     "published beside it. Carried in the Monte Carlo", True))
    if "vulnerable" in steps:
        v = D["vulnerable_share_R50"]
        lo, hi = total(vuln_share=v["low"]), total(vuln_share=v["high"])
        axes.append(("Share of people in a qualifying dwelling, +2 K line (30% to 50%)", lo, hi,
                     "ILLUSTRATIVE share (R-50); the dwelling-level share could not be sourced (DR-12)", True))
    lo, hi = total(hot_water_L=20.0), total(hot_water_L=41.0)
    axes.append(("Hot water quantity (20 L, R-51, to 41 L Danish practice)", lo, hi,
                 "Normative - DJ has RULED (R-51) at 20 L; 41 L published beside it as a sensitivity", True))
    if "food" in steps:
        lo, hi = total(food_rule="guidelines"), total(food_rule="modelled")
        axes.append(("Food amounts (dietary guidelines, R-64, to the customary modelled basket)", min(lo, hi), max(lo, hi),
                     "Normative - DJ has RULED (R-64); the customary pattern remains available above the floor", True))
    lo, hi = total(tomato="production_weighted_6_5"), total(tomato="locked_glasshouse_18")
    axes.append(("Tomato boundary (production-weighted 6.5 to locked 18)", lo, hi,
                 "Normative/boundary - DJ has RULED (R-5) at 11.33", True))
    lo, hi = total(cooking="dls_reference"), total(cooking="project_taxonomy_350")
    axes.append(("Cooking central value (DLS reference 85 to project taxonomy 350)", lo, hi,
                 "Unresolved evidence. The project taxonomy figure of 350 is 3.5-4.7x the decent-living "
                 "reference and has no external source", True))
    ranked = []
    for name, lo, hi, nature, in_ranking in axes:
        span = abs(hi - lo)
        ranked.append({"axis": name, "low": lo, "high": hi, "span_kWh": span,
                       "span_pct_of_central": 100.0 * span / central, "nature": nature,
                       "in_ranking": in_ranking})
    ranked.sort(key=lambda d: (not d["in_ranking"], -d["span_kWh"]))
    k = 0
    for d in ranked:
        if d["in_ranking"]:
            k += 1
            d["rank"] = str(k)
        else:
            d["rank"] = "MEMO"
    return ranked, central


# ===========================================================================
# 7.  Reporting
# ===========================================================================

INTERVAL_NOTES = {
    "EXCL_HEALTHCARE": ("THE FLOOR WITHOUT HEALTHCARE (R-8's second interval). Its upper end rests on "
                        "the ASSUMED B3 literature bracket running to 1.5, which the Danish measurement "
                        "contradicts. Compare DEPTH_MEASURED_ONLY"),
    "WITH_HEALTHCARE_B3": ("THE R-8 HEADLINE INTERVAL: adds the B3 healthcare service footprint to the B2 "
                           "floor. The depth caveat travels with it"),
    "DEPTH_MEASURED_ONLY": ("The excluded-healthcare interval with the depth axis restricted to the "
                            "range measured on Danish IO data instead of running out to the assumed 1.5"),
    "CORRELATED_BY_STATUS": ("One shared draw per source-status class instead of independent per-line "
                             "draws. Independence is a LOWER bound on the width and this is an upper bound"),
}
COLS3 = ("CED_Fossil_2.5_kWh_cap_yr", "CED_DK_2023_1.6_kWh_cap_yr", "CED_Renewable_1.0_kWh_cap_yr")


def build_results(params, basket, cfg, *, draws=None, with_mc=True):
    findings = load_findings()
    base = default_scenario(params, cfg)
    run = run_once(params, basket, cfg, base)
    lines = run["lines"]
    labels = list(params["pef_scenarios"])
    meta = {r["line_id"]: r for r in basket}
    rows = []
    con_tag = (cfg["shares"] + cfg["depth"] + cfg["healthcare"])

    def add(rtype, ident, name, f, d, r, **kw):
        rec = {"row_type": rtype, "id": ident, "name": name,
               COLS3[0]: f, COLS3[1]: d, COLS3[2]: r}
        rec.update(kw)
        rows.append(rec)

    for l in lines:
        m = meta[l["line_id"]]
        add("LINE", l["line_id"], m["service"],
            l["primary_Fossil_2.5"], l["primary_DK_2023_1.6"], l["primary_Renewable_1.0"],
            sector=l["sector"], quantity=run["context"]["quantities"][l["line_id"]], unit=m["unit"],
            intensity=run["context"]["intensities"][l["line_id"]], intensity_unit=m["intensity_unit"],
            energy_basis=m["effective_basis"] if m["effective_basis"] == m["energy_basis"]
            else f"{m['effective_basis']} (Wave 2 share device)",
            carrier=m["carrier"], share_electric=m["share_electric"],
            allocation_tier=m["allocation_tier"], boundary_depth=m["boundary_depth"],
            loss_regime=m["loss_regime"], delivered_DK_kWh=l["delivered_DK"],
            delivered_exergy_DK_kWh=l["exergy_DK"], in_floor_total=int(l["in_floor"]),
            status=m["status"], confidence=m["confidence"], source=m["source"], notes=m["notes"])

    for sec in SECTOR_ORDER:
        st = {lab: run["sector_totals"][lab].get(sec, 0.0) for lab in labels}
        if all(abs(v) < 1e-12 for v in st.values()):
            continue
        add("SECTOR_TOTAL", sec, f"{sec} total (in floor)", st["Fossil_2.5"], st["DK_2023_1.6"],
            st["Renewable_1.0"], sector=sec, in_floor_total=1, status="COMPUTED",
            source="sum of LINE rows above with in_floor_total=1")

    t = run["totals"]
    add("FLOOR_TOTAL", "FLOOR_kWh", "Survival floor, primary CED, kWh/cap/yr",
        t["Fossil_2.5"], t["DK_2023_1.6"], t["Renewable_1.0"], status="COMPUTED",
        source="sum of SECTOR_TOTAL rows", notes="Healthcare EXCLUDED in the central case; see the SCENARIO rows")
    add("FLOOR_TOTAL", "FLOOR_GJ", "Survival floor, primary CED, GJ/cap/yr",
        t["Fossil_2.5"] * 3.6 / 1000, t["DK_2023_1.6"] * 3.6 / 1000, t["Renewable_1.0"] * 3.6 / 1000,
        status="COMPUTED", source="kWh x 3.6 / 1000")
    span = 100 * (t["Fossil_2.5"] - t["Renewable_1.0"]) / t["DK_2023_1.6"]
    add("FLOOR_TOTAL", "TRIPLE_SPAN_PCT", "Grid triple span, percent of the DK-2023 floor",
        span, span, span, status="COMPUTED", source="(Fossil - Renewable) / DK-2023")
    t4ids = {r["line_id"] for r in basket if r["allocation_tier"] == "T4_population"
             and r["sector"] != "S8_Healthcare"}
    t4 = [l for l in lines if (not l["in_floor"]) and l["line_id"] in t4ids]
    add("FLOOR_TOTAL", "ALONGSIDE_T4_kWh",
        "Population-level (T4) lines, reported alongside the floor, kWh/cap/yr",
        sum(l["primary_Fossil_2.5"] for l in t4), sum(l["primary_DK_2023_1.6"] for l in t4),
        sum(l["primary_Renewable_1.0"] for l in t4), status="COMPUTED",
        source="sum of LINE rows with allocation_tier=T4_population",
        notes="CED Framework Spec v3 sec 2.2: collective infrastructure is reported beside the floor, not inside it")
    xr = [l for l in lines if l["line_id"] == "X_02"]
    add("FLOOR_TOTAL", "FLOOR_PLUS_UBE_R_kWh",
        "Floor plus the UBE-R transitional heating supplement, kWh/cap/yr",
        t["Fossil_2.5"] + sum(l["primary_Fossil_2.5"] for l in xr),
        t["DK_2023_1.6"] + sum(l["primary_DK_2023_1.6"] for l in xr),
        t["Renewable_1.0"] + sum(l["primary_Renewable_1.0"] for l in xr),
        status="COMPUTED", source="FLOOR_kWh + line X_02",
        notes="DJ rulings R-2 and R-3: the built-to-code floor for everyone, plus a time-limited supplement")
    add("FLOOR_TOTAL", "DELIVERED_EXERGY_DK", "Delivered exergy of the metered household services, kWh/cap/yr",
        NAN, run["delivered_exergy_DK"], NAN, status="COMPUTED",
        source="sum of delivered x Carnot factor at T0 = 281.65 K",
        notes="Reported because the share-of-floor claim is unit-dependent")

    scenarios = [
        ("HEALTHCARE_excluded", "Healthcare excluded (central case)", {"healthcare": "excluded"}),
        ("HEALTHCARE_estate_only", "Healthcare, hospital estate only (B2)", {"healthcare": "estate_only"}),
        ("HEALTHCARE_eeio_B3", f"Healthcare, service footprint from Danish EE-IO (B3), construction {cfg['healthcare']}",
         {"healthcare": "eeio_service_footprint"}),
        ("DEPTH_B1", "Boundary depth B1, narrow", {"boundary_depth": "B1"}),
        ("DEPTH_B2", "Boundary depth B2, base (adopted)", {"boundary_depth": "B2"}),
        ("DEPTH_B3_measured", "Boundary depth B3, truncation measured on Danish IO", {"boundary_depth": "B3_measured"}),
        ("DEPTH_B3_lit_low", "Boundary depth B3, literature low (+25%)", {"boundary_depth": "B3_literature_low"}),
        ("DEPTH_B3_lit_high", "Boundary depth B3, literature high (+50%)", {"boundary_depth": "B3_literature_high"}),
        ("FLEET_0", "Fleet electrification 0 (2023 Danish fleet)", {"fleet_electrification": 0.0}),
        ("FLEET_50", "Fleet electrification 50%", {"fleet_electrification": 0.5}),
        ("FLEET_100", "Fleet electrification 100%", {"fleet_electrification": 1.0}),
        ("MODAL_public", "Mobility: public transport (DJ ruling R-6)", {"modal_split": "dls_public_transport"}),
        ("MODAL_danish_actual", "Mobility: Danish actual modal split", {"modal_split": "danish_actual"}),
        ("TOMATO_delivered_11", "Tomato at 11.33 kWh/kg delivered (DJ ruling R-5)", {"tomato": "delivered_to_recipient_11"}),
        ("TOMATO_production_6_5", "Tomato at 6.5 kWh/kg production-weighted", {"tomato": "production_weighted_6_5"}),
        ("TOMATO_locked_18", "Tomato at the locked 18 kWh/kg glasshouse figure", {"tomato": "locked_glasshouse_18"}),
        ("COOKING_dls_85", "Cooking at the decent-living reference, 85 kWh (adopted)", {"cooking": "dls_reference"}),
        ("COOKING_taxonomy_350", "Cooking at the project taxonomy 350 kWh (withdrawn)", {"cooking": "project_taxonomy_350"}),
        ("FOODLOSS_household", "Food loss: household share only (x1.10, Phase 1 and v3)", {"food_loss": "household_only"}),
        ("FOODLOSS_cascade", "Food loss: full cascade central (adopted)", {"food_loss": "cascade_central"}),
        ("FOODLOSS_high", "Food loss: full cascade high", {"food_loss": "cascade_high"}),
        ("AREA_R32_gross_1_10", "R-32 area, net-to-gross 1.10", {"floor_area": 19.54 * 1.10}),
        ("AREA_R32_gross_1_175", "R-32 area, net-to-gross 1.175 (central)", {"floor_area": 19.54 * 1.175}),
        ("AREA_R32_gross_1_25", "R-32 area, net-to-gross 1.25", {"floor_area": 19.54 * 1.25}),
        ("AREA_RaoMin_ruled_out", "Rao & Min area 15.39 m2 net x 1.175 (ruled out by R-32; memo)", {"floor_area": 15.39 * 1.175}),
        ("AREA_Wave2_19_4", "Wave 2 area 19.4 m2 treated as gross (superseded)", {"floor_area": 19.4}),
        ("CHP_0_78", "District heat factor 0.78 (Energistatistik 200% method)", {"dh_variant": "energistatistik_200pct_0_78"}),
        ("CHP_0_85", "District heat factor 0.85 (BR18 regulatory)", {"dh_variant": "br18_regulatory_0_85"}),
        ("CHP_1_08", "District heat factor 1.08 (Energistyrelsen, adopted)", {"dh_variant": "energistyrelsen_1_08"}),
        ("CHP_1_43", "District heat factor 1.43 (energy allocation)", {"dh_variant": "energy_allocation_1_43"}),
        ("CAL_1_0", "Space-heat calibration 1.0 (R-48 range, low)", {"calibration": 1.0}),
        ("CAL_2_5", "Space-heat calibration 2.5 (R-48 range, high)", {"calibration": 2.5}),
        ("VULN_SHARE_30", "Vulnerable-dwelling share 30%", {"vuln_share": 0.30}),
        ("VULN_SHARE_50", "Vulnerable-dwelling share 50%", {"vuln_share": 0.50}),
        ("HOTWATER_41L", "Hot water 41 L/person/day (Danish practice; R-51 sensitivity)", {"hot_water_L": 41.0}),
        ("FOOD_MODELLED", "Food at the customary modelled amounts (pre-R-64)", {"food_rule": "modelled"}),
        ("FOOD_ALL_SCALED", "Food at the guidelines, every age scaled to NNR energy (R-64 sensitivity)", {"food_rule": "scaled"}),
        ("FOOD_LOSS_HOUSEHOLD_ONLY", "Food loss cascade removed (household share only)", {"food_loss": "household_only"}),
        ("ENVELOPE_LITERAL_BR18", "Space heat at BR18 sec 257 element values, not the frame-compliant envelope (E-RS-1)", {"envelope": "literal_br18"}),
        ("MOBILITY_8540_PKM", "OPTIONAL SENSITIVITY: 8,540 passenger-km (Kikstra et al.) instead of 5,000; does not change the floor",
         {"pkm_scale": 8540.0 / 5000.0}),
        ("HEALTHCARE_eeio_B3_CHP_0_78", "Healthcare included, district heat factor 0.78",
         {"healthcare": "eeio_service_footprint", "dh_variant": "energistatistik_200pct_0_78"}),
        ("HEALTHCARE_eeio_B3_CHP_1_43", "Healthcare included, district heat factor 1.43",
         {"healthcare": "eeio_service_footprint", "dh_variant": "energy_allocation_1_43"}),
    ]
    for ident, name, over in scenarios:
        s = dict(base)
        s.update(over)
        tt = run_once(params, basket, cfg, s)["totals"]
        add("SCENARIO", ident, name, tt["Fossil_2.5"], tt["DK_2023_1.6"], tt["Renewable_1.0"],
            status="COMPUTED", source="full model re-run with one axis changed")

    bench = params["decent_living_benchmark"]
    metered = [l for l in lines if l["in_floor"] and not isnan(l["delivered_DK"])]
    unmetered = [l for l in lines if l["in_floor"] and isnan(l["delivered_DK"])]
    delivered_metered = sum(l["delivered_DK"] for l in metered)
    add("BENCHMARK", "DELIVERED_METERED_kWh",
        f"Delivered (final) energy of the {len(metered)} metered floor lines, kWh/cap/yr",
        delivered_metered, delivered_metered, delivered_metered, status="COMPUTED",
        source="sum of delivered_DK_kWh over in-floor lines", notes="Delivered energy does not move with the grid scenario")
    pm = {k: sum(l[f"primary_{k}"] for l in metered) for k in labels}
    pu = {k: sum(l[f"primary_{k}"] for l in unmetered) for k in labels}
    add("BENCHMARK", "PRIMARY_METERED_kWh", "Primary CED of the same metered lines, kWh/cap/yr",
        pm["Fossil_2.5"], pm["DK_2023_1.6"], pm["Renewable_1.0"], status="COMPUTED",
        source="sum of primary over the same lines")
    add("BENCHMARK", "RATIO_MEASURED", "MEASURED primary-to-final ratio on the metered part of the floor",
        pm["Fossil_2.5"] / delivered_metered, pm["DK_2023_1.6"] / delivered_metered,
        pm["Renewable_1.0"] / delivered_metered, status="COMPUTED",
        source="primary / delivered on the metered lines",
        notes="The whole-basket ratio is NOT measurable from this model: the embodied and food lines carry no delivered value")
    add("BENCHMARK", "PRIMARY_UNMETERED_kWh", f"Primary CED of the {len(unmetered)} floor lines with no delivered value",
        pu["Fossil_2.5"], pu["DK_2023_1.6"], pu["Renewable_1.0"], status="COMPUTED",
        source="sum of primary over embodied and food lines",
        notes=f"{100 * pu['DK_2023_1.6'] / t['DK_2023_1.6']:.0f}% of the DK-2023 floor")
    # v5 (E-OD-1): final energy on the project's own conversion, 1.2 on food lines as the lower
    # ratio, and the decent-living comparison made like for like against Denmark's 15.6 GJ.
    fin_lo = {k: delivered_metered for k in labels}   # high ratio -> low final
    fin_hi = {k: delivered_metered for k in labels}
    for l in unmetered:
        r_low = bench["primary_to_final_food_low"] if l["sector"] == "S1_Food" else bench["primary_to_final_other_low"]
        for k in labels:
            fin_hi[k] += l[f"primary_{k}"] / r_low
            fin_lo[k] += l[f"primary_{k}"] / bench["primary_to_final_high"]
    for tag, fin, note in (("FLOOR_FINAL_GJ_ratio_high", fin_lo, "unmetered lines at 1.5"),
                           ("FLOOR_FINAL_GJ_ratio_low", fin_hi, "food lines at 1.2, other unmetered lines at 1.3")):
        add("BENCHMARK", tag, f"Floor (no healthcare) in FINAL energy, GJ/cap/yr: {note}",
            fin["Fossil_2.5"] * 0.0036, fin["DK_2023_1.6"] * 0.0036, fin["Renewable_1.0"] * 0.0036,
            status="COMPUTED", source="delivered energy where the model measures it; the stated ratio only where it does not",
            notes="Final energy does not depend on the grid: the three columns differ only through the unmetered lines' primary")
    comp = findings["healthcare"]["C"]["components_kWh"]["central"]
    hc_final = comp["F"] + comp["E"] + comp["H"]
    lmap = {l["line_id"]: l for l in lines}
    tr03 = lmap["TR_03"]["primary_DK_2023_1.6"]
    x01 = lmap["X_01"]["primary_DK_2023_1.6"]
    scope_lo = (fin_lo["DK_2023_1.6"] + hc_final + tr03 + x01 / bench["primary_to_final_high"]) * 0.0036
    scope_hi = (fin_hi["DK_2023_1.6"] + hc_final + tr03 + x01 / bench["primary_to_final_other_low"]) * 0.0036
    dk = bench["denmark_GJ_per_cap_final"]
    add("BENCHMARK", "FLOOR_AT_DLS_SCOPE_FINAL_GJ", "Floor + healthcare (HC_02) + transport infrastructure (TR_03) + school estate (X_01), FINAL GJ/cap/yr",
        scope_lo, (scope_lo + scope_hi) / 2, scope_hi, status="COMPUTED",
        source="columns: low / mid / high conversion (not a grid triple). HC_02 final = fuels + delivered electricity + delivered heat; TR_03 source basis final (CONTESTED)",
        notes=f"The decent-living model's own scope. Against Denmark's {dk} GJ: {scope_lo / dk:.2f}-{scope_hi / dk:.2f} times")
    ex = dk - sum(bench["denmark_components_GJ"][k] for k in ("healthcare", "education", "transport_infrastructure"))
    add("BENCHMARK", "DLS_DENMARK_GJ", "Decent-living energy, Denmark (Millward-Hopkins et al. 2020), GJ/cap/yr FINAL", dk, dk, dk,
        status="REFERENCE", source=bench["denmark_source"], notes=bench["denmark_basis"])
    add("BENCHMARK", "DLS_DENMARK_EX_HEALTH_EDU_INFRA_GJ", "The same, minus healthcare, education and transport infrastructure, GJ/cap/yr FINAL",
        ex, ex, ex, status="REFERENCE", source=bench["denmark_source"],
        notes=(f"Compare with FLOOR_FINAL rows: {fin_lo['DK_2023_1.6'] * 0.0036 / ex:.2f}-{fin_hi['DK_2023_1.6'] * 0.0036 / ex:.2f} times. "
               "It still contains 3.3 GJ of 'other' that the floor does not"))
    for ident, val, nm in (
            ("DLS_MEAN_GJ", bench["global_mean_GJ_per_cap_final"], "Decent-living benchmark, global mean, GJ/cap/yr FINAL"),
            ("DLS_MAX_GJ", bench["max_across_countries_GJ_per_cap_final"],
             "Decent-living benchmark, maximum across countries (mobility-driven, not a cold-climate range), GJ/cap/yr FINAL")):
        add("BENCHMARK", ident, nm, val, val, val, status="REFERENCE", source=bench["source"], notes=bench["basis"])

    # ---- household footprint, step 5: recomposed, band retired -------------
    hf = findings["household_footprint"]
    con = cfg["shares"]
    if con == "C":
        c3 = {lab: hf["C"][lab] for lab in labels}

        def trip(key):
            return c3["Fossil_2.5"][key], c3["DK_2023_1.6"][key], c3["Renewable_1.0"][key]
        basis_note = ("construction C: purchased goods at fuels + electricity x PEF + district heat x 1.08; "
                      "household direct = oil, gas, wood and gasworks gas as burned (ambient heat excluded) + "
                      "delivered electricity x PEF + delivered district heat x 1.08")
    else:
        v = hf[con]

        def trip(key):
            return NAN, v[key], NAN
        basis_note = f"construction {con} (one number; conversion factor embedded)"
    add("SANITY", "HH_PURCHASED_GJ", "Danish household footprint: purchased goods and services, GJ/cap/yr",
        *trip("purchased_GJ_per_cap"), status="COMPUTED",
        source="Danish EE-IO, complete boundary, domestic technology closure", notes=basis_note)
    add("SANITY", "HH_DIRECT_GJ", "Danish household footprint: energy households use directly, GJ/cap/yr",
        *trip("household_direct_GJ_per_cap"), status="COMPUTED",
        source="Danmarks Statistik ENE2HA household aggregate",
        notes=("Not in any industry's row once the double count is removed. Wave 2's note that household petrol "
               "and gas appear in exactly one term was WRONG: under the double count they appeared in both "
               "(refinery crude and pass-through gas inside the purchased term, and again here)"))
    add("SANITY", "HH_TOTAL_GJ", "Danish household energy footprint, composed, GJ/cap/yr",
        *trip("total_GJ_per_cap"), status="COMPUTED", source="the two rows above, summed",
        notes=("DESCRIPTIVE ONLY. The 100-120 GJ/cap band check is RETIRED (step 5): the band had no source, "
               "and no published figure measures this quantity. Wave 2's 123.0 is REJECTED (double counted)"))
    add("SANITY", "HH_TOTAL_DOMESTIC_CLOSURE_GJ", "Same footprint, domestic-only closure, GJ/cap/yr",
        *trip("total_domestic_closure_GJ_per_cap"), status="COMPUTED",
        source="as above, imports not traced", notes="For comparison with DST's own household figure below")
    dst = hf["DST_ENE2MU2N_households"]
    add("SANITY", "HH_DST_ENE2MU2N_GJ", "Danmarks Statistik's own household figure (ENE2MU2N), GJ/cap/yr",
        NAN, dst["direct_and_indirect_GJ_per_cap"], NAN, status="REFERENCE",
        source="Danmarks Statistik ENE2MU2N, household consumption, direct and indirect, domestic closure, 2023",
        notes=("A comparator, not a check: its 'direct' term (346.6 PJ) is not ENE3H's household total (270.0 PJ) "
               "and the difference is not reconciled. Same order of magnitude as the domestic-closure row above"))

    # ---- electric shares -----------------------------------------------------
    io_ids = [r["line_id"] for r in basket if r["share_electric_status"] == "DERIVED_IO"]
    zero_basket = [dict(r) for r in basket]
    for r in zero_basket:
        if r["carrier"] == "embodied":
            r["share_electric"] = 0.0
    tz = run_once(params, zero_basket, cfg, base)["totals"]
    add("DIAGNOSTIC", "TRIPLE_SPAN_PCT_AT_ZERO_EMBODIED_SHARE",
        "Grid triple span if the embodied lines were still declared 0% electric", NAN,
        100 * (tz["Fossil_2.5"] - tz["Renewable_1.0"]) / tz["DK_2023_1.6"], NAN, status="COMPUTED",
        source="the whole model re-run with embodied shares zeroed",
        notes="The reported span is the TRIPLE_SPAN_PCT row")
    shares = {l: meta[l]["share_electric"] for l in io_ids}
    add("DIAGNOSTIC", "IO_EMBODIED_ELECTRIC_SHARE",
        "Measured cumulative electric share of primary CED, IO-derived lines, mean", NAN,
        sum(shares.values()) / len(shares), NAN, status="COMPUTED",
        source=f"Danish EE-IO carrier composition, construction {cfg['shares']} (HC_02: construction {cfg['healthcare']})",
        notes=("range " + f"{min(shares.values()):.3f}-{max(shares.values()):.3f} across "
               + ", ".join(f"{k} {v:.3f}" for k, v in sorted(shares.items()))))
    comp = cfg["composition"]
    add("DIAGNOSTIC", "IO_FOOD_ELECTRIC_SHARE_CHECK",
        "Measured electric share for Danish agriculture, against the 0.22 the food lines carry", NAN,
        comp["01000"]["electric_share_of_primary_at_pef_ref"], NAN, status="COMPUTED",
        source=f"Danish EE-IO, industry 01000, construction {cfg['shares']}",
        notes=(f"food manufacturing (10120) measures {comp['10120']['electric_share_of_primary_at_pef_ref']:.3f}. "
               "The corroboration Wave 2 claimed for the food lines' 0.22 ('to within 0.03') is WITHDRAWN: it rested "
               "on the double count. The 0.22 is an LCA-side figure, not an IO figure, and is NOT changed in this "
               "run; see the narrative for its effect on the triple"))
    contested = [l for l in lines if l["in_floor"] and meta[l["line_id"]]["basis_reconciliation"] == "CONTESTED_UNCONVERTED"]
    add("DIAGNOSTIC", "CONTESTED_BASIS_kWh", "Floor energy whose declared basis its own source contradicts, kWh/cap/yr",
        NAN, sum(l["primary_DK_2023_1.6"] for l in contested), NAN, status="COMPUTED",
        source="in-floor lines with basis_reconciliation=CONTESTED_UNCONVERTED",
        notes="Lines: " + ", ".join(sorted(l["line_id"] for l in contested)))

    ranked, central = sensitivity_ranking(params, basket, cfg)
    for d in ranked:
        add("SENSITIVITY", f"RANK_{d['rank']}", d["axis"], NAN, d["span_kWh"], NAN,
            notes=f"{d['span_pct_of_central']:.1f}% of the DK-2023 floor. {d['nature']}",
            status="COMPUTED", source="one axis moved end to end, everything else at the central case")

    mcs = {}
    if with_mc:
        bdf = params["boundary_depth"]["factors_relative_to_B2"]
        mcs["EXCL_HEALTHCARE"] = monte_carlo(params, basket, cfg, base, draws=draws)
        mcs["WITH_HEALTHCARE_B3"] = monte_carlo(params, basket, cfg, {**base, "healthcare": "eeio_service_footprint"},
                                                draws=draws, variance_for=())
        mcs["DEPTH_MEASURED_ONLY"] = monte_carlo(params, basket, cfg, base, draws=draws,
                                                 depth_range=[bdf["B1"], bdf["B3_measured"]], variance_for=())
        mcs["CORRELATED_BY_STATUS"] = monte_carlo(params, basket, cfg, base, draws=draws, correlated=True,
                                                  variance_for=())
        mcs["WITH_HEALTHCARE_DEPTH_MEASURED_ONLY"] = monte_carlo(
            params, basket, cfg, {**base, "healthcare": "eeio_service_footprint"}, draws=draws,
            depth_range=[bdf["B1"], bdf["B3_measured"]], variance_for=())
        if "calibration" in cfg.get("steps", set()):
            for cf, ct in ((1.0, "CAL_1_0"), (2.5, "CAL_2_5")):
                mcs[f"EXCL_HEALTHCARE_{ct}"] = monte_carlo(params, basket, cfg, base, draws=draws, variance_for=(),
                                                           cal_fixed=cf)
                mcs[f"WITH_HEALTHCARE_{ct}"] = monte_carlo(params, basket, cfg, {**base, "healthcare": "eeio_service_footprint"},
                                                           draws=draws, variance_for=(), cal_fixed=cf)
        for tag, mc in mcs.items():
            src = (f"Monte Carlo, {draws or params['monte_carlo']['draws']} draws, seed "
                   f"{params['monte_carlo']['seed']}, standard-library engine; PERT on every line band widened by "
                   f"source status")
            add("INTERVAL", f"P05_{tag}", f"5th percentile ({tag})", mc["Fossil_2.5"]["p05"],
                mc["DK_2023_1.6"]["p05"], mc["Renewable_1.0"]["p05"], status="COMPUTED", source=src)
            add("INTERVAL", f"MEDIAN_{tag}", f"Median ({tag})", mc["Fossil_2.5"]["median"],
                mc["DK_2023_1.6"]["median"], mc["Renewable_1.0"]["median"], status="COMPUTED", source="Monte Carlo")
            add("INTERVAL", f"P95_{tag}", f"95th percentile ({tag})", mc["Fossil_2.5"]["p95"],
                mc["DK_2023_1.6"]["p95"], mc["Renewable_1.0"]["p95"], status="COMPUTED", source="Monte Carlo",
                notes=INTERVAL_NOTES.get(tag, "The calibration factor held fixed at the stated end of the R-48 range"
                                         if "_CAL_" in tag else "The healthcare-inclusive interval on the measured depth range only"))
        top = list(mcs["EXCL_HEALTHCARE"]["DK_2023_1.6"]["variance_share"].items())[:8]
        for k, (lid, share) in enumerate(top, 1):
            add("VARIANCE", f"VAR_{k}", f"{lid} — {meta[lid]['service']}", NAN, 100.0 * share, NAN,
                status="COMPUTED", source="share of the variance of the DK-2023 floor, excluding healthcare",
                notes=f"status {meta[lid]['status']}")

    ot = orientation_worked_example()
    add("DIAGNOSTIC", "ORIENTATION_TEST", "A-matrix orientation worked example passes", NAN,
        float(ot["passes"]), NAN, status="COMPUTED", source="orientation_worked_example()",
        notes=(f"A[i,j] = input from i per unit of output of j. True answer 0.5; stated convention "
               f"{ot['energy_with_stated_convention']}; transpose {ot['energy_with_transpose']}"))
    add("DIAGNOSTIC", "PHASE1_HAND_MULTIPLIER", "Phase 1 published Leontief total / published direct total",
        1.12, 1.12, 1.12, status="COMPUTED", source="Physics Audit Wave 1 sec 2.2, reproduced as a fixed reference",
        notes="A constant across three demand vectors is the signature of a hand-applied uplift")
    add("DIAGNOSTIC", "FOOD_RETAIL_MASS", "Food mass passing retail, computed from the food lines, kg/cap/yr",
        NAN, run["context"]["food_retail_throughput_kg"], NAN, status="COMPUTED",
        source="sum of food line quantities x the retail loss factor")
    sec = findings["sectors"]
    sc = sec["by_construction"][cfg["shares"]]
    add("DIAGNOSTIC", "IO_A_MEAN_COLSUM_REAL", "Mean column sum of the REAL Danish 9-sector A matrix", NAN,
        sum(sec["A9_col_sums"]) / len(sec["A9_col_sums"]), NAN, status="COMPUTED",
        source="Danmarks Statistik NAIO1F 2023, 69 industries aggregated to 9 (money only; unchanged by the correction)")
    add("DIAGNOSTIC", "IO_A_MEAN_COLSUM_PHASE1", "Mean column sum of the Phase 1 INVENTED A matrix", NAN,
        sum(sec["A_phase1_col_sums"]) / len(sec["A_phase1_col_sums"]), NAN, status="COMPUTED",
        source="outputs/leontief_ced.py, reproduced verbatim")
    add("DIAGNOSTIC", "IO_ORIENTATION_ERROR_PCT_REAL", "Effect of the orientation error on the REAL matrix, percent",
        NAN, sc["orientation_error_pct"], NAN, status="COMPUTED",
        source=f"real Danish 9-sector matrix, transposed vs correct, energy weights of construction {cfg['shares']}",
        notes="Wave 2 gave 34.7% on the double-counted energy weights")
    up = [u for u in sc["upstream_ratio"] if u]
    add("DIAGNOSTIC", "IO_SECTOR_UPSTREAM_RATIO_RANGE", "Sector cumulative-to-direct ratios, min and max (in the F and R columns)",
        min(up), NAN, max(up), status="COMPUTED",
        source=f"nine UBE sectors, construction {cfg['shares']}",
        notes="R-8's reasoning cites 1.43-36.7 (Wave 2). Every sector stays above Phase 1's 1.12 in every construction")
    trc = findings["truncation"][cfg["depth"]] if cfg["depth"] != "W2" else findings["truncation"]["W2"]
    add("DIAGNOSTIC", "IO_TRUNCATION_TIER1", "Share of complete-boundary energy captured by tiers 0-1", NAN,
        100.0 * trc["share_by_tier"][1], NAN, status="COMPUTED",
        source=f"Danish EE-IO tier expansion, construction {cfg['depth']}", notes="Survival-bundle series (actual Danish spending, v4 basis). From step 2 the floor uses DEPTH_FLOOR_MIX_B1")
    add("DIAGNOSTIC", "IO_TRUNCATION_TIER3", "Share of complete-boundary energy captured by tiers 0-3", NAN,
        100.0 * trc["share_by_tier"][3], NAN, status="COMPUTED",
        source=f"Danish EE-IO tier expansion, construction {cfg['depth']}",
        notes="Survival-bundle series (v4 basis). It does NOT confirm the assumed +25% to +50% bracket. From step 2 the floor uses DEPTH_FLOOR_MIX_B3")
    hcl = [l for l in lines if l["line_id"] == "HC_02"][0]
    if cfg["healthcare"] == "W2":
        # Wave 2 wrote the unrounded IO figure here (999.2529), not the ruled 999
        # carried by its HC_02 line, and had no triple in this row.
        w2hc = findings["healthcare"]["W2"]["central_health_domestic_technology"]
        hc_diag = (NAN, w2hc, NAN)
    else:
        hc_diag = (hcl["primary_Fossil_2.5"], hcl["primary_DK_2023_1.6"], hcl["primary_Renewable_1.0"])
    add("DIAGNOSTIC", "IO_HEALTHCARE_EEIO", "Healthcare service footprint from Danish EE-IO, kWh/cap/yr (central)",
        *hc_diag, status="COMPUTED",
        source=f"NAIO1F + ENE2HA 2023, industry 86000, construction {cfg['healthcare']}",
        notes=("low = domestic-only closure, high = health plus residential care; see "
               "healthcare_constructions_v5.csv. Wave 2's 999 is REJECTED as evidence (R-38); replaced by R-52"))

    # ---- v5 diagnostics ------------------------------------------------------
    st = run["sector_totals"]
    heat = {lab: st[lab].get("S3_Heating", 0.0) for lab in labels}
    add("DIAGNOSTIC", "HEATING_SHARE_PCT", "Heating (S3: space heat, hot water, vulnerable line) as % of the floor",
        100 * heat["Fossil_2.5"] / t["Fossil_2.5"], 100 * heat["DK_2023_1.6"] / t["DK_2023_1.6"],
        100 * heat["Renewable_1.0"] / t["Renewable_1.0"], status="COMPUTED", source="SECTOR_TOTAL S3_Heating / FLOOR_kWh",
        notes="Healthcare excluded. Ventilation fans (V_01) sit in S5_Shelter")
    h01 = lmap["H_01"]
    add("DIAGNOSTIC", "SPACE_HEAT_DELIVERED_kWh", "Space heat H_01, DELIVERED heat, kWh/cap/yr", NAN, h01["delivered_DK"], NAN,
        status="COMPUTED", source="H_01 delivered",
        notes=("R-13 band 387-719 kWh/cap/yr delivered. Eurostat nrg_d_hhq 2023: actual Danish space heat 4,656 kWh/cap/yr "
               "(Outside_Desk_Check.md sec 10.1)"))
    if "dwelling" in cfg.get("steps", set()):
        dwf = cfg["dwell"]
        add("DIAGNOSTIC", "DWELLING_REPRODUCTION_TESTS", "Dwelling method tests: TABULA check, BR18 elements vs frame, temperature sensitivity",
            NAN, float(dwf["tests"]["test1_method_within_20pct_of_TABULA"]), NAN, status="COMPUTED",
            source="dwelling_findings_v5.json", notes=json.dumps(dwf["tests"]))
    if cfg.get("floor_mix"):
        fm = cfg["floor_mix"]
        add("DIAGNOSTIC", "DEPTH_FLOOR_MIX_B1", "Depth factor B1 measured on the floor's own mix (R-61)", NAN, fm["B1"], NAN,
            status="COMPUTED", source="io_findings_v5.json parts_C x the floor's B2 weights at DK-2023",
            notes=("weights " + ", ".join(f"{p} {100 * w:.1f}%" for p, w in fm["weights_share"].items())
                   + "; part B1 " + ", ".join(f"{p} {v['B1']:.3f}" for p, v in fm["part_factors"].items())
                   + f"; variant with service lines fully captured B1 {fm['variant_service_lines_fully_captured']['B1']:.3f}"))
        add("DIAGNOSTIC", "DEPTH_FLOOR_MIX_B3", "Depth factor B3 measured on the floor's own mix (R-61)", NAN, fm["B3"], NAN,
            status="COMPUTED", source="as above",
            notes=f"variant with service lines fully captured B3 {fm['variant_service_lines_fully_captured']['B3']:.3f}")
    for r in rows:
        r["v5_figure_status"] = "PROVISIONAL"
        r["construction"] = f"v5 steps 1-{cfg.get('upto', 7)} (" + ", ".join(STEPS[:cfg.get('upto', 7)]) + ")"
    return rows, run, ranked, mcs


CSV_COLS = ["row_type", "id", "name", "sector", *COLS3, "quantity", "unit", "intensity", "intensity_unit",
            "energy_basis", "carrier", "share_electric", "allocation_tier", "boundary_depth", "loss_regime",
            "delivered_DK_kWh", "delivered_exergy_DK_kWh", "in_floor_total", "status", "confidence",
            "source", "notes", "v5_figure_status", "construction"]
NUMERIC4 = set(COLS3) | {"quantity", "intensity", "delivered_DK_kWh", "delivered_exergy_DK_kWh",
                         "share_electric", "in_floor_total"}


def _cell(col, v):
    if v is None or v == "":
        return ""
    if col in NUMERIC4:
        try:
            f = float(v)
        except (TypeError, ValueError):
            return str(v)
        if f != f:
            return ""
        return f"{round(f, 4):.4f}"
    return str(v)


def render_csv(rows) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(CSV_COLS)
    for r in rows:
        w.writerow([_cell(c, r.get(c, "")) for c in CSV_COLS])
    return buf.getvalue()


# ===========================================================================
# 8.  Self-checks
# ===========================================================================

def _mut(rows, lid, **kw):
    out = [dict(r) for r in rows]
    for r in out:
        if r["line_id"] == lid:
            for k, v in kw.items():
                r[k] = str(v)
            break
    return out


def _dup(rows, lid, **kw):
    out = [dict(r) for r in rows]
    src = [dict(r) for r in rows if r["line_id"] == lid][0]
    for k, v in kw.items():
        src[k] = str(v)
    out.append(src)
    return out


def corruption_battery():
    """The 36 corrupted baskets of Wave 2, plus one v4 case (AF)."""
    return [
        ("W1-D2  exact duplicate service row", lambda d: _dup(d, "HY_02", line_id="HY_09"), "T9"),
        ("W1-R2  contains[] naming another line id", lambda d: _mut(d, "H_01", contains="H_02"), "T9"),
        ("W1-DB  bare database name as a source", lambda d: _mut(d, "F_01", source="Ecoinvent"), "T11"),
        ("W1-CAR missing carrier field", lambda d: _mut(d, "F_01", carrier=""), "T1"),
        ("A  duplicate service under a second line id", lambda d: _dup(d, "A_03", line_id="A_09"), "T9"),
        ("B  contains[] naming another basket line", lambda d: _mut(d, "A_05", contains="CM_02"), "T9"),
        ("C  bare database name as a source", lambda d: _mut(d, "T_02", source="ecoinvent 3.x"), "T11"),
        ("D  missing carrier field", lambda d: _mut(d, "C_01", carrier=""), "T1"),
        ("E  band that does not bracket its own central value",
         lambda d: _mut(d, "F_09", intensity_low="10.0", intensity_high="12.0"), "T3"),
        ("F1 factor-of-ten decimal slip on an intensity", lambda d: _mut(d, "H_01", intensity="10.0"), "T6"),
        ("F2 factor-of-ten decimal slip on a quantity", lambda d: _mut(d, "H_01", quantity="5530"), "T6"),
        ("G  silent basis change: delivered electrical relabelled primary",
         lambda d: _mut(d, "A_02", energy_basis="primary_at_ref"), "T7"),
        ("H  semantic duplicate: one physical service under two names",
         lambda d: _dup(d, "H_01", line_id="H_09", service="household_space_heat", quantity="400",
                        substitution_class="heat_second"), "T9"),
        ("I  contains[] naming a line by service name", lambda d: _mut(d, "A_05", contains="customer premises router"), "T9"),
        ("J  negative quantity", lambda d: _mut(d, "F_01", quantity="-90"), "T3"),
        ("K  units that do not multiply out", lambda d: _mut(d, "F_01", intensity_unit="kWh/m3"), "T5"),
        ("L  electric share of 5.0", lambda d: _mut(d, "HY_07", share_electric="5.0"), "T4"),
        ("M  boundary-depth token B7", lambda d: _mut(d, "F_01", boundary_depth="B7"), "T2"),
        ("N  status token TOTALLY_MADE_UP", lambda d: _mut(d, "F_01", status="TOTALLY_MADE_UP"), "T2"),
        ("O  a T4 line moved inside the floor", lambda d: _mut(d, "TR_03", in_floor_total="1"), "T10"),
        ("P  a final-energy source declared as primary, same_basis",
         lambda d: _mut(d, "T_01", basis_reconciliation="same_basis"), "T8"),
        ("Q  a B3 line moved inside the B2 floor", lambda d: _mut(d, "HC_02", in_floor_total="1"), "T10"),
        ("R  IO-derived share with a hand-set status", lambda d: _mut(d, "C_01", share_electric_status="ESTIMATED"), "T2"),
        ("S  DERIVED_IO status on a hand-entered share", lambda d: _mut(d, "F_25", share_electric_status="DERIVED_IO"), "T2"),
        ("T  invalid sector token", lambda d: _mut(d, "F_01", sector="S99_Invented"), "T2"),
        ("U  exergy factor above 1", lambda d: _mut(d, "H_01", exergy_factor="1.4"), "T4"),
        ("V  thermal line with no delivery temperature", lambda d: _mut(d, "H_01", delivery_temperature_C=""), "T1"),
        ("W  a band spanning two orders of magnitude", lambda d: _mut(d, "F_09", intensity_low="0.05"), "T3"),
        ("X  zero intensity", lambda d: _mut(d, "F_02", intensity="0"), "T3"),
        ("Y  a single line larger than any survival service", lambda d: _mut(d, "X_02", intensity="2900"), "T6"),
        ("Z  empty source string", lambda d: _mut(d, "TR_02", source=""), "T1"),
        ("AA quantity outside its envelope", lambda d: _mut(d, "C_01", quantity="194"), "T6"),
        ("AB in_floor_total used as a weight", lambda d: _mut(d, "F_01", in_floor_total="0.5"), "T4"),
        ("AC identical numbers under two names", lambda d: _dup(d, "HY_03", line_id="HY_11", service="hair_wash_product"), "T9"),
        ("AD unknown energy basis token", lambda d: _mut(d, "F_01", energy_basis="primary_at_source"), "T2"),
        ("AE an IO industry code that does not exist", lambda d: _mut(d, "C_01", share_electric="IO:99999"), "resolve"),
        ("AF (v4) healthcare line hand-edited away from the IO model", lambda d: _mut(d, "HC_02", intensity="999"), "resolve"),
        ("AG (v5) space heat hand-edited away from the dwelling model", lambda d: _mut(d, "H_01", quantity="553"), "resolve"),
        ("AH (v5) cheese hand-edited back to the customary 21 kg", lambda d: _mut(d, "F_09", quantity="21.0"), "resolve"),
    ]


def run_corruption_battery(cfg, checks: list) -> None:
    raw, cols = read_basket_raw()
    passed = 0
    for label, mutate, expect in corruption_battery():
        fh = tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, newline="", encoding="utf-8")
        w = csv.DictWriter(fh, fieldnames=cols, lineterminator="\n")
        w.writeheader()
        w.writerows(mutate(raw))
        fh.close()
        try:
            load_basket(cfg, fh.name)
            raise AssertionError(f"loader FAILED to reject: {label}")
        except BasketError as exc:
            msg = str(exc)
            if expect != "resolve" and f"({expect})" not in msg:
                raise AssertionError(f"{label}: rejected, but not by the check it is aimed at ({expect}). "
                                     f"Message was:\n{msg[:600]}")
            passed += 1
        finally:
            os.unlink(fh.name)
    checks.append(f"Loader rejects all {passed} corrupted baskets in the failure-taxonomy battery "
                  f"(Wave 2's 36, v4's hand-edited healthcare line, and v5's hand-edited space heat and cheese): PASS")


def self_test(params, basket, rows, cfg) -> list:
    checks = []
    ot = orientation_worked_example()
    assert ot["passes"], "orientation worked example failed"
    checks.append("A-matrix orientation worked example: PASS")
    lines = [r for r in rows if r["row_type"] == "LINE" and r["in_floor_total"] == 1]
    for col in COLS3:
        by_sec = {}
        for r in lines:
            by_sec[r["sector"]] = by_sec.get(r["sector"], 0.0) + r[col]
        for sec, v in by_sec.items():
            row = [r for r in rows if r["row_type"] == "SECTOR_TOTAL" and r["id"] == sec][0]
            assert abs(row[col] - v) < 0.01, f"sector total {sec} does not reconcile in {col}"
        tot = [r for r in rows if r["row_type"] == "FLOOR_TOTAL" and r["id"] == "FLOOR_kWh"][0][col]
        assert abs(tot - sum(by_sec.values())) < 0.01, f"floor total does not reconcile in {col}"
    checks.append("Every sector total and the floor total reconcile with their own line rows to within 0.01 kWh: PASS")
    checks.append("No post-hoc multiplier is applied at any point: the floor total IS the sum of the line rows")
    services = [r["service"] for r in basket]
    assert len(set(services)) == len(services), "duplicate service (rule R1)"
    checks.append(f"Basket is a partition: {len(basket)} lines, {len(set(services))} distinct services: PASS")
    raw, _ = read_basket_raw()
    assert [r for r in raw if r["line_id"] == "F_25"][0]["quantity"] == "DERIVED_FOOD_MASS"
    checks.append("Retail node quantity is computed from the food lines, never hand-entered: PASS")
    run_corruption_battery(cfg, checks)
    hc = [r for r in rows if r["row_type"] == "LINE" and r["id"] == "HC_02"][0]
    assert hc["boundary_depth"] == "B3"
    checks.append("Healthcare EE-IO line is carried at B3 and is exempt from the B2 truncation adjustment: PASS")
    t4 = [r for r in basket if r["allocation_tier"] == "T4_population"]
    assert all(r["in_floor_total"] == 0 for r in t4)
    checks.append(f"All {len(t4)} population-level (T4) lines are reported alongside the floor: PASS")
    emb = [r for r in basket if r["carrier"] == "embodied"]
    assert all(r["share_electric"] > 0 for r in emb)
    checks.append(f"All {len(emb)} embodied lines carry a measured electric share, never hand-entered: PASS")
    contested = [r for r in basket if r["basis_reconciliation"] == "CONTESTED_UNCONVERTED"]
    assert not any(r["status"] in STATUS_FORBIDDEN_WHEN_CONTESTED for r in contested)
    checks.append(f"{len(contested)} lines declare a contested energy basis and none claims VERIFIED, DERIVED or ACCEPTABLE: PASS")
    sens = [r for r in rows if r["row_type"] == "SENSITIVITY"]
    assert any(r["id"] == "RANK_MEMO" for r in sens)
    assert "literature" not in [r for r in sens if r["id"] == "RANK_1"][0]["name"]
    checks.append("The unconfirmed B3 literature bracket is reported but not ranked: PASS")
    bench = [r for r in rows if r["row_type"] == "BENCHMARK" and r["id"] == "RATIO_MEASURED"]
    assert len(bench) == 1 and 1.0 < bench[0][COLS3[1]] < 1.3
    checks.append("The benchmark reconciliation uses the ratio the model MEASURES: PASS")
    if cfg["healthcare"] == "C":
        d, f_, r_ = hc[COLS3[1]], hc[COLS3[0]], hc[COLS3[2]]
        assert f_ > d > r_, "construction C healthcare is not a genuine triple"
        checks.append(f"Healthcare is a genuine triple under construction C ({f_:.0f} / {d:.0f} / {r_:.0f}): PASS")
    assert all(r["v5_figure_status"] == "PROVISIONAL" for r in rows)
    steps = cfg.get("steps", set())
    inf = {r["id"] for r in rows if r["row_type"] == "LINE" and r["in_floor_total"] == 1}
    for step, ids in STEP_LINES.items():
        assert all((i in inf) == (step in steps) for i in ids), f"step {step} lines misplaced"
    checks.append(f"New lines enter the floor only at their own step (V_01, C_03 at 'dwelling'; H_03 at 'vulnerable'): PASS")
    checks.append(f"Every one of the {len(rows)} output rows is tagged PROVISIONAL: PASS")
    return checks


# ===========================================================================
# 9.  Main
# ===========================================================================

def parse_args(argv):
    opts = {"construction": None, "shares": None, "depth": None, "healthcare": None, "draws": None, "upto": None}
    flags = set()
    i = 0
    while i < len(argv):
        a = argv[i]
        if a.startswith("--") and a[2:] in opts:
            opts[a[2:]] = argv[i + 1]
            i += 2
            continue
        flags.add(a)
        i += 1
    base = opts["construction"] or "C"
    cfg = {"shares": opts["shares"] or base, "depth": opts["depth"] or base,
           "healthcare": opts["healthcare"] or base}
    draws = int(opts["draws"]) if opts["draws"] else None
    cfg["upto"] = int(opts["upto"]) if opts["upto"] else 7
    return cfg, draws, flags


def results_path(cfg, draws) -> str:
    suffix = "" if cfg.get("upto", 7) == 7 else f"_step{cfg['upto']}"
    if draws:
        suffix += f"_quick{draws}"
    return RESULTS_BASE + suffix + ".csv"


def prepare_config(params_raw, findings, upto) -> dict:
    """v5 configuration for steps 1..upto, with the floor-mix depth factors for steps >= 2."""
    cfg = v5_config(params_raw, findings, upto)
    cfg_final = v5_config(params_raw, findings, 7)
    fm = floor_mix_depth(effective_params(params_raw, cfg_final), findings, load_basket(cfg_final), cfg_final)
    if upto >= 2:
        cfg["B1"], cfg["B3"] = fm["B1_rounded"], fm["B3_rounded"]
        cfg["floor_mix"] = fm
        fr = params_raw["boundary_depth"]["factors_relative_to_B2"]
        if (fr["B1"], fr["B3_measured"]) != (fm["B1_rounded"], fm["B3_rounded"]):
            raise BasketError(f"parameters_denmark_v5.json depth factors ({fr['B1']}, {fr['B3_measured']}) do not match "
                              f"the floor-mix measurement ({fm['B1_rounded']}, {fm['B3_rounded']}); re-derive, never hand-edit")
    return cfg


def main(argv) -> int:
    sw, draws, flags = parse_args(argv)
    params_raw = load_parameters()
    findings = load_findings()
    cfg = prepare_config(params_raw, findings, sw["upto"])
    params = effective_params(params_raw, cfg)
    basket = load_basket(cfg)
    rows, run, ranked, mcs = build_results(params, basket, cfg, draws=draws)
    text = render_csv(rows)
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    out_path = results_path(cfg, draws)

    if "--check" in flags:
        if not os.path.exists(out_path):
            print("results file not present; run without --check first")
            return 2
        with open(out_path, encoding="utf-8", newline="") as fh:
            on_disk = fh.read()
        same = on_disk == text
        print(f"results file reproduces byte-identically: {same}")
        print(f"sha256 (recomputed) {digest}")
        print(f"sha256 (on disk)    {hashlib.sha256(on_disk.encode('utf-8')).hexdigest()}")
        return 0 if same else 1

    checks = self_test(params, basket, rows, cfg)
    if "--self-test" in flags:
        for c in checks:
            print("  " + c)
        return 0

    with open(out_path, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)

    t = run["totals"]
    print("=" * 78)
    print(f"UBE survival floor, v5 - Denmark, DLS minimum, primary CED (LHV)   [ALL FIGURES PROVISIONAL]")
    print(f"Steps 1-{cfg['upto']}: {', '.join(STEPS[:cfg['upto']])} | depth {cfg['depth_source']} (B1 {cfg['B1']}, B3 {cfg['B3']})")
    print("=" * 78)
    print(f"{'Sector':<18}{'Fossil 2.5':>13}{'DK-2023 1.6':>14}{'Renewable 1.0':>15}{'share@DK':>10}")
    for sec in SECTOR_ORDER:
        v = {k: run["sector_totals"][k].get(sec, 0.0) for k in t}
        if all(abs(x) < 1e-9 for x in v.values()):
            continue
        print(f"{sec:<18}{v['Fossil_2.5']:>13.0f}{v['DK_2023_1.6']:>14.0f}{v['Renewable_1.0']:>15.0f}"
              f"{100 * v['DK_2023_1.6'] / t['DK_2023_1.6']:>9.1f}%")
    print(f"{'FLOOR kWh/cap/yr':<18}{t['Fossil_2.5']:>13.0f}{t['DK_2023_1.6']:>14.0f}{t['Renewable_1.0']:>15.0f}")
    for tag in ("EXCL_HEALTHCARE", "WITH_HEALTHCARE_B3"):
        m = mcs[tag]
        print(f"INTERVAL {tag} (5th-95th percentile, median):")
        for k in ("Fossil_2.5", "DK_2023_1.6", "Renewable_1.0"):
            print(f"  {k:<15} {m[k]['p05']:>7.0f} - {m[k]['p95']:<7.0f} (median {m[k]['median']:.0f})")
    print()
    for c in checks:
        print("  " + c)
    print(f"Wrote {os.path.basename(out_path)} ({len(rows)} rows, all computed, all PROVISIONAL)")
    print(f"sha256 {digest}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
