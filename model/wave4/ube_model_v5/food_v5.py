"""
food_v5.py - R-64: the food lines' group amounts from the Danish official dietary guidelines, by age band
======================================================================================================

Only QUANTITIES change.  Every food line keeps its per-kg CED, its electric share, its loss regime and
its band.  The retail node (F_25) follows automatically, because its quantity is the food mass.

SOURCES (all read 19 Sep 2026)
  * DTU Fodevareinstituttet, Lassen, Christensen, Fagt & Trolle (2020), "Rad om baeredygtig sund kost",
    Table 4.2, model 2 ("dansk tilpasset plantebaseret kost"), grams per 10 MJ per day.  Section 4.2.2
    step 6: the model is adapted to small children and older people "by scaling the nutrient content to
    these groups' reference value for energy intake".
  * Fodevarestyrelsen, De officielle Kostrad (2021), amounts poster: 600 g fruit and vegetables, 100 g
    cooked legumes, 90 g whole grain, 30 g nuts a day; at most 350 g meat and 350 g fish a week.
    Dairy by age (as recorded VERIFIED in Till_Unit_Design.md sec 3.1): 250 ml + 5 g cheese at 2-3 years;
    300 ml + 10 g at 4-10; 300-350 ml + 20 g at 11-17; 250 ml + 20 g at 18-70.
  * NNR 2023 energy reference values: "Energy - a scoping review for the Nordic Nutrition
    Recommendations 2023 project", Food & Nutrition Research (PMC10710868), Table 7 (ages 2-17, average
    PAL) and Table 11 (adults, PAL 1.6).
  * Statistics Denmark FOLK1A, 1 July 2023, by single year of age and sex (_dsdata/folk1a_2023K3.csv).

THE RULE (central; a judgement, stated and escalated)
  * Adults (18+): the official adult amounts, which are DTU model 2 at 10 MJ (the poster's 600 g fruit and
    vegetables = model 2's 300 + 300; 250 ml milk + 20 g cheese = model 2's dairy).
  * Children 2-17: model 2 scaled to the band's NNR reference energy (DTU's stated method), except dairy,
    which the poster sets by age.
  * Ages 0-1: model 2 scaled to about 2.6 and 3.6 MJ (ASSUMED from NNR Table 6's kJ/kg at typical weights);
    the guidelines do not apply to infants.
  SENSITIVITY: every age scaled to its NNR reference energy, adults at PAL 1.6 (the Till author's method,
  applied by age band instead of at one assumed level).

MAPPING to basket lines (the Till author's, Till_Unit_Design.md sec 3.5 and 14.2): grains (F_01), salt
(F_24) and the tomato line (F_04) held; vegetables = model 2 vegetables minus the held tomato; red meat,
fish and milk-plus-yoghurt split across their sub-lines in the modelled proportions; "animal fat" to
butter and cream; "vegetable fat" to fats and oils; "added sugar" to sugar; legumes at raw weight (the
basket line's basis, dry or cooked, is not stated in its source: flagged).

THE CLIMATE CRITERION, DECLARED (R-64): the 2021 guidelines are "godt for sundhed og klima"; DTU's
model 2 was built from the EAT-Lancet planetary-health diet.  Adopting them imports a carbon/climate
criterion into the food entitlement.  It does not use CED and does not touch the invariance test.

Run:  python food_v5.py   -> food_findings_v5.json
"""

from __future__ import annotations

import csv
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "food_findings_v5.json")
BASKET = os.path.join(HERE, "basket_denmark_v5.csv")
FOLK = os.path.join(HERE, "_dsdata", "folk1a_2023K3.csv")

MODEL2 = {  # g/day per 10 MJ, DTU 2020 Table 4.2
    "potatoes": 100.0, "vegetables": 300.0, "fruit": 300.0, "milk": 250.0, "cheese": 20.0,
    "red_meat": 19.0, "poultry": 38.0, "eggs": 15.0, "fish": 63.0, "legumes": 40.0,
    "nuts_seeds": 46.0, "vegetable_fat": 25.0, "animal_fat": 4.0, "added_sugar": 23.0,
}
# NNR 2023, Table 7 (average PAL, MJ/d) ages 2-17 boys / girls
NNR_CHILD = {2: (4.43, 4.08), 3: (4.88, 4.55), 4: (5.98, 5.48), 5: (6.22, 5.80), 6: (6.64, 6.19),
             7: (7.04, 6.52), 8: (7.42, 6.88), 9: (7.82, 7.28), 10: (9.08, 8.54), 11: (9.16, 8.57),
             12: (9.78, 9.03), 13: (10.54, 9.48), 14: (11.37, 9.83), 15: (12.18, 10.07),
             16: (12.79, 10.25), 17: (13.24, 10.35)}
# NNR 2023, Table 11 (PAL 1.6, MJ/d) men / women
NNR_ADULT = [((18, 24), 11.8, 9.4), ((25, 50), 11.3, 9.0), ((51, 70), 10.3, 8.3), ((71, 200), 10.1, 8.2)]
INFANT_MJ = {0: 2.6, 1: 3.6}   # ASSUMED from NNR Table 6 kJ/kg at typical weights
DAIRY_POSTER = [((2, 3), 250.0, 5.0), ((4, 10), 300.0, 10.0), ((11, 17), 325.0, 20.0),
                ((18, 200), 250.0, 20.0)]


