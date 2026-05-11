"""
Единый declarative binding поверх ScenarioDefinition: одна точка для политики сценария.

Пайплайны по-прежнему вызывают свои функции; здесь — фасад для чтения политики без дублирования констант.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

from app.shared.scenario_definitions import ScenarioDefinition, scenario_definition


@dataclass(frozen=True)
class ScenarioBundle:
    definition: ScenarioDefinition

    @classmethod
    def for_scenario_id(cls, scenario_id: str) -> ScenarioBundle | None:
        d = scenario_definition((scenario_id or "").strip())
        return cls(d) if d else None

    @property
    def scenario_id(self) -> str:
        return self.definition.scenario_id

    @property
    def feature(self) -> str:
        return self.definition.feature

    def verifier_profile_key(self, *, generation_mode: str | None = None) -> str:
        return self.definition.verifier_profile_key(generation_mode=generation_mode)

    def min_output_chars(self) -> int | None:
        return self.definition.min_output_chars

    def repair_focus(self) -> str:
        return self.definition.repair_focus

    def genre_constraints(self) -> Tuple[str, ...]:
        return self.definition.genre_constraints


def scenario_bundle(scenario_id: str) -> ScenarioBundle | None:
    return ScenarioBundle.for_scenario_id(scenario_id)
