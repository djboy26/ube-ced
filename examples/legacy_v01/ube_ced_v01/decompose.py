"""Where the energy goes: by upstream tier and by originating sector."""
from __future__ import annotations
import numpy as np
from .core import System, leontief_inverse


def tier_decomposition(system: System, f: np.ndarray, max_tier: int = 12, tol: float = 1e-9) -> list[float]:
    """Energy in each term of e_d (I + A + A^2 + ...) f.
    Returns [tier0, tier1, ...] until the term falls below tol or max_tier."""
    f = np.asarray(f, float)
    out, Akf = [], f.copy()
    for _ in range(max_tier + 1):
        term = float(system.e_d @ Akf)
        out.append(term)
        if term < tol and len(out) > 1:
            break
        Akf = system.A @ Akf
    return out


def sector_decomposition(system: System, f: np.ndarray) -> dict[str, float]:
    """CED attributed to the sector where the primary energy actually enters:
    contribution_i = e_d[i] * (L f)[i]. Sums exactly to the total CED."""
    Lf = leontief_inverse(system.A) @ np.asarray(f, float)
    return {name: float(system.e_d[i] * Lf[i]) for i, name in enumerate(system.names)}
