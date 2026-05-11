"""
Phase C.5: константы для E2E matrix / внешних скриптов (без зависимости от рантайма).

Скрипты могут импортировать списки стадий и сверять фактическую последовательность логов.
"""

from __future__ import annotations

# События «успешного» пути (порядок типичный, не жёсткий контракт)
TELEMETRY_PROGRESS_STAGES: tuple[str, ...] = (
    "pipeline_enter",
    "rag_complete",
    "prompt_ready",
    "llm_complete",
    "verify_complete",
    "pipeline_complete",
)

# Исходы без исключения (Phase C)
TELEMETRY_OUTCOME_STAGES: tuple[str, ...] = (
    "pipeline_aborted",
    "verify_failed",
    "rag_empty",
    "gate_blocked",
    "safe_draft_selected",
    "clarify_selected",
)

# Исключения (Phase B)
TELEMETRY_ERROR_STATUS: str = "error"

# Для матрицы: сценарий × ожидаемые финальные stage (заготовка под Phase C.5)
E2E_MATRIX_FEATURES: tuple[str, ...] = (
    "consult",
    "claims",
    "gpo",
    "admin",
    "contract",
    "bankruptcy",
    "analyze",
)


def telemetry_matrix_manifest() -> dict[str, tuple[str, ...] | str]:
    """Стабильный манифест для скриптов матрицы / CI (без I/O)."""
    return {
        "schema_version": "phase_c_1",
        "features": E2E_MATRIX_FEATURES,
        "progress_stages": TELEMETRY_PROGRESS_STAGES,
        "outcome_stages": TELEMETRY_OUTCOME_STAGES,
    }
