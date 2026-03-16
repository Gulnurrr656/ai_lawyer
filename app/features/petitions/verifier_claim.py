from __future__ import annotations

from typing import Any, Dict, List, Tuple


# =====================================================
# CLAIMS RAG VERIFIER — CANON-STRICT (ШАГ C / GPO)
# =====================================================
# ✅ ТОЛЬКО ДЛЯ ИСКОВЫХ ЗАЯВЛЕНИЙ (ГПО / ГПК)
# ✅ НЕ ИСПОЛЬЗУЕТСЯ В АДМИНИСТРАТИВНЫХ ЗАЯВЛЕНИЯХ
# ✅ НЕ ИСПОЛЬЗУЕТСЯ В ДОГОВОРАХ
#
# ЦЕЛЬ:
# - привести rag_payload к канону verified_rag
# - отсеять мусор/фейки/дубликаты
# - зафиксировать наличие/отсутствие процессуального ядра ГПК
# - дать pipeline_claim объективную картину правовой почвы
#
# ВАЖНО:
# - verifier НЕ решает судьбу иска
# - verifier НЕ компенсирует отсутствие норм
# - verifier НЕ подменяет судебную оценку
# =====================================================


_MIN_ARTICLE_TEXT_LEN = 40

_DEFAULT_MIN_PROCESSUAL = 6

# Для ИСКОВОГО производства допускается ТОЛЬКО ГПК + смежные процессуальные источники
_PROCESSUAL_SOURCE_MARKERS = (
    "гражданский процессуальный кодекс",
    "гпк",
)

_PROCESSUAL_TEXT_MARKERS = (
    "суд",
    "иск",
    "исков",
    "подсуд",
    "подведом",
    "доказательств",
    "госпошлин",
    "срок",
    "рассмотрен",
    "решен",
)

_FORBIDDEN_IN_ARTICLE = ("-", "_")


def _is_nonempty_str(x: Any) -> bool:
    return isinstance(x, str) and bool(x.strip())


def _normalize_space(s: str) -> str:
    return " ".join(s.strip().split())


def _looks_like_forged_article_number(article: str) -> bool:
    """
    Канон проекта:
    номер статьи — священен.
    Никаких индексов, дефисов, букв.
    """
    a = _normalize_space(article).lower()

    if any(ch in a for ch in _FORBIDDEN_IN_ARTICLE):
        return True

    for ch in a:
        if "a" <= ch <= "z" or "а" <= ch <= "я":
            return True

    allowed = set("0123456789 .,")
    if any(ch not in allowed for ch in a):
        return True

    digits = [c for c in a if c.isdigit()]
    if not digits:
        return True

    return False


def _is_processual(item: Dict[str, Any], a0: Dict[str, Any]) -> bool:
    """
    Проверка процессуального ядра ИСКА.
    АППК и административные источники здесь НЕДОПУСТИМЫ.
    """
    source = _normalize_space(str(item.get("source") or "")).lower()
    doc_id = _normalize_space(str(item.get("doc_id") or "")).lower()
    text = _normalize_space(str(a0.get("text") or "")).lower()

    if any(m in source for m in _PROCESSUAL_SOURCE_MARKERS):
        return True
    if any(m in doc_id for m in ("gpk", "гпк")):
        return True

    hit = 0
    for m in _PROCESSUAL_TEXT_MARKERS:
        if m in text:
            hit += 1
            if hit >= 2:
                return True

    return False


def verify_claim_rag(
    rag_payload: List[Dict[str, Any]],
    min_articles: int = 20,
    max_articles: int = 50,
    min_processual: int = _DEFAULT_MIN_PROCESSUAL,
) -> Dict[str, Any]:
    """
    CANON-STRICT verifier для RAG ИСКОВ (ГПО).

    ПРИНЦИП:
    verifier фиксирует допустимость правовой почвы,
    но НЕ гарантирует судебную защиту.
    """

    rag_payload = rag_payload or []

    stats: Dict[str, Any] = {
        "input_articles": len(rag_payload),
        "accepted_articles": 0,
        "rejected_articles": 0,
        "rejected_empty": 0,
        "rejected_bad_format": 0,
        "rejected_bad_article_number": 0,
        "rejected_no_source": 0,
        "rejected_duplicates": 0,
        "processual_count": 0,
        "insufficient": False,
        "missing": [],
    }

    verified: List[Dict[str, Any]] = []
    seen: set[Tuple[str, str]] = set()

    for item in rag_payload:
        if not isinstance(item, dict):
            stats["rejected_articles"] += 1
            stats["rejected_bad_format"] += 1
            continue

        source = item.get("source")
        if not _is_nonempty_str(source):
            stats["rejected_articles"] += 1
            stats["rejected_no_source"] += 1
            continue

        articles = item.get("articles")
        if not isinstance(articles, list) or not articles:
            stats["rejected_articles"] += 1
            stats["rejected_bad_format"] += 1
            continue

        a0 = articles[0]
        if not isinstance(a0, dict):
            stats["rejected_articles"] += 1
            stats["rejected_bad_format"] += 1
            continue

        article_num = a0.get("article")
        text = a0.get("text")

        if not _is_nonempty_str(article_num) or not _is_nonempty_str(text):
            stats["rejected_articles"] += 1
            stats["rejected_empty"] += 1
            continue

        article_num_norm = _normalize_space(str(article_num))
        text_norm = str(text).strip()

        if _looks_like_forged_article_number(article_num_norm):
            stats["rejected_articles"] += 1
            stats["rejected_bad_article_number"] += 1
            continue

        if len(text_norm) < _MIN_ARTICLE_TEXT_LEN:
            stats["rejected_articles"] += 1
            stats["rejected_empty"] += 1
            continue

        key = (_normalize_space(str(source)).lower(), article_num_norm)
        if key in seen:
            stats["rejected_articles"] += 1
            stats["rejected_duplicates"] += 1
            continue
        seen.add(key)

        verified.append(item)
        stats["accepted_articles"] += 1

        if _is_processual(item, a0):
            stats["processual_count"] += 1

        if len(verified) >= max_articles:
            break

    if stats["accepted_articles"] == 0:
        stats["insufficient"] = True
        stats["missing"] = ["no_valid_articles"]
        stats["error"] = "no_valid_articles"
        return {"verified_rag": [], "stats": stats}

    missing: List[str] = []

    if stats["accepted_articles"] < min_articles:
        missing.append("not_enough_unique_articles")

    if stats["processual_count"] < min_processual:
        missing.append("processual_core")

    if missing:
        stats["insufficient"] = True
        stats["missing"] = missing

    return {"verified_rag": verified, "stats": stats}