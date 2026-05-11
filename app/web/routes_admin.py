"""Admin panel routes."""

from __future__ import annotations

import json
import os
import time

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response

from app.shared.billing import confirm_order, reject_order
from app.shared.storage.repository import (
    list_all_documents,
    list_payment_orders,
    list_users,
)
from app.web.deps import current_user, is_admin, render


router = APIRouter()


def _require_admin(request: Request):
    user = current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="unauthorized")
    if not is_admin(user):
        raise HTTPException(status_code=403, detail="forbidden")
    return user


def _wants_html_redirect(request: Request) -> bool:
    """Form submits from HTML pages should redirect; API clients want JSON."""

    accept = (request.headers.get("accept") or "").lower()
    if "application/json" in accept and "text/html" not in accept:
        return False
    fmt = (request.query_params.get("format") or "").strip().lower()
    return fmt != "json"


@router.get("/admin")
async def admin_index(request: Request) -> Response:
    user = current_user(request)
    if not user:
        return RedirectResponse(url="/login?next=/admin", status_code=303)
    if not is_admin(user):
        raise HTTPException(status_code=403, detail="forbidden")
    return render(request, "admin_index.html", {})


@router.get("/admin/payments")
async def admin_payments(request: Request) -> Response:
    user = current_user(request)
    if not user:
        return RedirectResponse(url="/login?next=/admin/payments", status_code=303)
    if not is_admin(user):
        raise HTTPException(status_code=403, detail="forbidden")
    orders = list_payment_orders()
    return render(request, "admin_payments.html", {"orders": orders})


@router.get("/admin/payments/{order_id}")
async def admin_payment_detail(request: Request, order_id: int) -> Response:
    _require_admin(request)
    from app.shared.storage.repository import get_payment_order

    row = get_payment_order(order_id)
    if not row:
        raise HTTPException(status_code=404, detail="not_found")
    return render(request, "admin_payment_detail.html", {"order": row})


@router.post("/admin/payments/{order_id}/confirm")
async def admin_payment_confirm(
    request: Request,
    order_id: int,
    note: str = Form(""),
) -> JSONResponse:
    _require_admin(request)
    return JSONResponse(confirm_order(order_id, admin_note=note or None))


@router.post("/admin/payments/{order_id}/reject")
async def admin_payment_reject(
    request: Request,
    order_id: int,
    note: str = Form(""),
) -> JSONResponse:
    _require_admin(request)
    return JSONResponse(reject_order(order_id, admin_note=note or None))


@router.get("/admin/documents")
async def admin_documents(request: Request) -> Response:
    _require_admin(request)
    docs = list_all_documents()
    return render(request, "admin_documents.html", {"documents": docs})


@router.get("/admin/users")
async def admin_users(request: Request) -> Response:
    _require_admin(request)
    users = list_users()
    return render(request, "admin_users.html", {"users": users})


@router.get("/admin/ingest-queue")
async def admin_ingest_queue(request: Request) -> Response:
    """Render the official-source ingest queue (Adilet fallback results).

    HTML page by default. Returns JSON when the client sends
    ``Accept: application/json`` or requests ``?format=json``, so existing
    JSON consumers keep working.
    """

    _require_admin(request)
    from app.shared.external_sources.ingest_queue import count_by_status, load_queue

    items = load_queue()
    counts = count_by_status()

    fmt = (request.query_params.get("format") or "").strip().lower()
    accept = (request.headers.get("accept") or "").lower()
    wants_json = fmt == "json" or (
        "application/json" in accept and "text/html" not in accept
    )
    if wants_json:
        return JSONResponse({"items": items, "counts": counts})

    return render(
        request,
        "admin_ingest_queue.html",
        {"items": items, "counts": counts},
    )


@router.post("/admin/ingest-queue/{queue_id}/duplicate")
async def admin_ingest_queue_duplicate(
    request: Request, queue_id: str, note: str = Form("")
) -> Response:
    _require_admin(request)
    from app.shared.external_sources.ingest_queue import mark_duplicate

    updated = mark_duplicate(queue_id, note=note or "")
    if not updated:
        raise HTTPException(status_code=404, detail="queue_item_not_found")
    if _wants_html_redirect(request):
        return RedirectResponse(url="/admin/ingest-queue", status_code=303)
    return JSONResponse({"ok": True, "item": updated})


