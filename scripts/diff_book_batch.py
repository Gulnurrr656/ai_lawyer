from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.ingest.diff_checker import iter_json_files, load_json


def section_key(doc: dict) -> str:
    articles = doc.get("articles") or []
    if articles and isinstance(articles[0], dict):
        return str(articles[0].get("article") or "")
    return ""


def read_sections(path: Path) -> tuple[dict[str, dict], list[str]]:
    result: dict[str, dict] = {}
    errors: list[str] = []
    for file_path in iter_json_files(path):
        if file_path.name in {"import_report.json", "diff_report.json", "approve_report.json"}:
            continue
        try:
            doc = load_json(file_path)
            key = section_key(doc)
            if not key:
                errors.append(f"{file_path.name}: missing section id")
                continue
            if key in result:
                errors.append(f"{file_path.name}: duplicate section {key}")
                continue
            result[key] = {"path": str(file_path), "doc": doc, "text_hash": doc.get("text_hash")}
        except Exception as exc:
            errors.append(f"{file_path.name}: {exc}")
    return result, errors


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch", required=True)
    args = parser.parse_args()

    batch = Path(args.batch)
    if not batch.is_absolute():
        batch = ROOT / batch

    import_report_path = batch / "import_report.json"
    import_report = json.loads(import_report_path.read_text(encoding="utf-8")) if import_report_path.exists() else {}
    book_slug = import_report.get("book_slug") or batch.name.rsplit("_", 2)[0]
    rag_dir = ROOT / "rag" / "kz_legal_books" / str(book_slug)

    staging, staging_errors = read_sections(batch)
    current, current_errors = read_sections(rag_dir) if rag_dir.exists() else ({}, [])

    new_sections: list[str] = []
    same_sections: list[str] = []
    changed_sections: list[str] = []
    conflicts: list[str] = []

    for key, entry in sorted(staging.items()):
        if key not in current:
            new_sections.append(key)
        elif entry.get("text_hash") == current[key].get("text_hash"):
            same_sections.append(key)
        else:
            changed_sections.append(key)
            conflicts.append(f"{key}: same section id, different text_hash")

    report = {
        "batch": str(batch),
        "book_slug": book_slug,
        "rag_dir": str(rag_dir),
        "new_sections": new_sections,
        "same_sections": same_sections,
        "changed_sections": changed_sections,
        "conflicts": conflicts,
        "errors": staging_errors + current_errors,
        "RAG_CHANGED": False,
    }
    out = batch / "diff_report.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(str(out))


if __name__ == "__main__":
    main()
