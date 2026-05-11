from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.ingest.diff_checker import read_article_map
from app.ingest.validate_rag_json import filename_doc_id_mismatch, validate_rag_doc


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch", required=True)
    parser.add_argument("--source-id", required=True)
    args = parser.parse_args()

    batch = Path(args.batch)
    if not batch.is_absolute():
        batch = ROOT / batch
    rag_dir = ROOT / "rag" / args.source_id
    staging, staging_errors = read_article_map(batch)
    current, current_errors = read_article_map(rag_dir, include_non_json=True)

    new_articles: list[str] = []
    same_articles: list[str] = []
    changed_articles: list[str] = []
    conflicts: list[str] = []
    duplicates: list[str] = []
    errors: list[str] = staging_errors + current_errors

    seen: set[str] = set()
    for num, entry in sorted(staging.items()):
        if num in seen:
            duplicates.append(num)
        seen.add(num)
        doc = entry["doc"]
        errors.extend(f"{Path(entry['path']).name}: {e}" for e in validate_rag_doc(doc))
        if filename_doc_id_mismatch(entry["path"], doc):
            conflicts.append(f"{num}: filename does not match doc_id")
        if num not in current:
            new_articles.append(num)
        elif entry["hash"] == current[num]["hash"]:
            same_articles.append(num)
        else:
            changed_articles.append(num)
            conflicts.append(f"{num}: same article number, different text_hash")

    report = {
        "source_id": args.source_id,
        "batch": str(batch),
        "new_articles": new_articles,
        "same_articles": same_articles,
        "changed_articles": changed_articles,
        "new_points": new_articles,
        "same_points": same_articles,
        "changed_points": changed_articles,
        "conflicts": conflicts,
        "duplicates": duplicates,
        "errors": errors,
    }
    out = batch / "diff_report.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(str(out))


if __name__ == "__main__":
    main()
