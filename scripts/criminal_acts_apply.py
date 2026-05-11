"""Apply only green criminal-batch sources from the last bulk dry-run.

Reads ``reports/ingest/criminal_batch_dryrun/bulk_rag_ingest_report.json``
and, for every result with ``apply_allowed=True``:

1. Re-imports the source into a fresh staging batch via the right importer
   (laws → ``import_code_to_staging.py``, VS НП → ``import_vs_np_to_staging.py``,
   commentaries → ``import_legal_commentary_to_staging.py``).
2. Diffs the batch against ``rag/<source_id>``.
3. Runs ``approve_rag_batch.py --apply`` against the batch.

Before any apply we snapshot the **currently existing** RAG target folders into
``rag_backup_before_criminal_acts_final_apply_<timestamp>/`` (most criminal-batch
targets do not exist yet — those are skipped). The per-source ``approve``
script also creates its own per-folder backup when overwriting.

Writes ``reports/ingest/criminal_acts_apply_report.json`` and ``.md``.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "config" / "rag_source_registry.json"
DRY_RUN_REPORT = ROOT / "reports" / "ingest" / "criminal_batch_dryrun" / "bulk_rag_ingest_report.json"
APPLY_REPORT_DIR = ROOT / "reports" / "ingest"


@dataclass
class ApplyResult:
    source_id: str
    type: str
    file_path: str
    apply_allowed: bool = False
    applied: bool = False
    reason: str = ""
    batch_dir: str = ""
    copied_count: int = 0
    rag_json_count_after: int = 0
    per_source_backup_dir: Optional[str] = None
    stderr_tail: str = ""


def _run(cmd: List[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _import_command(entry: Dict[str, Any], src_type: str) -> List[str]:
    if src_type == "vs_np":
        cmd = [
            sys.executable,
            str(ROOT / "scripts" / "import_vs_np_to_staging.py"),
            "--docx", entry["file_path"],
            "--source-id", entry["source_id"],
            "--source-full-title", entry["title"],
            "--title-needle", entry.get("title_needle") or "",
            "--np-date", entry.get("np_date") or "",
            "--np-number", entry.get("np_number") or "",
        ]
        industries = entry.get("industry") or ["judicial_guidance"]
        cmd.append("--industry")
        cmd.extend(industries)
        return cmd
    if src_type == "commentary":
        cmd = [
            sys.executable,
            str(ROOT / "scripts" / "import_legal_commentary_to_staging.py"),
            "--file", entry["file_path"],
            "--source-id", entry["source_id"],
            "--title", entry["title"],
            "--staging-root", entry.get("staging_root") or "books",
        ]
        cs = entry.get("commentary_status") or ""
        if cs:
            cmd.extend(["--commentary-status", str(cs)])
        return cmd
    # Default: code/law importer
    cmd = [
        sys.executable,
        str(ROOT / "scripts" / "import_code_to_staging.py"),
        "--file", entry["file_path"],
        "--source-id", entry["source_id"],
        "--code-title", entry["title"],
        "--expected-min", str(entry.get("expected_min", 1)),
        "--expected-max", str(entry.get("expected_max", 1)),
        "--doc-type", entry.get("doc_type", "code_article"),
        "--authority-level", entry.get("authority_level", "code"),
        "--staging-root", entry.get("staging_root", "codes"),
    ]
    for ind in entry.get("industry") or []:
        cmd.extend(["--industry", ind])
    return cmd


def _rag_count(source_id: str) -> int:
    d = ROOT / "rag" / source_id
    if not d.is_dir():
        return 0
    return sum(1 for _ in d.glob("*.json"))


def main() -> int:
    if not DRY_RUN_REPORT.is_file():
        print(f"dry-run report not found: {DRY_RUN_REPORT}", file=sys.stderr)
        return 2
    dry = json.loads(DRY_RUN_REPORT.read_text(encoding="utf-8-sig"))
    reg = json.loads(REGISTRY.read_text(encoding="utf-8-sig"))
    by_id = {s["source_id"]: s for s in reg["sources"]}

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_root = ROOT / f"rag_backup_before_criminal_acts_final_apply_{timestamp}"
    backup_root.mkdir(parents=True, exist_ok=False)
    backup_manifest: List[Dict[str, Any]] = []

    results: List[ApplyResult] = []

    for r in dry.get("results") or []:
        sid = r.get("source_id") or ""
        src_type = r.get("type") or ""
        file_path = r.get("file_path") or ""
        entry = by_id.get(sid) or {}
        res = ApplyResult(source_id=sid, type=src_type, file_path=file_path)
        res.apply_allowed = bool(r.get("apply_allowed"))

        if not res.apply_allowed:
            # Capture the exact reason from the dry-run report.
            if not r.get("enabled", True):
                res.reason = f"disabled in registry: {entry.get('skip_reason') or 'enabled=false'}"
            elif not r.get("exists"):
                res.reason = "file_not_found"
            elif r.get("no_op"):
                res.reason = "no_op: rag already up-to-date"
            elif r.get("import_errors"):
                res.reason = f"import_errors={len(r['import_errors'])}"
            elif r.get("conflicts"):
                res.reason = f"conflicts={len(r['conflicts'])}"
            elif r.get("mojibake_count"):
                res.reason = f"mojibake={r['mojibake_count']}"
            else:
                res.reason = "blocked"
            res.rag_json_count_after = _rag_count(sid)
            results.append(res)
            continue

        # Pre-apply: snapshot existing rag/<sid>/ if any.
        rag_dir = ROOT / "rag" / sid
        if rag_dir.is_dir():
            dst = backup_root / sid
            shutil.copytree(rag_dir, dst)
            backup_manifest.append({"source_id": sid, "snapshot": str(dst.relative_to(ROOT))})

        # Step 1: fresh import into staging.
        cmd_import = _import_command(entry, src_type)
        p1 = _run(cmd_import)
        if p1.returncode != 0:
            res.reason = f"import failed: rc={p1.returncode}"
            res.stderr_tail = (p1.stderr or p1.stdout)[-400:]
            results.append(res)
            continue
        batch_lines = [ln for ln in (p1.stdout or "").strip().splitlines() if ln.strip()]
        if not batch_lines:
            res.reason = "import produced no batch path"
            res.stderr_tail = (p1.stderr or "")[-400:]
            results.append(res)
            continue
        batch_dir = Path(batch_lines[-1])
        if not batch_dir.is_absolute():
            batch_dir = ROOT / batch_dir
        res.batch_dir = str(batch_dir.relative_to(ROOT)).replace("\\", "/")

        # Step 2: diff.
        p2 = _run([
            sys.executable,
            str(ROOT / "scripts" / "diff_rag_batch.py"),
            "--batch", str(batch_dir),
            "--source-id", sid,
        ])
        if p2.returncode != 0:
            res.reason = f"diff failed: rc={p2.returncode}"
            res.stderr_tail = (p2.stderr or p2.stdout)[-400:]
            results.append(res)
            continue
        diff_report = json.loads((batch_dir / "diff_report.json").read_text(encoding="utf-8-sig"))
        if diff_report.get("conflicts") or diff_report.get("errors"):
            res.reason = (
                f"diff conflicts={len(diff_report.get('conflicts') or [])} "
                f"errors={len(diff_report.get('errors') or [])}"
            )
            results.append(res)
            continue

        # Step 3: approve --apply.
        p3 = _run([
            sys.executable,
            str(ROOT / "scripts" / "approve_rag_batch.py"),
            "--batch", str(batch_dir),
            "--source-id", sid,
            "--apply",
        ])
        try:
            approve_rep = json.loads((batch_dir / "approve_report.json").read_text(encoding="utf-8-sig"))
        except Exception:
            approve_rep = {}
        if p3.returncode != 0 or approve_rep.get("stopped"):
            res.reason = f"approve stopped: rc={p3.returncode}"
            res.stderr_tail = (p3.stderr or p3.stdout)[-400:]
            results.append(res)
            continue
        res.applied = bool(approve_rep.get("RAG_CHANGED"))
        res.copied_count = len(approve_rep.get("copied") or [])
        res.per_source_backup_dir = approve_rep.get("backup_dir")
        res.rag_json_count_after = _rag_count(sid)
        res.reason = "applied" if res.applied else "no_change"
        results.append(res)

    APPLY_REPORT_DIR.mkdir(parents=True, exist_ok=True)
    out_json = APPLY_REPORT_DIR / "criminal_acts_apply_report.json"
    out_md = APPLY_REPORT_DIR / "criminal_acts_apply_report.md"

    out_json.write_text(
        json.dumps(
            {
                "generated_at": datetime.now().isoformat(timespec="seconds"),
                "top_level_backup_dir": str(backup_root.relative_to(ROOT)).replace("\\", "/"),
                "top_level_backup_manifest": backup_manifest,
                "results": [asdict(r) for r in results],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    lines = [
        "# Criminal acts — apply report",
        "",
        f"_Generated_: {datetime.now().isoformat(timespec='seconds')}",
        "",
        f"Top-level backup: `{out_json.relative_to(ROOT).parent}/.../{backup_root.name}`",
        "",
        "| source_id | type | apply_allowed | applied | copied | json_after | reason |",
        "|---|---|:---:|:---:|---:|---:|---|",
    ]
    for r in results:
        lines.append(
            "| `{s}` | {t} | {aa} | {ap} | {cp} | {ja} | {r} |".format(
                s=r.source_id,
                t=r.type,
                aa="✅" if r.apply_allowed else "—",
                ap="✅" if r.applied else "—",
                cp=r.copied_count,
                ja=r.rag_json_count_after,
                r=r.reason,
            )
        )
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote:\n  {out_json}\n  {out_md}")
    print(f"Backup root: {backup_root}")
    # Write a tiny marker file inside the backup so it isn't empty.
    (backup_root / "MANIFEST.json").write_text(
        json.dumps(
            {"generated_at": datetime.now().isoformat(timespec="seconds"), "manifest": backup_manifest},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
