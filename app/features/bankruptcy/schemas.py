from dataclasses import dataclass
from typing import Literal


# Уровень риска для жёсткого стоп-гейта (уголовные / фиктивные маркеры)
RiskLevel = Literal["low", "medium", "high"]

RouteDecision = Literal["bankruptcy_allowed", "bankruptcy_blocked"]


@dataclass
class BankruptcyAssessment:
    risk_level: RiskLevel
    decision: RouteDecision
    reasons: list[str]
    notes: str
