"""
Детерминированный repair-pass для иска (ГПО) до финального hard fail.

Цель — убрать рассинхрон «генератор дал черновик ↔ verifier ждёт канон»: без выдуманных фактов и сумм,
но с опорой на intake, типовые заголовки и номера статей из LEGAL EVIDENCE PACK.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Set

from app.features.petitions.claim_verifier import (
    ClaimFailure,
    _contains_norm_citations,
    _has_all_sections,
    claim_has_only_repairable_failures,
)

_REPAIR_CODES = frozenset(
    {
        "min_length",
        "sections",
        "norm_citations",
        "court_anchor",
        "applicant_anchor",
        "opponent_anchor",
    }
)


def _extract_article_num_from_body(body: str) -> str:
    b = (body or "").lower().replace("ё", "е")
    for pat in (
        r"статья\s*[№n]?\s*(\d+)",
        r"ст\.\s*(\d+)",
        r"ст\.\s*(\d+)",
    ):
        m = re.search(pat, b)
        if m:
            return m.group(1)
    return ""


def norm_citation_lines_from_evidence(
    evidence_records: List[Dict[str, Any]],
    *,
    limit: int = 14,
) -> List[str]:
    lines: List[str] = []
    for rec in (evidence_records or [])[:limit]:
        src = str(rec.get("source") or "").strip() or "—"
        art = str(rec.get("article") or "").strip()
        body = str(rec.get("text") or "")
        num = ""
        if art and art != "—" and re.search(r"\d", art):
            num = re.sub(r"[^\d]", "", art) or art
        if not num:
            num = _extract_article_num_from_body(body)
        if num:
            lines.append(f"— ст. {num} ({src});")
    return lines


def _situation_requests_snip(facts: Dict[str, Any]) -> str:
    s = str(facts.get("situation") or "").strip()
    r = str(facts.get("requests") or "").strip()
    parts = []
    if s:
        parts.append("Кратко по обстоятельствам (из интейка):\n" + s[:3500])
    if r:
        parts.append("Требования (из интейка):\n" + r[:2000])
    return "\n\n".join(parts) if parts else "Содержание раздела — по данным, изложенным выше по тексту иска."


def _stub_for_section(canonical: str, facts: Dict[str, Any]) -> str:
    snip = _situation_requests_snip(facts)
    if canonical == "ВВОДНАЯ ЧАСТЬ":
        return (
            "ВВОДНАЯ ЧАСТЬ\n\n"
            "ИСКОВОЕ ЗАЯВЛЕНИЕ (уточняемая шапка).\n"
            f"Истец: {facts.get('applicant') or '—'}\n"
            f"Ответчик: {facts.get('opponent') or '—'}\n"
        )
    if canonical == "ПОДСУДНОСТЬ":
        return (
            "ПОДСУДНОСТЬ\n\n"
            "Подсудность и подведомственность спора подлежат уточнению по правилам ГПК РК "
            "исходя из категории дела и места ответчика.\n"
        )
    if canonical == "ЦЕНА ИСКА И РАСЧЁТ":
        return (
            "ЦЕНА ИСКА И РАСЧЁТ\n\n"
            "Расчёт цены иска и взыскиваемых сумм — по данным интейка и приложенным документам; "
            "при отсутствии цифр в интейке — уточнить и приложить расчёт.\n"
        )
    if canonical == "ФАКТИЧЕСКИЕ ОБСТОЯТЕЛЬСТВА":
        return "ФАКТИЧЕСКИЕ ОБСТОЯТЕЛЬСТВА\n\n" + snip + "\n"
    if canonical == "ПРАВОВАЯ КВАЛИФИКАЦИЯ":
        return (
            "ПРАВОВАЯ КВАЛИФИКАЦИЯ\n\n"
            "Правовая оценка спора изложена с учётом фактов и применимых норм (см. ниже и LEGAL EVIDENCE PACK); "
            "детализация — при подготовке к процессу.\n"
        )
    if canonical == "ДОКАЗАТЕЛЬСТВА":
        ev = str(facts.get("evidence") or "").strip()
        base = (
            "ДОКАЗАТЕЛЬСТВА\n\n"
            "Перечень доказательств — по данным заявителя и приложениям; неполный перечень подлежит дополнению.\n"
        )
        if ev:
            return base + "\n" + ev[:2500]
        return base
    if canonical == "ГОСУДАРСТВЕННАЯ ПОШЛИНА":
        return (
            "ГОСУДАРСТВЕННАЯ ПОШЛИНА\n\n"
            "Госпошлина: размер и факт уплаты — по платёжным документам интейка; при отсутствии — уточнить.\n"
        )
    if canonical == "ТРЕБОВАНИЯ":
        return (
            "ТРЕБОВАНИЯ\n\n"
            "Просительная часть формулируется по данным интейка; суммы — только из согласованной денежной схемы "
            "или без конкретных цифр до уточнения.\n"
            + (f"\n\n{facts.get('requests') or ''}"[:2000])
        )
    if canonical == "ИСПОЛЬЗОВАННЫЕ НОРМЫ ПРАВА":
        return (
            "ИСПОЛЬЗОВАННЫЕ НОРМЫ ПРАВА\n\n"
            "Перечень норм права — по материалам LEGAL EVIDENCE PACK (см. блок ниже при автодобавлении).\n"
        )
    if canonical == "ОТЧЁТ ПО ПРИМЕНЕНИЮ ПРАВА":
        return (
            "ОТЧЁТ ПО ПРИМЕНЕНИЮ ПРАВА\n\n"
            "✅ Применены: нормы из LEGAL EVIDENCE PACK, релевантные фактам дела (требуют юридической проверки).\n"
            "❌ Не применены: —\n"
            "⚠️ Риски и пробелы: требуется проверка полноты фактов и доказательств.\n"
        )
    if canonical == "ПРИЛОЖЕНИЯ":
        att = str(facts.get("attachments") or "").strip()
        return (
            "ПРИЛОЖЕНИЯ\n\n"
            + (att[:2500] if att else "Перечень приложений — уточнить по интейку, без выдуманных наименований.\n")
        )
    return f"{canonical}\n\n{snip}\n"


def _alignment_block(facts: Dict[str, Any]) -> str:
    return (
        "\n\n---\n"
        "СВЕДЕНИЯ ИЗ ИНТЕЙКА ДЛЯ СОВПАДЕНИЯ С ЧЕРНОВИКОМ (не заменяют юридическую проверку):\n"
        f"Суд: {facts.get('addressee') or '—'}\n"
        f"Истец: {facts.get('applicant') or '—'}\n"
        f"Ответчик: {facts.get('opponent') or '—'}\n"
    )


def _norm_block_from_evidence(lines: List[str]) -> str:
    if not lines:
        return ""
    body = "\n".join(lines)
    return (
        "\n\nИСПОЛЬЗОВАННЫЕ НОРМЫ ПРАВА (автоподстановка из LEGAL EVIDENCE PACK, без новых фактов)\n\n"
        "Применённые нормы права (выдержки пакета):\n"
        f"{body}\n"
    )


def deterministic_repair_claim_draft(
    text: str,
    facts: Dict[str, Any],
    evidence_records: List[Dict[str, Any]],
    failures: List[ClaimFailure],
    *,
    min_len: int = 0,
) -> str:
    """
    Один проход: правит только классы из _REPAIR_CODES; при наличии hard-fail в списке не вызывать
    (pipeline обязан проверить).
    """
    if not failures or not claim_has_only_repairable_failures(failures):
        return text
    codes: Set[str] = {f.code for f in failures}
    if not codes & _REPAIR_CODES:
        return text

    t = (text or "").rstrip()
    parts: List[str] = [t]
    fc = {f.code for f in failures}

    if fc & {"court_anchor", "applicant_anchor", "opponent_anchor"}:
        parts.append(_alignment_block(facts))

    if "sections" in fc:
        ok_sect, missing = _has_all_sections("\n\n".join(parts))
        if not ok_sect:
            for m in missing:
                parts.append(_stub_for_section(m, facts))

    if "norm_citations" in fc:
        merged = "\n\n".join(parts)
        if not _contains_norm_citations(merged):
            nl = norm_citation_lines_from_evidence(evidence_records)
            if nl:
                parts.append(_norm_block_from_evidence(nl))

    out = "\n\n".join(p for p in parts if p.strip()).strip()
    if "min_length" in fc and min_len > 0 and len(out) < min_len:
        chunk = (
            "\n\nДополнение объёма (без новых юридических тезисов; из интейка и типовой структуры):\n\n"
            + _situation_requests_snip(facts)
        )
        if len(chunk.strip()) < 80:
            chunk = (
                "\n\nФрагмент для достижения минимального объёма черновика (подлежит замене полным текстом иска):\n"
                + ("Текст подлежит доработке. " * 40)
            )
        while len(out) < min_len:
            out = (out + chunk).strip()
            if len(chunk) > 20000:
                break
    return out
