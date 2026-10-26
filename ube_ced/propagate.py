"""C9: sample every record triangularly between low/value/high, re-solve per draw, report numbers."""
from __future__ import annotations
import numpy as np
from .system import System
from .records import BasketItem
from .solve import leontief_inverse, hawkins_simon

DRAW_FLOOR = 10_000   # settled 26 Oct 2026: below this the 5th/95th percentiles are not stable
DRAW_FLOOR_REASON = ("10,000 draws is the floor because the 5th and 95th percentiles of a sum of ~10-100 "
                     "triangular variables move by less than 1% of the interval width between independent "
                     "runs at that size; below it they do not.")


def _tri(rng, lo, mode, hi, size=None):
    if lo == hi:
        return np.full(size, mode) if size else mode
    return rng.triangular(lo, mode, hi, size=size)


def propagate(system: System, f: np.ndarray, basket: list[BasketItem] | None = None,
              draws: int = DRAW_FLOOR, seed: int = 0) -> dict:
    if draws < DRAW_FLOOR:
        raise ValueError(f"draws={draws} below floor {DRAW_FLOOR}. {DRAW_FLOOR_REASON}")
    rng = np.random.default_rng(seed)
    n = system.n
    idx = {p: i for i, p in enumerate(system.processes)}

    # correlation groups: a record key may be assigned to a group; all members share one uniform quantile per draw
    key_of_rec = {}
    for g, members in system.correlation_groups.items():
        for m in members:
            key_of_rec[str(m)] = g
    groups = sorted(set(key_of_rec.values()))
    gidx = {g: i for i, g in enumerate(groups)}

    rec_keys = [f"{r.input}->{r.output}" for r in system.records]
    ext_keys = [f"EXTERNAL->{x.process}" + (f"#{x.tags}" if x.tags else "") for x in system.external]

    # quantiles: independent u per record, or shared u per group
    U_ind_r = rng.uniform(size=(draws, len(system.records)))
    U_ind_e = rng.uniform(size=(draws, len(system.external)))
    U_grp = rng.uniform(size=(draws, max(1, len(groups))))

    def tri_q(u, lo, mode, hi):
        if hi == lo:
            return np.full_like(u, mode)
        c = (mode - lo) / (hi - lo)
        out = np.where(u < c, lo + np.sqrt(u * (hi - lo) * (mode - lo)), hi - np.sqrt((1 - u) * (hi - lo) * (hi - mode)))
        return out

    Rv = np.zeros((draws, len(system.records)))
    for j, r in enumerate(system.records):
        u = U_grp[:, gidx[key_of_rec[rec_keys[j]]]] if rec_keys[j] in key_of_rec else U_ind_r[:, j]
        Rv[:, j] = tri_q(u, r.low, r.value, r.high) if r.distribution == "triangular" else r.value
    Ev = np.zeros((draws, len(system.external)))
    for j, x in enumerate(system.external):
        u = U_grp[:, gidx[key_of_rec[ext_keys[j]]]] if ext_keys[j] in key_of_rec else U_ind_e[:, j]
        Ev[:, j] = tri_q(u, x.low, x.value, x.high) if x.distribution == "triangular" else x.value
    Fv = None
    if basket:
        Fv = np.zeros((draws, len(basket)))
        Ub = rng.uniform(size=(draws, len(basket)))
        for j, b in enumerate(basket):
            Fv[:, j] = tri_q(Ub[:, j], b.low, b.quantity, b.high) if b.distribution == "triangular" else b.quantity

    out, rejected = np.empty(draws), 0
    for d in range(draws):
        A = np.zeros((n, n)); e = np.zeros(n)
        for j, r in enumerate(system.records):
            A[idx[r.input], idx[r.output]] += Rv[d, j]
        for j, x in enumerate(system.external):
            e[idx[x.process]] += Ev[d, j]
        ok, _ = hawkins_simon(A)
        if not ok:
            rejected += 1; out[d] = np.nan; continue
        L = np.linalg.inv(np.eye(n) - A)
        fd = f
        if Fv is not None:
            fd = np.zeros(n)
            for j, b in enumerate(basket):
                fd[idx[b.process]] += Fv[d, j]
        out[d] = (e @ L) @ fd
    x = out[~np.isnan(out)]
    return {"draws": draws, "draw_floor": DRAW_FLOOR, "draw_floor_reason": DRAW_FLOOR_REASON, "seed": seed,
            "rejected": rejected, "median": float(np.median(x)), "mean": float(x.mean()),
            "p05": float(np.percentile(x, 5)), "p95": float(np.percentile(x, 95)),
            "correlation_groups": groups, "samples": x}
