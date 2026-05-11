"""Adilet (adilet.zan.kz) client — safe, cached, rate-limited.

Design rules:

- **Never** replace the RAG. Adilet is fallback only.
- Real HTTP is gated by ``ZANGERPRO_ADILET_LIVE=1``. Without it (default and
  in tests) the client returns an empty result list, which is the safe
  behaviour for offline / CI environments.
- Hard timeout + small retry count; on any unexpected exception the
  caller gets an empty list with a status string, never a crash.
- Results are cached on disk under ``data/external_cache/adilet/``.
- ``download_adilet_docx_if_available`` is best-effort; if the Adilet page
  has no DOCX link, the function returns ``{"ok": False, "reason": ...}``.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

ADILET_HOST = "adilet.zan.kz"
ADILET_SEARCH_URL = "https://adilet.zan.kz/rus/search/docs"

DEFAULT_TIMEOUT_S = 12.0
DEFAULT_RETRIES = 1
DEFAULT_RATE_LIMIT_S = 1.5

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
CACHE_DIR = _PROJECT_ROOT / "data" / "external_cache" / "adilet"


@dataclass
class OfficialSourceResult:
    """A single official-source search hit.

    ``external_only=True`` and ``needs_ingest_review=True`` by construction —
    these results are *never* counted as RAG basis until indexed.
    """

    source_name: str = "adilet"
    title: str = ""
    url: str = ""
    doc_type: str = "unknown"
    act_form: str = ""
    date: str = ""
    status: str = ""
    language: str = "ru"
    snippet: str = ""
    confidence: float = 0.0
    external_only: bool = True
    needs_ingest_review: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_name": self.source_name,
            "title": self.title,
            "url": self.url,
            "doc_type": self.doc_type,
            "act_form": self.act_form,
            "date": self.date,
            "status": self.status,
            "language": self.language,
            "snippet": self.snippet,
            "confidence": self.confidence,
            "external_only": self.external_only,
            "needs_ingest_review": self.needs_ingest_review,
        }


def _is_live() -> bool:
    return os.environ.get("ZANGERPRO_ADILET_LIVE", "").strip() in ("1", "true", "yes")


def _ensure_cache_dir() -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR


def _query_hash(query: str) -> str:
    return hashlib.sha256(query.strip().lower().encode("utf-8")).hexdigest()[:24]


def _cache_path(query: str) -> Path:
    return _ensure_cache_dir() / f"search_{_query_hash(query)}.json"


def _load_cache(query: str, *, max_age_s: int = 24 * 3600) -> Optional[Dict[str, Any]]:
    p = _cache_path(query)
    if not p.is_file():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    ts = float(data.get("fetched_at_unix") or 0.0)
    if max_age_s > 0 and (time.time() - ts) > max_age_s:
        return None
    return data


def _save_cache(query: str, payload: Dict[str, Any]) -> None:
    p = _cache_path(query)
    try:
        p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as exc:
        logger.warning("adilet cache write failed: %s", exc)


def _try_import_requests():
    try:
        import requests  # type: ignore

        return requests
    except Exception:
        return None


_TITLE_RE = re.compile(r"<a[^>]+href=\"(?P<url>[^\"]+)\"[^>]*>(?P<title>[^<]+)</a>", re.I)


def _parse_adilet_search_html(html: str) -> List[OfficialSourceResult]:
    """Very defensive HTML parser — Adilet markup can change at any time."""

    if not html:
        return []
    out: List[OfficialSourceResult] = []
    for m in _TITLE_RE.finditer(html):
        url = (m.group("url") or "").strip()
        title = (m.group("title") or "").strip()
        if not url or not title:
            continue
        # Heuristic filter: keep only links that look like Adilet docs.
        if "/docs/" not in url and "doc_id=" not in url:
            continue
        if not url.startswith("http"):
            url = "https://" + ADILET_HOST + url
        out.append(
            OfficialSourceResult(
                source_name="adilet",
                title=title[:240],
                url=url,
                language="ru",
                snippet="",
                confidence=0.4,
            )
        )
        if len(out) >= 20:
            break
    return out


def search_adilet(query: str, limit: int = 5) -> List[OfficialSourceResult]:
    """Search Adilet for ``query``. Safe / offline by default.

    Live mode requires ``ZANGERPRO_ADILET_LIVE=1`` and the ``requests``
    package; otherwise the function returns ``[]`` immediately. Cached
    results (from a previous live call) are still served when offline.
    """

    q = (query or "").strip()
    if not q:
        return []

    cached = _load_cache(q)
    if cached and isinstance(cached.get("results"), list):
        return [
            OfficialSourceResult(**{k: v for k, v in r.items() if k in OfficialSourceResult.__annotations__})
            for r in cached["results"][:limit]
        ]

    if not _is_live():
        return []

    requests = _try_import_requests()
    if requests is None:
        return []

    last_exc: Optional[Exception] = None
    for attempt in range(max(1, DEFAULT_RETRIES + 1)):
        try:
            resp = requests.get(
                ADILET_SEARCH_URL,
                params={"q": q, "where": "all"},
                timeout=DEFAULT_TIMEOUT_S,
                headers={"User-Agent": "ZangerPro/1.0 (+adilet-fallback)"},
            )
            if resp.status_code != 200:
                last_exc = RuntimeError(f"adilet http {resp.status_code}")
                continue
            results = _parse_adilet_search_html(resp.text)[:limit]
            _save_cache(
                q,
                {
                    "query": q,
                    "fetched_at_unix": time.time(),
                    "results": [r.to_dict() for r in results],
                },
            )
            time.sleep(DEFAULT_RATE_LIMIT_S)
            return results
        except Exception as exc:  # pragma: no cover — defensive
            last_exc = exc
            time.sleep(DEFAULT_RATE_LIMIT_S)
    logger.info("adilet search failed: %s", last_exc)
    return []


def fetch_adilet_document(url: str) -> Dict[str, Any]:
    """Fetch a document's metadata page. Safe stub when live mode is off."""

    if not url:
        return {"ok": False, "reason": "empty_url"}

    if not _is_live():
        return {"ok": False, "reason": "live_mode_disabled"}

    requests = _try_import_requests()
    if requests is None:
        return {"ok": False, "reason": "requests_unavailable"}

    try:
        resp = requests.get(
            url, timeout=DEFAULT_TIMEOUT_S, headers={"User-Agent": "ZangerPro/1.0"}
        )
        return {
            "ok": resp.status_code == 200,
            "status_code": resp.status_code,
            "url": url,
            "length": len(resp.text or ""),
        }
    except Exception as exc:
        return {"ok": False, "reason": f"{type(exc).__name__}: {exc}", "url": url}


