"""Pre-apply audit for the CRIMINAL ACTS + COMMENTARY batch.

Reads ``reports/ingest/criminal_batch_dryrun/bulk_rag_ingest_report.json`` (last
dry-run) plus current ``rag/`` state and the registry, then writes:

- ``reports/ingest/criminal_acts_apply_precheck.json``
- ``reports/ingest/criminal_acts_apply_precheck.md``

For each of the 10 batch source_ids it reports:

| source_id | file | exists | registry_enabled | rag_folder_exists | current_json_count | action |

Actions:
- ``already_applied_noop``       — same hash, nothing new in staging diff
- ``new_ingest_needed``          — dry-run green, ready to apply
- ``conflict_review_needed``     — diff/import errors / conflicts
- ``missing_file``               — DOCX not on disk
- ``manual_classification_needed`` — registry skip_reason demands it
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]

BATCH_IDS: tuple[str, ...] = (
    "kz_law_aml_cft_code",
    "kz_law_operational_search_activity_code",
    "kz_law_advocacy_legal_aid_code",
    "kz_law_law_enforcement_service_code",
    "kz_law_prosecutor_office_code",
    "kz_law_anti_corruption_code",
    "kz_vs_np_criminal_amendments_code",
    "kz_vs_np_criminal_minors_code",
    "kz_book_vs_np_commentary",
    "kz_book_uk_special_part_commentary_old",
)


def _rag_json_count(source_id: str) -> int:
    d = ROOT / "rag" / source_id
    if not d.is_dir():
        return 0
    return sum(1 for _ in d.glob("*.json"))


def main() -> int:
    reg_path = ROOT / "config" / "rag_source_registry.json"
    if not reg_path.is_file():
        print(f"registry not found: {reg_path}", file=sys.stderr)
        return 2
    reg = json.loads(reg_path.read_text(encoding="utf-8-sig"))
    by_id: Dict[str, Dict[str, Any]] = {
        s.get("source_id"): s for s in (reg.get("sources") or [])
    }

    dry_path = (
        ROOT / "reports" / "ingest" / "criminal_batch_dryrun" / "bulk_rag_ingest_report.json"
    )
    dry: Dict[str, Dict[str, Any]] = {}
    if dry_path.is_file():
        data = json.loads(dry_path.read_text(encoding="utf-8-sig"))
        for r in data.get("results") or []:
            dry[r.get("source_id")] = r

    rows: List[Dict[str, Any]] = []
    for sid in BATCH_IDS:
        entry = by_id.get(sid) or {}
        rel_path = str(entry.get("file_path") or "")
        path = ROOT / rel_path if rel_path else None
        exists = bool(path and path.is_file())
        enabled = bool(entry.get("enabled", False))
        skip_reason = str(entry.get("skip_reason") or "")
        rag_dir = ROOT / "rag" / sid
        rag_exists = rag_dir.is_dir()
        rag_count = _rag_json_count(sid)

        dr = dry.get(sid) or {}

        if not exists:
            action = "missing_file"
        elif skip_reason and "manual" in skip_reason.lower():
            action = "manual_classification_needed"
        elif dr.get("apply_allowed"):
            action = "new_ingest_needed"
        elif dr.get("no_op"):
            action = "already_applied_noop"
        elif dr.get("import_errors") or dr.get("conflicts") or dr.get("diff_errors"):
            action = "conflict_review_needed"
        else:
            action = "unknown_state"

        rows.append(
            {
                "source_id": sid,
                "file": rel_path,
                "exists": exists,
                "registry_enabled": enabled,
                "registry_skip_reason": skip_reason,
                "rag_folder_exists": rag_exists,
                "current_json_count": rag_count,
                "dry_run_blocks": int(dr.get("total_blocks") or 0),
                "dry_run_new": len(dr.get("new_blocks") or []),
                "dry_run_conflicts": len(dr.get("conflicts") or []),
                "dry_run_mojibake": int(dr.get("mojibake_count") or 0),
                "dry_run_import_errors": list(dr.get("import_errors") or []),
                "apply_allowed": bool(dr.get("apply_allowed")),
                "action": action,
            }
        )

    out_json = ROOT / "reports" / "ingest" / "criminal_acts_apply_precheck.json"
    out_md = ROOT / "reports" / "ingest" / "criminal_acts_apply_precheck.md"
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(
        json.dumps(
            {
                "generated_at": datetime.now().isoformat(timespec="seconds"),
                "rows": rows,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    lines = [
        "# Criminal acts — apply precheck",
        "",
        f"_Generated_: {datetime.now().isoformat(timespec='seconds')}",
        "",
        "| source_id | file | exists | enabled | rag_dir | current_json | action |",
        "|---|---|---:|---:|---:|---:|---|",
    ]
    for r in rows:
        lines.append(
            "| `{sid}` | `{f}` | {e} | {en} | {rd} | {cnt} | {a} |".format(
                sid=r["source_id"],
                f=r["file"],
                e="✅" if r["exists"] else "—",
                en="✅" if r["registry_enabled"] else "—",
                rd="✅" if r["rag_folder_exists"] else "—",
                cnt=r["current_json_count"],
                a=r["action"],
            )
        )
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote:\n  {out_json}\n  {out_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
