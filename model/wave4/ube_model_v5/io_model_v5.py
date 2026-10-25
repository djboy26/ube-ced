"""
io_model_v5.py - the Danish energy-extended input-output model (v4 + the floor-mix depth parts)
==============================================================================================

v5 CHANGE (R-61): the survival bundle is also split into three parts, goods,
services and household energy, each with its own tier series, so that the
depth factors can be re-measured on the floor's own mix (ube_model_v5.py
weights the parts by the floor).  The split is the Physics Validator's
(Rerun_Verification.md sec 3.5).  Everything else is v4, unchanged.


Replaces Wave 2's ``dst_io_prepare.py`` and ``dk_sector_io.py`` (which needed
numpy and pandas) with a standard-library implementation, and removes the
double count confirmed in ``IO_Double_Count_Check.md`` (ruling R-38).

WHAT WAS WRONG
--------------
Wave 2 took each industry's direct energy as ETOT - EKONV from the Danish
energy account ENE2HA.  Removing EKONV (electricity, district heat, gasworks
gas) at the users stopped power-station fuel being counted twice.  But the
same account records two other TRANSFORMATION INPUTS, energy that enters an
industry only to leave it as a different fuel, and Wave 2 left both in:

  * EROOL, crude oil and refinery feedstocks, at the refinery (19000),
    322.06 PJ.  The products are recorded again as oil products (EOIL) at
    every user that burns them.
  * ENGI, natural gas "extraction and imports", at the gas utility (35000),
    99.21 PJ.  This is gas passing through the Danish grid; its users record
    it again when they burn it, and the gas the utility burns itself is
    recorded separately (ENGF, 11.91 PJ).

The oil and gas extraction industry's own ENGI (06090, 13.77 PJ) is platform
fuel, burned offshore, and is NOT removed.

THE FOUR CONSTRUCTIONS (all computed; C is ruled at R-39)
---------------------------------------------------------
W2  Wave 2 exactly as published: e = ETOT - EKONV.  Kept only so that the
    regression suite can prove this engine reproduces Wave 2 to the digit.
A   The minimal correction: W2 minus EROOL (everywhere) and minus ENGI at
    35000.  Power-station fuel stays at 35000 and reaches users through money.
B   Danmarks Statistik's own allocation: the gross energy consumption vector
    ENE3H, in which the conversion sector is zeroed and its fuel, including
    conversion and network losses, is passed to the users of electricity,
    district heat and gasworks gas.
C   Triple-consistent, RULED AT R-39: fuels counted as burned (the A vector
    with the conversion plants' fuel removed), PLUS cumulative delivered
    electricity x the scenario PEF, PLUS cumulative delivered district heat x
    the district-heat factor.  Only C keeps the grid factor separate, so only
    C yields a genuine triple.  Four refinements, each quantified separately
    against the Physics Validator's construction C in the findings file:
      (i)   at the two conversion industries (35000 utilities, 37390 waste
            incineration) road-transport fuel is kept: it is burned by
            vehicles, not plants;
      (ii)  the conversion sector's own purchased electricity for power and
            district heat (35000's sub-industries 350010 and 350030, 10.55 PJ:
            plant own use, heat pumps and electric boilers) is removed, because
            the electricity PEF and the district-heat factor are defined per
            unit DELIVERED and already contain it.  This resolves the overlap
            R-39 carries into this re-run.  POST-VERIFICATION CHANGE: the gas
            business's 1.74 PJ (350020) is inside neither factor and is KEPT
            (Rerun_Verification.md sec 2.3; +3.2 kWh on healthcare's central);
      (iii) ambient heat extracted by heat pumps (EVMP) is removed from the
            fuels, because the project counts heat pumps by their electricity
            at PEF/COP, never by the ambient heat (the heating line H_01 does
            exactly this);
      (iv)  delivered gasworks gas (EGVG, 0.21 PJ) is kept as a fuel burned.

Everything is GJ and million DKK; per-capita figures are kWh/cap/yr at 1 kWh =
3.6 MJ, population 5,935,000 (FOLK1A mid-2023, carried from Wave 2).

ENERGY BASIS.  ENE2HA and ENE3H are kept on a lower-heating-value basis
(Energistyrelsen, 'Begreber og definitioner': "I den danske energistatistik
anvendes nedre braendvaerdi").  That the DST account inherits this basis is an
inference, stated as such.  Wind and solar are counted at their electricity
output in A and B (physical energy content); in C they are inside the PEF.

Run:  python io_model_v4.py          (offline, from _dsdata/)
Outputs: io_findings_v5.json, dk_io_energy_coefficients_v5.csv,
         dk_household_coicop_footprint_v5.csv, ube_sector_io_summary_v5.csv,
         ube_sector_A_matrix_real.csv, healthcare_constructions_v5.csv
"""

from __future__ import annotations

import csv
import json
import os
import statistics

import dst_data as dd
from linalg import (Leontief, dot, matvec, orientation_worked_example,
                    spectral_radius_nonneg, technical_coefficients, transpose)

HERE = os.path.dirname(os.path.abspath(__file__))
PARAMS = os.path.join(HERE, "parameters_denmark_v5.json")
GJ_TO_KWH = 1000.0 / 3.6

CONVERSION_INDUSTRIES = ("35000", "37390")
ROAD_TRANSPORT_FUELS = ("EGASOTR", "EMBZF", "ELPGTR")
GAS_BUSINESS = "350020"   # sub-industry of 35000: manufacture and distribution of gas
HEALTH, CARE, PHARMA = "86000", "87880", "21000"

# Survival-category household final demand, exactly Wave 2's list, for the
# supply-chain tier expansion behind the boundary-depth factors B1 and B3.
SURVIVAL_COICOP = [
    "ACP0113", "ACP0310", "ACP0320", "ACP0440", "ACP0450", "ACP0520", "ACP0530",
    "ACP0540", "ACP0560", "ACP0610", "ACP0620", "ACP0634", "ACP0720", "ACP0730",
    "ACP0810", "ACP0830", "ACP1310",
]
HEALTH_COICOP = ["ACP0610", "ACP0620", "ACP0634"]
# R-61 floor-mix parts (Rerun_Verification.md sec 3.5; pv_floorw.py): a partition of SURVIVAL_COICOP
GOODS_COICOP = ["ACP0113", "ACP0310", "ACP0320", "ACP0520", "ACP0530", "ACP0540", "ACP0560", "ACP0610",
                "ACP0810", "ACP1310"]
