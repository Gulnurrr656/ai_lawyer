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

from app.ingest.build_vs_np_json import build_vs_np_point_document
from app.ingest.slugify import safe_filename
from app.ingest.split_vs_np_points import split_vs_np_docx
from app.ingest.validate_rag_json import filename_doc_id_mismatch, is_suspicious_mojibake, validate_rag_doc

DEFAULT_DOCX = ROOT / "inbox" / "acts" / "vs_np_labor_disputes.docx"
LABOR_SOURCE_ID = "kz_vs_np_labor_disputes_code"
SOURCE_FULL_TITLE_LABOR = (
    "Нормативное постановление Верховного Суда Республики Казахстан "
    "\"О некоторых вопросах применения судами законодательства при разрешении трудовых споров\""
)
TITLE_NEEDLE_LABOR = "О некоторых вопросах применения судами законодательства при разрешении трудовых споров"

KOAP_GP_DOCX = ROOT / "inbox" / "acts" / "vs_np_koap_general_part.docx"
KOAP_GP_SOURCE_ID = "kz_vs_np_koap_general_part_code"
SOURCE_FULL_TITLE_KOAP_GP = (
    "Нормативное постановление Верховного Суда Республики Казахстан "
    "\"О некоторых вопросах применения судами норм Общей части Кодекса Республики Казахстан об административных правонарушениях\""
)
TITLE_NEEDLE_KOAP_GP = "Общей части Кодекса Республики Казахстан об административных правонарушениях"


def main() -> None:
    parser = argparse.ArgumentParser(description="Импорт НП ВС (пункты) в staging/vs_np без law/code pipeline.")
    parser.add_argument(
        "--preset",
        choices=("labor_disputes", "koap_general_part"),
        default=None,
        help="Готовый профиль (переключает docx, source_id, заголовок, дату, номер НП, industry).",
    )
    parser.add_argument("--docx", type=Path, default=None)
    parser.add_argument("--source-id", default=None)
    parser.add_argument("--source-full-title", default=None)
    parser.add_argument("--title-needle", default=None)
    parser.add_argument("--np-date", default=None)
    parser.add_argument("--np-number", default=None)
    parser.add_argument(
        "--industry",
        nargs="+",
        default=None,
        help="Отрасли JSON (например: administrative_offense administrative_law)",
    )
    parser.add_argument("--out-root", type=Path, default=ROOT / "staging" / "vs_np")
    args = parser.parse_args()

    docx = args.docx
    source_id = args.source_id
    source_full_title = args.source_full_title
    title_needle = args.title_needle
    np_date = args.np_date
    np_number = args.np_number
    industry = args.industry

    if args.preset == "labor_disputes":
        docx = docx or DEFAULT_DOCX
        source_id = source_id or LABOR_SOURCE_ID
        source_full_title = source_full_title or SOURCE_FULL_TITLE_LABOR
        title_needle = title_needle or TITLE_NEEDLE_LABOR
        np_date = np_date or "2024-11-28"
        np_number = np_number or "1"
        industry = industry or ["labor_law", "civil_procedure"]
    elif args.preset == "koap_general_part":
        docx = docx or KOAP_GP_DOCX
        source_id = source_id or KOAP_GP_SOURCE_ID
        source_full_title = source_full_title or SOURCE_FULL_TITLE_KOAP_GP
        title_needle = title_needle or TITLE_NEEDLE_KOAP_GP
        np_date = np_date or "2016-12-22"
        np_number = np_number or "12"
        industry = industry or ["administrative_offense", "administrative_law"]
    else:
        docx = docx or DEFAULT_DOCX
        source_id = source_id or LABOR_SOURCE_ID
        source_full_title = source_full_title or SOURCE_FULL_TITLE_LABOR
        title_needle = title_needle or TITLE_NEEDLE_LABOR
        np_date = np_date or "2024-11-28"
        np_number = np_number or "1"
        industry = industry or ["labor_law", "civil_procedure"]

    docx = docx if docx.is_absolute() else ROOT / docx
    out_root = args.out_root if args.out_root.is_absolute() else ROOT / args.out_root

    errors: list[str] = []
    filename_mismatches: list[str] = []
    empty_text: list[str] = []

    source_docx_ok = docx.is_file()
    if not source_docx_ok:
        errors.append(f"SOURCE_DOCX_MISSING: {docx}")

    preamble: list[str] = []
    points: list = []
    if source_docx_ok:
        preamble, points = split_vs_np_docx(docx)

    numbers = [p.number for p in points]
    dup_counter = Counter(numbers)
    duplicate_points = sorted(n for n, c in dup_counter.items() if c > 1)

    nums_set = set(numbers)
    plain_present = sorted({int(x) for x in nums_set if x.isdigit()})
    if plain_present:
        expected_min = plain_present[0]
        expected_max = plain_present[-1]
        missing_points = [str(i) for i in range(expected_min, expected_max + 1) if str(i) not in nums_set]
    else:
        expected_min = 0
        expected_max = 0
        missing_points = []

    for p in points:
        if not (p.text or "").strip():
            empty_text.append(p.number)

    haystack = "\n\n".join(preamble)
    title_found = bool(title_needle and title_needle in haystack)

    suspicious_mojibake_count = sum(is_suspicious_mojibake(p.text) for p in points)
    suspicious_mojibake_count += int(is_suspicious_mojibake(haystack))
    mojibake_flag = suspicious_mojibake_count > 0

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    batch_dir = out_root / f"{source_id}_{ts}"
    batch_dir.mkdir(parents=True, exist_ok=True)

    for p in points:
        try:
            doc = build_vs_np_point_document(
                source_id=source_id,
                source_full_title=source_full_title,
                point_number=p.number,
                point_text=p.text,
                np_date=np_date,
                np_number=np_number,
                industry=industry,
            )
        except ValueError as exc:
            errors.append(f"point {p.number}: {exc}")
            continue

        fname = safe_filename(doc["doc_id"])
        path = batch_dir / fname
        path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")

        if filename_doc_id_mismatch(path.name, doc):
            filename_mismatches.append(path.name)

        for msg in validate_rag_doc(doc):
            errors.append(f"{path.name}: {msg}")

    try:
        target_folder = str(batch_dir.relative_to(ROOT))
    except ValueError:
        target_folder = str(batch_dir)

    split_examples: dict[str, str] = {}
    if points:
        split_examples["point_first_number"] = points[0].number
        split_examples["point_first_preview"] = points[0].text[:400]
    if len(points) > 1:
        split_examples["point_second_number"] = points[1].number
        split_examples["point_second_preview"] = points[1].text[:400]
    if points:
        split_examples["point_last_number"] = points[-1].number
        split_examples["point_last_preview"] = points[-1].text[:400]

    report = {
        "SOURCE_DOCX_OK": source_docx_ok,
        "docx_path": str(docx),
        "title_found": title_found,
        "title_needle": title_needle,
        "source_id": source_id,
        "preset": args.preset,
        "batch_dir": str(batch_dir),
        "target_folder": target_folder,
        "total_points_found": len(points),
        "expected_min": expected_min,
        "expected_max": expected_max,
        "missing_points": missing_points,
        "duplicate_points": duplicate_points,
        "point_numbers": numbers,
        "empty_text": empty_text,
        "filename_doc_id_mismatch": filename_mismatches,
        "mojibake": mojibake_flag,
        "suspicious_mojibake_count": suspicious_mojibake_count,
        "preamble_paragraphs": preamble,
        "errors": errors,
        "split_examples": split_examples,
    }

    out_report = batch_dir / "import_report.json"
    out_report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(str(batch_dir))


if __name__ == "__main__":
    main()
