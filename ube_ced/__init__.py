"""ube-ced: Cumulative Energy Demand of survival goods via Leontief input-output.

Core equation (primary kWh per unit of final demand):

    epsilon = e_d . (I - A)^-1
    CED(f)  = epsilon . f

A      technical coefficients, a_ij = units of i consumed per unit of j produced
e_d    direct primary energy intensity per unit output of each process, kWh
f      final demand vector, physical units
"""
from .core import System, leontief_inverse, ced_vector, ced, spectral_radius, hawkins_simon_ok
from .decompose import tier_decomposition, sector_decomposition
from .io import load_system, load_scenarios
from .basket import Basket, basket_ced
from .montecarlo import monte_carlo

__version__ = "0.1.2"
__all__ = [
    "System", "leontief_inverse", "ced_vector", "ced", "spectral_radius", "hawkins_simon_ok",
    "tier_decomposition", "sector_decomposition", "load_system", "load_scenarios",
    "Basket", "basket_ced", "monte_carlo",
]
