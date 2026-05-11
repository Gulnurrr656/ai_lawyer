# app/features/contracts/legal_nodes/__init__.py

from __future__ import annotations

from app.features.contracts.legal_nodes.manufacture_v1 import MANUFACTURE_LEGAL_NODES_V1
from app.features.contracts.legal_nodes.rent_v1 import RENT_LEGAL_NODES_V1
from app.features.contracts.legal_nodes.service_v1 import SERVICE_LEGAL_NODES_V1
from app.features.contracts.legal_nodes.subcontract_v1 import SUBCONTRACT_LEGAL_NODES_V1
from app.features.contracts.legal_nodes.supply_v1 import SUPPLY_LEGAL_NODES_V1, LegalNodeV1


def get_legal_nodes_v1(profile_key: str) -> tuple[LegalNodeV1, ...]:
    """Граф узлов v1 для legal assembly; иначе пустой кортеж."""
    pk = (profile_key or "").strip().lower()
    if pk == "supply":
        return SUPPLY_LEGAL_NODES_V1
    if pk == "rent":
        return RENT_LEGAL_NODES_V1
    if pk == "service":
        return SERVICE_LEGAL_NODES_V1
    if pk == "manufacture":
        return MANUFACTURE_LEGAL_NODES_V1
    if pk == "subcontract":
        return SUBCONTRACT_LEGAL_NODES_V1
    return ()
