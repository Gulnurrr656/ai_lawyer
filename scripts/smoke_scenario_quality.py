#!/usr/bin/env python3
"""Быстрый smoke перед ручным прогоном Telegram: импорты + минимальные вызовы dispatch."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    from app.shared.scenario_quality_dispatch import (
        PostLlmVerifyContext,
        build_repair_user_prompt,
        max_repair_rounds_for_scenario,
        quality_gate_spec,
        run_post_llm_verify,
    )
    from app.shared.scenario_definitions import scenario_definition, all_static_scenario_ids
    from app.shared.scenario_registry import (
        SCENARIO_ANALYZE_DOCUMENT,
        SCENARIO_CONSULT_MEMO,
    )

    assert scenario_definition(SCENARIO_CONSULT_MEMO)
    assert scenario_definition(SCENARIO_ANALYZE_DOCUMENT)
    for sid in all_static_scenario_ids():
        assert quality_gate_spec(sid) is not None

    ok_short, _ = run_post_llm_verify(
        PostLlmVerifyContext(
            scenario_id=SCENARIO_CONSULT_MEMO,
            text="коротко",
            min_output_chars=5000,
        )
    )
    assert ok_short is False

    assert max_repair_rounds_for_scenario(SCENARIO_CONSULT_MEMO) >= 0
    rp = build_repair_user_prompt(
        scenario_id=SCENARIO_CONSULT_MEMO,
        fail_reason="test",
        body="…",
    )
    assert "test" in rp and "ИСПРАВЬ" in rp

    print("smoke_scenario_quality: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
