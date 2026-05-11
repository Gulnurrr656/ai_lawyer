from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence

from app.retriever.search import infer_hinted_source_ids_for_rag

RAG_BASE_PATH = Path(os.getenv("RAG_BASE_PATH", "rag"))
INDEX_BASE_PATH = Path(os.getenv("INDEX_BASE_PATH", "index"))

# Раньше здесь ошибочно мапили kz_gpk_code → kz_pk_code. Физические папки rag/ не трогаем;
# логический source_id должен совпадать с Canon и с app.retriever.search.
_SOURCE_FOLDER_OVERRIDES: dict[str, str] = {}


def _norm(text: Any) -> str:
    return str(text or "").casefold().replace("ё", "е")


def _tokens(text: str) -> list[str]:
    return [t for t in re.findall(r"[\w-]+", _norm(text), flags=re.UNICODE) if len(t) >= 3]


def _article_numbers(query: str) -> set[str]:
    q = _norm(query)
    nums: set[str] = set()
    patterns = (
        r"\bст(?:атья|атьи|\.|)\s*№?\s*(\d+(?:-\d+)?)\b",
        r"\barticle\s+(\d+(?:-\d+)?)\b",
        r"\bart\.?\s*(\d+(?:-\d+)?)\b",
    )
    for pattern in patterns:
        nums.update(re.findall(pattern, q, flags=re.IGNORECASE | re.UNICODE))
    return nums


def _json_files(path: Path) -> Iterable[Path]:
    if not path.is_dir():
        return []
    return sorted(p for p in path.iterdir() if p.is_file() and p.suffix.lower() == ".json")


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8-sig") as f:
        return json.load(f)


def _discover_source_folders() -> dict[str, Path]:
    """Build source_id -> folder from index storage_layout plus real rag dirs."""
    out: dict[str, Path] = {}

    if INDEX_BASE_PATH.is_dir():
        for idx_path in INDEX_BASE_PATH.rglob("*.json"):
            try:
                idx = _load_json(idx_path)
            except Exception:
                continue
            if not isinstance(idx, Mapping):
                continue
            storage = idx.get("storage_layout")
            if not isinstance(storage, Mapping):
                continue
            folders = storage.get("folders")
            source_to_folder = storage.get("source_to_folder")
            if not isinstance(folders, Mapping) or not isinstance(source_to_folder, Mapping):
                continue
            for source_id, folder_key in source_to_folder.items():
                if not isinstance(source_id, str) or not isinstance(folder_key, str):
                    continue
                folder_raw = folders.get(folder_key)
                if not isinstance(folder_raw, str) or not folder_raw.strip():
                    continue
                folder = Path(folder_raw)
                out.setdefault(source_id, folder)

    if RAG_BASE_PATH.is_dir():
        for child in sorted(RAG_BASE_PATH.iterdir()):
            if child.is_dir():
                out.setdefault(child.name, child)

    for source_id, folder in _SOURCE_FOLDER_OVERRIDES.items():
        out[source_id] = RAG_BASE_PATH / folder

    return out


def _rag_folder_for_source_id(source_id: str) -> Path:
    folders = _discover_source_folders()
    return folders.get(source_id, RAG_BASE_PATH / _SOURCE_FOLDER_OVERRIDES.get(source_id, source_id))


def infer_source_ids_from_query(query: str) -> list[str]:
    return infer_hinted_source_ids_for_rag(query)


def all_known_source_ids() -> list[str]:
    return sorted(_discover_source_folders().keys())


def load_article(path: str | Path) -> Dict[str, Any]:
    obj = _load_json(Path(path))
    if not isinstance(obj, dict):
        raise ValueError(f"RAG article is not an object: {path}")
    return obj


def _valid_article_doc(obj: Mapping[str, Any]) -> bool:
    articles = obj.get("articles")
    return isinstance(articles, list) and bool(articles) and isinstance(articles[0], Mapping)


def scan_source(source_id: str) -> List[Dict[str, Any]]:
    source_path = _rag_folder_for_source_id(source_id)
    articles: List[Dict[str, Any]] = []

    for file in _json_files(source_path):
        try:
            article = load_article(file)
        except Exception:
            continue
        if not _valid_article_doc(article):
            continue
        article.setdefault("source_id", source_id)
        article.setdefault("_rag_path", str(file))
        articles.append(article)

    return articles


def _article_numbers_in_doc(doc: Mapping[str, Any]) -> set[str]:
    nums: set[str] = set()
    for item in doc.get("articles") or []:
        if isinstance(item, Mapping) and item.get("article") is not None:
            nums.add(str(item.get("article")).casefold())
    return nums


def _article_text(doc: Mapping[str, Any]) -> str:
    parts: list[str] = [
        str(doc.get("doc_id") or ""),
        str(doc.get("source_id") or ""),
        str(doc.get("source") or ""),
        str(doc.get("doc_type") or ""),
    ]
    chapter = doc.get("chapter")
    if isinstance(chapter, Mapping):
        parts.extend([str(chapter.get("number") or ""), str(chapter.get("title") or "")])
    for item in doc.get("articles") or []:
        if not isinstance(item, Mapping):
            continue
        parts.extend(
            [
                str(item.get("article") or ""),
                str(item.get("title") or ""),
                str(item.get("text") or ""),
            ]
        )
    return "\n".join(parts)