def download_adilet_docx_if_available(url: str, target_path: str) -> Dict[str, Any]:
    """Best-effort DOCX download. Returns ``ok=False`` when not available."""

    if not _is_live():
        return {"ok": False, "reason": "live_mode_disabled", "url": url}

    requests = _try_import_requests()
    if requests is None:
        return {"ok": False, "reason": "requests_unavailable"}

    try:
        resp = requests.get(url, timeout=DEFAULT_TIMEOUT_S, headers={"User-Agent": "ZangerPro/1.0"})
        if resp.status_code != 200:
            return {"ok": False, "reason": f"http_{resp.status_code}", "url": url}
        ctype = (resp.headers.get("content-type") or "").lower()
        if "wordprocessingml" not in ctype and not url.lower().endswith(".docx"):
            return {"ok": False, "reason": "no_docx", "url": url}
        tp = Path(target_path)
        tp.parent.mkdir(parents=True, exist_ok=True)
        tp.write_bytes(resp.content)
        return {"ok": True, "path": str(tp), "url": url, "bytes": len(resp.content)}
    except Exception as exc:
        return {"ok": False, "reason": f"{type(exc).__name__}: {exc}", "url": url}


__all__ = [
    "ADILET_HOST",
    "ADILET_SEARCH_URL",
    "OfficialSourceResult",
    "search_adilet",
    "fetch_adilet_document",
    "download_adilet_docx_if_available",
]