SERVICES_COICOP = ["ACP0440", "ACP0620", "ACP0634", "ACP0730", "ACP0830"]
ENERGY_COICOP = ["ACP0450", "ACP0720"]
assert sorted(GOODS_COICOP + SERVICES_COICOP + ENERGY_COICOP) == sorted(SURVIVAL_COICOP)

# The nine-sector map, unchanged from Wave 2 (dk_sector_io.py).
SECTOR_MAP = {
    "S1_Food": ["01000", "03000", "10120", "47000"],
    "S2_Water": ["36000"],
    "S3_Heating": ["35000"],
    "S4_Appliances": ["27000", "26000"],
    "S5_Shelter": ["41430", "23000", "16000", "24000", "25000", "31320", "68203"],
    "S6_Clothing": ["13150"],
    "S7_Hygiene": ["20000", "17000", "37390"],
    "S8_Healthcare": ["86000", "87880", "21000"],
    "S9_Transport": ["49000", "52000", "61000", "62630", "29000"],
}
SECTORS = list(SECTOR_MAP)
A_PHASE1 = [
    [0.05, 0.02, 0.03, 0.01, 0.01, 0.01, 0.01, 0.00, 0.01],
    [0.01, 0.04, 0.02, 0.01, 0.01, 0.00, 0.02, 0.01, 0.00],
    [0.02, 0.01, 0.05, 0.02, 0.03, 0.01, 0.01, 0.01, 0.01],
    [0.02, 0.01, 0.03, 0.04, 0.02, 0.01, 0.01, 0.01, 0.02],
    [0.03, 0.01, 0.04, 0.02, 0.06, 0.02, 0.01, 0.01, 0.02],
    [0.01, 0.00, 0.01, 0.01, 0.01, 0.04, 0.01, 0.00, 0.01],
    [0.01, 0.02, 0.01, 0.01, 0.01, 0.01, 0.03, 0.01, 0.00],
    [0.01, 0.01, 0.01, 0.01, 0.01, 0.00, 0.01, 0.05, 0.01],
    [0.01, 0.01, 0.02, 0.03, 0.02, 0.01, 0.01, 0.01, 0.04],
]


def load_params() -> dict:
    with open(PARAMS, encoding="utf-8") as fh:
        return json.load(fh)


# ===========================================================================
# 1.  The direct-energy vectors, one per construction
# ===========================================================================

def build_vectors(codes, ene, e3h) -> dict:
    """Every direct-energy vector the constructions need, in GJ, by industry."""
    def g(c, k):
        return ene.get(("V" + c, k), 0.0)

    w2 = [max(g(c, "ETOT") - g(c, "EKONV"), 0.0) for c in codes]
    a = []
    for c in codes:
        v = g(c, "ETOT") - g(c, "EKONV") - g(c, "EROOL")
        if c == "35000":
            v -= g(c, "ENGI")
        a.append(max(v, 0.0))
    b = [e3h.get(("V" + c, "ETOT"), 0.0) for c in codes]

    def c_parts(keep_road_fuel=True, zero_conv_own_el=True, drop_ambient=True,
                add_gasworks=True, zero_37390_el_heat=False, keep_gas_business_el=True):
        F, E, H = [], [], []
        for c, av in zip(codes, a):
            if c in CONVERSION_INDUSTRIES:
                f = sum(g(c, k) for k in ROAD_TRANSPORT_FUELS) if keep_road_fuel else 0.0
            else:
                f = av - (g(c, "EVMP") if drop_ambient else 0.0)
                if add_gasworks:
                    f += g(c, "EGVG")
            el, dh = g(c, "EEL"), g(c, "EFJV")
            if c == "35000" and zero_conv_own_el:
                # Post-verification change (Rerun_Verification.md sec 2.3): of the
                # utility's 12.29 PJ, power production (350010, 2.51 PJ) and district
                # heat (350030, 8.05 PJ) are inside the PEF and the DH factor; the
                # gas business's 1.74 PJ (350020) is inside neither and stays in.
                el = g(GAS_BUSINESS, "EEL") if keep_gas_business_el else 0.0
                dh = 0.0
            if c == "37390" and zero_37390_el_heat:
                el, dh = 0.0, 0.0
            F.append(max(f, 0.0))
            E.append(el)
            H.append(dh)
        return F, E, H

    C_F, C_E, C_H = c_parts()
    # The Physics Validator's construction C, reproduced so every refinement
    # can be quantified from it: 35000 and 37390 zeroed entirely, all
    # delivered electricity and heat kept, ambient heat kept, no gasworks gas.
    V_F = [0.0 if c in CONVERSION_INDUSTRIES else av for c, av in zip(codes, a)]
    V_E = [g(c, "EEL") for c in codes]
    V_H = [g(c, "EFJV") for c in codes]
    steps = {
        "validator_C": (V_F, V_E, V_H),
        "step1_keep_road_fuel": (c_parts(True, False, False, False)),
        "step2_first_run_zero_all_35000_own_electricity_SUPERSEDED":
            c_parts(True, True, False, False, keep_gas_business_el=False),
        "step2_plus_zero_35000_own_electricity_except_gas_business": (c_parts(True, True, False, False)),
        "step3_plus_drop_ambient_heat": (c_parts(True, True, True, False)),
        "step4_plus_gasworks_gas_ADOPTED": (C_F, C_E, C_H),
        "sensitivity_also_zero_37390_electricity_and_heat":
            c_parts(True, True, True, True, zero_37390_el_heat=True),
    }
    removed = {
        "EROOL_all_industries_GJ": sum(g(c, "EROOL") for c in codes),
        "ENGI_at_35000_GJ": g("35000", "ENGI"),
        "ENGI_at_06090_kept_GJ": g("06090", "ENGI"),
        "C_conversion_fuel_removed_35000_GJ": a[codes.index("35000")] - C_F[codes.index("35000")],
        "C_conversion_fuel_removed_37390_GJ": a[codes.index("37390")] - C_F[codes.index("37390")],
        "C_road_fuel_kept_35000_37390_GJ": sum(C_F[codes.index(c)] for c in CONVERSION_INDUSTRIES),
        "C_ambient_heat_removed_GJ": sum(g(c, "EVMP") for c in codes if c not in CONVERSION_INDUSTRIES),
        "C_35000_own_electricity_removed_GJ": g("35000", "EEL") - g(GAS_BUSINESS, "EEL"),
        "C_35000_gas_business_electricity_kept_GJ": g(GAS_BUSINESS, "EEL"),
        "C_gasworks_gas_added_GJ": sum(g(c, "EGVG") for c in codes if c not in CONVERSION_INDUSTRIES),
    }
    return {"W2": w2, "A": a, "B": b, "C_F": C_F, "C_E": C_E, "C_H": C_H,
            "E_all": [g(c, "EEL") for c in codes], "c_steps": steps, "removed": removed}


