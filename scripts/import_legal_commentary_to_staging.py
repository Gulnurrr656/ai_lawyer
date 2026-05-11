"""Import a legal commentary DOCX into staging as section-granularity JSON.

Uses :func:`app.ingest.build_book_json.build_legal_commentary_doc` so docs are
marked secondary (``can_be_used_as_primary_basis=false``).

Writes ``staging/books/<source_id>_<timestamp>/`` and prints the batch path on stdout.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.ingest.build_book_json import build_legal_commentary_doc
from app.ingest.extract_text import extract_text_with_meta
from app.ingest.slugify import safe_filename
from app.ingest.split_book_sections import split_book_sections
from app.ingest.validate_rag_json import (
    is_suspicious_mojibake,
    mojibake_hits,
    repair_mojibake_preview,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", required=True)
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--title", required=True, help="Full Russian title of the commentary/book.")
    parser.add_argument("--staging-root", default="books")
    parser.add_argument(
        "--commentary-status",
        default="",
        help='e.g. "old" for outdated editions — stored in doc notes.',
    )
    args = parser.parse_args()

    input_path = Path(args.file)
    if not input_path.is_absolute():
        input_path = ROOT / input_path
    if not input_path.is_file():
        print(f"file not found: {input_path}", file=sys.stderr)
        return 2

    batch = (
        ROOT
        / "staging"
        / args.staging_root
        / f"{args.source_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    )
    batch.mkdir(parents=True, exist_ok=False)

    meta = extract_text_with_meta(input_path)
    sections, split_errors = split_book_sections(meta["text"])
    warnings: list[str] = list(meta["warnings"])
    errors: list[str] = []
    for msg in split_errors:
        s = str(msg)
        # `weak_structure_detected; split by size` is a partition strategy
        # fallback, not a structural error — book has no Глава/Раздел headers,
        # so we split by size. Surface as warning so apply is not blocked.
        if s.startswith("weak_structure_detected"):
            warnings.append(s)
        else:
            errors.append(s)

    suspicious_mojibake: list[dict] = []
    status_note = (args.commentary_status or "").strip() or None
    extra_notes: list[str] = []
    if status_note == "old":
        extra_notes.append(
            "Устаревшее издание комментария. При противоречии с действующим "
            "законодательством приоритет у актуальных кодексов и законов."
        )

    for section in sections:
        doc = build_legal_commentary_doc(
            source_id=args.source_id,
            full_title=args.title,
            section_id=section.section_id,
            section_title=section.title,
            section_text=section.text,
            chapter_number=str(section.chapter_number or ""),
            chapter_title=str(section.chapter_title or ""),
            is_primary_law=False,
            can_be_used_as_primary_basis=False,
            commentary_status=status_note,
            extra_notes=extra_notes or None,
        )
        text = str(doc["articles"][0].get("text") or "")
        if is_suspicious_mojibake(text):
            suspicious_mojibake.append(
                {
                    "section": section.section_id,
                    "hits": mojibake_hits(text),
                    "repair_preview": repair_mojibake_preview(text),
                }
            )
        out_name = safe_filename(doc["doc_id"])
        (batch / out_name).write_text(
            json.dumps(doc, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    report = {
        "source_id": args.source_id,
        "input_file": str(input_path.relative_to(ROOT)).replace("\\", "/"),
        "batch_dir": str(batch.relative_to(ROOT)).replace("\\", "/"),
        "total_sections_found": len(sections),
        "section_ids_found": [s.section_id for s in sections],
        "errors": errors,
        "warnings": warnings,
        "suspicious_mojibake_count": len(suspicious_mojibake),
        "suspicious_mojibake": suspicious_mojibake,
        "suspicious_articles": [x["section"] for x in suspicious_mojibake],
        "RAG_CHANGED": False,
    }
    (batch / "import_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(str(batch))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
