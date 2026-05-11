from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run_script(script: str, args: list[str], *, rag_changed: bool = False) -> int:
    cmd = [sys.executable, str(ROOT / "scripts" / script), *args]
    completed = subprocess.run(cmd, cwd=str(ROOT), check=False)
    print(f"RAG_CHANGED = {str(rag_changed).lower()}")
    return completed.returncode


def add_common_approve_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")


def code_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    code = subparsers.add_parser("code")
    actions = code.add_subparsers(dest="action", required=True)

    inventory = actions.add_parser("inventory")
    inventory.add_argument("--source-id", required=True)

    import_cmd = actions.add_parser("import")
    import_cmd.add_argument("--file", required=True)
    import_cmd.add_argument("--source-id", required=True)
    import_cmd.add_argument("--title", required=True)
    import_cmd.add_argument("--expected-min", type=int, required=True)
    import_cmd.add_argument("--expected-max", type=int, required=True)
    import_cmd.add_argument("--doc-type", default="code_article")
    import_cmd.add_argument("--authority-level", default="code")
    import_cmd.add_argument("--status", default="active")
    import_cmd.add_argument("--effective-from", default=None)
    import_cmd.add_argument("--as-of-date", default=None)
    import_cmd.add_argument("--chapter-prefix", default="ch")
    import_cmd.add_argument("--industry", nargs="*", default=[])
    import_cmd.add_argument("--note", action="append", dest="notes", default=[])

    diff = actions.add_parser("diff")
    diff.add_argument("--batch", required=True)
    diff.add_argument("--source-id", required=True)

    approve = actions.add_parser("approve")
    approve.add_argument("--batch", required=True)
    approve.add_argument("--source-id", required=True)
    approve.add_argument("--mode", choices=["missing-only"], default="missing-only")
    approve.add_argument("--from-article", type=int)
    approve.add_argument("--to-article", type=int)
    add_common_approve_args(approve)


