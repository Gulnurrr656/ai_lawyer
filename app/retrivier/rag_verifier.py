from typing import Dict, List


# обязательные юридические блоки
REQUIRED_BLOCKS = {
    "subject": ["предмет", "оказание услуг", "обязанности"],
    "term": ["срок", "сроки", "исполнение"],
    "liability": ["ответственность", "убытки", "неустойка", "штраф"],
    "jurisdiction": ["подсудность", "суд", "юрисдикция"],
    "force_majeure": ["форс-мажор", "непреодолимая сила"],
    "tax": ["ндс", "налог", "налогообложение"]
}


def article_matches_block(article: Dict, keywords: List[str]) -> bool:
    text = article["articles"][0]["text"].lower()
    return any(k in text for k in keywords)


def verify_and_filter_rag(
    rag_payload: Dict,
    min_articles: int = 50,
    max_articles: int = 80
) -> Dict:
    rag_context = rag_payload["rag_context"]

    block_hits = {block: [] for block in REQUIRED_BLOCKS}

    # распределяем статьи по блокам
    for art in rag_context:
        for block, keywords in REQUIRED_BLOCKS.items():
            if article_matches_block(art, keywords):
                block_hits[block].append(art)

    # проверка покрытия
    missing_blocks = [
        block for block, arts in block_hits.items() if not arts
    ]

    if missing_blocks:
        raise RuntimeError(
            f"RAG verification failed. Missing blocks: {missing_blocks}"
        )

    # собираем финальный пакет
    final_articles = []
    for block, arts in block_hits.items():
        final_articles.extend(arts)

    # дедуп по doc_id
    uniq = {}
    for art in final_articles:
        uniq[art["doc_id"]] = art

    final_list = list(uniq.values())

    # режем до лимита
    final_list = final_list[:max_articles]

    if len(final_list) < min_articles:
        raise RuntimeError(
            f"Verified RAG too small: {len(final_list)} articles"
        )

    return {
        "verified_rag": final_list,
        "stats": {
            "total_verified": len(final_list),
            "blocks": {k: len(v) for k, v in block_hits.items()}
        }
    }