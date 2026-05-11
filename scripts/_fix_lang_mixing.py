"""One-shot template sweep: drop slash labels, convert hardcoded 'kk'/'ru'.

Run once after rewriting ``product_copy.py`` to enforce single-language
rendering. Idempotent.

Transforms applied per Jinja file under ``app/web/templates``:

1. Slash dual-label patterns are collapsed to one language call:
       {{ t('K', 'kk') }} / {{ t('K', 'ru') }}   ->   {{ t('K', lang) }}
2. Pipe dual labels:
       {{ t('K', 'kk') }} | {{ t('K', 'ru') }}   ->   {{ t('K', lang) }}
3. Bilingual middle-dot blocks like:
       {{ t('K', 'kk') }} · {{ t('K', 'ru') }}   ->   {{ t('K', lang) }}
4. Remaining hardcoded ``t('K', 'kk')`` / ``t('K', 'ru')`` calls are
   switched to ``t('K', lang)``.
5. Inline element ``lang="kk"`` / ``lang="ru"`` attributes are removed
   (the document already declares ``<html lang="...">``).

The script never deletes content; it only removes attributes and merges
duplicate labels.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "app" / "web" / "templates"

# Skip files we've already manually rewritten / templates we don't want
# clobbered by regex sweep.
SKIP = {
    "base.html",        # already cleaned manually
    "index.html",       # already rewritten manually
}

# Patterns =================================================================

# 1) {{ t('K', 'kk') }} <sep> {{ t('K', 'ru') }}  -> {{ t('K', lang) }}
DUAL_TT = re.compile(
    r"\{\{\s*t\(\s*('[^']+'|\"[^\"]+\")\s*,\s*'kk'\s*\)\s*\}\}"  # KK call
    r"\s*[/|·]\s*"                                                  # separator
    r"\{\{\s*t\(\s*\1\s*,\s*'ru'\s*\)\s*\}\}"                     # RU call same key
)

# 2) Plain hardcoded 'kk' / 'ru' params (apply after step 1 collapses pairs).
SINGLE_KK = re.compile(r"(\bt\([^)]*?),\s*'kk'\s*\)")
SINGLE_RU = re.compile(r"(\bt\([^)]*?),\s*'ru'\s*\)")

# 3) Inline element lang attributes (kk/ru) — drop them. Keep en/zh/etc.
INLINE_LANG_ATTR = re.compile(r'\s+lang="(kk|ru)"')

# Slash labels in literal text like "X / Y" or "{{ t('K', lang) }} / {{ t('K', lang) }}"
# (after step 2 they're duplicated). Collapse "{{ expr }} / {{ expr }}" -> "{{ expr }}".
DUP_EXPR_SLASH = re.compile(
    r"(\{\{[^{}]+\}\})\s*[/|·]\s*\1"
)


def transform(text: str) -> str:
    text = DUAL_TT.sub(lambda m: f"{{{{ t({m.group(1)}, lang) }}}}", text)
    text = SINGLE_KK.sub(lambda m: f"{m.group(1)}, lang)", text)
    text = SINGLE_RU.sub(lambda m: f"{m.group(1)}, lang)", text)
    text = DUP_EXPR_SLASH.sub(lambda m: m.group(1), text)
    text = INLINE_LANG_ATTR.sub("", text)
    return text


def main() -> int:
    changed = 0
    total = 0
    for path in sorted(TEMPLATES.rglob("*.html")):
        if path.name in SKIP:
            continue
        total += 1
        src = path.read_text(encoding="utf-8")
        out = transform(src)
        if out != src:
            path.write_text(out, encoding="utf-8")
            changed += 1
            print(f"updated: {path.relative_to(ROOT)}")
    print(f"\nDone: {changed} / {total} files changed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
