from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.ingest.validate_rag_json import filename_doc_id_mismatch, validate_rag_doc


ARTICLE_MARKER_RE = re.compile(r"(?im)^\s*Статья\s+\d+(?:-\d+)?\.")


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-id", required=True)
    args = parser.parse_args()

    source_dir = ROOT / "rag" / args.source_id
    report_dir = ROOT / "reports" / "ingest"
    report_dir.mkdir(parents=True, exist_ok=True)

    total_files = list(source_dir.iterdir()) if source_dir.exists() else []
    json_files = [p for p in total_files if p.is_file() and p.suffix.lower() == ".json"]
    found_articles: list[str] = []
    article_to_files: dict[str, list[str]] = {}
    invalid_json: list[str] = []
    non_json_valid_json_files: list[dict] = []
    filename_doc_id_mismatch_list: list[str] = []
    empty_text: list[str] = []
    suspicious_short_text: list[str] = []
    files_with_multiple_article_markers: list[str] = []

    def inspect_doc(path: Path, doc: dict, *, non_json: bool = False) -> None:
        if filename_doc_id_mismatch(path, doc):
            filename_doc_id_mismatch_list.append(path.name)
        if non_json:
            non_json_valid_json_files.append(
                {
                    "file": path.name,
                    "doc_id": doc.get("doc_id"),
                    "recommendation": f"rename {path.name} -> {doc.get('doc_id')}.json",
                }
            )
        validate_rag_doc(doc)
        for item in doc.get("articles") or []:
            num = str(item.get("article") or "")
            text = str(item.get("text") or "")
            found_articles.append(num)
            article_to_files.setdefault(num, []).append(path.name)
            if not text.strip():
                empty_text.append(path.name)
            if 0 < len(text.strip()) < 400:
                suspicious_short_text.append(f"{path.name}|article={num}|chars={len(text.strip())}")
            markers = ARTICLE_MARKER_RE.findall(text)
            if len(set(markers)) > 1:
                files_with_multiple_article_markers.append(path.name)

    for path in sorted(json_files):
        try:
            inspect_doc(path, load_json(path))
        except Exception as exc:
            invalid_json.append(f"{path.name}: {exc}")

    for path in sorted(p for p in total_files if p.is_file() and p.suffix.lower() != ".json"):
        try:
            doc = load_json(path)
        except Exception:
            continue
        inspect_doc(path, doc, non_json=True)

    duplicates = {k: v for k, v in article_to_files.items() if len(v) > 1}
    report = {
        "source_id": args.source_id,
        "folder": str(source_dir),
        "total_files": len([p for p in total_files if p.is_file()]),
        "json_files": len(json_files),
        "non_json_valid_json_files": non_json_valid_json_files,
        "found_articles": sorted(set(found_articles), key=lambda x: [int(p) for p in x.split("-") if p.isdigit()]),
        "duplicate_articles": duplicates,
        "invalid_json": invalid_json,
        "filename_doc_id_mismatch": filename_doc_id_mismatch_list,
        "empty_text": empty_text,
        "suspicious_short_text": suspicious_short_text,
        "files_with_multiple_article_markers": files_with_multiple_article_markers,
    }
    out = report_dir / f"inventory_{args.source_id}.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(str(out))


if __name__ == "__main__":
    main()