def household_direct(ene, e3h) -> dict:
    """What households burn or receive directly, per construction, GJ."""
    def h(k):
        return ene.get(("EHUSHOLD", k), 0.0)
    fuel = h("ETOT") - h("EKONV")
    return {
        "fuel_ETOT_minus_EKONV": fuel,
        "fuel_excl_ambient_plus_gasworks": fuel - h("EVMP") + h("EGVG"),
        "ambient_heat_EVMP": h("EVMP"),
        "delivered_electricity_EEL": h("EEL"),
        "delivered_district_heat_EFJV": h("EFJV"),
        "gasworks_gas_EGVG": h("EGVG"),
        "ene3h_gross": e3h.get(("EHUSHOLD", "ETOT"), 0.0),
    }


def hh_C(hd, pef, dhf):
    return (hd["fuel_excl_ambient_plus_gasworks"] + pef * hd["delivered_electricity_EEL"]
            + dhf * hd["delivered_district_heat_EFJV"])


# ===========================================================================
# 2.  The model
# ===========================================================================

class IOModel:
    def __init__(self):
        self.params = load_params()
        self.pop = float(self.params["population_DK_2023"])
        self.pef = self.params["pef_scenarios"]
        self.pef_ref = self.params["pef_reference"]
        hc = self.params["heat_carrier"]
        self.dh_variants = hc["district_heat_factor_variants"]
        self.dhf = self.dh_variants[hc["district_heat_factor_default"]]

        io = dd.load_io()
        self.codes, self.idx, self.x = io["codes"], io["idx"], io["x"]
        self.Z_dom, self.Z_imp = io["Z_dom"], io["Z_imp"]
        self.hh_fd, self.hh_fd_dom = io["hh_fd"], io["hh_fd_dom"]
        self.n = len(self.codes)
        self.ene = dd.load_ene2ha()
        self.e3h = dd.load_ene3h()
        self.mu1 = dd.load_ene2mu1n()
        self.mu2 = dd.load_ene2mu2n()

        n = self.n
        self.Z_tot = [[self.Z_dom[i][j] + self.Z_imp[i][j] for j in range(n)] for i in range(n)]
        self.A_tot = technical_coefficients(self.Z_tot, self.x)
        self.A_dom = technical_coefficients(self.Z_dom, self.x)
        self.L = {"tot": Leontief(self.A_tot), "dom": Leontief(self.A_dom)}

        self.vec = build_vectors(self.codes, self.ene, self.e3h)
        self.hh = household_direct(self.ene, self.e3h)

    # -- helpers ---------------------------------------------------------
    def intensity(self, e):
        return [(ei / xi if xi > 0 else 0.0) for ei, xi in zip(e, self.x)]

    def mult(self, e, closure):
        return self.L[closure].multiplier(self.intensity(e))

    def percap(self, gj):
        return gj * GJ_TO_KWH / self.pop

    def k(self, code):
        return self.idx[code]

    # -- 2.1  multipliers for every construction and closure ---------------
    def multipliers(self):
        v = self.vec
        m = {}
        for con in ("W2", "A", "B"):
            m[con] = {cl: self.mult(v[con], cl) for cl in ("dom", "tot")}
        for part in ("C_F", "C_E", "C_H"):
            m[part] = {cl: self.mult(v[part], cl) for cl in ("dom", "tot")}
        m["E_all"] = {cl: self.mult(v["E_all"], cl) for cl in ("dom", "tot")}
        self.m = m
        return m

    def m_C(self, closure, pef, dhf):
        F, E, H = (self.m[p][closure] for p in ("C_F", "C_E", "C_H"))
        return [f + pef * e + dhf * h for f, e, h in zip(F, E, H)]

    # -- 2.2  healthcare -----------------------------------------------------
    def healthcare_scalar(self, m_dom, m_tot) -> dict:
        kh, kc = self.k(HEALTH), self.k(CARE)
        x = self.x
        return {
            "low_health_domestic_only": self.percap(m_dom[kh] * x[kh]),
            "central_health_domestic_technology": self.percap(m_tot[kh] * x[kh]),
            "high_health_plus_care_domestic_technology":
                self.percap(m_tot[kh] * x[kh] + m_tot[kc] * x[kc]),
            "care_only_domestic_technology": self.percap(m_tot[kc] * x[kc]),
            "health_plus_care_domestic_only":
                self.percap(m_dom[kh] * x[kh] + m_dom[kc] * x[kc]),
            "multiplier_86000_tot_GJ_per_mDKK": m_tot[kh],
            "multiplier_86000_dom_GJ_per_mDKK": m_dom[kh],
        }

    def healthcare_C_components(self, F, E, H) -> dict:
        """Low / central / high, each split into fuels F, electricity E, heat H (kWh)."""
        mF = {cl: self.mult(F, cl) for cl in ("dom", "tot")}
        mE = {cl: self.mult(E, cl) for cl in ("dom", "tot")}
        mH = {cl: self.mult(H, cl) for cl in ("dom", "tot")}
        out = {}
        for band, (cl, inds) in {
                "low": ("dom", [HEALTH]),
                "central": ("tot", [HEALTH]),
                "high": ("tot", [HEALTH, CARE])}.items():
            comp = {}
            for name, mm in (("F", mF), ("E", mE), ("H", mH)):
                comp[name] = sum(self.percap(mm[cl][self.k(c)] * self.x[self.k(c)])
                                 for c in inds)
            out[band] = comp
        return out

    def triple(self, comp, dhf=None):
        dhf = self.dhf if dhf is None else dhf
        return {lab: comp["F"] + p * comp["E"] + dhf * comp["H"]
                for lab, p in self.pef.items()}

    def healthcare(self) -> dict:
        m = self.m
        out = {}
        for con in ("W2", "A", "B"):
            out[con] = self.healthcare_scalar(m[con]["dom"], m[con]["tot"])
        comps = self.healthcare_C_components(self.vec["C_F"], self.vec["C_E"], self.vec["C_H"])
        out["C"] = {
            "components_kWh": comps,
            "triple": {band: self.triple(comps[band]) for band in comps},
            "dh_convention_sensitivity_central": {
                name: self.triple(comps["central"], val)
                for name, val in self.dh_variants.items()},
        }
        steps = {}
        for name, (F, E, H) in self.vec["c_steps"].items():
            cc = self.healthcare_C_components(F, E, H)
            steps[name] = {band: self.triple(cc[band]) for band in cc}
        out["C"]["refinement_steps_from_validator_C"] = steps
        # Disclosure 1: household-only health demand (production vs demand basis)
        f_health = [0.0] * self.n
        for c in HEALTH_COICOP:
            for i, v in enumerate(self.hh_fd.get(c, [0.0] * self.n)):
                f_health[i] += v
        disc1 = {con: self.percap(dot(m[con]["tot"], f_health)) for con in ("W2", "A", "B")}
        disc1["C"] = {lab: self.percap(dot(self.m_C("tot", p, self.dhf), f_health))
                      for lab, p in self.pef.items()}
        out["disclosure1_household_only_health_kWh"] = disc1
        # Disclosure 2: pharmacy-dispensed drugs, order of magnitude.  Wave 2's
        # 25-60 was scaled from household demand for 21000; it moves with the
        # 21000 multiplier.
        kp = self.k(PHARMA)
        ratio = {con: m[con]["tot"][kp] / m["W2"]["tot"][kp] for con in ("A", "B")}
        ratio["C"] = self.m_C("tot", self.pef_ref, self.dhf)[kp] / m["W2"]["tot"][kp]
        out["disclosure2_pharmacy_drugs_kWh"] = {
            con: [25.0 * r, 60.0 * r] for con, r in ratio.items()}
        out["disclosure2_multiplier_ratio_21000"] = ratio
        out["population"] = self.pop
        return out

    # -- 2.3  cumulative electric shares ------------------------------------
    def carrier_composition(self) -> dict:
        m = self.m
        mel = m["E_all"]["tot"]
        comp = {}
        for con in ("W2", "A", "B"):
            by = {}
            for c in self.codes:
                k = self.k(c)
                if m[con]["tot"][k] <= 0:
                    continue
                by[c] = {"cumulative_primary_GJ_per_mDKK": m[con]["tot"][k],
                         "cumulative_delivered_electricity_GJ_per_mDKK": mel[k],
                         "electric_share_of_primary_at_pef_ref":
                             mel[k] * self.pef_ref / m[con]["tot"][k]}
            comp[con] = {"definition": "delivered electricity (all industries) x PEF_ref "
                                       "/ cumulative primary of this construction "
                                       "(Wave 2's definition)", "by_industry": by}
        by = {}
        mC = self.m_C("tot", self.pef_ref, self.dhf)
        for c in self.codes:
            k = self.k(c)
            if mC[k] <= 0:
                continue
            by[c] = {"cumulative_primary_GJ_per_mDKK": mC[k],
                     "cumulative_fuels_GJ_per_mDKK": m["C_F"]["tot"][k],
                     "cumulative_delivered_electricity_GJ_per_mDKK": m["C_E"]["tot"][k],
                     "cumulative_delivered_district_heat_GJ_per_mDKK": m["C_H"]["tot"][k],
                     "electric_share_of_primary_at_pef_ref":
                         self.pef_ref * m["C_E"]["tot"][k] / mC[k]}
        comp["C"] = {"definition": "PEF_ref x cumulative delivered electricity / (fuels + "
                                   "PEF_ref x electricity + DH factor x district heat), "
                                   "all on construction C: numerator and denominator "
                                   "count electricity at the same factor",
                     "by_industry": by}
        comp["pef_reference"] = self.pef_ref
        comp["dh_factor_reference"] = self.dhf
        comp["closure"] = "domestic technology assumption (domestic + imported flows)"
        return comp

    # -- 2.4  supply-chain tier expansion and the depth factors -------------
    def survival_demand(self):
        f = [0.0] * self.n
        for c in SURVIVAL_COICOP:
            for i, v in enumerate(self.hh_fd.get(c, [0.0] * self.n)):
                f[i] += v
        return f

    def demand(self, classes):
        f = [0.0] * self.n
        for c in classes:
            for i, v in enumerate(self.hh_fd.get(c, [0.0] * self.n)):
                f[i] += v
        return f

    def tier_series(self, e, hh0=0.0, kmax=12, f=None):
        f = self.survival_demand() if f is None else f
        eint = self.intensity(e)
        vals, term, cum = [], list(f), hh0
        for _ in range(kmax + 1):
            cum += dot(eint, term)
            vals.append(cum)
            term = matvec(self.A_tot, term)
        complete = dot(self.L["tot"].multiplier(eint), f) + hh0
        share = [v / complete for v in vals]
        return {"series_GJ": vals, "complete_GJ": complete, "share_by_tier": share,
                "household_direct_at_tier0_GJ": hh0,
                "B1": share[1] / share[3], "B3_measured": 1.0 / share[3]}

    def truncation(self) -> dict:
        """
        THE TIER-0 CONVENTION, and why it is needed at all.  Wave 2's survival
        bundle carried the oil and gas households burn only THROUGH the double
        count: a krone of petrol bought from the refinery carried refinery crude
        (about 102 PJ at tier 0), and a krone of gas bought from the utility
        carried pass-through gas.  Remove the double count and that energy leaves
        the series entirely, unless it is put back where it is actually burned.

        ADOPTED ('like-for-like, fossil only'): put back exactly what Wave 2
        carried, at the point of use, and nothing it did not carry.  It is the
        FOSSIL oil and gas: the 6.9 PJ of biomethane in households' gas and the
        4.4 PJ of biofuel in their road fuel are booked as renewables and left
        out, as Wave 2's refinery never carried them (B1 0.911 with them in):
          A  households' oil products and natural gas as burned (their
             electricity and heat still reach them through the utility's
             money-spread fuel, as in Wave 2);
          B  households' oil, gas and gross converted energy from ENE3H;
          C  households' oil, gas and gasworks gas as burned, plus delivered
             electricity x PEF and delivered district heat x the DH factor.
        Household wood and other biomass was never in Wave 2's series (a
        household buying firewood buys a product whose energy no industry
        records), so it is left out and reported as a sensitivity.
        SENSITIVITIES: the Physics Validator's variant (electricity and heat
        only at tier 0; it omits household oil and gas), and 'all household
        direct energy' (adds wood and other biomass).
        """
        v, hd, e = self.vec, self.hh, self.ene

        def h(k):
            return e.get(("EHUSHOLD", k), 0.0)

        def g3(k):
            return self.e3h.get(("EHUSHOLD", k), 0.0)
        oil_gas = h("EOIL") + h("ENGF")
        out = {
            "W2": self.tier_series(v["W2"]),
            "A": self.tier_series(v["A"], oil_gas),
            "B": self.tier_series(v["B"], g3("EOIL") + g3("ENGF") + g3("EKONV")),
        }
        for lab, p in self.pef.items():
            ext = [f + p * el + self.dhf * hh for f, el, hh in zip(v["C_F"], v["C_E"], v["C_H"])]
            hh0 = oil_gas + h("EGVG") + p * h("EEL") + self.dhf * h("EFJV")
            out[f"C_{lab}"] = self.tier_series(ext, hh0)
            if p == self.pef_ref:
                ext_ref = ext
                out["C"] = out[f"C_{lab}"]
                out["sensitivity_C_validator_electricity_and_heat_only"] = self.tier_series(
                    ext, p * h("EEL") + self.dhf * h("EFJV"))
                out["sensitivity_C_all_household_direct_incl_wood"] = self.tier_series(
                    ext, hh_C(hd, p, self.dhf))
                out["sensitivity_C_nothing_at_tier0"] = self.tier_series(ext, 0.0)
        # option 1 plus households' biomethane and blended biofuel (the renewables
        # inside the gas and road fuel they burn: EBIO and EBIOOIL)
        out["sensitivity_C_fossil_plus_biomethane_and_biofuel"] = self.tier_series(
            ext_ref, oil_gas + h("EGVG") + h("EBIO") + h("EBIOOIL")
            + self.pef_ref * h("EEL") + self.dhf * h("EFJV"))
        # R-61: the floor-mix parts (construction C at DK-2023, option 1 at tier 0 for energy)
        out["parts_C"] = {
            "goods": self.tier_series(ext_ref, 0.0, f=self.demand(GOODS_COICOP)),
            "services": self.tier_series(ext_ref, 0.0, f=self.demand(SERVICES_COICOP)),
            "energy": self.tier_series(ext_ref, oil_gas + h("EGVG") + self.pef_ref * h("EEL")
                                       + self.dhf * h("EFJV"), f=self.demand(ENERGY_COICOP)),
            "energy_option3": self.tier_series(ext_ref, hh_C(hd, self.pef_ref, self.dhf),
                                               f=self.demand(ENERGY_COICOP)),
            "classes": {"goods": GOODS_COICOP, "services": SERVICES_COICOP, "energy": ENERGY_COICOP}}
        out["sensitivity_A_validator_no_household_fuel"] = self.tier_series(v["A"])
        out["sensitivity_A_all_household_direct_fuel"] = self.tier_series(
            v["A"], hd["fuel_ETOT_minus_EKONV"])
        out["sensitivity_B_all_household_gross"] = self.tier_series(v["B"], hd["ene3h_gross"])
        out["wave2_tier0_via_purchases_GJ"] = {
            c: self.survival_demand()[self.k(c)] * self.intensity(v["W2"])[self.k(c)]
            for c in ("35000", "19000")}
        out["definition"] = ("share = energy captured by supply-chain tiers 0..k of "
                             "survival-category household final demand / complete "
                             "boundary. B1 = share(0..1)/share(0..3); B3_measured = "
                             "1/share(0..3). Tier-0 household energy: see truncation() "
                             "docstring (like-for-like with Wave 2)")
        return out

    # -- 2.5  household footprint (the SANITY rows) --------------------------
    def household_footprint(self) -> dict:
        m, hd = self.m, self.hh
        vecs = list(self.hh_fd.values())

        def purchased(mm):
            return sum(dot(mm, v) for v in vecs)
        out = {}
        for con, direct in (("W2", hd["fuel_ETOT_minus_EKONV"]),
                            ("A", hd["fuel_ETOT_minus_EKONV"]),
                            ("B", hd["ene3h_gross"])):
            p_tot, p_dom = purchased(m[con]["tot"]), purchased(m[con]["dom"])
            out[con] = {"purchased_GJ_per_cap": p_tot / self.pop,
                        "purchased_domestic_closure_GJ_per_cap": p_dom / self.pop,
                        "household_direct_GJ_per_cap": direct / self.pop,
                        "total_GJ_per_cap": (p_tot + direct) / self.pop,
                        "total_domestic_closure_GJ_per_cap": (p_dom + direct) / self.pop}
        out["C"] = {}
        for lab, p in self.pef.items():
            p_tot = purchased(self.m_C("tot", p, self.dhf))
            p_dom = purchased(self.m_C("dom", p, self.dhf))
            direct = hh_C(hd, p, self.dhf)
            out["C"][lab] = {"purchased_GJ_per_cap": p_tot / self.pop,
                             "purchased_domestic_closure_GJ_per_cap": p_dom / self.pop,
                             "household_direct_GJ_per_cap": direct / self.pop,
                             "total_GJ_per_cap": (p_tot + direct) / self.pop,
                             "total_domestic_closure_GJ_per_cap": (p_dom + direct) / self.pop}
        # DST's own household figure, ENE2MU2N, for description only
        mu2 = self.mu2
        out["DST_ENE2MU2N_households"] = {
            "direct_GJ": mu2.get(("ACPT", "ETOT", "ENEDIREA")),
            "direct_and_indirect_GJ": mu2.get(("ACPT", "ETOT", "ENEINTEA")),
            "direct_and_indirect_GJ_per_cap": mu2.get(("ACPT", "ETOT", "ENEINTEA"), 0) / self.pop,
            "note": "domestic closure, DST gross-energy basis. Its 'direct' term is not "
                    "defined as ENE3H's household total, so it is a comparator, not a check"}
        # Try to reconstruct DST's household figure with construction B
        fdom = [0.0] * self.n
        for v in self.hh_fd_dom.values():
            for i, t in enumerate(v):
                fdom[i] += t
        eB = self.intensity(self.vec["B"])
        out["DST_ENE2MU2N_reconstruction_B"] = {
            "tier0_of_domestic_purchases_GJ": dot(eB, fdom),
            "complete_of_domestic_purchases_GJ": dot(m["B"]["dom"], fdom),
            "complete_plus_ene3h_households_GJ": dot(m["B"]["dom"], fdom) + hd["ene3h_gross"]}
        return out

    # -- 2.6  nine-sector aggregation ----------------------------------------
    def sectors(self) -> dict:
        idx, x, Z = self.idx, self.x, self.Z_tot
        msz = len(SECTORS)
        x9 = [sum(x[idx[c]] for c in SECTOR_MAP[s]) for s in SECTORS]
        A9 = [[sum(Z[idx[i]][idx[j]] for i in SECTOR_MAP[a] for j in SECTOR_MAP[b]) / x9[bb]
               for bb, b in enumerate(SECTORS)] for a in SECTORS]
        out = {"A9": A9, "x9": x9,
               "A9_col_sums": [sum(A9[i][j] for i in range(msz)) for j in range(msz)],
               "A9_row_sums": [sum(r) for r in A9],
               "A_phase1_col_sums": [sum(A_PHASE1[i][j] for i in range(msz)) for j in range(msz)]}
        L9, L9T = Leontief(A9), Leontief(transpose(A9))
        C_ref = [f + self.pef_ref * e + self.dhf * h
                 for f, e, h in zip(self.vec["C_F"], self.vec["C_E"], self.vec["C_H"])]
        by = {}
        for con, e, mm in (("W2", self.vec["W2"], self.m["W2"]["tot"]),
                           ("A", self.vec["A"], self.m["A"]["tot"]),
                           ("B", self.vec["B"], self.m["B"]["tot"]),
                           ("C", C_ref, self.m_C("tot", self.pef_ref, self.dhf))):
            ed = [sum(e[idx[c]] for c in SECTOR_MAP[s]) for s in SECTORS]
            et = [sum(mm[idx[c]] * x[idx[c]] for c in SECTOR_MAP[s]) for s in SECTORS]
            up = [(t / d if d > 0 else None) for t, d in zip(et, ed)]
            eint9 = [d / xx for d, xx in zip(ed, x9)]
            corr = dot(L9.multiplier(eint9), x9) / dot(eint9, x9)
            wrong = dot(L9T.multiplier(eint9), x9) / dot(eint9, x9)
            by[con] = {"direct_GJ": ed, "cumulative_GJ": et, "upstream_ratio": up,
                       "economy_multiplier_correct": corr,
                       "economy_multiplier_transposed": wrong,
                       "orientation_error_pct": 100.0 * (wrong / corr - 1.0)}
        out["by_construction"] = by
        return out

    # -- 2.7  per-industry coefficient table ----------------------------------
    def coefficient_rows(self):
        m = self.m
        rows = []
        mC = self.m_C("tot", self.pef_ref, self.dhf)
        for c in self.codes:
            k = self.k(c)
            r = {"industry_code": c, "output_mDKK": self.x[k],
                 "ETOT_GJ": self.ene.get(("V" + c, "ETOT"), 0.0),
                 "EKONV_GJ": self.ene.get(("V" + c, "EKONV"), 0.0),
                 "EROOL_GJ": self.ene.get(("V" + c, "EROOL"), 0.0),
                 "ENGI_GJ": self.ene.get(("V" + c, "ENGI"), 0.0),
                 "direct_W2_GJ": self.vec["W2"][k], "direct_A_GJ": self.vec["A"][k],
                 "direct_B_ENE3H_GJ": self.vec["B"][k],
                 "direct_C_fuels_GJ": self.vec["C_F"][k],
                 "direct_C_electricity_GJ": self.vec["C_E"][k],
                 "direct_C_district_heat_GJ": self.vec["C_H"][k]}
            for con in ("W2", "A", "B"):
                r[f"multiplier_{con}_tot"] = m[con]["tot"][k]
                r[f"multiplier_{con}_dom"] = m[con]["dom"][k]
            r["multiplier_C_tot_at_ref"] = mC[k]
            r["multiplier_C_fuels_tot"] = m["C_F"]["tot"][k]
            r["multiplier_C_electricity_tot"] = m["C_E"]["tot"][k]
            r["multiplier_C_district_heat_tot"] = m["C_H"]["tot"][k]
            rows.append(r)
        return rows


