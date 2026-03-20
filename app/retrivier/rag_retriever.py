import json
import os
from typing import List, Dict
from collections import defaultdict


RAG_BASE_PATH = "rag"

# Логические source_id (в коде/индексах) → фактическая папка в rag/
# kz_gpk_code: в корпусе нет отдельной папки; гражданская процедура — kz_pk_code.
_SOURCE_FOLDER_OVERRIDES = {
    "kz_gk_code": "kz_gk__code",
    "kz_tk_code": "kz_tk__code",
    "kz_gpk_code": "kz_pk_code",
}


def _rag_folder_for_source_id(source_id: str) -> str:
    return _SOURCE_FOLDER_OVERRIDES.get(source_id, source_id)


# =====================================================
# ЗАГРУЗКА СТАТЬИ
# =====================================================
def load_article(path: str) -> Dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# =====================================================
# СКАНИРОВАНИЕ ИСТОЧНИКА (КОДЕКС / ЗАКОН / НП ВС)
# =====================================================
def scan_source(source_id: str) -> List[Dict]:
    folder = _rag_folder_for_source_id(source_id)
    source_path = os.path.join(RAG_BASE_PATH, folder)
    articles: List[Dict] = []

    if not os.path.isdir(source_path):
        return articles

    for file in os.listdir(source_path):
        if not file.endswith(".json"):
            continue

        full_path = os.path.join(source_path, file)
        try:
            article = load_article(full_path)

            # 🔒 БЕРЁМ ТОЛЬКО РЕАЛЬНЫЕ СТАТЬИ
            if not isinstance(article, dict):
                continue
            if "articles" not in article:
                continue
            if not article.get("articles"):
                continue

            articles.append(article)
        except Exception:
            continue

    return articles


# =====================================================
# БАЗОВЫЙ РАНКИНГ (УСИЛЕН, НО НЕ ПЕРЕПИСАН)
# =====================================================
def simple_rank(query: str, articles: List[Dict]) -> List[Dict]:
    query = query.lower().strip()
    ranked = []

    if not query:
        return ranked

    for art in articles:
        # 🔒 ЖЁСТКАЯ ЗАЩИТА
        if not isinstance(art, dict):
            continue
        if "articles" not in art:
            continue
        if not art.get("articles"):
            continue

        first = art["articles"][0]
        text = first.get("text")
        if not isinstance(text, str):
            continue

        text_l = text.lower()
        score = sum(1 for word in query.split() if word and word in text_l)

        if score > 0:
            ranked.append((score, art))

    ranked.sort(key=lambda x: x[0], reverse=True)
    return [a for _, a in ranked]


# =====================================================
# 🔥 РАВНОМЕРНОЕ ПОКРЫТИЕ ИСТОЧНИКОВ
# =====================================================
def balance_by_source(articles: List[Dict], min_per_source: int = 3) -> List[Dict]:
    """
    Гарантирует, что из КАЖДОГО источника будет
    минимум N статей (если они есть).
    """
    grouped = defaultdict(list)

    for art in articles:
        src = art.get("source")
        if not isinstance(src, str):
            continue
        grouped[src].append(art)

    balanced: List[Dict] = []
    for _, items in grouped.items():
        balanced.extend(items[:min_per_source])

    return balanced


# =====================================================
# 🔥 СОРТИРОВКА ПО ЮРИДИЧЕСКОЙ СИЛЕ
# =====================================================
def legal_priority_sort(articles: List[Dict]) -> List[Dict]:
    """
    Приоритет:
    1) Кодексы
    2) Нормативные постановления ВС
    3) Законы
    """
    priority_map = {
        "code": 3,
        "np": 2,
        "law": 1,
    }

    def score(art: Dict) -> int:
        doc_type = art.get("doc_type")
        return priority_map.get(doc_type, 0)

    return sorted(articles, key=score, reverse=True)


# =====================================================
# ОСНОВНОЙ RETRIEVE_RAG (СТАБИЛЬНЫЙ)
# =====================================================
def retrieve_rag(
    task_type: str,
    queries: List[str],
    source_ids: List[str],
    min_articles: int = 15
) -> Dict:
    collected: List[Dict] = []

    # 1️⃣ СБОР ПО ВСЕМ ИСТОЧНИКАМ И ЗАПРОСАМ
    for source_id in source_ids:
        articles = scan_source(source_id)
        for q in queries:
            if not q:
                continue
            ranked = simple_rank(q, articles)
            collected.extend(ranked)

    # 2️⃣ ДЕДУП ПО doc_id
    uniq: Dict[str, Dict] = {}
    for art in collected:
        doc_id = art.get("doc_id")
        if not isinstance(doc_id, str):
            continue
        uniq[doc_id] = art

    rag_list = list(uniq.values())

    # 3️⃣ ГАРАНТИЯ, ЧТО ЭТО НЕ "ОДИН ГК"
    balanced = balance_by_source(rag_list, min_per_source=3)
    combined = {a["doc_id"]: a for a in rag_list}
    for a in balanced:
        combined[a["doc_id"]] = a

    rag_list = list(combined.values())

    # 4️⃣ СОРТИРОВКА ПО ЮРИДИЧЕСКОЙ СИЛЕ
    rag_list = legal_priority_sort(rag_list)

    # 5️⃣ КОНТРОЛЬ ПОКРЫТИЯ
    if len(rag_list) < min_articles:
        raise RuntimeError(
            f"RAG coverage failed: found {len(rag_list)} articles, required {min_articles}"
        )

    return {
        "task_type": task_type,
        "rag_context": rag_list,
        "coverage": {
            "unique_articles": len(rag_list),
            "unique_sources": list({a.get("source") for a in rag_list if a.get("source")}),
            "sources_count": {
                s: len([a for a in rag_list if a.get("source") == s])
                for s in {a.get("source") for a in rag_list if a.get("source")}
            }
        }
    }