"""Флаги Stage 1 legal intelligence layer (включается без изменения существующих пайплайнов)."""

from __future__ import annotations

import os
import random


def legal_engine_enabled() -> bool:
    """LEGAL_ENGINE=1|true|yes|on — хендлеры могут ветвиться на новый слой; по умолчанию выкл."""
    v = (os.getenv("LEGAL_ENGINE") or "0").strip().lower()
    return v in ("1", "true", "yes", "on")


def legal_engine_telemetry_enabled() -> bool:
    """LEGAL_ENGINE_TELEMETRY=1|true|yes|on — structured run logs (Phase 4A+); по умолчанию выкл."""
    v = (os.getenv("LEGAL_ENGINE_TELEMETRY") or "0").strip().lower()
    return v in ("1", "true", "yes", "on")


def legal_engine_telemetry_trace_id_env() -> str:
    """LEGAL_ENGINE_TELEMETRY_TRACE_ID — внешний correlation id (обрезается); пусто если нет."""
    v = (os.getenv("LEGAL_ENGINE_TELEMETRY_TRACE_ID") or "").strip()
    return v[:128] if v else ""


def legal_engine_telemetry_sample_keep() -> bool:
    """
    LEGAL_ENGINE_TELEMETRY_SAMPLE_RATE — доля прогонов с телеметрией (0.0…1.0), по умолчанию 1.

    При отборе «мимо» maybe_start_legal_run_telemetry вернёт None для всего прогона.
    """
    raw = (os.getenv("LEGAL_ENGINE_TELEMETRY_SAMPLE_RATE") or "1").strip()
    try:
        rate = float(raw)
    except ValueError:
        rate = 1.0
    rate = max(0.0, min(1.0, rate))
    if rate >= 1.0:
        return True
    if rate <= 0.0:
        return False
    return random.random() < rate
