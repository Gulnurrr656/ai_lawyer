from typing import Dict, List, Optional


# === КАРТА БЛОКОВ (ОБЩАЯ, БЕЗ ЖЁСТКИХ ТРЕБОВАНИЙ) ===
BLOCK_KEYWORDS = {
    "subject": ["предмет", "оказание услуг", "обязанности"],
    "term": ["срок", "сроки", "исполнение"],
    "liability": ["ответственность", "убытки", "неустойка", "штраф"],
    "jurisdiction": ["подсудность", "суд", "юрисдикция"],
    "force_majeure": ["форс-мажор", "непреодолимая сила"],
    "tax": ["ндс", "налог", "налогообложение"],
}


def article_matches_block(article: Dict, keywords: List[str]) -> bool:
    text = article["articles"][0]["text"].lower()
    return any(k in text for k in keywords)


def verify_and_filter_rag(
    rag_payload: Dict,
    *,
    required_blocks: Optional[List[str]] = None,
    min_articles: int = 30,
    max_articles: int = 80,
) -> Dict:
    """
    Универсальный verifier.
    ❗ НЕ знает тип документа.
    ❗ Требования передаются извне.
    """

    rag_context = rag_payload["rag_context"]

    # если требования не заданы — НИЧЕГО не требуем
    if not required_blocks:
        required_blocks = []

    block_hits = {block: [] for block in BLOCK_KEYWORDS}

    # распределяем статьи по блокам
    for art in rag_context:
        for block, keywords in BLOCK_KEYWORDS.items():
            if article_matches_block(art, keywords):
                block_hits[block].append(art)

    # проверка ТОЛЬКО обязательных блоков
    missing_blocks = [
        block for block in required_blocks if not block_hits.get(block)
    ]

    if missing_blocks:
        raise RuntimeError(
            f"RAG verification failed. Missing required blocks: {missing_blocks}"
        )

    # собираем статьи:
    final_articles = []
    for block in required_blocks:
        final_articles.extend(block_hits.get(block, []))

    # если обязательных блоков нет — берём всё
    if not final_articles:
        final_articles = rag_context.copy()

    # дедуп по doc_id
    uniq = {}
    for art in final_articles:
        uniq[art["doc_id"]] = art

    final_list = list(uniq.values())[:max_articles]

    if len(final_list) < min_articles:
        raise RuntimeError(
            f"Verified RAG too small: {len(final_list)} articles"
        )

    return {
        "verified_rag": final_list,
        "stats": {
            "total_verified": len(final_list),
            "required_blocks": required_blocks,
            "coverage": {
                block: len(block_hits.get(block, []))
                for block in required_blocks
            },
        },
    }
