"""Generate detailed conflict report for kz_uk_code.

Compares the current ``rag/kz_uk_code/`` corpus against the latest staging batch
and produces both Markdown and JSON reports under ``reports/ingest/``.

Each conflicting article gets:
- article number,
- old (in rag) file path, hash, text preview,
- new (staging) file path, hash, text preview.

Pure read-only: never modifies ``rag/`` or staging.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
RAG_DIR = ROOT / "rag" / "kz_uk_code"
STAGING_PARENT = ROOT / "staging" / "codes"
REPORT_DIR = ROOT / "reports" / "ingest"


def _latest_uk_batch() -> Optional[Path]:
    if not STAGING_PARENT.is_dir():
        return None
    candidates = sorted(
        (p for p in STAGING_PARENT.iterdir() if p.is_dir() and p.name.startswith("kz_uk_code_")),
        key=lambda p: p.name,
    )
    return candidates[-1] if candidates else None


def _load_doc(path: Path) -> Optional[Dict[str, Any]]:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return None


def _article_number_and_text(doc: Dict[str, Any]) -> Tuple[Optional[str], str]:
    arts = doc.get("articles")
    if isinstance(arts, list) and arts:
        first = arts[0]
        if isinstance(first, dict):
            n = first.get("article")
            t = first.get("text") or first.get("body") or ""
            if n is not None:
                return str(n), str(t)
    art = doc.get("article")
    if isinstance(art, dict):
        n = art.get("number") or art.get("article")
        t = art.get("text") or art.get("body") or ""
        if n is not None:
            return str(n), str(t)
    n = doc.get("article_number")
    t = doc.get("text") or doc.get("body") or ""
    if n is not None:
        return str(n), str(t)
    return None, ""


def _hash_text(t: str) -> str:
    return hashlib.sha256(t.encode("utf-8")).hexdigest()[:16]


def _read_articles(folder: Path) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    if not folder.is_dir():
        return out
    for fp in sorted(folder.glob("*.json")):
        if fp.name in {"diff_report.json", "import_report.json", "approve_report.json"}:
            continue
        doc = _load_doc(fp)
        if not isinstance(doc, dict):
            continue
        num, text = _article_number_and_text(doc)
        if num is None:
            continue
        out[num] = {
            "path": str(fp.relative_to(ROOT)).replace("\\", "/"),
            "hash": _hash_text(text),
            "preview": text[:500],
            "len": len(text),
            "doc_id": doc.get("doc_id"),
        }
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch", default=None,
                        help="Staging batch dir; default: latest kz_uk_code_* in staging/codes")
    parser.add_argument("--report-dir", default=str(REPORT_DIR))
    args = parser.parse_args()

    batch = Path(args.batch) if args.batch else _latest_uk_batch()
    if batch is None or not batch.is_dir():
        print("[uk-conflict] no kz_uk_code staging batch found", file=sys.stderr)
        return 2

    if not RAG_DIR.is_dir():
        print(f"[uk-conflict] missing rag dir: {RAG_DIR}", file=sys.stderr)
        return 2

    rag_articles = _read_articles(RAG_DIR)
    staging_articles = _read_articles(batch)

    rag_keys = set(rag_articles.keys())
    staging_keys = set(staging_articles.keys())

    conflicts: List[Dict[str, Any]] = []
    same: List[str] = []
    new_in_staging: List[str] = []
    only_in_rag: List[str] = []

    for num in sorted(rag_keys & staging_keys, key=lambda s: (
            int(s.split("-")[0]) if s.split("-")[0].isdigit() else 10**9, s)):
        old = rag_articles[num]
        new = staging_articles[num]
        if old["hash"] == new["hash"]:
            same.append(num)
            continue
        conflicts.append({
            "article_number": num,
            "old_file": old["path"],
            "new_file": new["path"],
            "old_text_hash": old["hash"],
            "new_text_hash": new["hash"],
            "old_text_len": old["len"],
            "new_text_len": new["len"],
            "old_text_preview": old["preview"],
            "new_text_preview": new["preview"],
        })

    for num in sorted(staging_keys - rag_keys,
                      key=lambda s: (int(s.split("-")[0]) if s.split("-")[0].isdigit() else 10**9, s)):
        new_in_staging.append(num)

    for num in sorted(rag_keys - staging_keys,
                      key=lambda s: (int(s.split("-")[0]) if s.split("-")[0].isdigit() else 10**9, s)):
        only_in_rag.append(num)

    has_conflicts = bool(conflicts)
    new_full_count = len(staging_articles)
    rag_count = len(rag_articles)

    coverage_ratio = round(rag_count / new_full_count, 4) if new_full_count else None
    new_dominates = new_full_count > rag_count * 3 and new_full_count >= 200
    if has_conflicts and new_dominates:
        recommendation = "C"
        recommendation_text = (
            "Recommended: ingest the new full DOCX as a separate source_id "
            "(`kz_uk_code_full`) without touching the existing partial corpus. "
            "Requires explicit user approval before execution."
        )
    elif has_conflicts:
        recommendation = "B"
        recommendation_text = (
            "Recommended: keep current rag/kz_uk_code untouched, manually review "
            "each conflicting article, and replace only after legal cross-check."
        )
    else:
        recommendation = "A"
        recommendation_text = (
            "No conflicts detected; current partial corpus stays as-is until apply allowed."
        )

    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_id": "kz_uk_code",
        "rag_dir": str(RAG_DIR.relative_to(ROOT)).replace("\\", "/"),
        "batch": str(batch.relative_to(ROOT)).replace("\\", "/"),
        "rag_article_count": rag_count,
        "staging_article_count": new_full_count,
        "coverage_ratio_rag_over_staging": coverage_ratio,
        "conflicts_count": len(conflicts),
        "same_count": len(same),
        "new_in_staging_count": len(new_in_staging),
        "only_in_rag_count": len(only_in_rag),
        "has_conflicts": has_conflicts,
        "recommendation": recommendation,
        "recommendation_text": recommendation_text,
        "options": {
            "A": "Keep current partial corpus (do nothing).",
            "B": "Manual replace after article-by-article review.",
            "C": "Ingest as separate source_id `kz_uk_code_full` (requires explicit approval).",
        },
        "conflicts": conflicts,
        "new_in_staging": new_in_staging,
        "only_in_rag": only_in_rag,
    }

    rep_dir = Path(args.report_dir)
    rep_dir.mkdir(parents=True, exist_ok=True)
    json_out = rep_dir / "kz_uk_code_conflicts_report.json"
    json_out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    md_lines: List[str] = []
    md_lines.append("# kz_uk_code — Conflict Report")
    md_lines.append("")
    md_lines.append(f"_Generated_: {report['generated_at']}")
    md_lines.append("")
    md_lines.append("## Summary")
    md_lines.append("")
    md_lines.append(f"- rag dir: `{report['rag_dir']}`")
    md_lines.append(f"- staging batch: `{report['batch']}`")
    md_lines.append(f"- rag articles: **{rag_count}**")
    md_lines.append(f"- staging articles (new DOCX): **{new_full_count}**")
    md_lines.append(f"- coverage ratio rag/staging: **{coverage_ratio}**")
    md_lines.append(f"- conflicts (same number, different text): **{len(conflicts)}**")
    md_lines.append(f"- same hash: **{len(same)}**")
    md_lines.append(f"- new in staging only: **{len(new_in_staging)}**")
    md_lines.append(f"- only in rag (orphan): **{len(only_in_rag)}**")
    md_lines.append("")
    md_lines.append("## Recommendation")
    md_lines.append("")
    md_lines.append(f"**Option {recommendation}** — {recommendation_text}")
    md_lines.append("")
    md_lines.append("Options:")
    md_lines.append("- **A** — keep current partial corpus.")
    md_lines.append("- **B** — manual replace after review.")
    md_lines.append("- **C** — ingest new DOCX as `kz_uk_code_full` (separate source_id).")
    md_lines.append("")
    md_lines.append("> Decision required from product owner. The pipeline does not auto-apply.")
    md_lines.append("")
    md_lines.append("## Conflicts (article-by-article)")
    md_lines.append("")
    if conflicts:
        for c in conflicts:
            md_lines.append(f"### Article {c['article_number']}")
            md_lines.append("")
            md_lines.append(f"- old file: `{c['old_file']}` (hash `{c['old_text_hash']}`, len {c['old_text_len']})")
            md_lines.append(f"- new file: `{c['new_file']}` (hash `{c['new_text_hash']}`, len {c['new_text_len']})")
            md_lines.append("")
            md_lines.append("Old preview (rag):")
            md_lines.append("")
            md_lines.append("```")
            md_lines.append(c["old_text_preview"])
            md_lines.append("```")
            md_lines.append("")
            md_lines.append("New preview (staging):")
            md_lines.append("")
            md_lines.append("```")
            md_lines.append(c["new_text_preview"])
            md_lines.append("```")
            md_lines.append("")
    else:
        md_lines.append("_No conflicts._")
        md_lines.append("")

    if new_in_staging:
        md_lines.append("## New articles only in staging (not in rag)")
        md_lines.append("")
        md_lines.append(f"Total: **{len(new_in_staging)}** articles.")
        md_lines.append("")
        md_lines.append("First 30: " + ", ".join(new_in_staging[:30]))
        md_lines.append("")

    if only_in_rag:
        md_lines.append("## Articles only in rag (not in staging)")
        md_lines.append("")
        md_lines.append(f"Total: **{len(only_in_rag)}** articles.")
        md_lines.append("")
        md_lines.append(", ".join(only_in_rag))
        md_lines.append("")

    md_out = rep_dir / "kz_uk_code_conflicts_report.md"
    md_out.write_text("\n".join(md_lines), encoding="utf-8")

    print(f"[uk-conflict] wrote: {json_out}")
    print(f"[uk-conflict] wrote: {md_out}")
    print(f"[uk-conflict] conflicts={len(conflicts)} new={len(new_in_staging)} same={len(same)} only_in_rag={len(only_in_rag)}")
    print(f"[uk-conflict] recommendation: {recommendation}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