# ===========================================================================
# 3.  Regression tests: this class of error must not return silently
# ===========================================================================

def test_a_gross_energy(model: IOModel, tol: float = 0.02) -> dict:
    """
    (a) The industries' direct-energy extension plus households' direct fuel
    must reconcile with DST's ENE3H gross energy consumption for the same year
    within 2%.  Applied to construction A's vector (the corrected Wave 2
    extension).  The Wave 2 vector is run through the same test to show the
    test catches the error it exists for.
    """
    ref = model.e3h[("ETOT", "ETOT")]
    hh = model.hh["fuel_ETOT_minus_EKONV"]
    res = {"reference_ENE3H_total_GJ": ref,
           "reference_ENE3H_industries_GJ": model.e3h[("EV", "ETOT")],
           "reference_ENE3H_households_GJ": model.e3h[("EHUSHOLD", "ETOT")],
           "household_direct_fuel_GJ": hh, "tolerance": tol}
    for con in ("W2", "A"):
        tot = sum(model.vec[con]) + hh
        res[con] = {"industries_GJ": sum(model.vec[con]), "total_GJ": tot,
                    "gap_pct": 100.0 * (tot / ref - 1.0),
                    "passes": abs(tot / ref - 1.0) <= tol}
    # (a2) the fuels alone, outside the conversion plants, against DST's
    # non-converted energy outside the same plants
    conv = set(CONVERSION_INDUSTRIES)
    ours = sum(v for c, v in zip(model.codes, model.vec["A"]) if c not in conv)
    dst = sum(model.e3h.get(("V" + c, "ETOT"), 0.0) - model.e3h.get(("V" + c, "EKONV"), 0.0)
              for c in model.codes if c not in conv)
    res["fuels_outside_conversion_plants"] = {
        "A_GJ": ours, "DST_ENE3H_non_converted_GJ": dst,
        "gap_pct": 100.0 * (ours / dst - 1.0), "passes": abs(ours / dst - 1.0) <= tol}
    res["passes"] = res["A"]["passes"] and res["fuels_outside_conversion_plants"]["passes"]
    res["catches_wave2_error"] = not res["W2"]["passes"]
    return res


