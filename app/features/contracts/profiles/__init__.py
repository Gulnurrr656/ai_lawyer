# app/features/contracts/profiles/__init__.py

from .rent import get_rent_profile
from .service import get_service_profile
from .subcontract import get_subcontract_profile
from .supply import get_supply_profile
from .manufacture import get_manufacture_profile


def get_contract_profile(profile_key: str):
    """
    КАНОН:
    - profiles — это ТОЛЬКО юридические профили
    - никакой FSM
    - никакие scenario сюда не импортируются
    """
    if profile_key == "rent":
        return get_rent_profile()
    if profile_key == "service":
        return get_service_profile()
    if profile_key == "subcontract":
        return get_subcontract_profile()
    if profile_key == "supply":
        return get_supply_profile()
    if profile_key == "manufacture":
        return get_manufacture_profile()

    raise ValueError(f"Unknown contract profile: {profile_key}")


__all__ = [
    "get_contract_profile",
    "get_rent_profile",
    "get_service_profile",
    "get_subcontract_profile",
    "get_supply_profile",
    "get_manufacture_profile",
]