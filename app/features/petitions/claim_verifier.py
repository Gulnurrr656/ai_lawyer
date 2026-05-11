# Верификация искового (ГПО) после LLM: секции, якоря фактов, RAG-first pack.

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Tuple

from app.features.petitions.claim_monetary_schema import verify_claim_monetary_model

ClaimFailureSeverity = Literal["hard", "repairable"]


@dataclass(frozen=True)
class ClaimFailure:
    code: str
    message: str
    severity: ClaimFailureSeverity


_FAILURE_SEVERITY: Dict[str, ClaimFailureSeverity] = {
    "min_length": "repairable",
    "sections": "repairable",
    "norm_citations": "repairable",
    "forbidden_phrases": "hard",
    "court_anchor": "repairable",
    "applicant_anchor": "repairable",
    "opponent_anchor": "repairable",
    "monetary": "hard",
}

# Канонические имена для текста ошибки; для каждого — фразы в нормализованном тексте (рёгистр/ё не важны).
# ВВОДНАЯ ЧАСТЬ: отдельная логика — модель часто пишет шапку без заголовка «вводная часть», а с «ИСКОВОЕ ЗАЯВЛЕНИЕ».
_CLAIM_SECTION_SPECS: List[Tuple[str, Tuple[str, ...]]] = [
    ("ВВОДНАЯ ЧАСТЬ", ("вводная часть", "описательная часть")),
    ("ПОДСУДНОСТЬ", ("подсудность",)),
    ("ЦЕНА ИСКА И РАСЧЁТ", ("цена иска и расчет", "ценой иска", "расчет цены иска", "расчёт цены иска")),
    ("ФАКТИЧЕСКИЕ ОБСТОЯТЕЛЬСТВА", ("фактические обстоятельства", "обстоятельства дела")),
    (
        "ПРАВОВАЯ КВАЛИФИКАЦИЯ",
        ("правовая квалификация", "юридическая квалификация", "правовая оценка", "квалификация спора"),
    ),
    ("ДОКАЗАТЕЛЬСТВА", ("доказательства",)),
    (
        "ГОСУДАРСТВЕННАЯ ПОШЛИНА",
        (
            "государственная пошлина",
            "госпошлина",
            "уплате государственной пошлины",
            "размере государствен",
            "размер госпошлины",
            "уплате госпошлины",
        ),
    ),
    ("ТРЕБОВАНИЯ", ("требования", "просительная часть", "прошу:")),
    (
        "ИСПОЛЬЗОВАННЫЕ НОРМЫ ПРАВА",
        (
            "использованные нормы права",
            "перечень норм права",
            "примененные нормы права",
            "применённые нормы права",
            "нормы материального права",
            "применимые нормы",
            "перечень применённых норм",
        ),
    ),
    (
        "ОТЧЁТ ПО ПРИМЕНЕНИЮ ПРАВА",
        (
            "отчет по применению права",
            "отчёт по применению права",
            "отчет о применении норм",
            "применение норм права",
            "сводка по нормам права",
            "✅ применены",
            "не применены",
        ),
    ),
    ("ПРИЛОЖЕНИЯ", ("приложения", "приложение 1", "перечень приложений")),
]

_PARTY_STOPWORDS = frozenset(
    {
        "ооо",
        "тоо",
        "ао",
        "ип",
        "чп",
        "пао",
        "зао",
        "некоммерческое",
        "акционерное",
        "общество",
        "ограниченной",
        "ответственностью",
        "товарищество",
        "дополнительной",
        "г",
        "г.",
        "ул",
        "ул.",
        "пр",
        "пр-т",
        "проспект",
        "д",
        "д.",
        "кв",
        "кв.",
        "область",
        "обл",
        "район",
        "р-н",
        "имени",
        "им.",
        "индивидуальный",
        "предприниматель",
        "бин",
        "иин",
    }
)

_FORBIDDEN_PHRASES = [
    "обращение",
    "административное заявление",
    "обязанности государственного органа",
    "порядок рассмотрения обращений",
    "административное производство",
    "аппк",
    "по общим принципам",
    "исходя из законодательства в целом",
    "нормы отсутствуют в rag",
]


def require_claim_evidence_pack(records: List[Dict[str, Any]]) -> None:
    try:
        need = int(os.getenv("CLAIM_EVIDENCE_PACK_MIN", "10"))
    except ValueError:
        need = 10
    need = max(4, min(need, 60))
    if not records or len(records) < need:
        raise RuntimeError(
            f"LEGAL EVIDENCE PACK для иска недостаточен: записей {len(records or [])}, "
            f"требуется ≥ {need}. Проверьте RAG/retrieve_rag."
        )


