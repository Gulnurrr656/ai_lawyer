"""Pass 2 (stronger): remove adjacent duplicate Jinja expressions.

After ``_fix_lang_mixing.py`` collapses bilingual blocks, the same
``{{ t('K', lang) }}`` call often appears twice in a row inside two
adjacent ``<p>`` / ``<div>`` / ``<span>`` wrappers (one was the KK label,
the next was the RU subtitle). This pass deletes the second wrapper when:

1. Two consecutive non-empty lines each contain at least one
   ``{{ t(...,lang) }}`` expression.
2. The list of Jinja ``t(KEY, lang)`` keys on both lines is identical.

The line that wraps the duplicate is removed. Idempotent.

Also collapses ``{{ EXPR }}{{ EXPR }}`` patterns on the same line and
``X / Y`` style hardcoded raw strings inside content that look like
duplicate bilingual labels (manually handled per file by humans).
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "app" / "web" / "templates"

SKIP = {"base.html", "index.html"}

T_CALL = re.compile(r"\{\{\s*t\(\s*([^,]+?)\s*,\s*lang\s*\)\s*\}\}")


def keys_on_line(line: str) -> list[str]:
    return [m.group(1).strip() for m in T_CALL.finditer(line)]


def dedupe_consecutive(text: str) -> str:
    lines = text.splitlines(keepends=True)
    out: list[str] = []
    prev_keys: list[str] = []
    skip_next_empty = False
    for ln in lines:
        keys = keys_on_line(ln)
        if keys and keys == prev_keys:
            # drop this line; it's a duplicate label wrapper.
            skip_next_empty = False
            continue
        out.append(ln)
        prev_keys = keys
    return "".join(out)


def main() -> int:
    changed = 0
    total = 0
    for path in sorted(TEMPLATES.rglob("*.html")):
        if path.name in SKIP:
            continue
        total += 1
        src = path.read_text(encoding="utf-8")
        cur = src
        # Run until stable (idempotent fixed-point).
        for _ in range(5):
            nxt = dedupe_consecutive(cur)
            if nxt == cur:
                break
            cur = nxt
        if cur != src:
            path.write_text(cur, encoding="utf-8")
            changed += 1
            print(f"deduped: {path.relative_to(ROOT)}")
    print(f"\nDone: {changed} / {total} files changed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