def test_b_dst_multipliers(model: IOModel, tol: float = 0.03, tol_max: float = 0.10) -> dict:
    """
    (b) Domestic-closure multipliers computed by this engine from DST's own
    direct-energy vector must reproduce DST's published ENE2MU1N multipliers
    to a median gap within 3%, AND no single industry may be off by more than
    10%.  The second criterion exists because a median cannot see a local
    error: with ENE2MU1N's labels taken as published, the median is still
    2.7% while human health is off by 35%.  The seven-label permutation in
    ENE2MU1N is derived from the data and undone first.  Two negative controls
    show the test has teeth: the naive (un-remapped) comparison, and the
    transposed A matrix (the orientation error Wave 1 found).  Residual gaps of
    up to about 7% are consistent with DST computing at a finer (117-industry)
    level than the 69 industries used here.
    """
    codes, x = model.codes, model.x
    mu = model.mu1
    remap = dd.derive_ene2mu1n_remap(mu, codes, x)
    moved = {k: v for k, v in remap.items() if k != v}
    true_of = remap
    enedir = [0.0] * model.n
    enemul = [None] * model.n
    for lab in codes:
        k = model.k(true_of[lab])
        enedir[k] = mu.get(("V" + lab, "ETOT", "ENEDIR"), 0.0)
        val = mu.get(("V" + lab, "ETOT", "ENEMUL"), 0.0)
        enemul[k] = val if val > 0 else None
    ene3h_vec = model.vec["B"]
    max_vec_gap = max(abs(a - b) for a, b in zip(enedir, ene3h_vec))

    def gaps(mults, published):
        out = {}
        for c in codes:
            k = model.k(c)
            if published[k]:
                out[c] = mults[k] / published[k] - 1.0
        return out

    m_dom = model.mult(enedir, "dom")
    g = gaps(m_dom, enemul)
    med = statistics.median(abs(v) for v in g.values())
    # negative control 1: labels taken as published
    naive_pub = [None] * model.n
    for lab in codes:
        val = mu.get(("V" + lab, "ETOT", "ENEMUL"), 0.0)
        naive_pub[model.k(lab)] = val if val > 0 else None
    naive_dir = [mu.get(("V" + c, "ETOT", "ENEDIR"), 0.0) for c in codes]
    g_naive = gaps(model.mult(naive_dir, "dom"), naive_pub)
    # negative control 2: the transposed A matrix
    LT = Leontief(transpose(model.A_dom))
    g_T = gaps(LT.multiplier(model.intensity(enedir)), enemul)
    kh = model.k(HEALTH)
    return {
        "remap_published_label_to_true_industry": moved,
        "enedir_equals_ene3h_after_remap_max_gap_GJ": max_vec_gap,
        "n_industries_compared": len(g),
        "median_abs_gap_pct": 100.0 * med,
        "max_abs_gap_pct": 100.0 * max(abs(v) for v in g.values()),
        "share_within_3pct": sum(1 for v in g.values() if abs(v) <= 0.03) / len(g),
        "gap_by_industry_pct": {c: 100.0 * v for c, v in sorted(g.items())},
        "human_health": {"ours": m_dom[kh], "DST_published": enemul[kh]},
        "tolerance_median": tol,
        "tolerance_max": tol_max,
        "passes": med <= tol and max(abs(v) for v in g.values()) <= tol_max,
        "negative_control_naive_labels": {
            "median_abs_gap_pct": 100.0 * statistics.median(abs(v) for v in g_naive.values()),
            "max_abs_gap_pct": 100.0 * max(abs(v) for v in g_naive.values()),
            "human_health_gap_pct": 100.0 * g_naive.get(HEALTH, float("nan")),
            "industries_off_by_more_than_10pct": sorted(c for c, v in g_naive.items() if abs(v) > 0.10),
            "fails_as_it_should": not (statistics.median(abs(v) for v in g_naive.values()) <= tol
                                       and max(abs(v) for v in g_naive.values()) <= tol_max)},
        "negative_control_transposed_A": {
            "median_abs_gap_pct": 100.0 * statistics.median(abs(v) for v in g_T.values()),
            "fails_as_it_should": statistics.median(abs(v) for v in g_T.values()) > tol},
    }


