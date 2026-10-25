"""Leontief core. Pure numpy. No side effects."""
from __future__ import annotations
from dataclasses import dataclass, field
import numpy as np


@dataclass
class System:
    """A closed set of n processes.

    names : process names, length n
    units : physical unit of each process output, length n
    A     : n x n technical coefficients. A[i, j] = units of i per unit of j. Read by column.
    e_d   : length n. Direct primary energy per unit output of each process, kWh.
    meta  : free-form provenance (source, date, notes). Never used in arithmetic.
    """
    names: list[str]
    units: list[str]
    A: np.ndarray
    e_d: np.ndarray
    meta: dict = field(default_factory=dict)

    def __post_init__(self):
        self.A = np.asarray(self.A, dtype=float)
        self.e_d = np.asarray(self.e_d, dtype=float).reshape(-1)
        n = len(self.names)
        if self.A.shape != (n, n):
            raise ValueError(f"A must be {n}x{n}, got {self.A.shape}")
        if self.e_d.shape != (n,):
            raise ValueError(f"e_d must have length {n}, got {self.e_d.shape}")
        if len(self.units) != n:
            raise ValueError("units length must equal names length")
        if (self.A < 0).any():
            raise ValueError("A has negative coefficients")
        if (self.e_d < 0).any():
            raise ValueError("e_d has negative entries")

    @property
    def n(self) -> int:
        return len(self.names)

    def index(self, name: str) -> int:
        return self.names.index(name)

    def unit_demand(self, name: str, amount: float = 1.0) -> np.ndarray:
        f = np.zeros(self.n)
        f[self.index(name)] = amount
        return f

    def copy(self) -> "System":
        return System(list(self.names), list(self.units), self.A.copy(), self.e_d.copy(), dict(self.meta))

    def with_changes(self, A: dict[tuple[str, str], float] | None = None,
                     e_d: dict[str, float] | None = None) -> "System":
        """Return a modified copy. A keys are (input_name, output_name)."""
        s = self.copy()
        for (i, j), v in (A or {}).items():
            s.A[s.index(i), s.index(j)] = v
        for k, v in (e_d or {}).items():
            s.e_d[s.index(k)] = v
        return s


def spectral_radius(A: np.ndarray) -> float:
    return float(np.max(np.abs(np.linalg.eigvals(np.asarray(A, float)))))


def hawkins_simon_ok(A: np.ndarray) -> bool:
    """Hawkins-Simon: all leading principal minors of (I - A) positive.
    Equivalent, for non-negative A, to rho(A) < 1 and (I - A)^-1 >= 0."""
    M = np.eye(len(A)) - np.asarray(A, float)
    for k in range(1, len(A) + 1):
        if np.linalg.det(M[:k, :k]) <= 0:
            return False
    return True


def leontief_inverse(A: np.ndarray) -> np.ndarray:
    A = np.asarray(A, float)
    if not hawkins_simon_ok(A):
        raise ValueError(f"System is not productive: rho(A) = {spectral_radius(A):.4f} (Hawkins-Simon fails)")
    return np.linalg.inv(np.eye(len(A)) - A)


def ced_vector(system: System) -> np.ndarray:
    """epsilon = e_d . (I - A)^-1. Primary kWh per unit output of each process."""
    return system.e_d @ leontief_inverse(system.A)


def ced(system: System, f: np.ndarray) -> float:
    """Primary kWh for final demand vector f."""
    return float(ced_vector(system) @ np.asarray(f, float))
