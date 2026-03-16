from __future__ import annotations

from typing import Any, Dict, List, Tuple


# =====================================================
# STATEMENTS RAG VERIFIER — CANON-STRICT (ШАГ C)
# =====================================================
# ✅ ТОЛЬКО ДЛЯ ЗАЯВЛЕНИЙ (ГПО / АДМ)
# ✅ НЕ ИСПОЛЬЗУЕТСЯ В ДОГОВОРАХ
# ✅ БЕЗ force_majeure
#
# ЦЕЛЬ:
# - привести rag_payload к канону verified_rag
# - отсеять мусор/фейки/дубликаты
# - не раздувать RAG ради min_articles
# - дать pipeline понятные stats + флаги insufficient/missing
# =====================================================


# Эвристика: минимальная длина текста нормы (чтобы отсеять пустые/обрывки)
_MIN_ARTICLE_TEXT_LEN = 40

# Эвристика: минимальное количество процессуальных норм (ГПК/АППК),
# чтобы заявление в суд было хоть как-то обосновано процессуально.
_DEFAULT_MIN_PROCESSUAL = 6

# Ключевые маркеры для процессуального ядра (без привязки к source_id,
# т.к. в текущем каноне verifier видит source/doc_id как строки).
_PROCESSUAL_SOURCE_MARKERS = (
    "гражданский процессуальный кодекс",
    "гпк",
    "административный процедурно-процессуальный кодекс",
    "аппк",
)

# Эвристика: слова, которые часто встречаются в процессуальных нормах
# (используется только как запасной маркер, если source неочевиден)
_PROCESSUAL_TEXT_MARKERS = (
    "суд",
    "исков",
    "заявлен",
    "подсуд",
    "подведом",
    "доказательств",
    "приложен",
    "госпошлин",
    "срок",
    "рассмотрен",
)

# Недопустимые символы/паттерны в номере статьи (защита от подделок):
# - дефисы/нижние подчёркивания/буквы (150-1, 150_1, 150dup)
# - двойные точки, мусорные хвосты
# Разрешаем: цифры, точки, пробелы, запятые, "п."/"ч."/"ст." и похожее
# (т.к. в некоторых источниках статья может храниться как "150", "150-1" нельзя,
# но "150" + "п.2" можно встречать либо в title/text; в article держим чисто).
_FORBIDDEN_IN_ARTICLE = ("-", "_")


def _is_nonempty_str(x: Any) -> bool:
    return isinstance(x, str) and bool(x.strip())


def _normalize_space(s: str) -> str:
    return " ".join(s.strip().split())


def _looks_like_forged_article_number(article: str) -> bool:
    """
    Жёсткое правило проекта:
    поле article НЕ трогаем и НЕ индексируем.
    Здесь отсекаем очевидные подделки/индексации.
    """
    a = _normalize_space(article).lower()

    # Запрещаем дефисы/подчёркивания (13-7, 150_1)
    if any(ch in a for ch in _FORBIDDEN_IN_ARTICLE):
        return True

    # Запрещаем буквы (150dup, art150, etc.)
    for ch in a:
        if "a" <= ch <= "z" or "а" <= ch <= "я":
            return True

    # Разрешаем цифры, пробелы, точки, запятые
    allowed = set("0123456789 .,")
    if any(ch not in allowed for ch in a):
        return True

    # Пустое/слишком короткое
    digits = [c for c in a if c.isdigit()]
    if not digits:
        return True

    return False


def _is_processual(item: Dict[str, Any], a0: Dict[str, Any]) -> bool:
    """
    Определяем, относится ли норма к процессуальному ядру (ГПК/АППК).
    Приоритет: source/doc_id, запасной вариант: текстовые маркеры.
    """
    source = _normalize_space(str(item.get("source") or "")).lower()
    doc_id = _normalize_space(str(item.get("doc_id") or "")).lower()
    text = _normalize_space(str(a0.get("text") or "")).lower()

    if any(m in source for m in _PROCESSUAL_SOURCE_MARKERS):
        return True
    if any(m in doc_id for m in ("gpk", "appc", "гпк", "аппк")):
        return True

    # Запасной эвристический маркер по тексту (мягкий)
    hit = 0
    for m in _PROCESSUAL_TEXT_MARKERS:
        if m in text:
            hit += 1
            if hit >= 2:
                return True

    return False


def verify_statement_rag(
    rag_payload: List[Dict[str, Any]],
    min_articles: int = 20,
    max_articles: int = 50,
    min_processual: int = _DEFAULT_MIN_PROCESSUAL,
) -> Dict[str, Any]:
    """
    CANON-STRICT verifier для RAG заявлений.

    ВАЖНО:
    - Совместим с build_petition_prompt: source + articles[0].article/text
    - Не подделывает номера статей
    - Режет дубликаты (source, article)
    - Не обнуляет verified_rag из-за min_articles (кроме accepted=0)
    - Выдаёт insufficient/missing для решения pipeline (repair/отказ)
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
        # ---- 1) Форматная проверка канона ----
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

        # ---- 2) Проверка "реальности" номера статьи (анти-фейки) ----
        if _looks_like_forged_article_number(article_num_norm):
            stats["rejected_articles"] += 1
            stats["rejected_bad_article_number"] += 1
            continue

        # ---- 3) Минимальная проверка качества текста ----
        if len(text_norm) < _MIN_ARTICLE_TEXT_LEN:
            stats["rejected_articles"] += 1
            stats["rejected_empty"] += 1
            continue

        # ---- 4) Дедупликация (source, article) ----
        key = (_normalize_space(str(source)).lower(), article_num_norm)
        if key in seen:
            stats["rejected_articles"] += 1
            stats["rejected_duplicates"] += 1
            continue
        seen.add(key)

        # ---- 5) Принятие ----
        verified.append(item)
        stats["accepted_articles"] += 1

        if _is_processual(item, a0):
            stats["processual_count"] += 1

        if len(verified) >= max_articles:
            break

    # ---- 6) Hard fail: вообще нет валидных норм ----
    if stats["accepted_articles"] == 0:
        stats["insufficient"] = True
        stats["missing"] = ["no_valid_articles"]
        stats["error"] = "no_valid_articles"
        return {"verified_rag": [], "stats": stats}

    # ---- 7) Soft fail: не хватает уникальных/минимальных ----
    missing: List[str] = []
    if stats["accepted_articles"] < min_articles:
        missing.append("not_enough_unique_articles")

    if stats["processual_count"] < min_processual:
        missing.append("processual_core")

    if missing:
        stats["insufficient"] = True
        stats["missing"] = missing

    # ВАЖНО: НЕ обнуляем verified_rag, даже если insufficient=True
    return {"verified_rag": verified, "stats": stats}