@router.get("/admin/ingest-queue/{queue_id}/docx")
async def admin_ingest_queue_docx(
    request: Request, queue_id: str
) -> Response:
    """Return a cached Adilet DOCX if it was downloaded into the cache.

    This route never makes a live HTTP request — it only serves a file that
    already exists in ``data/external_cache/adilet/``. When the file is not
    there yet, returns a structured 404 with hints (KZ + RU) so the admin UI
    can show a clear "not cached yet" message instead of a broken link.
    """

    _require_admin(request)
    from app.shared.external_sources.ingest_queue import load_queue

    item = next((it for it in load_queue() if it.get("queue_id") == queue_id), None)
    if not item:
        raise HTTPException(status_code=404, detail="queue_item_not_found")

    from app.shared.external_sources import adilet_client

    url = (item.get("url") or "").strip()
    if not url:
        return JSONResponse({"ok": False, "error": "no_url"}, status_code=404)

    import hashlib

    fname = "docx_" + hashlib.sha256(url.encode("utf-8")).hexdigest()[:16] + ".docx"
    cached = adilet_client.CACHE_DIR / fname
    if not cached.is_file():
        return JSONResponse(
            {
                "ok": False,
                "error": "docx_not_cached",
                "hint_kk": "Adilet DOCX әлі кэште жоқ. Жүйе live download жасамайды.",
                "hint_ru": "DOCX из Adilet ещё не в кэше. Live-загрузка отключена.",
            },
            status_code=404,
        )
    return FileResponse(
        str(cached),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=cached.name,
    )


@router.post("/admin/ingest-queue/{queue_id}/approve")
async def admin_ingest_queue_approve(
    request: Request, queue_id: str, note: str = Form("")
) -> Response:
    _require_admin(request)
    from app.shared.external_sources.ingest_queue import approve_for_staging

    updated = approve_for_staging(queue_id, note=note or "")
    if not updated:
        raise HTTPException(status_code=404, detail="queue_item_not_found")
    if _wants_html_redirect(request):
        return RedirectResponse(url="/admin/ingest-queue", status_code=303)
    return JSONResponse({"ok": True, "item": updated})


@router.post("/admin/ingest-queue/{queue_id}/reject")
async def admin_ingest_queue_reject(
    request: Request, queue_id: str, note: str = Form("")
) -> Response:
    _require_admin(request)
    from app.shared.external_sources.ingest_queue import reject_queue_item

    updated = reject_queue_item(queue_id, note=note or "")
    if not updated:
        raise HTTPException(status_code=404, detail="queue_item_not_found")
    if _wants_html_redirect(request):
        return RedirectResponse(url="/admin/ingest-queue", status_code=303)
    return JSONResponse({"ok": True, "item": updated})


@router.post("/admin/ingest-queue/{queue_id}/map")
async def admin_ingest_queue_map(
    request: Request,
    queue_id: str,
    mapped_to_source_id: str = Form(""),
    note: str = Form(""),
) -> Response:
    _require_admin(request)
    if not mapped_to_source_id.strip():
        raise HTTPException(status_code=400, detail="mapped_to_source_id_required")
    from app.shared.external_sources.ingest_queue import map_to_existing

    updated = map_to_existing(
        queue_id, mapped_to_source_id=mapped_to_source_id.strip(), note=note or ""
    )
    if not updated:
        raise HTTPException(status_code=404, detail="queue_item_not_found")
    if _wants_html_redirect(request):
        return RedirectResponse(url="/admin/ingest-queue", status_code=303)
    return JSONResponse({"ok": True, "item": updated})


@router.get("/admin/cases")
async def admin_cases_list(request: Request) -> Response:
    _require_admin(request)
    from app.shared.case_session.case_store import list_all_cases_admin

    cases = list_all_cases_admin()
    return render(request, "admin_cases.html", {"cases": cases})


@router.get("/admin/cases/{case_id}")
async def admin_case_detail(request: Request, case_id: str) -> Response:
    _require_admin(request)
    from app.shared.case_session.case_store import get_case

    cf = get_case(case_id)
    if not cf:
        raise HTTPException(status_code=404, detail="case_not_found")
    prof_blob = cf.professor_analysis_snapshot or {}
    professor_json = json.dumps(prof_blob, ensure_ascii=False, indent=2)[:32000]
    return render(
        request,
        "admin_case_detail.html",
        {"case": cf, "professor_json": professor_json},
    )


