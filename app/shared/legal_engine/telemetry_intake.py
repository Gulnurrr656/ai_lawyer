"""Короткие вызовы телеметрии из хендлеров (intake / policy), без PII."""

from __future__ import annotations

from app.shared.legal_engine.run_record import (
    FeatureKey,
    log_legal_run_outcome,
    maybe_start_legal_run_telemetry,
)


def emit_telemetry_pipeline_aborted(
    *, scenario_id: str, feature: FeatureKey, outcome_code: str
) -> None:
    """Зарезервировано для ранних выходов без отдельной стадии (матрица E2E)."""
    rec = maybe_start_legal_run_telemetry(scenario_id=scenario_id, feature=feature)
    log_legal_run_outcome(
        rec,
        stage="pipeline_aborted",
        status="aborted",
        outcome_code=outcome_code,
    )


def emit_telemetry_gate_blocked(*, scenario_id: str, feature: FeatureKey, outcome_code: str) -> None:
    rec = maybe_start_legal_run_telemetry(scenario_id=scenario_id, feature=feature)
    log_legal_run_outcome(
        rec,
        stage="gate_blocked",
        status="aborted",
        outcome_code=outcome_code,
    )


def emit_telemetry_clarify_selected(
    *, scenario_id: str, feature: FeatureKey, clarify_depth: int
) -> None:
    rec = maybe_start_legal_run_telemetry(scenario_id=scenario_id, feature=feature)
    log_legal_run_outcome(
        rec,
        stage="clarify_selected",
        status="selected",
        outcome_code="clarify_queue",
        clarify_depth=clarify_depth,
    )


def emit_telemetry_safe_draft_selected(*, scenario_id: str, feature: FeatureKey) -> None:
    rec = maybe_start_legal_run_telemetry(scenario_id=scenario_id, feature=feature)
    log_legal_run_outcome(
        rec,
        stage="safe_draft_selected",
        status="selected",
        outcome_code="safe_draft",
    )
