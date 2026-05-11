# Верификация административного заявления (АППК) — отдельно от claim / ГПО.

from __future__ import annotations

import os
from typing import Any, Dict, List, Tuple

REQUIRED_ADMIN_PETITION_SECTIONS = [
    "ВВОДНАЯ ЧАСТЬ",
    "ФАКТИЧЕСКИЕ ОБСТОЯТЕЛЬСТВА",
    "ПРАВОВАЯ КВАЛИФИКАЦИЯ",
    "ТРЕБОВАНИЯ",
    "ИСПОЛЬЗОВАННЫЕ НОРМЫ ПРАВА",
    "СВОДКА ПО НОРМАМ (ПРИЛОЖЕНИЕ К ЗАЯВЛЕНИЮ)",
]

ADMIN_SECTIONS_REQUIRE_LEGAL_BASIS = [
    "ВВОДНАЯ ЧАСТЬ",
    "ФАКТИЧЕСКИЕ ОБСТОЯТЕЛЬСТВА",
    "ПРАВОВАЯ КВАЛИФИКАЦИЯ",
    "ТРЕБОВАНИЯ",
]

_FORBIDDEN_PHRASES = [
    "по общим принципам",
    "исходя из законодательства в целом",
    "нормы отсутствуют в предоставленном rag",
    "нормы отсутствуют в rag",
    "составлено на основании общих принципов",
    "суд республики казахстан",
    "в суд республики казахстан",
    "адресат: суд республики казахстан",
    "отсутствует прямая норма в verified_rag",
]


def require_admin_evidence_pack(records: List[Dict[str, Any]]) -> None:
    try:
        need = int(os.getenv("ADMIN_PETITION_EVIDENCE_PACK_MIN", "6"))
    except ValueError:
        need = 6
    need = max(4, min(need, 50))
    if not records or len(records) < need:
        raise RuntimeError(
            f"LEGAL EVIDENCE PACK для административного заявления недостаточен: "
            f"записей {len(records or [])}, требуется ≥ {need}."
        )


def _has_all_sections(text: str) -> Tuple[bool, List[str]]:
    missing: List[str] = []
    for sec in REQUIRED_ADMIN_PETITION_SECTIONS:
        if sec not in (text or ""):
            missing.append(sec)
    return len(missing) == 0, missing


def _has_legal_basis_in_key_sections(text: str) -> Tuple[bool, List[str]]:
    src = text or ""
    missing: List[str] = []
    for sec in ADMIN_SECTIONS_REQUIRE_LEGAL_BASIS:
        idx = src.find(sec)
        if idx == -1:
            missing.append(sec)
            continue

        next_idx = None
        for other in REQUIRED_ADMIN_PETITION_SECTIONS:
            if other == sec:
                continue
            j = src.find(other, idx + len(sec))
            if j != -1:
                next_idx = j if next_idx is None else min(next_idx, j)

        block = src[idx:next_idx] if next_idx is not None else src[idx:]
        if "ПРАВОВОЕ ОСНОВАНИЕ" not in block:
            missing.append(sec)

    return len(missing) == 0, missing


def _contains_norm_citations(text: str) -> bool:
    t = (text or "").lower()
    return ("статья" in t) and (("пункт" in t) or ("част" in t) or ("ст." in t))


def _has_forbidden_phrases(text: str) -> List[str]:
    t = (text or "").lower()
    return [p for p in _FORBIDDEN_PHRASES if p in t]


def verify_admin_petition_document(text: str, *, rag_len: int, min_len: int) -> Tuple[bool, str]:
    """Пост-проверка черновика административного заявления (не ГПО)."""
    txt = (text or "").strip()
    if len(txt) < min_len:
        return False, f"Недостаточный объём: {len(txt)} < {min_len}"

    ok_sections, missing_sections = _has_all_sections(txt)
    if not ok_sections:
        return False, f"Нет обязательных разделов: {', '.join(missing_sections)}"

    ok_basis, missing_basis = _has_legal_basis_in_key_sections(txt)
    if not ok_basis:
        return False, f"Нет блока 'ПРАВОВОЕ ОСНОВАНИЕ' в разделах: {', '.join(missing_basis)}"

    if not _contains_norm_citations(txt):
        return False, "Нет явных ссылок на нормы (статья/пункт/часть)"

    if rag_len >= 20:
        forbidden = _has_forbidden_phrases(txt)
        if forbidden:
            return False, f"Запрещённые формулировки при непустом RAG: {', '.join(forbidden)}"

    return True, ""
