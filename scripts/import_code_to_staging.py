from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.ingest.build_code_json import build_code_article_json
from app.ingest.extract_text import extract_text_with_meta
from app.ingest.slugify import safe_filename
from app.ingest.split_articles import split_articles
from app.ingest.validate_rag_json import (
    is_suspicious_mojibake,
    mojibake_hits,
    repair_mojibake_preview,
    validate_rag_doc,
)


def sort_key(num: str):
    return [int(x) for x in str(num).split("-")]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", required=True)
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--code-title", required=True)
    parser.add_argument("--expected-min", type=int, required=True)
    parser.add_argument("--expected-max", type=int, required=True)
    # Optional constitution-specific fields (backward compatible: defaults match code behaviour)
    parser.add_argument("--doc-type", default="code_article")
    parser.add_argument("--authority-level", default="code")
    parser.add_argument("--status", default="active")
    parser.add_argument("--effective-from", default=None)
    parser.add_argument("--as-of-date", default=None)
    parser.add_argument("--chapter-prefix", default="ch")
    parser.add_argument("--industry", nargs="*", default=[])
    parser.add_argument("--note", action="append", dest="notes", default=[])
    parser.add_argument(
        "--staging-root",
        default="codes",
        choices=("codes", "laws"),
        help="Subdirectory under staging/ for the batch (default: codes). Use 'laws' for standalone laws.",
    )
    args = parser.parse_args()

    input_path = Path(args.file)
    extracted = extract_text_with_meta(input_path)
    articles = split_articles(extracted["text"])
    batch_name = f"{args.source_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    batch_dir = ROOT / "staging" / args.staging_root / batch_name
    batch_dir.mkdir(parents=True, exist_ok=False)

    errors: list[str] = list(extracted["warnings"])
    suspicious: list[str] = []
    suspicious_mojibake: list[dict] = []
    article_numbers: list[str] = []

    for article in articles:
        article_numbers.append(str(article["article_number"]))
        errors.extend(f"article {article['article_number']}: {e}" for e in article.get("errors") or [])
        doc = build_code_article_json(
            source_id=args.source_id,
            code_title=args.code_title,
            article=article,
            doc_type=args.doc_type,
            authority_level=args.authority_level,
            status=args.status,
            effective_from=args.effective_from,
            as_of_date=args.as_of_date,
            industry=args.industry or [],
            notes=args.notes or [],
            chapter_prefix=args.chapter_prefix,
        )
        validation_errors = validate_rag_doc(doc)
        errors.extend(f"{doc['doc_id']}: {e}" for e in validation_errors)
        text = doc["articles"][0]["text"]
        title = doc["articles"][0]["title"]
        quality_text = "\n".join([str(doc.get("source") or ""), title, text])
        if is_suspicious_mojibake(quality_text):
            suspicious_mojibake.append(
                {
                    "doc_id": doc["doc_id"],
                    "article": article["article_number"],
                    "filename": safe_filename(doc["doc_id"]),
                    "hits": mojibake_hits(quality_text),
                    "repair_preview": repair_mojibake_preview(quality_text),
                }
            )
        if len(text) < 400:
            suspicious.append(f"{doc['doc_id']}|article={article['article_number']}|chars={len(text)}")
        out = batch_dir / safe_filename(doc["doc_id"])
        with out.open("w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, indent=2)

    counts = Counter(article_numbers)
    duplicates = sorted([n for n, c in counts.items() if c > 1], key=sort_key)
    numeric_found = {int(n) for n in article_numbers if n.isdigit()}
    missing = [n for n in range(args.expected_min, args.expected_max + 1) if n not in numeric_found]

    report = {
        "source_id": args.source_id,
        "code_title": args.code_title,
        "input_file": str(input_path),
        "batch_dir": str(batch_dir),
        "total_articles_found": len(articles),
        "article_numbers_found": sorted(set(article_numbers), key=sort_key),
        "missing_numbers_in_expected_range": missing,
        "duplicate_articles": duplicates,
        "suspicious_articles": suspicious,
        "suspicious_mojibake_count": len(suspicious_mojibake),
        "suspicious_mojibake": suspicious_mojibake,
        "errors": errors,
    }
    with (batch_dir / "import_report.json").open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(str(batch_dir))


if __name__ == "__main__":
    main()
