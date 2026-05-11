from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.ingest.build_book_json import build_book_doc
from app.ingest.extract_text import extract_text_with_meta
from app.ingest.slugify import normalize_source_id, safe_filename
from app.ingest.split_book_sections import split_book_sections


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", required=True)
    parser.add_argument("--book-title", required=True)
    parser.add_argument("--book-slug", default="auto")
    args = parser.parse_args()

    input_path = Path(args.file)
    if not input_path.is_absolute():
        input_path = ROOT / input_path
    book_slug = normalize_source_id(input_path.stem if args.book_slug == "auto" else args.book_slug)
    batch = ROOT / "staging" / "books" / f"{book_slug}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    batch.mkdir(parents=True, exist_ok=False)

    meta = extract_text_with_meta(input_path)
    sections, split_errors = split_book_sections(meta["text"])
    errors = list(meta["warnings"]) + split_errors

    for section in sections:
        doc = build_book_doc(
            book_title=args.book_title,
            book_slug=book_slug,
            section_id=section.section_id,
            section_title=section.title,
            section_text=section.text,
            chapter_number=section.chapter_number,
            chapter_title=section.chapter_title,
        )
        (batch / safe_filename(doc["doc_id"])).write_text(
            json.dumps(doc, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    report = {
        "book_title": args.book_title,
        "book_slug": book_slug,
        "input_file": str(args.file),
        "batch_dir": str(batch),
        "total_sections_found": len(sections),
        "section_ids_found": [section.section_id for section in sections],
        "errors": errors,
        "RAG_CHANGED": False,
    }
    (batch / "import_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(str(batch))


if __name__ == "__main__":
    main()
