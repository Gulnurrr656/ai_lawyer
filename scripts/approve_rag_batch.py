from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.ingest.diff_checker import read_article_map
from app.ingest.validate_rag_json import filename_doc_id_mismatch, validate_rag_doc

REPORT_JSON_FILES = {"approve_report.json", "diff_report.json", "import_report.json"}


def article_base(article_number: str) -> int | None:
    match = re.match(r"^\s*(\d+)(?:-\d+)?\s*$", str(article_number))
    if not match:
        return None
    return int(match.group(1))


def is_in_article_range(article_number: str, from_article: int | None, to_article: int | None) -> bool:
    if from_article is None and to_article is None:
        return True
    base = article_base(article_number)
    if base is None:
        return False
    if from_article is not None and base < from_article:
        return False
    if to_article is not None and base > to_article:
        return False
    return True


def is_report_json_error(error: str) -> bool:
    file_name = error.split(":", 1)[0]
    return Path(file_name).name in REPORT_JSON_FILES


def import_report_mojibake_count(batch: Path) -> int:
    report_path = batch / "import_report.json"
    if not report_path.exists():
        return 0
    try:
        data = json.loads(report_path.read_text(encoding="utf-8-sig"))
    except Exception:
        return 0
    return int(data.get("suspicious_mojibake_count") or 0)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch", required=True)
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--mode", choices=["missing-only"], default="missing-only")
    parser.add_argument("--from-article", type=int)
    parser.add_argument("--to-article", type=int)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    dry_run = args.dry_run or not args.apply

    batch = Path(args.batch)
    if not batch.is_absolute():
        batch = ROOT / batch
    rag_dir = ROOT / "rag" / args.source_id
    suspicious_mojibake_count = import_report_mojibake_count(batch)
    blocked_by_mojibake = suspicious_mojibake_count > 0
    staging, staging_errors = read_article_map(batch)
    current, current_errors = read_article_map(rag_dir, include_non_json=True)

    errors = [e for e in staging_errors if not is_report_json_error(e)] + current_errors
    skipped_conflicts: list[str] = []
    approved_candidates: list[dict] = []
    skipped_existing: list[str] = []
    skipped_by_range: list[str] = []

    for num, entry in sorted(staging.items()):
        if not is_in_article_range(num, args.from_article, args.to_article):
            skipped_by_range.append(num)
            continue
        doc = entry["doc"]
        errors.extend(f"{Path(entry['path']).name}: {e}" for e in validate_rag_doc(doc))
        if filename_doc_id_mismatch(entry["path"], doc):
            skipped_conflicts.append(f"{num}: filename does not match doc_id")
            continue
        if num in current:
            skipped_existing.append(num)
            continue
        approved_candidates.append({"article": num, "src": entry["path"], "dst": str(rag_dir / Path(entry["path"]).name)})

    report = {
        "source_id": args.source_id,
        "batch": str(batch),
        "mode": args.mode,
        "from_article": args.from_article,
        "to_article": args.to_article,
        "dry_run": dry_run,
        "apply": args.apply,
        "RAG_CHANGED": False,
        "BLOCKED_BY_MOJIBAKE": blocked_by_mojibake,
        "suspicious_mojibake_count": suspicious_mojibake_count,
        "approved_candidates": approved_candidates,
        "errors": errors,
        "skipped_conflicts": skipped_conflicts,
        "skipped_existing": skipped_existing,
        "skipped_by_range": skipped_by_range,
        "backup_dir": None,
        "copied": [],
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

    if blocked_by_mojibake:
        report["stopped"] = True
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        raise SystemExit(f"stopped: BLOCKED_BY_MOJIBAKE; report={out}")

    if rag_dir.is_dir():
        backup_dir = ROOT / f"rag_backup_{args.source_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        shutil.copytree(rag_dir, backup_dir)
        report["backup_dir"] = str(backup_dir)
        report["backup_created"] = True
        report["created_source_folder"] = False
    else:
        rag_dir.mkdir(parents=True, exist_ok=True)
        report["backup_dir"] = None
        report["backup_created"] = False
        report["backup_reason"] = "source folder did not exist"
        report["created_source_folder"] = True

    for item in approved_candidates:
        dst = Path(item["dst"])
        if dst.exists():
            skipped_existing.append(item["article"])
            continue
        shutil.copy2(item["src"], dst)
        report["copied"].append(item)

    report["RAG_CHANGED"] = bool(report["copied"])
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(str(out))


if __name__ == "__main__":
    main()
