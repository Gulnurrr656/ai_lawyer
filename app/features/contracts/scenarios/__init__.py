# app/features/contracts/scenarios/__init__.py

from .service import SERVICE_SCENARIO
from .rent import RENT_SCENARIO
from .subcontract import SUBCONTRACT_SCENARIO
from .supply import SUPPLY_SCENARIO
from .manufacture import MANUFACTURE_SCENARIO
from .short_intake import SHORT_SCENARIOS

LEGACY_SCENARIOS = {
    "rent": RENT_SCENARIO,
    "service": SERVICE_SCENARIO,
    "subcontract": SUBCONTRACT_SCENARIO,
    "supply": SUPPLY_SCENARIO,
    "manufacture": MANUFACTURE_SCENARIO,
}

__all__ = [
    "SERVICE_SCENARIO",
    "RENT_SCENARIO",
    "SUBCONTRACT_SCENARIO",
    "SUPPLY_SCENARIO",
    "MANUFACTURE_SCENARIO",
    "SHORT_SCENARIOS",
    "LEGACY_SCENARIOS",
]