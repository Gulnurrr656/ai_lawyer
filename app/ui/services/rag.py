from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional


class RagResult:
    """
    Унифицированный результат RAG
    """
    def __init__(self, source_id: str, doc_id: str, text: str):
        self.source_id = source_id
        self.doc_id = doc_id
        self.text = text

    def to_prompt_chunk(self) -> str:
        return (
            f"[{self.source_id} | {self.doc_id}]\n"
            f"{self.text}"
        )


class RagService:
    """
    RAG-сервис:
    1) пытается использовать retrivier
    2) если retrivier недоступен — fallback поиск по rag/<source_id>/*.json
    """

    def __init__(self, rag_root: str = "rag", top_k: int = 8):
        self.rag_root = Path(rag_root)
        self.top_k = top_k
        self._retriever = self._load_retriever()

    # ---------- PUBLIC API ----------

    def retrieve(
        self,
        query: str,
        source_ids: List[str],
    ) -> List[RagResult]:
        if self._retriever:
            return self._retrieve_via_retriever(query, source_ids)

        return self._retrieve_fallback(query, source_ids)

    # ---------- RETRIEVER ----------

    def _load_retriever(self):
        """
        Лениво подключаем retrivier, если он существует.
        Никаких падений, никаких логов секретов.
        """
        try:
            from app.retrivier.retriever import retrieve  # type: ignore
            return retrieve
        except Exception:
            return None

    def _retrieve_via_retriever(
        self,
        query: str,
        source_ids: List[str],
    ) -> List[RagResult]:
        raw_hits = self._retriever(
            query=query,
            source_ids=source_ids,
            top_k=self.top_k,
        )

        results: List[RagResult] = []

        for hit in raw_hits:
            results.append(
                RagResult(
                    source_id=hit["source_id"],
                    doc_id=hit["doc_id"],
                    text=hit["text"],
                )
            )

        return results

    # ---------- FALLBACK ----------

    def _retrieve_fallback(
        self,
        query: str,
        source_ids: List[str],
    ) -> List[RagResult]:
        """
        Каноничный fallback:
        - rag/<source_id>/*.json
        - 1 файл = 1 статья
        - ищем по text статьи
        """

        results: List[RagResult] = []
        query_lower = query.lower()

        for source_id in source_ids:
            source_dir = self.rag_root / source_id
            if not source_dir.exists():
                continue

            for file in source_dir.glob("*.json"):
                try:
                    with open(file, "r", encoding="utf-8") as f:
                        data = json.load(f)

                    article = data["articles"][0]
                    text = article["text"]

                    if query_lower in text.lower():
                        results.append(
                            RagResult(
                                source_id=source_id,
                                doc_id=data["doc_id"],
                                text=text,
                            )
                        )

                except Exception:
                    # намеренно игнорируем битые файлы
                    continue

        return results[: self.top_k]


# ---------- HELPERS ----------

def build_rag_context(results: List[RagResult]) -> str:
    """
    Формирует rag_context для LLM
    """
    if not results:
        return "Нормы права не найдены."

    chunks = [r.to_prompt_chunk() for r in results]
    return "\n\n".join(chunks)