def test_wave2_reproduction(model: IOModel) -> dict:
    """With the correction switched off, this engine must reproduce Wave 2."""
    hc = model.healthcare_scalar(model.m["W2"]["dom"], model.m["W2"]["tot"])
    expect = {"low_health_domestic_only": 640.2795, "central_health_domestic_technology": 999.2529,
              "high_health_plus_care_domestic_technology": 2194.7979}
    path = os.path.normpath(os.path.join(HERE, "..", "..", "wave2", "ube_model",
                                         "ube_sector_io_findings.json"))
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            w2 = json.load(fh)["healthcare"]
        expect = {"low_health_domestic_only": w2["health_only_kWh_per_cap_domesticonly"],
                  "central_health_domestic_technology": w2["health_only_kWh_per_cap_domtech"],
                  "high_health_plus_care_domestic_technology": w2["health_plus_care_kWh_per_cap_domtech"]}
    gaps = {k: hc[k] - v for k, v in expect.items()}
    sum_pj = sum(model.vec["W2"]) / 1e6
    return {"expected_from_wave2_findings": expect, "reproduced": {k: hc[k] for k in expect},
            "max_abs_gap_kWh": max(abs(v) for v in gaps.values()),
            "sum_extension_PJ": sum_pj, "expected_sum_extension_PJ": 1446.20,
            "passes": max(abs(v) for v in gaps.values()) < 0.01 and abs(sum_pj - 1446.20) < 0.01}


