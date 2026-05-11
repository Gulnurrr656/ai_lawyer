"""Direct routing checks for criminal RAG sources (no LLM)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.retriever.search import search  # noqa: E402

CHECKS = [
    {"q": "статья 1 УК РК", "expect_source": "kz_uk_code_full", "expect_article": "1",
     "note": "Option C: full UK preferred over legacy partial"},
    {"q": "статья 999 УК РК", "expect_source": None, "expect_article": None,
     "expect_empty_or_no_match": True},
    {"q": "статья 1 УПК РК", "expect_source": "kz_upk_code", "expect_article": "1"},
    {"q": "статья 1 УИК РК", "expect_source": "kz_uik_code", "expect_article": "1"},
    {"q": "О судебном приговоре пункт 1",
     "expect_source": "kz_vs_np_criminal_sentence_code", "expect_point": "1"},
    {"q": "О назначении уголовного наказания пункт 1",
     "expect_source": "kz_vs_np_criminal_punishment_code", "expect_point": "1"},
    {"q": "О практике рассмотрения уголовных дел в апелляционном порядке пункт 1",
     "expect_source": "kz_vs_np_criminal_appeal_code", "expect_point": "1"},
    {"q": "О применении законодательства, регламентирующего рассмотрение уголовных дел в кассационном порядке пункт 1",
     "expect_source": None, "expect_empty_or_no_match": True,
     "note": "missing on disk → expect NOT_FOUND"},
    {"q": "О поступившему уголовному делу пункт 1",
     "expect_source": None, "expect_empty_or_no_match": True,
     "note": "missing on disk → expect NOT_FOUND"},
    {"q": "О рассмотрении уголовных дел в сокращенном порядке пункт 1",
     "expect_source": None, "expect_empty_or_no_match": True,
     "note": "missing on disk → expect NOT_FOUND"},
]


def _first(results):
    if not results:
        return {}
    return results[0]


def _doc_article(doc):
    arts = doc.get("articles") or []
    if isinstance(arts, list) and arts:
        first = arts[0]
        if isinstance(first, dict):
            n = first.get("article")
            if n is not None:
                return str(n)
    return None


def _doc_point(doc):
    pts = doc.get("points") or []
    if isinstance(pts, list) and pts:
        first = pts[0]
        if isinstance(first, dict):
            n = first.get("number") or first.get("point") or first.get("id")
            if n is not None:
                return str(n)
    p = doc.get("point") or {}
    if isinstance(p, dict):
        n = p.get("number")
        if n is not None:
            return str(n)
    return None


rows = []
for c in CHECKS:
    res = search(c["q"])
    top = _first(res)
    actual_sid = (top.get("source_id") or top.get("source") or "") if top else ""
    actual_article = _doc_article(top) if top else None
    actual_point = _doc_point(top) if top else None

    expect_empty = c.get("expect_empty_or_no_match", False)
    expect_sid = c.get("expect_source")
    expect_art = c.get("expect_article")
    expect_pt = c.get("expect_point")

    if expect_empty:
        ok = (not res) or (expect_sid and actual_sid != expect_sid)
        if expect_sid is None:
            ok = not res
    else:
        ok = (actual_sid == expect_sid)
        if expect_art is not None:
            ok = ok and (actual_article == expect_art)
        if expect_pt is not None:
            ok = ok and (actual_point == expect_pt)

    rows.append({
        "query": c["q"],
        "expected_source": expect_sid or "<empty/NOT_FOUND>",
        "expected_article_or_point": expect_art or expect_pt or ("<none>" if expect_empty else ""),
        "result_count": len(res),
        "actual_source": actual_sid or "<none>",
        "actual_article": actual_article,
        "actual_point": actual_point,
        "ok": ok,
        "note": c.get("note", ""),
    })

print("| # | query | expected | actual_source | actual_n | result_count | ok |")
print("|---|---|---|---|---|---:|:---:|")
for i, r in enumerate(rows, 1):
    sid = r["actual_source"]
    n = r["actual_article"] or r["actual_point"] or "—"
    print(f"| {i} | {r['query'][:60]} | {r['expected_source']} {r['expected_article_or_point']} | "
          f"{sid} | {n} | {r['result_count']} | {'✅' if r['ok'] else '❌'} |")

(ROOT / "reports" / "ingest").mkdir(parents=True, exist_ok=True)
out = ROOT / "reports" / "ingest" / "criminal_routing_checks.json"
out.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
print()
print("written:", out)
ok_n = sum(1 for r in rows if r["ok"])
print(f"summary: {ok_n}/{len(rows)} pass")