def _normalize_ws(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())


def _norm_heading_tokens(s: str) -> str:
    """Для поиска заголовков разделов: регистр + унификация ё/е (текст модели часто «Вводная часть», канон — «ВВОДНАЯ ЧАСТЬ»)."""
    return (s or "").lower().replace("ё", "е")


def _norm_party_compare(s: str) -> str:
    x = _normalize_ws(s).lower().replace("ё", "е")
    for old, new in (("«", '"'), ("»", '"'), ("'", '"')):
        x = x.replace(old, new)
    return x


def _party_anchor_fragments(chunk: str, *, max_slice: int) -> List[str]:
    raw = _normalize_ws(chunk)
    if not raw:
        return []
    low = raw.lower()
    out: List[str] = []
    seen: set[str] = set()

    def add(s: str) -> None:
        s2 = _norm_party_compare(s)
        if len(s2) < 3:
            return
        frag = s2 if len(s2) <= max_slice else s2[:max_slice]
        if frag not in seen:
            seen.add(frag)
            out.append(frag)

    add(raw)
    m = re.search(r"«([^»]{2,200})»", raw)
    if m:
        add(m.group(1))
    for pat in (r"^ооо\s+", r"^тоо\s+", r"^ао\s+", r"^ип\s+", r"^чп\s+"):
        stripped = re.sub(pat, "", low, flags=re.I, count=1)
        if stripped != low:
            add(stripped)
    return out


def _party_significant_tokens(norm_chunk: str) -> List[str]:
    words = re.findall(r"[a-яёa-z]{3,}", norm_chunk)
    return [w for w in words if w not in _PARTY_STOPWORDS]