# ===========================================================================
# 4.  Run and write
# ===========================================================================

def productivity(model: IOModel) -> dict:
    out = {}
    for tag, A in (("dom", model.A_dom), ("tot", model.A_tot)):
        colsum = [sum(A[i][j] for i in range(model.n)) for j in range(model.n)]
        out[tag] = {"spectral_radius": spectral_radius_nonneg(A),
                    "max_column_sum": max(colsum), "mean_column_sum": sum(colsum) / len(colsum)}
        out[tag]["productive"] = out[tag]["spectral_radius"] < 1.0
    return out


def run(write: bool = True) -> dict:
    model = IOModel()
    model.multipliers()
    findings = {
        "_README": ["Written by io_model_v4.py. Every figure PROVISIONAL pending the Physics "
                    "Validator's check of the v4 re-run (R-38). Primary energy, LHV, as the "
                    "Danish energy account records it; kWh/cap/yr at 1 kWh = 3.6 MJ; "
                    "Denmark 2023."],
        "year": dd.YEAR,
        "population": model.pop,
        "orientation_test": orientation_worked_example(),
        "productivity": productivity(model),
        "extension_totals_PJ": {con: sum(model.vec[con]) / 1e6 for con in ("W2", "A", "B")}
        | {"C_fuels": sum(model.vec["C_F"]) / 1e6,
           "C_delivered_electricity": sum(model.vec["C_E"]) / 1e6,
           "C_delivered_district_heat": sum(model.vec["C_H"]) / 1e6},
        "removed_PJ": {k: v / 1e6 for k, v in model.vec["removed"].items()},
        "household_direct_PJ": {k: v / 1e6 for k, v in model.hh.items()},
        "healthcare": model.healthcare(),
        "carrier_composition": model.carrier_composition(),
        "truncation": model.truncation(),
        "household_footprint": model.household_footprint(),
        "sectors": model.sectors(),
        "regression_tests": {
            "a_gross_energy_ENE3H": test_a_gross_energy(model),
            "b_DST_multipliers_ENE2MU1N": test_b_dst_multipliers(model),
            "wave2_reproduction": test_wave2_reproduction(model),
        },
        "inputs_sha256": {f: dd.sha256_of(f) for f in dd.PULLS},
    }
    if write:
        write_outputs(model, findings)
    return findings