def _score_article(query: str, doc: Mapping[str, Any], source_hint_ids: set[str]) -> int:
    q = _norm(query)
    if not q.strip():
        return 0

    doc_id = _norm(doc.get("doc_id"))
    source_id = _norm(doc.get("source_id"))
    source = _norm(doc.get("source"))
    hay = _norm(_article_text(doc))
    article_nums = _article_numbers(query)
    doc_nums = _article_numbers_in_doc(doc)

    score = 0
    if source_id in source_hint_ids:
        score += 120
    if source_hint_ids and source_id not in source_hint_ids and any(h in source for h in source_hint_ids):
        score += 40

    if article_nums:
        if article_nums & doc_nums:
            score += 1000
        else:
            score -= 250

    for n in article_nums:
        if f"art{n}" in doc_id or f"_art{n}" in doc_id or f"статья {n}" in hay:
            score += 120

    if q in hay:
        score += min(200, len(q) // 2)

    seen: set[str] = set()
    for tok in _tokens(query):
        if tok in seen:
            continue
        seen.add(tok)
        if tok in doc_id:
            score += 25
        elif tok in source_id or tok in source:
            score += 20
        elif tok in hay:
            score += 5

    return score


def simple_rank(query: str, articles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    source_hints = set(_norm(s) for s in infer_source_ids_from_query(query))
    ranked: list[tuple[int, Dict[str, Any]]] = []
    for art in articles:
        if not isinstance(art, dict) or not _valid_article_doc(art):
            continue
        score = _score_article(query, art, source_hints)
        if score > 0:
            ranked.append((score, art))
    ranked.sort(key=lambda x: x[0], reverse=True)
    out: list[Dict[str, Any]] = []
    for score, art in ranked:
        copied = dict(art)
        copied["retrieval_score"] = score
        out.append(copied)
    return out


def _legal_priority(doc: Mapping[str, Any]) -> int:
    priority_map = {
        "code": 3,
        "np": 2,
        "law": 1,
    }
    return priority_map.get(str(doc.get("doc_type") or ""), 0)


def _source_key(doc: Mapping[str, Any]) -> str:
    return str(doc.get("source_id") or doc.get("source") or "")


def _dedupe_best(items: Iterable[Mapping[str, Any]]) -> list[Dict[str, Any]]:
    best: dict[str, Dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, Mapping):
            continue
        doc_id = item.get("doc_id")
        if not isinstance(doc_id, str) or not doc_id:
            continue
        score = int(item.get("retrieval_score") or 0)
        old = best.get(doc_id)
        if old is None or score > int(old.get("retrieval_score") or 0):
            best[doc_id] = dict(item)
    return list(best.values())


def _balance_top_by_source(items: Sequence[Dict[str, Any]], min_per_source: int) -> list[Dict[str, Any]]:
    if min_per_source <= 0:
        return list(items)
    grouped: dict[str, list[Dict[str, Any]]] = {}
    for item in items:
        grouped.setdefault(_source_key(item), []).append(item)
    out: list[Dict[str, Any]] = []
    seen: set[str] = set()
    for group in grouped.values():
        for item in group[:min_per_source]:
            doc_id = str(item.get("doc_id") or "")
            if doc_id and doc_id not in seen:
                seen.add(doc_id)
                out.append(item)
    for item in items:
        doc_id = str(item.get("doc_id") or "")
        if doc_id and doc_id not in seen:
            seen.add(doc_id)
            out.append(item)
    return out


def retrieve_rag(
    task_type: str,
    queries: List[str],
    source_ids: List[str] | None,
    min_articles: int = 15,
    *,
    max_articles: int | None = None,
    strict: bool = False,
) -> Dict[str, Any]:
    clean_queries = [q for q in (queries or []) if isinstance(q, str) and q.strip()]
    inferred: list[str] = []
    for q in clean_queries:
        inferred.extend(infer_source_ids_from_query(q))

    requested_sources = [s for s in (source_ids or []) if isinstance(s, str) and s.strip()]
    if strict and inferred:
        # Strict article lookup should not be diluted by unrelated scenario sources.
        requested_sources = []
    merged_source_ids = list(dict.fromkeys([*inferred, *requested_sources]))
    if not merged_source_ids:
        merged_source_ids = all_known_source_ids()

    source_articles: dict[str, list[Dict[str, Any]]] = {
        source_id: scan_source(source_id) for source_id in merged_source_ids
    }

    collected: list[Dict[str, Any]] = []
    for source_id, articles in source_articles.items():
        if not articles:
            continue
        for q in clean_queries:
            ranked = simple_rank(q, articles)
            for item in ranked:
                item.setdefault("source_id", source_id)
            collected.extend(ranked)

    rag_list = _dedupe_best(collected)
    rag_list.sort(
        key=lambda a: (
            int(a.get("retrieval_score") or 0),
            _legal_priority(a),
            str(a.get("doc_id") or ""),
        ),
        reverse=True,
    )

    if strict:
        requested_numbers = set().union(*(_article_numbers(q) for q in clean_queries))
        if requested_numbers:
            rag_list = [a for a in rag_list if requested_numbers & _article_numbers_in_doc(a)]

    rag_list = _balance_top_by_source(rag_list, min_per_source=3 if not strict else 0)
    if max_articles is not None:
        rag_list = rag_list[: max(0, int(max_articles))]

    if len(rag_list) < int(min_articles):
        if strict:
            rag_list = []
        else:
            raise RuntimeError(
                f"RAG coverage failed: found {len(rag_list)} articles, required {min_articles}. "
                f"sources={merged_source_ids}"
            )

    sources = sorted({_source_key(a) for a in rag_list if _source_key(a)})
    return {
        "task_type": task_type,
        "rag_context": rag_list,
        "coverage": {
            "unique_articles": len(rag_list),
            "unique_sources": sources,
            "sources_count": {
                s: len([a for a in rag_list if _source_key(a) == s])
                for s in sources
            },
            "queries": clean_queries,
            "source_ids": merged_source_ids,
            "strict": strict,
        },
    }
