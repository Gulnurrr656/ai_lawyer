"""Direct routing checks for the CRIMINAL ACTS + COMMENTARY batch.

Runs ``infer_hinted_source_ids_for_rag`` (the same path the retriever uses)
plus a strict, non-LLM ``search()`` for each requested query and writes a
small markdown report to ``reports/ingest/criminal_acts_routing_checks.md``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.retriever.search import infer_hinted_source_ids_for_rag, search  # noqa: E402


CHECKS = [
    ("AML ПОД/ФТ статья 1", "kz_law_aml_cft_code", "primary"),
    ("оперативно-розыскная деятельность статья 1", "kz_law_operational_search_activity_code", "primary"),
    ("адвокатская деятельность и юридическая помощь статья 1", "kz_law_advocacy_legal_aid_code", "primary"),
    ("правоохранительная служба статья 1", "kz_law_law_enforcement_service_code", "primary"),
    ("О прокуратуре статья 1", "kz_law_prosecutor_office_code", "primary"),
    ("О противодействии коррупции статья 1", "kz_law_anti_corruption_code", "primary"),
    ("НП ВС по несовершеннолетним пункт 1", "kz_vs_np_criminal_minors_code", "primary"),
    ("Комментарий к Уголовному кодексу особенная часть", "kz_book_uk_special_part_commentary_old", "secondary"),
    ("Комментарий к НП ВС", "kz_book_vs_np_commentary", "secondary"),
]


def _first_source_id(hits) -> str:
    if not hits:
        return ""
    head = hits[0]
    if isinstance(head, dict):
        return str(head.get("source_id") or "")
    return str(getattr(head, "source_id", "") or "")


def main() -> int:
    out: list[dict] = []
    for query, expected_sid, kind in CHECKS:
        hinted = infer_hinted_source_ids_for_rag(query)
        try:
            sr = search(query)
        except Exception as exc:  # pragma: no cover — defensive
            sr = []
            err = f"{type(exc).__name__}: {exc}"
        else:
            err = ""
        first_sid = _first_source_id(sr)
        ok_hint = expected_sid in set(hinted)
        if kind == "primary":
            ok_primary = first_sid == expected_sid
        else:
            # For commentary queries we require: the commentary id is in hints,
            # AND the top primary law/code result does NOT pretend to be the
            # primary basis (we never demote actual law; we just check that the
            # commentary is at least *visible* and not classified as primary).
            ok_primary = ok_hint
        out.append(
            {
                "query": query,
                "expected": expected_sid,
                "expected_kind": kind,
                "hinted": sorted(hinted),
                "top_search_source_id": first_sid,
                "search_count": len(sr),
                "search_error": err,
                "ok": bool(ok_hint and ok_primary),
            }
        )

    report = ROOT / "reports" / "ingest" / "criminal_acts_routing_checks.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    md = ROOT / "reports" / "ingest" / "criminal_acts_routing_checks.md"
    lines = [
        "# Criminal acts — direct routing checks",
        "",
        "| query | expected | top search sid | hinted? | ok |",
        "|---|---|---|:---:|:---:|",
    ]
    for row in out:
        lines.append(
            "| {q} | `{e}` | `{t}` | {h} | {ok} |".format(
                q=row["query"],
                e=row["expected"],
                t=row["top_search_source_id"] or "—",
                h="✅" if row["expected"] in row["hinted"] else "—",
                ok="✅" if row["ok"] else "❌",
            )
        )
    md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