@router.post("/admin/cases/{case_id}/review")
async def admin_case_review(
    request: Request,
    case_id: str,
    note: str = Form(""),
) -> Response:
    _require_admin(request)
    from app.shared.case_session.case_store import get_case, update_case

    if not get_case(case_id):
        raise HTTPException(status_code=404, detail="case_not_found")
    update_case(
        case_id,
        admin_reviewed_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
        admin_notes=(note or "")[:4000],
    )
    if _wants_html_redirect(request):
        return RedirectResponse(url=f"/admin/cases/{case_id}", status_code=303)
    return JSONResponse({"ok": True})


@router.post("/admin/cases/{case_id}/mark-reviewed")
async def admin_case_mark_reviewed(
    request: Request,
    case_id: str,
    note: str = Form(""),
) -> Response:
    """Spec alias for ``/review`` — sets ``admin_reviewed_at`` and ``admin_notes``."""

    return await admin_case_review(request, case_id, note)


@router.post("/admin/cases/{case_id}/grant-access")
async def admin_case_grant_access(
    request: Request,
    case_id: str,
    note: str = Form(""),
) -> Response:
    """Mark the case as admin-granted access (no biller transaction).

    Side effects:
    - ``payment_status = access_granted``
    - ``status`` upgraded to ``paid`` if the case is still in ``draft``;
      kept as-is otherwise (preserves ``document_ready`` / ``analysis_ready``).
    - ``admin_reviewed_at`` and ``admin_notes`` updated.
    """

    _require_admin(request)
    from app.shared.case_session.case_store import (
        PAYMENT_STATUS_ACCESS_GRANTED,
        get_case,
        update_case,
    )

    cf = get_case(case_id)
    if not cf:
        raise HTTPException(status_code=404, detail="case_not_found")
    new_status = cf.status if cf.status not in ("draft", "") else "paid"
    updated = update_case(
        case_id,
        payment_status=PAYMENT_STATUS_ACCESS_GRANTED,
        status=new_status,
        admin_reviewed_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
        admin_notes=(note or cf.admin_notes or "")[:4000],
    )
    if _wants_html_redirect(request):
        return RedirectResponse(url=f"/admin/cases/{case_id}", status_code=303)
    return JSONResponse(
        {
            "ok": True,
            "case_id": case_id,
            "payment_status": updated.payment_status,
            "status": updated.status,
        }
    )


# Backwards-compatible alias used by the original admin UI.
@router.post("/admin/cases/{case_id}/grant")
async def admin_case_grant_legacy(
    request: Request, case_id: str, note: str = Form("")
) -> Response:
    return await admin_case_grant_access(request, case_id, note)


@router.post("/admin/cases/{case_id}/reject-access")
async def admin_case_reject_access(
    request: Request,
    case_id: str,
    note: str = Form(""),
) -> Response:
    _require_admin(request)
    from app.shared.case_session.case_store import (
        PAYMENT_STATUS_REJECTED,
        get_case,
        update_case,
    )

    cf = get_case(case_id)
    if not cf:
        raise HTTPException(status_code=404, detail="case_not_found")
    updated = update_case(
        case_id,
        payment_status=PAYMENT_STATUS_REJECTED,
        admin_reviewed_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
        admin_notes=(note or cf.admin_notes or "")[:4000],
    )
    if _wants_html_redirect(request):
        return RedirectResponse(url=f"/admin/cases/{case_id}", status_code=303)
    return JSONResponse(
        {
            "ok": True,
            "case_id": case_id,
            "payment_status": updated.payment_status,
        }
    )


