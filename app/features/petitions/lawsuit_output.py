# app/features/petitions/lawsuit_output.py
"""Лёгкая пост-обработка текста искового заявления (ветка B petitions)."""

from __future__ import annotations


def finalize_lawsuit_output(text: str) -> str:
    s = (text or "").strip()
    if not s:
        return ""
    while "\n\n\n" in s:
        s = s.replace("\n\n\n", "\n\n")
    lines = [ln.rstrip() for ln in s.splitlines()]
    return "\n".join(lines).strip()
