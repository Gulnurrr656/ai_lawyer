"""Bulk dry-run ingest of all DOCX sources listed in
``config/rag_source_registry.json``.

For every ``enabled`` source we:

1. Verify the DOCX is on disk.
2. Call the existing ``import_code_to_staging.py`` or
   ``import_vs_np_to_staging.py`` to produce a staging batch + import report.
3. Call ``diff_rag_batch.py`` to compare staging against ``rag/<source_id>``.
4. Call ``approve_rag_batch.py --dry-run`` to validate the apply path
   without copying anything into ``rag/``.

We then aggregate everything into:

- ``reports/ingest/bulk_rag_ingest_report.json``
- ``reports/ingest/bulk_rag_ingest_report.md``

This script never modifies ``rag/``. It never copies DOCX into ``rag/``.
The only mutating side effect is creating staging batches under
``staging/`` and writing reports under ``reports/ingest/``.

A source is marked ``apply_allowed = true`` only when **all** of these are
green:

- DOCX exists.
- ``import`` produced at least one block (article or point).
- ``import`` reports zero ``suspicious_mojibake_count``.
- ``import`` reports zero ``errors``.
- ``diff`` reports zero ``conflicts`` and zero ``errors``.
- ``diff`` reports at least one ``new_articles`` / ``new_points`` (otherwise
  there is nothing to apply — we mark ``no_op = true``).
- ``approve --dry-run`` reports ``stopped == false``.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

REGISTRY_PATH = ROOT / "config" / "rag_source_registry.json"
REPORT_DIR = ROOT / "reports" / "ingest"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@dataclass
class SourceResult:
    source_id: str
    file_path: str
    category: str
    type: str  # 'code' | 'law' | 'vs_np'
    enabled: bool = True
    skip_reason: str = ""
    exists: bool = False
    title_found: Optional[bool] = None
    mojibake_count: int = 0
    total_blocks: int = 0
    missing: List[str] = field(default_factory=list)
    duplicates: List[str] = field(default_factory=list)
    new_blocks: List[str] = field(default_factory=list)
    same_blocks: List[str] = field(default_factory=list)
    changed_blocks: List[str] = field(default_factory=list)
    conflicts: List[str] = field(default_factory=list)
    import_errors: List[str] = field(default_factory=list)
    diff_errors: List[str] = field(default_factory=list)
    approve_errors: List[str] = field(default_factory=list)
    approve_stopped: bool = False
    no_op: bool = False
    dry_run_ok: bool = False
    apply_allowed: bool = False
    batch_dir: str = ""
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_id": self.source_id,
            "file_path": self.file_path,
            "category": self.category,
            "type": self.type,
            "enabled": self.enabled,
            "skip_reason": self.skip_reason,
            "exists": self.exists,
            "title_found": self.title_found,
            "mojibake_count": self.mojibake_count,
            "total_blocks": self.total_blocks,
            "missing": self.missing,
            "duplicates": self.duplicates,
            "new_blocks": self.new_blocks,
            "same_blocks_count": len(self.same_blocks),
            "changed_blocks": self.changed_blocks,
            "conflicts": self.conflicts,
            "import_errors": self.import_errors,
            "diff_errors": self.diff_errors,
            "approve_errors": self.approve_errors,
            "approve_stopped": self.approve_stopped,
            "no_op": self.no_op,
            "dry_run_ok": self.dry_run_ok,
            "apply_allowed": self.apply_allowed,
            "batch_dir": self.batch_dir,
            "notes": self.notes,
        }


def _classify_type(entry: Dict[str, Any]) -> str:
    dt = str(entry.get("doc_type") or "")
    if dt == "legal_commentary" or str(entry.get("authority_level") or "") == "commentary":
        return "commentary"
    if entry.get("granularity") == "point":
        return "vs_np"
    auth = entry.get("authority_level") or ""
    if auth == "law":
        return "law"
    if auth in ("code", "constitution"):
        return "code"
    return entry.get("doc_type", "")


def _read_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return None


def _run(cmd: List[str], cwd: Path) -> subprocess.CompletedProcess:
    """Run a child process; never raise."""

    return subprocess.run(
        cmd,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


# ---------------------------------------------------------------------------
# Per-source pipeline
# ---------------------------------------------------------------------------

def _import_code(entry: Dict[str, Any]) -> subprocess.CompletedProcess:
    cmd = [
        sys.executable,
        str(ROOT / "scripts" / "import_code_to_staging.py"),
        "--file",
        entry["file_path"],
        "--source-id",
        entry["source_id"],
        "--code-title",
        entry["title"],
        "--expected-min",
        str(entry.get("expected_min", 1)),
        "--expected-max",
        str(entry.get("expected_max", 1)),
        "--doc-type",
        entry.get("doc_type", "code_article"),
        "--authority-level",
        entry.get("authority_level", "code"),
        "--staging-root",
        entry.get("staging_root", "codes"),
    ]
    for ind in entry.get("industry") or []:
        cmd.extend(["--industry", ind])
    return _run(cmd, ROOT)


def _import_vs_np(entry: Dict[str, Any]) -> subprocess.CompletedProcess:
    cmd = [
        sys.executable,
        str(ROOT / "scripts" / "import_vs_np_to_staging.py"),
        "--docx",
        entry["file_path"],
        "--source-id",
        entry["source_id"],
        "--source-full-title",
        entry["title"],
        "--title-needle",
        entry.get("title_needle") or "",
        "--np-date",
        entry.get("np_date") or "",
        "--np-number",
        entry.get("np_number") or "",
    ]
    industry = entry.get("industry") or ["judicial_guidance"]
    cmd.append("--industry")
    cmd.extend(industry)
    return _run(cmd, ROOT)


def _import_commentary(entry: Dict[str, Any]) -> subprocess.CompletedProcess:
    cmd = [
        sys.executable,
        str(ROOT / "scripts" / "import_legal_commentary_to_staging.py"),
        "--file",
        entry["file_path"],
        "--source-id",
        entry["source_id"],
        "--title",
        entry["title"],
        "--staging-root",
        entry.get("staging_root") or "books",
    ]
    cs = entry.get("commentary_status") or ""
    if cs:
        cmd.extend(["--commentary-status", str(cs)])
    return _run(cmd, ROOT)


def _diff(source_id: str, batch_dir: Path) -> subprocess.CompletedProcess:
    return _run(
        [
            sys.executable,
            str(ROOT / "scripts" / "diff_rag_batch.py"),
            "--batch",
            str(batch_dir),
            "--source-id",
            source_id,
        ],
        ROOT,
    )


def _approve_dry(source_id: str, batch_dir: Path) -> subprocess.CompletedProcess:
    return _run(
        [
            sys.executable,
            str(ROOT / "scripts" / "approve_rag_batch.py"),
            "--batch",
            str(batch_dir),
            "--source-id",
            source_id,
            "--dry-run",
        ],
        ROOT,
    )


def process_source(entry: Dict[str, Any]) -> SourceResult:
    sid = entry.get("source_id", "")
    file_path = entry.get("file_path", "")
    category = entry.get("category", "")
    src_type = _classify_type(entry)
    res = SourceResult(
        source_id=sid,
        file_path=file_path,
        category=category,
        type=src_type,
        enabled=bool(entry.get("enabled", True)),
        skip_reason=str(entry.get("skip_reason", "") or ""),
    )
    if not res.enabled:
        res.notes.append(f"disabled: {res.skip_reason or 'enabled=false'}")
        return res

    abs_path = ROOT / file_path
    res.exists = abs_path.is_file()
    if not res.exists:
        res.notes.append("file_not_found")
        return res

    # Step 1: import → staging
    if src_type == "vs_np":
        proc = _import_vs_np(entry)
    elif src_type == "commentary":
        proc = _import_commentary(entry)
    else:
        proc = _import_code(entry)
    if proc.returncode != 0:
        res.import_errors.append(
            f"import exit={proc.returncode}: {(proc.stderr or proc.stdout)[:600]}"
        )
        return res
    batch_path = (proc.stdout or "").strip().splitlines()
    batch_dir = Path(batch_path[-1]) if batch_path else Path("")
    if not batch_dir.is_absolute():
        batch_dir = ROOT / batch_dir
    if not batch_dir.is_dir():
        res.import_errors.append(f"batch dir not found: {batch_dir}")
        return res
    res.batch_dir = str(batch_dir)

    import_report = _read_json(batch_dir / "import_report.json") or {}
    res.title_found = import_report.get("title_found")
    res.mojibake_count = int(import_report.get("suspicious_mojibake_count") or 0)
    res.import_errors.extend(import_report.get("errors") or [])
    res.missing = list(
        import_report.get("missing_numbers_in_expected_range")
        or import_report.get("missing_points")
        or []
    )
    res.duplicates = list(
        import_report.get("duplicate_articles")
        or import_report.get("duplicate_points")
        or []
    )
    res.total_blocks = int(
        import_report.get("total_articles_found")
        or import_report.get("total_points_found")
        or import_report.get("total_sections_found")
        or 0
    )

    # Step 2: diff
    proc_d = _diff(sid, batch_dir)
    if proc_d.returncode != 0:
        res.diff_errors.append(
            f"diff exit={proc_d.returncode}: {(proc_d.stderr or proc_d.stdout)[:600]}"
        )
        return res
    diff_report = _read_json(batch_dir / "diff_report.json") or {}
    res.diff_errors.extend(diff_report.get("errors") or [])
    res.conflicts = list(diff_report.get("conflicts") or [])
    res.new_blocks = list(diff_report.get("new_articles") or [])
    res.same_blocks = list(diff_report.get("same_articles") or [])
    res.changed_blocks = list(diff_report.get("changed_articles") or [])

    # Step 3: approve --dry-run
    proc_a = _approve_dry(sid, batch_dir)
    approve_report = _read_json(batch_dir / "approve_report.json") or {}
    res.approve_errors.extend(approve_report.get("errors") or [])
    res.approve_stopped = bool(approve_report.get("stopped", False)) or proc_a.returncode != 0

    # Decide
    res.no_op = (not res.new_blocks) and (not res.changed_blocks)
    res.dry_run_ok = (
        res.exists
        and res.total_blocks > 0
        and res.mojibake_count == 0
        and not res.import_errors
        and not res.conflicts
        and not res.diff_errors
        and not res.approve_errors
        and not res.approve_stopped
    )
    res.apply_allowed = res.dry_run_ok and not res.no_op
    if res.no_op:
        res.notes.append("nothing_to_apply")
    return res


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def write_markdown(results: List[SourceResult], out_path: Path) -> None:
    lines: List[str] = []
    lines.append("# Bulk RAG Ingest — Dry Run Report")
    lines.append("")
    lines.append(f"_Generated_: {datetime.now().isoformat(timespec='seconds')}")
    lines.append("")

    # Categorize
    enabled = [r for r in results if r.enabled and r.exists]
    disabled = [r for r in results if not r.enabled]
    missing_files = [r for r in results if r.enabled and not r.exists]
    appliable = [r for r in enabled if r.apply_allowed]
    no_ops = [r for r in enabled if r.no_op and not r.apply_allowed]
    blocked = [r for r in enabled if not r.apply_allowed and not r.no_op]

    lines.append("## Totals")
    lines.append("")
    lines.append(f"- registered sources: **{len(results)}**")
    lines.append(f"- enabled and present: **{len(enabled)}**")
    lines.append(f"- ready to apply: **{len(appliable)}**")
    lines.append(f"- no-op (already in rag): **{len(no_ops)}**")
    lines.append(f"- blocked (errors/conflicts/mojibake): **{len(blocked)}**")
    lines.append(f"- disabled in registry: **{len(disabled)}**")
    lines.append(f"- missing on disk: **{len(missing_files)}**")
    lines.append("")

    def _table(title: str, rows: List[SourceResult]) -> None:
        lines.append(f"## {title}")
        lines.append("")
        if not rows:
            lines.append("_none_")
            lines.append("")
            return
        lines.append("| source_id | type | file | blocks | new | conflicts | mojibake | apply_allowed | reason |")
        lines.append("|---|---|---|---:|---:|---:|---:|:---:|---|")
        for r in rows:
            reason = ""
            if r.import_errors:
                reason = f"import_errors={len(r.import_errors)}"
            elif r.conflicts:
                reason = f"conflicts={len(r.conflicts)}"
            elif r.mojibake_count:
                reason = f"mojibake={r.mojibake_count}"
            elif r.approve_stopped:
                reason = "approve_stopped"
            elif r.no_op:
                reason = "no_op"
            lines.append(
                f"| `{r.source_id}` | {r.type} | `{r.file_path}` | {r.total_blocks} | "
                f"{len(r.new_blocks)} | {len(r.conflicts)} | {r.mojibake_count} | "
                f"{'✅' if r.apply_allowed else '—'} | {reason} |"
            )
        lines.append("")

    _table("Ready to apply (green)", appliable)
    _table("No-op (already in rag, no new blocks)", no_ops)
    _table("Blocked", blocked)
    _table("Missing on disk", missing_files)
    _table("Disabled in registry", disabled)

    out_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry", default=str(REGISTRY_PATH))
    parser.add_argument("--report-dir", default=str(REPORT_DIR))
    parser.add_argument(
        "--only",
        nargs="*",
        default=None,
        help="Limit to a subset of source_id values (useful for testing).",
    )
    args = parser.parse_args()

    registry_path = Path(args.registry)
    if not registry_path.is_file():
        print(f"registry not found: {registry_path}", file=sys.stderr)
        return 2
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    sources: List[Dict[str, Any]] = list(registry.get("sources") or [])
    if args.only:
        only = set(args.only)
        sources = [s for s in sources if s.get("source_id") in only]

    results: List[SourceResult] = []
    for entry in sources:
        sid = entry.get("source_id", "")
        print(f"[bulk-dry-run] {sid} ...", flush=True)
        try:
            results.append(process_source(entry))
        except Exception as exc:  # pragma: no cover — defensive
            r = SourceResult(
                source_id=sid,
                file_path=entry.get("file_path", ""),
                category=entry.get("category", ""),
                type=_classify_type(entry),
                enabled=bool(entry.get("enabled", True)),
            )
            r.import_errors.append(f"unhandled: {type(exc).__name__}: {exc}")
            results.append(r)

    out_dir = Path(args.report_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "bulk_rag_ingest_report.json"
    md_path = out_dir / "bulk_rag_ingest_report.md"
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "registry": str(registry_path),
        "results": [r.to_dict() for r in results],
    }
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    write_markdown(results, md_path)
    print(f"\n[bulk-dry-run] reports written:\n  {json_path}\n  {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
