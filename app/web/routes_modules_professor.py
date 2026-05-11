"""Professor Advocate Machine endpoints exposed under module prefixes.

Adds JSON endpoints so the professor analysis is reachable not only from the
consultation page but also from civil / administrative / criminal /
bankruptcy / document-new / document-analysis modules without touching their
existing HTML pages.
"""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.shared.case_session.strategy_store import (
    get_selected_strategy,
    list_strategy_meta,
)
from app.web.deps import current_user


router = APIRouter()


_MODULE_DOMAIN: Dict[str, str] = {
    "civil": "civil",
    "administrative": "administrative",
    "criminal": "criminal",
    "bankruptcy": "bankruptcy",
    "documents-new": "civil",
    "document-analysis": "civil",
}


def _user_id(request: Request) -> int | None:
    u = current_user(request)
    return int(u["id"]) if u else None


async def _professor_payload(query: str, *, case_id: str | None, user_id: int | None) -> Dict[str, Any]:
    from app.shared.legal_engine_v2 import answer_legal_question_v2

    result = await answer_legal_question_v2(query, use_llm=False)
    professor: Dict[str, Any] = dict(result.professor_analysis or {})
    professor.setdefault("strategy_options", list_strategy_meta())
    persisted = None
    if case_id:
        rec = get_selected_strategy(case_id=case_id, user_id=user_id)
        persisted = rec.to_dict() if rec else None
    return {
        "ok": True,
        "answer": result.answer,
        "llm_status": result.llm_status,
        "professor_analysis": professor,
        "selected_strategy": persisted,
    }


def _build(prefix: str, module_key: str) -> None:
    @router.get(f"/{prefix}/professor", name=f"{module_key}_professor")
    async def _module_professor(  # type: ignore[no-redef]
        request: Request,
        q: str = "",
        case_id: str = "",
    ) -> JSONResponse:
        text = (q or "").strip()
        if not text:
            return JSONResponse(
                {
                    "ok": False,
                    "error": "query_required",
                    "module": module_key,
                    "available_options": list_strategy_meta(),
                },
                status_code=400,
            )
        payload = await _professor_payload(
            text, case_id=case_id or None, user_id=_user_id(request)
        )
        payload["module"] = module_key
        payload["domain_hint"] = _MODULE_DOMAIN.get(module_key, "civil")
        return JSONResponse(payload)


for _prefix, _module in (
    ("civil", "civil"),
    ("administrative", "administrative"),
    ("criminal", "criminal"),
    ("bankruptcy", "bankruptcy"),
    ("documents/new", "documents-new"),
    ("document-analysis", "document-analysis"),
):
    _build(_prefix, _module)


__all__ = ["router"]