def energy(age, sex):
    if age <= 1:
        return INFANT_MJ[age]
    if age <= 17:
        return NNR_CHILD[age][0 if sex == "1" else 1]
    for (a0, a1), m, w in NNR_ADULT:
        if a0 <= age <= a1:
            return m if sex == "1" else w


def population():
    pop = []
    for r in csv.DictReader(open(FOLK, encoding="utf-8-sig"), delimiter=";"):
        if r["ALDER"] == "IALT":
            continue
        pop.append((int(r["ALDER"]), r["KØN"], float(r["INDHOLD"])))
    return pop


def per_person(age, sex, rule):
    E = energy(age, sex)
    if rule == "central" and age >= 18:
        s = 1.0
    else:
        s = E / 10.0
    g = {k: v * s for k, v in MODEL2.items()}
    if rule == "central" and age >= 2:
        for (a0, a1), milk, cheese in DAIRY_POSTER:
            if a0 <= age <= a1:
                g["milk"], g["cheese"] = milk, cheese
    return g, E


def group_amounts(rule):
    pop = population()
    P = sum(n for _, _, n in pop)
    tot = {k: 0.0 for k in MODEL2}
    e_mean = 0.0
    eq = 0.0
    for age, sex, n in pop:
        g, E = per_person(age, sex, rule)
        for k in tot:
            tot[k] += g[k] * n
        e_mean += E * n
        eq += (10.0 if (rule == "central" and age >= 18) else E) * n
    return {k: v / P for k, v in tot.items()}, e_mean / P, eq / P, P


def basket_rows():
    return {r["line_id"]: r for r in csv.DictReader(open(BASKET, encoding="utf-8"))}


def line_quantities(g):
    """g: group amounts, g/day per person -> kg/cap/yr for each food line."""
    b = basket_rows()
    q = {lid: float(b[lid]["quantity"]) for lid in b if lid.startswith("F_") and lid != "F_25"}
    kg = lambda gd: gd * 365.0 / 1000.0
    out = dict(q)
    out["F_02"] = kg(g["potatoes"])
    out["F_03"] = kg(g["vegetables"]) - q["F_04"]
    out["F_05"] = kg(g["fruit"])
    out["F_06"] = kg(g["legumes"])
    milk_split = q["F_07"] / (q["F_07"] + q["F_08"])
    out["F_07"] = kg(g["milk"]) * milk_split
    out["F_08"] = kg(g["milk"]) * (1 - milk_split)
    out["F_09"] = kg(g["cheese"])
    out["F_10"] = kg(g["animal_fat"])
    red = ("F_11", "F_12", "F_14")
    rs = sum(q[l] for l in red)
    for l in red:
        out[l] = kg(g["red_meat"]) * q[l] / rs
    out["F_13"] = kg(g["poultry"])
    fish = ("F_15", "F_16", "F_17", "F_18", "F_19")
    fs = sum(q[l] for l in fish)
    for l in fish:
        out[l] = kg(g["fish"]) * q[l] / fs
    out["F_20"] = kg(g["eggs"])
    out["F_21"] = kg(g["vegetable_fat"])
    out["F_22"] = kg(g["added_sugar"])
    out["F_23"] = kg(g["nuts_seeds"])
    return out, q


def run(write=True):
    res = {"_README": ["Written by food_v5.py. kg/cap/yr as eaten. Every figure PROVISIONAL."],
           "model2_g_per_10MJ": MODEL2}
    for rule in ("central", "sensitivity_all_energy_scaled"):
        g, e, eq, P = group_amounts("central" if rule == "central" else "scaled")
        lines, modelled = line_quantities(g)
        res[rule] = {"group_g_per_day": g, "mean_reference_energy_MJ_d": e,
                     "mean_model2_equivalent_MJ_d": eq, "population": P,
                     "line_kg_cap_yr": lines,
                     "food_mass_kg_cap_yr": sum(v for k, v in lines.items() if k not in ("F_04",)) }
        res["modelled_kg_cap_yr"] = modelled
    for lvl in (8.5, 9.0, 10.0):   # the Till author's paired-cost levels, for reproduction
        g = {k: v * lvl / 10.0 for k, v in MODEL2.items()}
        res[f"till_reproduction_{lvl}MJ"] = line_quantities(g)[0]
    res["climate_criterion_declared"] = (
        "The Danish official dietary guidelines (2021) are 'godt for sundhed og klima' and DTU's model 2 "
        "was derived from the EAT-Lancet planetary-health diet: adopting them (R-64) imports a climate "
        "(carbon) criterion into the food entitlement. It is declared here, as R-64 requires. It uses no "
        "CED figure.")
    if write:
        json.dump(res, open(OUT, "w", encoding="utf-8"), indent=2, sort_keys=True)
        open(OUT, "a").write("\n")
    return res


if __name__ == "__main__":
    r = run()
    for rule in ("central", "sensitivity_all_energy_scaled"):
        x = r[rule]
        print(rule, "mean NNR energy %.2f MJ/d, model-2 equivalent %.2f MJ/d, population %.0f"
              % (x["mean_reference_energy_MJ_d"], x["mean_model2_equivalent_MJ_d"], x["population"]))
        print("  groups g/d", {k: round(v, 1) for k, v in x["group_g_per_day"].items()})
    m = r["modelled_kg_cap_yr"]; c = r["central"]["line_kg_cap_yr"]
    for l in sorted(m):
        print(f"  {l}: modelled {m[l]:7.2f} -> central {c[l]:7.2f} kg/cap/yr")
