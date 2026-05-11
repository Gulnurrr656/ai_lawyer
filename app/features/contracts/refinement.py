# app/features/contracts/refinement.py
"""
Точка расширения: доработка договора после черновика (Этап 3).

Пока не реализовано. Сессия и хендлеры будут использовать REFINEMENT_SESSION_KEY
и отдельные состояния FSM, не смешиваясь с analyze/consult/claims.
"""

from __future__ import annotations

# Сохранение контекста после первой генерации (черновик + facts + profile).
REFINEMENT_SESSION_KEY = "contract_refinement_draft"

__all__ = ["REFINEMENT_SESSION_KEY"]
