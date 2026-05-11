#!/usr/bin/env python3
"""
Phase C.5: заготовка для внешнего E2E matrix — импорт констант без запуска бота.

Пример:
  python scripts/e2e_telemetry_matrix_stub.py
"""

from __future__ import annotations

from app.shared.legal_engine.telemetry_e2e import (
    E2E_MATRIX_FEATURES,
    TELEMETRY_OUTCOME_STAGES,
    TELEMETRY_PROGRESS_STAGES,
)


def main() -> None:
    print("features:", ", ".join(E2E_MATRIX_FEATURES))
    print("progress_stages:", len(TELEMETRY_PROGRESS_STAGES))
    print("outcome_stages:", len(TELEMETRY_OUTCOME_STAGES))


if __name__ == "__main__":
    main()
