"""Sort DOCX files for CRIMINAL ACTS + COMMENTARY batch into canonical inbox paths.

Creates working folders, backs up originals, copies canonical names, detects
duplicates, and writes ``reports/ingest/criminal_batch_pre_audit.{json,md}``.
Does **not** modify ``rag/``.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]

CRIMINAL_REGISTRY_SOURCE_IDS: frozenset[str] = frozenset(
    {
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
    }
)

SCAN_DIRS = [
    ROOT / "inbox/_criminal_batch_acts",
    ROOT / "inbox/_unsorted_legal_docs",
    ROOT / "inbox/acts",
    ROOT / "inbox/codes",
    ROOT / "inbox/vs_np",
    ROOT / "inbox/vs_np/criminal",
    ROOT / "inbox/books/criminal",
    ROOT / "inbox",
]

OUTPUT_DIRS_REL = (
    "inbox/_criminal_batch_acts",
    "inbox/_criminal_batch_acts_original_backup",
    "inbox/_needs_review",
    "inbox/acts",
    "inbox/vs_np/criminal",
    "inbox/books/criminal",
)

REPORT_JSON = ROOT / "reports/ingest/criminal_batch_pre_audit.json"
REPORT_MD = ROOT / "reports/ingest/criminal_batch_pre_audit.md"


def sync_criminal_batch_registry_flags() -> bool:
    """Set ``enabled`` / ``skip_reason`` for the 10 criminal-batch sources from disk."""

    reg_path = ROOT / "config" / "rag_source_registry.json"
    if not reg_path.is_file():
        return False
    data = json.loads(reg_path.read_text(encoding="utf-8-sig"))
    sources = data.get("sources") or []
    changed = False
    for entry in sources:
        sid = str(entry.get("source_id") or "")
        if sid not in CRIMINAL_REGISTRY_SOURCE_IDS:
            continue
        if sid == "kz_vs_np_criminal_amendments_code":
            if entry.get("enabled") is not False:
                entry["enabled"] = False
                changed = True
            if entry.get("skip_reason") != "manual classification required":
                entry["skip_reason"] = "manual classification required"
                changed = True
            continue

        rel = str(entry.get("file_path") or "").replace("\\", "/")
        path = ROOT / rel
        if path.is_file():
            if not entry.get("enabled", False):
                entry["enabled"] = True
                changed = True
            if "skip_reason" in entry:
                entry.pop("skip_reason")
                changed = True
        else:
            if entry.get("enabled", False):
                entry["enabled"] = False
                changed = True
            if entry.get("skip_reason") != "DOCX missing":
                entry["skip_reason"] = "DOCX missing"
                changed = True

    if changed:
        reg_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return changed


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _safe_copy(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


@dataclass
class SourceRule:
    source_id: str
    canonical_rel: str  # relative to ROOT
    detected_type: str
    title_ru: str
    # lowercase needles matched against normalized filename
    filename_needles: Tuple[str, ...]
    # optional extra title needles for classification table
    alt_needles: Tuple[str, ...] = ()


BATCH_RULES: Tuple[SourceRule, ...] = (
    SourceRule(
        "kz_law_aml_cft_code",
        "inbox/acts/kz_law_aml_cft_code.docx",
        "law",
        'Закон РК «О противодействии легализации (отмыванию) доходов...»',
        (
            "legalization",
            "laundering",
            "proceeds from crime",
            "terrorism",
            "weapons of mass",
            "mass destruction",
            "противодействии легализации",
            "финансированию терроризма",
        ),
    ),
    SourceRule(
        "kz_law_operational_search_activity_code",
        "inbox/acts/kz_law_operational_search_activity_code.docx",
        "law",
        'Закон РК «Об оперативно-розыскной деятельности»',
        ("operational-search", "operational_search", "оперативно-розыск"),
    ),
    SourceRule(
        "kz_law_advocacy_legal_aid_code",
        "inbox/acts/kz_law_advocacy_legal_aid_code.docx",
        "law",
        'Закон РК «Об адвокатской деятельности и юридической помощи»',
        ("advocacy", "legal aid", "адвокат", "advocacy and legal"),
    ),
    SourceRule(
        "kz_law_law_enforcement_service_code",
        "inbox/acts/kz_law_law_enforcement_service_code.docx",
        "law",
        'Закон РК «О правоохранительной службе»',
        ("law enforcement service", "правоохранительной службе"),
    ),
    SourceRule(
        "kz_law_prosecutor_office_code",
        "inbox/acts/kz_law_prosecutor_office_code.docx",
        "law",
        'Закон РК «О прокуратуре»',
        ("prosecutor's office", "on the prosecutor", "прокуратуре"),
    ),
    SourceRule(
        "kz_vs_np_criminal_amendments_code",
        "inbox/vs_np/criminal/kz_vs_np_criminal_amendments_code.docx",
        "judicial_guidance",
        'НП ВС РК «О внесении изменений и дополнений в некоторые НП ВС...»',
        ("amendments and additions", "нормативные постановления", "criminal and criminal procedure legislation", "внесении изменений"),
    ),
    SourceRule(
        "kz_vs_np_criminal_minors_code",
        "inbox/vs_np/criminal/kz_vs_np_criminal_minors_code.docx",
        "judicial_guidance",
        'НП ВС РК «О судебной практике по делам об уголовных правонарушениях несовершеннолетних...»',
        ("minors", "несовершеннолетн", "juvenile", "antiобщественных"),
    ),
    SourceRule(
        "kz_book_vs_np_commentary",
        "inbox/books/criminal/kz_book_vs_np_commentary.docx",
        "legal_commentary",
        "Комментарий к нормативным постановлениям Верховного Суда РК",
        ("commentary on the regulatory resolutions", "комментарий к нормативным постановлениям"),
    ),
    SourceRule(
        "kz_book_uk_special_part_commentary_old",
        "inbox/books/criminal/kz_book_uk_special_part_commentary_old.docx",
        "legal_commentary",
        "Комментарий к УК РК (Особенная часть), старое издание",
        ("commentary on the criminal code", "special part", "old edition", "особенная часть"),
    ),
    SourceRule(
        "kz_law_anti_corruption_code",
        "inbox/acts/kz_law_anti_corruption_code.docx",
        "law",
        'Закон РК «О противодействии коррупции»',
        ("combating corruption", "противодействии коррупции", "anti-corruption"),
    ),
)


def _norm_name(name: str) -> str:
    return name.lower().replace("ё", "е")


def _match_rule(path: Path) -> Optional[SourceRule]:
    n = _norm_name(path.name)
    hits: List[Tuple[int, SourceRule]] = []
    for rule in BATCH_RULES:
        score = sum(1 for nd in rule.filename_needles if nd.lower() in n)
        if score:
            hits.append((score, rule))
    if not hits:
        return None
    hits.sort(key=lambda x: (-x[0], x[1].source_id))
    best_score, best = hits[0]
    second = hits[1][0] if len(hits) > 1 else 0
    if best_score == second and len(hits) > 1:
        # ambiguous — pick longest rule id tie-breaker
        pass
    return best


def ensure_dirs() -> None:
    for rel in OUTPUT_DIRS_REL:
        (ROOT / Path(rel)).mkdir(parents=True, exist_ok=True)


def collect_docx() -> List[Path]:
    seen: set[str] = set()
    out: List[Path] = []
    for d in SCAN_DIRS:
        if not d.is_dir():
            continue
        for p in d.rglob("*.docx"):
            key = str(p.resolve())
            if key in seen:
                continue
            seen.add(key)
            out.append(p)
    return sorted(out, key=lambda x: str(x).lower())


def main() -> int:
    ensure_dirs()
    backup_dir = ROOT / "inbox/_criminal_batch_acts_original_backup"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    scanned_rows: List[Dict[str, Any]] = []
    audit_rows: List[Dict[str, Any]] = []

    for path in collect_docx():
        rule = _match_rule(path)
        rel = str(path.relative_to(ROOT)).replace("\\", "/")
        if rule is None:
            scanned_rows.append(
                {
                    "file_name": path.name,
                    "relative_path": rel,
                    "detected_title": "",
                    "detected_type": "unknown",
                    "target_folder": "",
                    "canonical_file_name": "",
                    "proposed_source_id": "",
                    "confidence": 0.0,
                    "action": "no_match_in_batch",
                }
            )
            continue

        canonical = ROOT / rule.canonical_rel.replace("/", "\\")
        detected_title = rule.title_ru
        tgt_folder = str(canonical.parent.relative_to(ROOT)).replace("\\", "/")

        # Backup copy (timestamped subfolder once per run — flat copy with original name)
        backup_sub = backup_dir / timestamp
        backup_sub.mkdir(parents=True, exist_ok=True)
        if path.resolve() != (backup_sub / path.name).resolve():
            try:
                shutil.copy2(path, backup_sub / path.name)
            except OSError:
                pass

        action = "canonical_copy"
        dup_note = ""
        if canonical.is_file():
            h1 = _sha256(path)
            h2 = _sha256(canonical)
            if h1 == h2:
                action = "no_op_identical"
            else:
                action = "duplicate_conflict"
                dup_note = f"hash_src={h1[:16]} hash_canon={h2[:16]}"
                rev = ROOT / "inbox/_needs_review" / f"dup_{rule.source_id}_{path.name}"
                try:
                    shutil.copy2(path, rev)
                except OSError:
                    pass

        if action not in {"no_op_identical"}:
            if action == "duplicate_conflict":
                pass  # do not overwrite canonical
            else:
                try:
                    _safe_copy(path, canonical)
                except OSError as exc:
                    action = f"copy_failed:{exc}"

        scanned_rows.append(
            {
                "file_name": path.name,
                "relative_path": rel,
                "detected_title": detected_title,
                "detected_type": rule.detected_type,
                "target_folder": tgt_folder,
                "canonical_file_name": canonical.name,
                "proposed_source_id": rule.source_id,
                "confidence": 1.0,
                "action": action,
                "notes": dup_note,
            }
        )

    # Audit table: per batch source_id
    for rule in BATCH_RULES:
        canon = ROOT / rule.canonical_rel.replace("/", "\\")
        exists = canon.is_file()
        rag_dir = ROOT / "rag" / rule.source_id
        rag_count = 0
        if rag_dir.is_dir():
            rag_count = sum(1 for _ in rag_dir.glob("*.json"))
        if not exists:
            act = "missing_file"
        elif rag_count > 0:
            act = "already_in_rag_noop_or_diff"
        else:
            act = "new_ingest_needed"
        audit_rows.append(
            {
                "source_id": rule.source_id,
                "canonical_file": rule.canonical_rel,
                "exists": exists,
                "current_rag_folder": f"rag/{rule.source_id}",
                "current_json_count": rag_count,
                "action": act,
                "detected_type": rule.detected_type,
            }
        )

    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "scan_directories": [str(d.relative_to(ROOT)).replace("\\", "/") for d in SCAN_DIRS],
        "files_scanned": scanned_rows,
        "source_audit": audit_rows,
    }
    REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    lines: List[str] = [
        "# Criminal batch — pre-audit",
        "",
        f"_Generated_: {payload['generated_at']}",
        "",
        "## Source audit",
        "",
        "| source_id | canonical_file | exists | rag_json | action |",
        "|---|---|---:|---:|---|",
    ]
    for row in audit_rows:
        lines.append(
            f"| `{row['source_id']}` | `{row['canonical_file']}` | "
            f"{'✅' if row['exists'] else '—'} | {row['current_json_count']} | {row['action']} |"
        )
    lines.append("")
    lines.append("## Files classified")
    lines.append("")
    for row in scanned_rows:
        if row.get("proposed_source_id"):
            lines.append(
                f"- **{row['file_name']}** → `{row['proposed_source_id']}` ({row['action']})"
            )
    REPORT_MD.write_text("\n".join(lines), encoding="utf-8")
    sync_criminal_batch_registry_flags()
    print(f"Wrote:\n  {REPORT_JSON}\n  {REPORT_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
