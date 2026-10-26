"""A survival basket is just a final-demand vector with names attached."""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np
from .core import System, ced, ced_vector


@dataclass
class Basket:
    items: dict[str, float]   # process name -> physical units per period

    def vector(self, system: System) -> np.ndarray:
        f = np.zeros(system.n)
        for name, q in self.items.items():
            f[system.index(name)] = q
        return f


def basket_ced(system: System, basket: Basket) -> tuple[float, dict[str, float]]:
    """Total primary kWh for the basket, and the per-item breakdown."""
    eps = ced_vector(system)
    per_item = {name: float(eps[system.index(name)] * q) for name, q in basket.items.items()}
    return float(sum(per_item.values())), per_item
