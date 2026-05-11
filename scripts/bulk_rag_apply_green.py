"""Bulk apply phase. Reads the dry-run report, takes only the sources where
``apply_allowed = true``, creates a single global backup of ``rag/`` and
then runs ``approve_rag_batch.py --apply`` per source.

Sources with **any** of these are NEVER applied:

- import / diff / approve errors
- conflicts (filename↔doc_id mismatch, hash mismatch on existing block)
- mojibake (suspicious_mojibake_count > 0)
- empty staging (total_blocks == 0)
- no new blocks to apply (no_op)

The script writes:

- ``reports/ingest/bulk_rag_apply_report.json``
- ``reports/ingest/bulk_rag_apply_report.md``

Usage:

    python scripts/bulk_rag_apply_green.py            # dry confirm only
    python scripts/bulk_rag_apply_green.py --apply    # actually copy JSON

A timestamped global backup is created before any apply call:
``rag_backup_before_bulk_apply_<YYYYmmdd_HHMMSS>``.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DRY_REPORT = ROOT / "reports" / "ingest" / "bulk_rag_ingest_report.json"
APPLY_REPORT_DIR = ROOT / "reports" / "ingest"


def _run(cmd: List[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def make_global_backup() -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = ROOT / f"rag_backup_before_bulk_apply_{ts}"
    src = ROOT / "rag"
    if src.is_dir():
        shutil.copytree(src, target)
    else:
        target.mkdir(parents=True, exist_ok=True)
    return target


def write_apply_markdown(rows: List[Dict[str, Any]], backup_path: Path | None, out_path: Path) -> None:
    lines: List[str] = []
    lines.append("# Bulk RAG Apply Report")
    lines.append("")
    lines.append(f"_Generated_: {datetime.now().isoformat(timespec='seconds')}")
    lines.append("")
    if backup_path:
        lines.append(f"**Global backup**: `{backup_path.name}`")
    else:
        lines.append("**Global backup**: _not created — dry-run mode_")
    lines.append("")
    if not rows:
        lines.append("_no green sources to apply_")
    else:
        applied = [r for r in rows if r.get("applied")]
        skipped = [r for r in rows if not r.get("applied")]
        lines.append(f"- applied: **{len(applied)}**")
        lines.append(f"- skipped: **{len(skipped)}**")
        lines.append("")
        lines.append("| source_id | applied | json_added | reason |")
        lines.append("|---|:---:|---:|---|")
        for r in rows:
            reason = r.get("reason") or ""
            lines.append(
                f"| `{r['source_id']}` | "
                f"{'✅' if r.get('applied') else '—'} | "
                f"{r.get('copied_count', 0)} | {reason} |"
            )
    out_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", default=str(DRY_REPORT))
    parser.add_argument("--apply", action="store_true",
                        help="Actually copy approved JSON into rag/. "
                             "Without this flag the script only prints the plan.")
    args = parser.parse_args()

    report_path = Path(args.report)
    if not report_path.is_file():
        print(f"dry-run report not found: {report_path}", file=sys.stderr)
        print("Run scripts/bulk_rag_ingest_dry_run.py first.", file=sys.stderr)
        return 2

    report = json.loads(report_path.read_text(encoding="utf-8"))
    candidates: List[Dict[str, Any]] = [
        r for r in (report.get("results") or []) if r.get("apply_allowed")
    ]
    print(f"green candidates: {len(candidates)}")
    for c in candidates:
        print(f"  - {c['source_id']} ({len(c.get('new_blocks', []))} new blocks)")

    if not args.apply:
        print("\n[dry-confirm] re-run with --apply to actually copy JSON files.")
        # Still write a "plan" report so the user has paper trail.
        out = APPLY_REPORT_DIR / "bulk_rag_apply_plan.md"
        out.parent.mkdir(parents=True, exist_ok=True)
        write_apply_markdown(
            [
                {
                    "source_id": c["source_id"],
                    "applied": False,
                    "copied_count": 0,
                    "reason": "plan_only",
                }
                for c in candidates
            ],
            None,
            out,
        )
        return 0

    backup = make_global_backup()
    print(f"\nbackup: {backup}")

    rows: List[Dict[str, Any]] = []
    for c in candidates:
        sid = c["source_id"]
        batch_dir = c.get("batch_dir") or ""
        if not batch_dir or not Path(batch_dir).is_dir():
            rows.append(
                {
                    "source_id": sid,
                    "applied": False,
                    "copied_count": 0,
                    "reason": "batch_dir_missing",
                }
            )
            continue
        proc = _run(
            [
                sys.executable,
                str(ROOT / "scripts" / "approve_rag_batch.py"),
                "--batch",
                batch_dir,
                "--source-id",
                sid,
                "--apply",
            ]
        )
        approve_path = Path(batch_dir) / "approve_report.json"
        approve_data: Dict[str, Any] = {}
        if approve_path.is_file():
            try:
                approve_data = json.loads(approve_path.read_text(encoding="utf-8-sig"))
            except Exception:
                approve_data = {}
        copied_count = len(approve_data.get("copied") or [])
        applied = (proc.returncode == 0) and bool(approve_data.get("RAG_CHANGED"))
        reason = ""
        if proc.returncode != 0:
            reason = f"approve exit={proc.returncode}"
        elif not approve_data.get("RAG_CHANGED"):
            reason = "rag_unchanged"
        rows.append(
            {
                "source_id": sid,
                "applied": applied,
                "copied_count": copied_count,
                "backup_dir": approve_data.get("backup_dir"),
                "batch_dir": batch_dir,
                "reason": reason,
            }
        )
        print(f"  applied {sid}: copied={copied_count}, ok={applied}")

    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "global_backup": str(backup),
        "rows": rows,
    }
    APPLY_REPORT_DIR.mkdir(parents=True, exist_ok=True)
    json_out = APPLY_REPORT_DIR / "bulk_rag_apply_report.json"
    md_out = APPLY_REPORT_DIR / "bulk_rag_apply_report.md"
    json_out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_apply_markdown(rows, backup, md_out)
    print(f"\nreports written:\n  {json_out}\n  {md_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