def law_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Standalone laws (law_article / authority law), batches under staging/laws/."""

    law = subparsers.add_parser("law")
    actions = law.add_subparsers(dest="action", required=True)

    import_cmd = actions.add_parser("import")
    import_cmd.add_argument("--file", required=True)
    import_cmd.add_argument("--source-id", required=True)
    import_cmd.add_argument("--title", required=True)
    import_cmd.add_argument("--expected-min", type=int, required=True)
    import_cmd.add_argument("--expected-max", type=int, required=True)
    import_cmd.add_argument("--doc-type", default="law_article")
    import_cmd.add_argument("--authority-level", default="law")
    import_cmd.add_argument("--status", default="active")
    import_cmd.add_argument("--effective-from", default=None)
    import_cmd.add_argument("--as-of-date", default=None)
    import_cmd.add_argument("--chapter-prefix", default="ch")
    import_cmd.add_argument("--industry", nargs="*", default=[])
    import_cmd.add_argument("--note", action="append", dest="notes", default=[])

    diff = actions.add_parser("diff")
    diff.add_argument("--batch", required=True)
    diff.add_argument("--source-id", required=True)

    approve = actions.add_parser("approve")
    approve.add_argument("--batch", required=True)
    approve.add_argument("--source-id", required=True)
    approve.add_argument("--mode", choices=["missing-only"], default="missing-only")
    approve.add_argument("--from-article", type=int)
    approve.add_argument("--to-article", type=int)
    add_common_approve_args(approve)


def book_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    book = subparsers.add_parser("book")
    actions = book.add_subparsers(dest="action", required=True)

    import_cmd = actions.add_parser("import")
    import_cmd.add_argument("--file", required=True)
    import_cmd.add_argument("--book-title", required=True)
    import_cmd.add_argument("--book-slug", default="auto")

    diff = actions.add_parser("diff")
    diff.add_argument("--batch", required=True)

    approve = actions.add_parser("approve")
    approve.add_argument("--batch", required=True)
    add_common_approve_args(approve)


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="kind", required=True)
    code_parser(subparsers)
    law_parser(subparsers)
    book_parser(subparsers)
    args = parser.parse_args()

    if args.kind == "code" and args.action == "inventory":
        raise SystemExit(run_script("inventory_rag.py", ["--source-id", args.source_id]))

    if args.kind == "code" and args.action == "import":
        cmd_args = [
            "--file", args.file,
            "--source-id", args.source_id,
            "--code-title", args.title,
            "--expected-min", str(args.expected_min),
            "--expected-max", str(args.expected_max),
            "--doc-type", args.doc_type,
            "--authority-level", args.authority_level,
            "--status", args.status,
            "--chapter-prefix", args.chapter_prefix,
        ]
        if args.effective_from:
            cmd_args.extend(["--effective-from", args.effective_from])
        if args.as_of_date:
            cmd_args.extend(["--as-of-date", args.as_of_date])
        for ind in (args.industry or []):
            cmd_args.extend(["--industry", ind])
        for note in (args.notes or []):
            cmd_args.extend(["--note", note])
        raise SystemExit(run_script("import_code_to_staging.py", cmd_args))

    if args.kind == "law" and args.action == "import":
        cmd_args = [
            "--file",
            args.file,
            "--source-id",
            args.source_id,
            "--code-title",
            args.title,
            "--expected-min",
            str(args.expected_min),
            "--expected-max",
            str(args.expected_max),
            "--doc-type",
            args.doc_type,
            "--authority-level",
            args.authority_level,
            "--status",
            args.status,
            "--chapter-prefix",
            args.chapter_prefix,
            "--staging-root",
            "laws",
        ]
        if args.effective_from:
            cmd_args.extend(["--effective-from", args.effective_from])
        if args.as_of_date:
            cmd_args.extend(["--as-of-date", args.as_of_date])
        for ind in args.industry or []:
            cmd_args.extend(["--industry", ind])
        for note in args.notes or []:
            cmd_args.extend(["--note", note])
        raise SystemExit(run_script("import_code_to_staging.py", cmd_args))

    if args.kind == "law" and args.action == "diff":
        raise SystemExit(run_script("diff_rag_batch.py", ["--batch", args.batch, "--source-id", args.source_id]))

    if args.kind == "law" and args.action == "approve":
        cmd_args = ["--batch", args.batch, "--source-id", args.source_id, "--mode", args.mode]
        if args.from_article is not None:
            cmd_args.extend(["--from-article", str(args.from_article)])
        if args.to_article is not None:
            cmd_args.extend(["--to-article", str(args.to_article)])
        cmd_args.append("--apply" if args.apply else "--dry-run")
        raise SystemExit(run_script("approve_rag_batch.py", cmd_args, rag_changed=args.apply))

    if args.kind == "code" and args.action == "diff":
        raise SystemExit(run_script("diff_rag_batch.py", ["--batch", args.batch, "--source-id", args.source_id]))

    if args.kind == "code" and args.action == "approve":
        cmd_args = ["--batch", args.batch, "--source-id", args.source_id, "--mode", args.mode]
        if args.from_article is not None:
            cmd_args.extend(["--from-article", str(args.from_article)])
        if args.to_article is not None:
            cmd_args.extend(["--to-article", str(args.to_article)])
        cmd_args.append("--apply" if args.apply else "--dry-run")
        raise SystemExit(run_script("approve_rag_batch.py", cmd_args, rag_changed=args.apply))

    if args.kind == "book" and args.action == "import":
        raise SystemExit(
            run_script(
                "import_book_to_staging.py",
                ["--file", args.file, "--book-title", args.book_title, "--book-slug", args.book_slug],
            )
        )

    if args.kind == "book" and args.action == "diff":
        raise SystemExit(run_script("diff_book_batch.py", ["--batch", args.batch]))

    if args.kind == "book" and args.action == "approve":
        cmd_args = ["--batch", args.batch, "--apply" if args.apply else "--dry-run"]
        raise SystemExit(run_script("approve_book_batch.py", cmd_args, rag_changed=args.apply))

    parser.error("unsupported command")


if __name__ == "__main__":
    main()
