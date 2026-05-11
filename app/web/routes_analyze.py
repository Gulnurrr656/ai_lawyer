"""Document analysis routes (DOCX/TXT MVP).

If a richer extractor is wired later, replace ``_extract_text``. For MVP we
support DOCX (via python-docx) and TXT. PDF is graceful-fallback.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse, RedirectResponse, Response

from app.shared.product_copy import get_copy
from app.shared.storage.repository import record_upload
from app.web.deps import current_user, get_config, render, resolve_language


router = APIRouter()


@router.get("/analyze")
async def analyze_page(request: Request) -> Response:
    user = current_user(request)
    if not user:
        return RedirectResponse(url="/login?next=/analyze", status_code=303)
    return render(request, "analyze.html", {"result": None})


@router.get("/document-analysis/new")
async def document_analysis_alias(request: Request) -> Response:
    """Spec-aligned alias for the analysis page."""

    user = current_user(request)
    if not user:
        return RedirectResponse(
            url="/login?next=/document-analysis/new", status_code=303
        )
    return render(request, "analyze.html", {"result": None})


@router.post("/analyze/upload")
async def analyze_upload(
    request: Request,
    file: UploadFile = File(...),
) -> JSONResponse:
    user = current_user(request)
    if not user:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    cfg = get_config()
    upload_dir = Path(cfg.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    safe_name = (file.filename or "upload").replace("/", "_").replace("\\", "_")
    target = upload_dir / f"u{user['id']}_{safe_name}"
    data = await file.read()
    target.write_bytes(data)
    record_upload(
        user_id=int(user["id"]),
        purpose="analyze",
        file_path=str(target),
        original_name=file.filename or "",
    )
    text = _extract_text(target)
    if not text:
        lang = resolve_language(request)
        return JSONResponse(
            {
                "ok": False,
                "error": "extraction_unavailable",
                "message": get_copy("doc_analyze_unavailable", lang),
            },
            status_code=200,
        )
    preview = text[:1500]
    return JSONResponse(
        {
            "ok": True,
            "filename": safe_name,
            "preview": preview,
            "char_count": len(text),
        }
    )


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------

def _extract_text(path: Path) -> Optional[str]:
    suffix = path.suffix.lower()
    if suffix == ".txt":
        try:
            return path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return None
    if suffix == ".docx":
        try:
            from docx import Document  # python-docx
        except Exception:
            return None
        try:
            doc = Document(str(path))
            return "\n".join(p.text for p in doc.paragraphs if p.text)
        except Exception:
            return None
    if suffix == ".pdf":
        try:
            import pypdf

            reader = pypdf.PdfReader(str(path))
            chunks = []
            for page in reader.pages:
                try:
                    chunks.append(page.extract_text() or "")
                except Exception:
                    chunks.append("")
            return "\n".join(chunks)
        except Exception:
            return None
    return None


__all__ = ["router"]
