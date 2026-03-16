from typing import Literal, Dict, Any
from dataclasses import dataclass


RiskLevel = Literal["safe", "borderline", "criminal_risk"]
RouteDecision = Literal["bankruptcy_allowed", "bankruptcy_not_allowed"]


@dataclass
class BankruptcyAssessment:
    risk_level: RiskLevel
    decision: RouteDecision
    reasons: list[str]
    notes: str