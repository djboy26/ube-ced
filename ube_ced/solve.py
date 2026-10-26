"""C1–C7: the solver, with two implementations that must agree."""
from __future__ import annotations
from dataclasses import dataclass, field
import numpy as np
from .system import System

RECONCILE_TOL = 1e-9      # C7, settled 26 Oct 2026
TIER_RESIDUAL = 1e-9      # C3


class NotProductive(ValueError):
    pass


def hawkins_simon(A: np.ndarray) -> tuple[bool, int]:
    """All leading principal minors of (I - A) positive. Returns (ok, first failing order)."""
    M = np.eye(len(A)) - A
    for k in range(1, len(A) + 1):
        if np.linalg.det(M[:k, :k]) <= 0:
            return False, k
    return True, 0


def spectral_radius(A: np.ndarray) -> float:
    return float(np.max(np.abs(np.linalg.eigvals(A)))) if len(A) else 0.0


def leontief_inverse(A: np.ndarray, names: list[str] | None = None) -> np.ndarray:
    ok, k = hawkins_simon(A)
    if not ok:
        block = names[:k] if names else f"first {k} processes"
        raise NotProductive(f"Hawkins-Simon fails at order {k}: sub-block {block} consumes at least as much as it produces (rho(A)={spectral_radius(A):.4f})")
    return np.linalg.inv(np.eye(len(A)) - A)


def tier_series(A: np.ndarray, e: np.ndarray, f: np.ndarray, residual: float = TIER_RESIDUAL, max_tier: int = 500) -> list[float]:
    """C3: e A^k f for k = 0, 1, ... until the term < residual * running total (and at least 3 tiers)."""
    out, Akf = [], f.astype(float).copy()
    for k in range(max_tier + 1):
        term = float(e @ Akf)
        out.append(term)
        total = sum(out)
        if k >= 2 and total > 0 and term < residual * total:
            break
        Akf = A @ Akf
    return out


@dataclass
class Solution:
    ced: float                                   # kWh external per functional unit (C1)
    epsilon: np.ndarray                          # per unit of each process
    L: np.ndarray                                # (I - A)^-1
    tiers: list[float]                           # C3
    tier_99: int
    tier_999: int
    by_sector: dict[str, float]                  # C4
    by_tag: dict[str, dict[str, float]]          # C5: key -> value -> kWh
    rho: float
    reconciliation_gap: float                    # |inversion - series| / ced
    zero_coefficients: int
    f: np.ndarray = field(repr=False, default=None)

    def check(self):
        if self.ced > 0 and self.reconciliation_gap > RECONCILE_TOL:
            raise RuntimeError(f"C7: inversion and tier series disagree by {self.reconciliation_gap:.3e} > {RECONCILE_TOL}")


def solve(system: System, f: np.ndarray) -> Solution:
    A, e = system.A, system.e
    f = np.asarray(f, float)
    L = leontief_inverse(A, system.processes)
    eps = e @ L
    ced_inv = float(eps @ f)

    tiers = tier_series(A, e, f)
    ced_ser = float(sum(tiers))
    gap = abs(ced_inv - ced_ser) / ced_inv if ced_inv > 0 else abs(ced_inv - ced_ser)

    cum, t99, t999 = 0.0, None, None
    for k, t in enumerate(tiers):
        cum += t
        if t99 is None and ced_ser > 0 and cum >= 0.99 * ced_ser: t99 = k
        if t999 is None and ced_ser > 0 and cum >= 0.999 * ced_ser: t999 = k

    Lf = L @ f
    by_sector = {p: float(e[i] * Lf[i]) for i, p in enumerate(system.processes)}
    by_tag = {}
    for key in system.tag_keys:
        by_tag[key] = {val: float(ev @ Lf) for val, ev in system.e_by_tag(key).items()}

    sol = Solution(ced_inv, eps, L, tiers, t99 if t99 is not None else len(tiers) - 1,
                   t999 if t999 is not None else len(tiers) - 1, by_sector, by_tag,
                   spectral_radius(A), gap, system.zero_count(), f)
    sol.check()
    return sol
