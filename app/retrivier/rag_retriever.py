import json
import os
from typing import List, Dict


RAG_BASE_PATH = "rag"


def load_article(path: str) -> Dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def scan_source(source_id: str) -> List[Dict]:
    source_path = os.path.join(RAG_BASE_PATH, source_id)
    articles = []

    if not os.path.isdir(source_path):
        return articles

    for file in os.listdir(source_path):
        if file.endswith(".json"):
            full_path = os.path.join(source_path, file)
            try:
                article = load_article(full_path)
                articles.append(article)
            except Exception:
                continue

    return articles


def simple_rank(query: str, articles: List[Dict]) -> List[Dict]:
    query = query.lower()
    ranked = []

    for art in articles:
        text = art["articles"][0]["text"].lower()
        score = sum(1 for word in query.split() if word in text)
        if score > 0:
            ranked.append((score, art))

    ranked.sort(key=lambda x: x[0], reverse=True)
    return [a for _, a in ranked]


def retrieve_rag(
    task_type: str,
    queries: List[str],
    source_ids: List[str],
    min_articles: int = 15
) -> Dict:
    collected = []

    for source_id in source_ids:
        articles = scan_source(source_id)
        for q in queries:
            ranked = simple_rank(q, articles)
            collected.extend(ranked)

    # дедуп по doc_id
    uniq = {}
    for art in collected:
        uniq[art["doc_id"]] = art

    rag_list = list(uniq.values())

    if len(rag_list) < min_articles:
        raise RuntimeError(
            f"RAG coverage failed: found {len(rag_list)} articles, required {min_articles}"
        )

    return {
        "task_type": task_type,
        "rag_context": rag_list,
        "coverage": {
            "unique_articles": len(rag_list),
            "unique_sources": list({a['source'] for a in rag_list})
        }
    }