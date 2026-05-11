from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.diff_book_batch import read_sections


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch", required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    dry_run = args.dry_run or not args.apply

    batch = Path(args.batch)
    if not batch.is_absolute():
        batch = ROOT / batch
    import_report_path = batch / "import_report.json"
    import_report = json.loads(import_report_path.read_text(encoding="utf-8")) if import_report_path.exists() else {}
    book_slug = import_report.get("book_slug") or batch.name.rsplit("_", 2)[0]
    rag_dir = ROOT / "rag" / "kz_legal_books" / str(book_slug)

    staging, staging_errors = read_sections(batch)
    current, current_errors = read_sections(rag_dir) if rag_dir.exists() else ({}, [])

    errors = staging_errors + current_errors
    approved_candidates: list[dict] = []
    skipped_existing: list[str] = []
    skipped_conflicts: list[str] = []

    for key, entry in sorted(staging.items()):
        dst = rag_dir / Path(entry["path"]).name
        if key in current:
            if entry.get("text_hash") == current[key].get("text_hash"):
                skipped_existing.append(key)
            else:
                skipped_conflicts.append(f"{key}: same section id, different text_hash")
            continue
        approved_candidates.append({"section": key, "src": entry["path"], "dst": str(dst)})

    report = {
        "batch": str(batch),
        "book_slug": book_slug,
        "dry_run": dry_run,
        "apply": args.apply,
        "approved_candidates": approved_candidates,
        "skipped_existing": skipped_existing,
        "skipped_conflicts": skipped_conflicts,
        "errors": errors,
        "backup_dir": None,
        "copied": [],
        "RAG_CHANGED": False,
    }
    out = batch / "approve_report.json"
    if errors or skipped_conflicts:
        report["stopped"] = True
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        raise SystemExit(f"stopped: conflicts/errors found; report={out}")

    if dry_run:
        report["stopped"] = False
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(str(out))
        return

    backup_dir = ROOT / f"rag_backup_kz_legal_books_{book_slug}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    if rag_dir.exists():
        shutil.copytree(rag_dir, backup_dir)
        report["backup_dir"] = str(backup_dir)
    rag_dir.mkdir(parents=True, exist_ok=True)

    for item in approved_candidates:
        dst = Path(item["dst"])
        if dst.exists():
            skipped_existing.append(item["section"])
            continue
        shutil.copy2(item["src"], dst)
        report["copied"].append(item)

    report["RAG_CHANGED"] = bool(report["copied"])
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(str(out))


if __name__ == "__main__":
    main()
