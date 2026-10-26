"""Propagate input uncertainty through the inverse. Each coefficient gets an
independent triangular or uniform distribution; correlation is not modelled."""
from __future__ import annotations
import numpy as np
from .core import System, ced, hawkins_simon_ok


def monte_carlo(system: System, f: np.ndarray, spread: float = 0.25, n: int = 20_000,
                seed: int | None = 0, dist: str = "triangular") -> dict:
    """spread: fractional half-width around each nonzero A and e_d entry.
    Returns median, mean, p05, p95, and the accepted sample count."""
    rng = np.random.default_rng(seed)
    f = np.asarray(f, float)
    samples = []
    for _ in range(n):
        s = system.copy()
        if dist == "triangular":
            kA = rng.triangular(1 - spread, 1.0, 1 + spread, size=s.A.shape)
            ke = rng.triangular(1 - spread, 1.0, 1 + spread, size=s.e_d.shape)
        else:
            kA = rng.uniform(1 - spread, 1 + spread, size=s.A.shape)
            ke = rng.uniform(1 - spread, 1 + spread, size=s.e_d.shape)
        s.A = s.A * kA
        s.e_d = s.e_d * ke
        if not hawkins_simon_ok(s.A):
            continue
        samples.append(ced(s, f))
    x = np.asarray(samples)
    return {
        "n_accepted": int(len(x)),
        "median": float(np.median(x)),
        "mean": float(x.mean()),
        "p05": float(np.percentile(x, 5)),
        "p95": float(np.percentile(x, 95)),
    }
