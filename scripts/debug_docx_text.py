from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.ingest.validate_rag_json import mojibake_hits

MARKERS = ("Рљ", "Рґ", "РЅ", "СЃ", "С‚", "Рѕ")


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    parser = argparse.ArgumentParser()
    parser.add_argument("--file", required=True)
    args = parser.parse_args()

    path = Path(args.file)
    if not path.is_absolute():
        path = ROOT / path

    from docx import Document

    doc = Document(str(path))
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    sample = paragraphs[:30]
    sample_text = "\n".join(sample)
    hits = {marker: sample_text.count(marker) for marker in MARKERS if sample_text.count(marker)}
    all_hits = mojibake_hits("\n".join(paragraphs))
    source_ok = not all_hits

    print(f"file: {path}")
    print("first_30_non_empty_paragraphs:")
    for index, paragraph in enumerate(sample, start=1):
        print(f"{index:02d}: {paragraph}")
    print(f"sample_mojibake_markers: {hits}")
    print(f"all_docx_mojibake_markers: {all_hits}")
    print(f"SOURCE_DOCX_OK = {str(source_ok).lower()}")


if __name__ == "__main__":
    main()
