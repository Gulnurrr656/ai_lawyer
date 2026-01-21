from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional


@dataclass
class GeneratedFiles:
    docx_path: Path
    pdf_path: Path
    title: str


class GeneratedStore:
    """
    Простой in-memory стор:
    user_id -> последние сгенерированные файлы.
    (Под прод/Рейлвей потом можно заменить на Redis/DB без смены API.)
    """
    def __init__(self):
        self._store: Dict[int, GeneratedFiles] = {}

    def set(self, user_id: int, files: GeneratedFiles) -> None:
        self._store[user_id] = files

    def get(self, user_id: int) -> Optional[GeneratedFiles]:
        return self._store.get(user_id)


generated_store = GeneratedStore()