def _fmt(v):
    if isinstance(v, float):
        return f"{v:.8g}"
    return "" if v is None else v


def write_outputs(model: IOModel, f: dict) -> None:
    with open(os.path.join(HERE, "io_findings_v5.json"), "w", encoding="utf-8") as fh:
        json.dump(f, fh, indent=2, sort_keys=True)
        fh.write("\n")
    rows = model.coefficient_rows()
    with open(os.path.join(HERE, "dk_io_energy_coefficients_v5.csv"), "w",
              encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow({k: _fmt(v) for k, v in r.items()})
    # household COICOP footprint, per construction (domestic technology)
    mC = model.m_C("tot", model.pef_ref, model.dhf)
    with open(os.path.join(HERE, "dk_household_coicop_footprint_v5.csv"), "w",
              encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["coicop", "household_spend_mDKK", "embodied_GJ_W2", "embodied_GJ_A",
                    "embodied_GJ_B", "embodied_GJ_C_at_DK_2023"])
        for code, vec in sorted(model.hh_fd.items()):
            spend = sum(vec)
            if spend <= 0:
                continue
            w.writerow([code, _fmt(spend)] + [_fmt(dot(model.m[c]["tot"], vec))
                                              for c in ("W2", "A", "B")] + [_fmt(dot(mC, vec))])
    sec = f["sectors"]
    with open(os.path.join(HERE, "ube_sector_A_matrix_real.csv"), "w",
              encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["supplying_sector_row"] + SECTORS)
        for s, row in zip(SECTORS, sec["A9"]):
            w.writerow([s] + [f"{v:.6f}" for v in row])
    with open(os.path.join(HERE, "ube_sector_io_summary_v5.csv"), "w",
              encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["sector", "dst_industries", "output_mDKK_2023"]
                   + [f"upstream_ratio_{c}" for c in ("W2", "A", "B", "C")]
                   + ["A_real_column_sum", "A_phase1_column_sum"])
        for i, s in enumerate(SECTORS):
            w.writerow([s, "+".join(SECTOR_MAP[s]), f"{sec['x9'][i]:.6g}"]
                       + [f"{sec['by_construction'][c]['upstream_ratio'][i]:.6g}"
                          for c in ("W2", "A", "B", "C")]
                       + [f"{sec['A9_col_sums'][i]:.6g}", f"{sec['A_phase1_col_sums'][i]:.6g}"])
    hc = f["healthcare"]
    with open(os.path.join(HERE, "healthcare_constructions_v5.csv"), "w",
              encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["construction", "band", "definition", "Fossil_2.5_kWh_cap_yr",
                    "DK_2023_1.6_kWh_cap_yr", "Renewable_1.0_kWh_cap_yr", "is_a_genuine_triple",
                    "energy_basis", "figure_status"])
        defs = {"low": "human health 86000, domestic-only closure",
                "central": "human health 86000, domestic-technology closure",
                "high": "human health 86000 + residential care 87880, domestic-technology closure"}
        keys = {"low": "low_health_domestic_only",
                "central": "central_health_domestic_technology",
                "high": "high_health_plus_care_domestic_technology"}
        for con in ("W2", "A", "B"):
            for band in ("low", "central", "high"):
                v = hc[con][keys[band]]
                w.writerow([con, band, defs[band], "", f"{v:.1f}", "", "no: one number with a "
                            "conversion factor embedded (see the narrative)",
                            "primary, LHV, electricity and heat at the construction's embedded "
                            "factor", "REJECTED as evidence (double counted); ruling stands until "
                            "DJ changes it" if con == "W2" else "PROVISIONAL"])
        for band in ("low", "central", "high"):
            t = hc["C"]["triple"][band]
            w.writerow(["C (ruled R-39)", band, defs[band], f"{t['Fossil_2.5']:.1f}",
                        f"{t['DK_2023_1.6']:.1f}", f"{t['Renewable_1.0']:.1f}", "yes",
                        "primary CED, LHV: fuels as burned + delivered electricity x PEF + "
                        "delivered district heat x 1.08", "PROVISIONAL"])


if __name__ == "__main__":
    f = run()
    hc = f["healthcare"]
    print("Healthcare, kWh/cap/yr (primary, LHV, Denmark 2023)")
    for con in ("W2", "A", "B"):
        h = hc[con]
        print(f"  {con:<3} low {h['low_health_domestic_only']:7.1f}  central "
              f"{h['central_health_domestic_technology']:7.1f}  high "
              f"{h['high_health_plus_care_domestic_technology']:7.1f}   (one number, DK column)")
    for band in ("low", "central", "high"):
        t = hc["C"]["triple"][band]
        print(f"  C   {band:<7} {t['Fossil_2.5']:7.1f} / {t['DK_2023_1.6']:7.1f} / {t['Renewable_1.0']:7.1f}")
    tr = f["truncation"]
    for con in ("W2", "A", "B", "C", "sensitivity_C_validator_electricity_and_heat_only"):
        s = tr[con]["share_by_tier"]
        print(f"  tiers {con[:36]:<36} t0 {s[0]*100:5.1f}%  0-1 {s[1]*100:5.1f}%  0-3 {s[3]*100:5.1f}%"
              f"  B1 {tr[con]['B1']:.3f}  B3 {tr[con]['B3_measured']:.3f}")
    rt = f["regression_tests"]
    print("Regression (a):", rt["a_gross_energy_ENE3H"]["passes"],
          f"A gap {rt['a_gross_energy_ENE3H']['A']['gap_pct']:+.2f}%",
          f"(W2 gap {rt['a_gross_energy_ENE3H']['W2']['gap_pct']:+.1f}%)")
    print("Regression (b):", rt["b_DST_multipliers_ENE2MU1N"]["passes"],
          f"median {rt['b_DST_multipliers_ENE2MU1N']['median_abs_gap_pct']:.2f}%")
    print("Wave 2 reproduction:", rt["wave2_reproduction"]["passes"],
          f"max gap {rt['wave2_reproduction']['max_abs_gap_kWh']:.2e} kWh")