def _party_anchor_ok(chunk: str, text: str, *, min_len: int, max_slice: int) -> bool:
    """
    Истец/ответчик из интейка редко совпадает посимвольно с тем, как модель пишет шапку
    (ООО «X» vs полное наименование, кавычки «»/" и т.д.).
    """
    raw = _normalize_ws(chunk)
    if len(raw) < min_len:
        return True
    t = _norm_party_compare(text)
    t_nospace = re.sub(r"\s+", "", t)
    for frag in _party_anchor_fragments(raw, max_slice=max_slice):
        if len(frag) >= min_len and frag in t:
            return True
    for m in re.finditer(r"\d{10,14}", re.sub(r"\s+", "", raw.lower())):
        if m.group(0) in t_nospace:
            return True
    norm_full = _norm_party_compare(raw)
    toks = _party_significant_tokens(norm_full)
    if len(toks) >= 2:
        need = max(2, (len(toks) * 2 + 2) // 3)
        hit = sum(1 for w in toks if w in t)
        if hit >= need:
            return True
    if len(toks) == 1 and len(toks[0]) >= 5 and toks[0] in t:
        return True
    return False


def _intro_section_present(full_text: str, t_norm: str) -> bool:
    """
    Вводная часть иска по явному заголовку или по фактической шапке (строки 1–3 типового иска без слова «вводная»).
    """
    if any(p in t_norm for p in ("вводная часть", "описательная часть")):
        return True
    if "1) вводная" in t_norm or "1. вводная" in t_norm:
        return True
    head = _norm_heading_tokens((full_text or "")[:5500])
    if "исковое заявление" in head and "истец" in head and (
        "ответчик" in head or "ответчи" in head
    ):
        return True
    # «В наименование суда … суд», далее реквизиты сторон
    if (
        re.search(r"в\s+[а-яёa-z0-9«»\s,\.\-–—]{8,220}\s+суд", head)
        and "истец" in head
        and ("ответчик" in head or "ответчи" in head)
    ):
        return True
    return False


def _has_all_sections(text: str) -> Tuple[bool, List[str]]:
    t = _norm_heading_tokens(text)
    missing: List[str] = []
    for canonical, phrases in _CLAIM_SECTION_SPECS:
        if canonical == "ВВОДНАЯ ЧАСТЬ":
            if not _intro_section_present(text, t):
                missing.append(canonical)
            continue
        if not any(p in t for p in phrases):
            missing.append(canonical)
    return len(missing) == 0, missing


def _contains_norm_citations(text: str) -> bool:
    """
    Достаточная эвристика «нормы процитированы».
    Раньше требовалось одновременно «статья» и ещё «пункт»/«част»/«ст.» — из‑за этого отваливались
    нормальные тексты только со «статья N ГК РК» или только со «ст. N».
    """
    t = (text or "").lower().replace("ё", "е")
    patterns = [
        r"стать(?:я|и|е|ю|ёй|ею)\s*[№n]?\s*\d+",
        r"ст\.\s*\d+",
        r"ст\.\d+",
        r"\bпункт\s*[№n]?\s*\d+",
        r"\bчасть\s*[№n]?\s*\d+",
        r"\bч\.\s*\d+",
    ]
    if any(re.search(p, t) for p in patterns):
        return True
    # «п. N» рядом с отсылкой к кодексу / статье
    if re.search(r"\bп\.\s*\d+", t) and (
        re.search(r"стать(?:я|и|е|ю|ёй|ею)", t)
        or "ст." in t
        or "гк рк" in t
        or "гпк" in t
        or "нк рк" in t
    ):
        return True
    return False


def _has_forbidden_phrases(text: str) -> List[str]:
    t = (text or "").lower()
    return [p for p in _FORBIDDEN_PHRASES if p in t]


def collect_claim_failures(
    text: str,
    facts: Dict[str, Any],
    *,
    min_len: int,
) -> List[ClaimFailure]:
    """
    Все проверки иска без раннего выхода: нужна классификация hard/repairable и детерминированный repair-pass.
    Порядок в списке: сначала hard, затем repairable (для сообщения пользователю / LLM repair).
    """
    txt = (text or "").strip()
    found: List[ClaimFailure] = []

    def add(code: str, message: str) -> None:
        sev = _FAILURE_SEVERITY.get(code, "repairable")
        found.append(ClaimFailure(code=code, message=message, severity=sev))

    if len(txt) < min_len:
        add("min_length", f"Недостаточный объём: {len(txt)} < {min_len}")

    ok_sections, missing = _has_all_sections(txt)
    if not ok_sections:
        add("sections", f"Отсутствуют обязательные разделы: {', '.join(missing)}")

    if txt and not _contains_norm_citations(txt):
        add(
            "norm_citations",
            "В тексте не найдены оформленные ссылки на нормы (ожидаются форматы вроде: «статья 10», «ст. 10», «пункт 2»).",
        )

    forbidden = _has_forbidden_phrases(txt)
    if forbidden:
        add("forbidden_phrases", f"Обнаружены запрещённые формулировки: {', '.join(forbidden)}")

    addressee = _normalize_ws(str(facts.get("addressee") or ""))
    applicant = _normalize_ws(str(facts.get("applicant") or ""))
    opponent = _normalize_ws(str(facts.get("opponent") or ""))

    if addressee and not _party_anchor_ok(addressee, txt, min_len=10, max_slice=160):
        add(
            "court_anchor",
            "Шапка: наименование суда из фактов пользователя не найдено в тексте иска (нет устойчивого совпадения).",
        )
    if applicant and not _party_anchor_ok(applicant, txt, min_len=12, max_slice=180):
        add(
            "applicant_anchor",
            "Текст иска не содержит достаточного соответствия данным об истце из интейка",
        )
    if opponent and opponent.lower() not in (
        "не указано",
        "не указан",
        "—",
        "-",
    ) and not _party_anchor_ok(opponent, txt, min_len=10, max_slice=140):
        add(
            "opponent_anchor",
            "Текст иска не содержит достаточного соответствия данным об ответчике из интейка",
        )

    ok_amt, amt_reason = verify_claim_monetary_model(txt, facts)
    if not ok_amt and amt_reason:
        add("monetary", amt_reason)

    hard = [f for f in found if f.severity == "hard"]
    soft = [f for f in found if f.severity != "hard"]
    return hard + soft


def claim_has_only_repairable_failures(failures: List[ClaimFailure]) -> bool:
    return bool(failures) and all(f.severity == "repairable" for f in failures)


def genre_repair_eligible(failures: List[ClaimFailure]) -> bool:
    """
    Один genre-repair (АППК / адм-лексика): только если единственные hard — forbidden_phrases.
    Сочетается с любыми repairable (секции, якоря, нормы-регекс и т.д.).
    """
    if not failures:
        return False
    if not any(f.code == "forbidden_phrases" for f in failures):
        return False
    return not any(f.severity == "hard" and f.code != "forbidden_phrases" for f in failures)


def verify_claim_document(
    text: str,
    facts: Dict[str, Any],
    *,
    min_len: int,
) -> Tuple[bool, str]:
    """Детерминированная проверка иска: объём, структура, цитаты, приложения, якоря фактов."""
    failures = collect_claim_failures(text, facts, min_len=min_len)
    if not failures:
        return True, ""
    return False, failures[0].message