@router.post("/admin/cases/{case_id}/retry-generate")
async def admin_case_retry_generate(
    request: Request, case_id: str, note: str = Form("")
) -> Response:
    """Re-run the document writer for this case using stored facts.

    Requires a ``selected_strategy_id`` *or* enough free-text in
    ``client_goal`` / ``facts`` to seed the writer. Returns a structured
    error when prerequisites are missing — never raises 500.
    """

    _require_admin(request)
    import asyncio

    from app.shared.case_session.case_store import (
        attach_document_to_case,
        get_case,
        update_case,
    )
    from app.shared.storage.repository import create_document, update_document
    from app.web.deps import get_config

    cf = get_case(case_id)
    if not cf:
        raise HTTPException(status_code=404, detail="case_not_found")

    seed_text_parts: list[str] = []
    if cf.client_goal:
        seed_text_parts.append(cf.client_goal)
    if cf.facts:
        seed_text_parts.extend(cf.facts)
    seed_text = "\n".join(p for p in seed_text_parts if p).strip()

    if not seed_text and not cf.selected_strategy_id:
        payload = {
            "ok": False,
            "error": "insufficient_input",
            "hint_kk": "Іс файлында мақсат пен фактілер жоқ. Стратегия да таңдалмаған.",
            "hint_ru": "В деле нет цели/фактов и не выбрана стратегия.",
        }
        if _wants_html_redirect(request):
            return RedirectResponse(url=f"/admin/cases/{case_id}", status_code=303)
        return JSONResponse(payload, status_code=400)

    last_doc_type = ""
    if cf.generated_documents:
        last_doc_type = str(cf.generated_documents[-1].get("doc_type") or "")
    doc_type = last_doc_type or "legal_opinion"

    from app.shared.legal_engine_v2 import (
        generate_document_draft_v2,
        is_docx_supported,
        render_document_docx,
    )

    cfg = get_config()
    document_id = create_document(
        user_id=int(cf.user_id),
        doc_type=doc_type,
        title="",
        status="generating",
        session_id=None,
    )

    try:
        doc = await asyncio.wait_for(
            generate_document_draft_v2(
                seed_text or cf.title or case_id,
                doc_type=doc_type,
                use_llm=bool(cfg.openai_api_key) and not cfg.fake_llm,
                case_id=case_id,
                user_id=int(cf.user_id),
            ),
            timeout=60.0,
        )
    except asyncio.TimeoutError:
        update_document(document_id, status="failed")
        payload = {"ok": False, "error": "timeout", "document_id": document_id}
        if _wants_html_redirect(request):
            return RedirectResponse(url=f"/admin/cases/{case_id}", status_code=303)
        return JSONResponse(payload, status_code=504)
    except Exception as exc:  # pragma: no cover — defensive
        update_document(document_id, status="failed")
        payload = {
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
            "document_id": document_id,
        }
        if _wants_html_redirect(request):
            return RedirectResponse(url=f"/admin/cases/{case_id}", status_code=303)
        return JSONResponse(payload, status_code=500)

    file_path: str | None = None
    if is_docx_supported():
        out_path = cfg.storage_dir / f"document_{document_id}_{int(cf.user_id)}.docx"
        try:
            file_path = render_document_docx(doc, str(out_path))
        except Exception:  # pragma: no cover
            file_path = None

    title = doc.title or (doc.doc_type or doc_type or "document")
    update_document(
        document_id,
        status="ready",
        content_text=doc.full_text or "",
        file_path=file_path,
        title=title,
    )
    attach_document_to_case(case_id, document_id, file_path, str(doc.doc_type or doc_type), title=title)
    update_case(
        case_id,
        status="document_ready",
        admin_reviewed_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
        admin_notes=(note or cf.admin_notes or "admin retry")[:4000],
    )
    if _wants_html_redirect(request):
        return RedirectResponse(url=f"/admin/cases/{case_id}", status_code=303)
    return JSONResponse(
        {
            "ok": True,
            "case_id": case_id,
            "document_id": document_id,
            "has_docx": bool(file_path),
            "title": title,
        }
    )


@router.get("/admin/orders")
async def admin_orders_list(request: Request) -> Response:
    _require_admin(request)
    from app.shared.payments.order_store import list_orders_admin

    orders = [o.to_dict() for o in list_orders_admin()]
    fmt = (request.query_params.get("format") or "").strip().lower()
    accept = (request.headers.get("accept") or "").lower()
    if fmt == "json" or ("application/json" in accept and "text/html" not in accept):
        return JSONResponse({"orders": orders})
    return render(request, "admin_orders.html", {"orders": orders})


