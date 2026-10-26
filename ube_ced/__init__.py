"""ube-ced core (UBE 101): energy accounting at a fully specified reference condition.

    epsilon = e . (I - A)^-1          external kWh per unit of each process
    CED(f)  = epsilon . f             external kWh per functional unit

The core contains no place, year, grid, fuel mix, averaging rule or convention.
Those are declared by specific models (spec v2, section 6).
"""
from .records import Status, Record, ExternalRecord, BasketItem, ValidationError
from .system import System, Declaration, load_system, load_basket, freeze_hashes
from .solve import Solution, solve
from .stress import stress
from .propagate import propagate
from .scenario import scenario
from .report import build_report, write_report
from .battery import battery
from .conform import conform

from ._version import __version__
__all__ = ["Status", "Record", "ExternalRecord", "BasketItem", "ValidationError",
           "System", "Declaration", "load_system", "load_basket", "freeze_hashes",
           "Solution", "solve", "stress", "propagate", "scenario",
           "build_report", "write_report", "battery", "conform", "__version__"]
