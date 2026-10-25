"""
dst_data.py - the Danmarks Statistik extracts the v4 model reads, and nothing else
=================================================================================

Standard library only.  Every table is read from ``_dsdata/`` beside this file,
so the whole model runs offline.  ``python dst_data.py --refetch`` downloads
fresh copies from the StatBank API with ``urllib`` and records what it got in
``_dsdata/fetch_log.json`` (URL, bytes, SHA-256, time, and the table's own
"last updated" stamp).

The five tables
---------------
NAIO1F    Input-output table, supply by industries, 69 industries, current
          prices, 2023.  Domestic production (P1_BP) and imports (P7AD2121).
          Carried over unchanged from Wave 2.
ENE2HA    Energy account in GJ, detailed, by use (69 industries + households)
          and energy type, 2023.  Carried over unchanged from Wave 2.
ENE3H     Gross energy consumption in GJ, by industry and energy type, 2023.
          DST's own double-count-free total.  NEW in v4: regression test (a).
ENE2MU1N  Direct and indirect use of energy (multipliers), by industry,
          current prices, 2023.  NEW in v4: regression test (b).
ENE2MU2N  Direct and indirect use of energy by final demand, current prices,
          2023.  NEW in v4: used only for a descriptive comparison of the
          household footprint.

A defect in ENE2MU1N, found by the Physics Validator and confirmed here
----------------------------------------------------------------------
In ENE2MU1N the rows for seven industries carry another industry's figures.
The whole block (direct energy, intensity, multiplier) is consistent within
itself, but it sits under the wrong label.  ``derive_ene2mu1n_remap`` finds
the true owner of every label from the data rather than from a hard-coded
list.  The implied output (direct energy / intensity) of each block has to
match exactly one industry's output in NAIO1F.  The result is a permutation
of 68203/68204/68300, 84101/84202 and 85101/85202, and it is the difference
between sorted code order and DST's own display order (``ind69.txt`` lists
68300 before 68203, 84202 before 84101 and 85202 before 85101).  ENE3H and
ENE2HA do NOT have this defect: their values sit under the right labels.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "_dsdata")
YEAR = "2023"
API = "https://api.statbank.dk/v1"

# file name -> (table, query parameters).  The first three are the Wave 2
# pulls, byte-identical to the Wave 2 cache (checked against the live API on
# 19 September 2026).
PULLS = {
    "naio1f_P1_BP_2023.csv": ("NAIO1F", {"TILGANG1": "P1_BP", "TILGANG2": "*",
                                         "ANVENDELSE": "*", "PRISENHED": "V",
                                         "Tid": YEAR}),
    "naio1f_P7AD2121_2023.csv": ("NAIO1F", {"TILGANG1": "P7AD2121", "TILGANG2": "*",
                                            "ANVENDELSE": "*", "PRISENHED": "V",
                                            "Tid": YEAR}),
    "ene2ha_2023.csv": ("ENE2HA", {"ANVEND": "*", "ENERGI1": "*", "Tid": YEAR}),
    "ene3h_2023.csv": ("ENE3H", {"BRANCHE": "*", "ENERGI1": "*", "Tid": YEAR}),
    "ene2mu1n_2023.csv": ("ENE2MU1N", {"BRANCHE": "*", "ENERGI1": "*", "MULT": "*",
                                       "PRISENHED": "V", "Tid": YEAR}),
    "ene2mu2n_2023.csv": ("ENE2MU2N", {"ANVEND1": "*", "ENERGI1": "*", "MULT": "*",
                                       "PRISENHED": "V", "Tid": YEAR}),
}
TABLE_INFO = ["NAIO1F", "ENE2HA", "ENE3H", "ENE2MU1N", "ENE2MU2N"]


# ---------------------------------------------------------------------------
# Retrieval (only with --refetch; the model never touches the network)
# ---------------------------------------------------------------------------

def _get(url: str) -> bytes:
    import urllib.request
    with urllib.request.urlopen(url, timeout=300) as r:
        return r.read()


def fetch_all(only: list | None = None) -> None:
    os.makedirs(DATA, exist_ok=True)
    log_path = os.path.join(DATA, "fetch_log.json")
    log = {}
    if os.path.exists(log_path):
        with open(log_path, encoding="utf-8") as fh:
            log = json.load(fh)
    stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    for table in TABLE_INFO:
        url = f"{API}/tableinfo/{table}?lang=en&format=JSON"
        body = _get(url)
        with open(os.path.join(DATA, f"info_{table}.json"), "wb") as fh:
            fh.write(body)
        log.setdefault("tableinfo", {})[table] = {
            "url": url, "retrieved_utc": stamp,
            "table_updated": json.loads(body.decode("utf-8")).get("updated")}
    for fname, (table, params) in PULLS.items():
        if only and fname not in only:
            continue
        q = "&".join(f"{k}={v}" for k, v in params.items())
        url = f"{API}/data/{table}/CSV?lang=en&valuePresentation=Code&{q}"
        body = _get(url)
        with open(os.path.join(DATA, fname), "wb") as fh:
            fh.write(body)
        log.setdefault("extracts", {})[fname] = {
            "table": table, "url": url, "retrieved_utc": stamp,
            "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest()}
        print(f"  fetched {fname} ({len(body):,} bytes)")
    with open(log_path, "w", encoding="utf-8") as fh:
        json.dump(log, fh, indent=2, sort_keys=True)
        fh.write("\n")


def _need(fname: str) -> str:
    path = os.path.join(DATA, fname)
    if not os.path.exists(path):
        raise SystemExit(f"Missing cached extract {path}. Run: python dst_data.py --refetch")
    return path


def _rows(fname: str):
    with open(_need(fname), encoding="utf-8-sig", newline="") as fh:
        rd = csv.reader(fh, delimiter=";")
        header = next(rd)
        for r in rd:
            if r:
                yield dict(zip(header, r))


def sha256_of(fname: str) -> str:
    with open(_need(fname), "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

_IND = re.compile(r"T\d{5}")
_USE = re.compile(r"A\d{5}")
_COICOP = re.compile(r"ACP\d{4}")


def load_io() -> dict:
    """
    The 69-industry input-output table, exactly as Wave 2's dst_io_prepare.py
    read it: codes sorted; Z[i][j] = product of industry i used by industry j
    (million DKK); x_j = domestic output of j (row total, 'Total use'); and
    household final consumption by COICOP class, by supplying industry.
    """
    dom = list(_rows("naio1f_P1_BP_2023.csv"))
    imp = list(_rows("naio1f_P7AD2121_2023.csv"))
    codes = sorted({r["TILGANG2"][1:] for r in dom if _IND.fullmatch(r["TILGANG2"])})
    n = len(codes)
    idx = {c: k for k, c in enumerate(codes)}

    def matrix(rows):
        M = [[0.0] * n for _ in range(n)]
        for r in rows:
            s, u = r["TILGANG2"], r["ANVENDELSE"]
            if _IND.fullmatch(s) and _USE.fullmatch(u):
                M[idx[s[1:]]][idx[u[1:]]] = float(r["INDHOLD"])
        return M

    Z_dom = matrix(dom)
    Z_imp = matrix(imp)
    x = [0.0] * n
    for r in dom:
        if r["ANVENDELSE"] == "AA00000" and _IND.fullmatch(r["TILGANG2"]):
            x[idx[r["TILGANG2"][1:]]] = float(r["INDHOLD"])

    hh_tot, hh_dom = {}, {}
    for rows, is_dom in ((dom, True), (imp, False)):
        for r in rows:
            s, u = r["TILGANG2"], r["ANVENDELSE"]
            if _COICOP.fullmatch(u) and _IND.fullmatch(s):
                v = hh_tot.setdefault(u, [0.0] * n)
                v[idx[s[1:]]] += float(r["INDHOLD"])
                if is_dom:
                    w = hh_dom.setdefault(u, [0.0] * n)
                    w[idx[s[1:]]] += float(r["INDHOLD"])
    return {"codes": codes, "idx": idx, "x": x, "Z_dom": Z_dom, "Z_imp": Z_imp,
            "hh_fd": hh_tot, "hh_fd_dom": hh_dom}


def _numeric_table(fname: str, keys: tuple) -> dict:
    out = {}
    for r in _rows(fname):
        try:
            out[tuple(r[k] for k in keys)] = float(r["INDHOLD"])
        except (TypeError, ValueError):
            pass
    return out


def load_ene2ha() -> dict:
    """(use, energy type) -> GJ.  Use codes: 'V01000' ... , 'EHUSHOLD', 'EV', ..."""
    return _numeric_table("ene2ha_2023.csv", ("ANVEND", "ENERGI1"))


def load_ene3h() -> dict:
    """(industry, energy type) -> GJ of gross energy consumption."""
    return _numeric_table("ene3h_2023.csv", ("BRANCHE", "ENERGI1"))


def load_ene2mu1n() -> dict:
    """(industry label, energy type, MULT) -> value, labels AS PUBLISHED."""
    return _numeric_table("ene2mu1n_2023.csv", ("BRANCHE", "ENERGI1", "MULT"))


def load_ene2mu2n() -> dict:
    return _numeric_table("ene2mu2n_2023.csv", ("ANVEND1", "ENERGI1", "MULT"))


def derive_ene2mu1n_remap(mu: dict, codes: list, x: list, tol: float = 0.005) -> dict:
    """
    For every industry label in ENE2MU1N, find the industry whose NAIO1F output
    equals the block's implied output (ENEDIR / ENEINT for total energy).
    Returns {published label: true industry}.  Raises if the answer is not a
    permutation.  Industries with no energy (ENEINT = 0) keep their label.
    """
    remap = {}
    for c in codes:
        ed = mu.get(("V" + c, "ETOT", "ENEDIR"), 0.0)
        ei = mu.get(("V" + c, "ETOT", "ENEINT"), 0.0)
        if ei <= 0:
            remap[c] = c
            continue
        implied = ed / ei
        # closest output; ENEINT is published to 3 decimals, so the implied
        # output carries a small rounding error and two industries can sit
        # within 0.5% of each other.  The closest match must be within tol,
        # and the whole mapping must come out as a permutation (checked below).
        gap, best = min((abs(implied / xk - 1.0), k) for k, xk in zip(codes, x) if xk > 0)
        if gap > tol:
            raise ValueError(f"ENE2MU1N label {c}: implied output {implied:.0f} matches no industry")
        remap[c] = best
    if sorted(remap.values()) != sorted(codes):
        raise ValueError("ENE2MU1N label remap is not a permutation")
    return remap


if __name__ == "__main__":
    if "--refetch" in sys.argv:
        print("Fetching from the Danmarks Statistik StatBank API ...")
        fetch_all()
    io = load_io()
    print(f"NAIO1F: {len(io['codes'])} industries, total output "
          f"{sum(io['x']):,.0f} m DKK, {len(io['hh_fd'])} household COICOP classes")
    for f in ("ene2ha_2023.csv", "ene3h_2023.csv", "ene2mu1n_2023.csv", "ene2mu2n_2023.csv"):
        print(f"{f}: sha256 {sha256_of(f)[:16]}...")