@router.get("/admin/orders/{order_id}")
async def admin_order_detail(request: Request, order_id: str) -> Response:
    _require_admin(request)
    from app.shared.payments.order_store import get_order
    from app.shared.payments.tariffs import get_tariff

    order = get_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="order_not_found")
    tariff = get_tariff(order.tariff_code)
    return render(
        request,
        "admin_order_detail.html",
        {
            "order": order.to_dict(),
            "tariff": tariff.to_dict() if tariff else None,
        },
    )


@router.post("/admin/orders/{order_id}/confirm")
async def admin_order_confirm(
    request: Request, order_id: str, note: str = Form("")
) -> Response:
    """Manual confirm: order → ``paid`` + case → ``access_granted``.

    Idempotent. Always returns JSON when the client sends
    ``Accept: application/json``, otherwise redirects back to the order.
    """

    _require_admin(request)
    from app.shared.case_session.case_store import (
        PAYMENT_STATUS_ACCESS_GRANTED,
        get_case,
        set_payment_status,
    )
    from app.shared.payments.order_store import (
        ORDER_STATUS_PAID,
        get_order,
        update_order_status,
    )

    order = get_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="order_not_found")
    if order.status == ORDER_STATUS_PAID:
        if _wants_html_redirect(request):
            return RedirectResponse(
                url=f"/admin/orders/{order_id}", status_code=303
            )
        return JSONResponse(
            {"ok": True, "order_id": order_id, "status": ORDER_STATUS_PAID, "idempotent": True}
        )

    updated = update_order_status(
        order_id,
        ORDER_STATUS_PAID,
        admin_notes=(note or order.admin_notes or "admin manual confirm")[:4000],
        mark_paid_now=True,
    )
    if order.case_id:
        try:
            cf = get_case(order.case_id)
            if cf and cf.user_id == order.user_id:
                set_payment_status(
                    order.case_id,
                    PAYMENT_STATUS_ACCESS_GRANTED,
                    admin_notes=(note or "manual confirm")[:4000],
                    mark_reviewed=True,
                )
        except Exception:  # pragma: no cover
            pass
    if _wants_html_redirect(request):
        return RedirectResponse(url=f"/admin/orders/{order_id}", status_code=303)
    return JSONResponse({"ok": True, "order_id": updated.order_id, "status": updated.status})


@router.post("/admin/orders/{order_id}/reject")
async def admin_order_reject(
    request: Request, order_id: str, note: str = Form("")
) -> Response:
    _require_admin(request)
    from app.shared.case_session.case_store import (
        PAYMENT_STATUS_REJECTED,
        get_case,
        set_payment_status,
    )
    from app.shared.payments.order_store import (
        ORDER_STATUS_REJECTED,
        get_order,
        update_order_status,
    )

    order = get_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="order_not_found")
    updated = update_order_status(
        order_id,
        ORDER_STATUS_REJECTED,
        admin_notes=(note or order.admin_notes or "admin reject")[:4000],
    )
    if order.case_id:
        try:
            cf = get_case(order.case_id)
            if cf and cf.user_id == order.user_id:
                set_payment_status(
                    order.case_id,
                    PAYMENT_STATUS_REJECTED,
                    admin_notes=(note or "admin reject")[:4000],
                    mark_reviewed=True,
                )
        except Exception:  # pragma: no cover
            pass
    if _wants_html_redirect(request):
        return RedirectResponse(url=f"/admin/orders/{order_id}", status_code=303)
    return JSONResponse({"ok": True, "order_id": updated.order_id, "status": updated.status})


@router.get("/admin/cases/{case_id}/documents/{document_id}/download")
async def admin_case_document_download(
    request: Request, case_id: str, document_id: int
) -> Response:
    _require_admin(request)
    from pathlib import Path

    from app.shared.case_session.case_store import get_case
    from app.shared.storage.repository import get_user_document

    cf = get_case(case_id)
    if not cf:
        raise HTTPException(status_code=404, detail="case_not_found")
    doc = get_user_document(document_id, int(cf.user_id))
    if not doc:
        raise HTTPException(status_code=404, detail="document_not_found")
    fp = doc.get("file_path")
    if not fp or not os.path.isfile(fp):
        raise HTTPException(status_code=404, detail="file_missing")
    return FileResponse(
        fp,
        filename=Path(fp).name,
        media_type=(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
    )


__all__ = ["router"]
