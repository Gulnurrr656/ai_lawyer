# RAG Ingest Runbook

This project uses a staging-first ingest flow. Do not write new source files directly into `rag/`.

## Core Rules

- One legal block equals one JSON file.
- Code sources: one article equals one JSON file.
- Book sources: one section, paragraph, or semantic block equals one JSON file.
- Source text must not be rewritten, shortened, or paraphrased.
- All imports go to `staging/` first.
- Production `rag/` changes only after diff, dry-run approve, and explicit apply.
- Codes use `authority_level = code`.
- Books and commentary use `authority_level = commentary`.

## Folders

- Put code DOCX/TXT/PDF files in `inbox/codes/`.
- Put book DOCX/TXT/PDF files in `inbox/books/`.
- Code batches are created in `staging/codes/<source_id>_<date_time>/`.
- Book batches are created in `staging/books/<book_slug>_<date_time>/`.
- Code approve writes to `rag/<source_id>/` only with explicit `--apply`.
- Book approve writes to `rag/kz_legal_books/<book_slug>/` only with explicit `--apply`.

## Code Ingest

Inventory current RAG:

```powershell
python scripts/ingest_source.py code inventory --source-id kz_family_code
```

Import a code file to staging:

```powershell
python scripts/ingest_source.py code import --file inbox/codes/family_code.docx --source-id kz_family_code --title "Кодекс Республики Казахстан О браке (супружестве) и семье" --expected-min 1 --expected-max 283
```

Diff the batch:

```powershell
python scripts/ingest_source.py code diff --batch staging/codes/<batch_name> --source-id kz_family_code
```

Dry-run approve:

```powershell
python scripts/ingest_source.py code approve --batch staging/codes/<batch_name> --source-id kz_family_code --mode missing-only --from-article 145 --to-article 283 --dry-run
```

Real approve requires explicit `--apply`:

```powershell
python scripts/ingest_source.py code approve --batch staging/codes/<batch_name> --source-id kz_family_code --mode missing-only --from-article 145 --to-article 283 --apply
```

## Book Ingest

Import a book to staging:

```powershell
python scripts/ingest_source.py book import --file inbox/books/book.docx --book-title "Название книги" --book-slug auto
```

Diff the book batch:

```powershell
python scripts/ingest_source.py book diff --batch staging/books/<batch_name>
```

Dry-run approve:

```powershell
python scripts/ingest_source.py book approve --batch staging/books/<batch_name> --dry-run
```

Real approve requires explicit `--apply`:

```powershell
python scripts/ingest_source.py book approve --batch staging/books/<batch_name> --apply
```

## What Staging Means

`staging/` is a review area. It is safe to create, inspect, delete, and recreate batches there. Files in staging are not used by the bot until approved into `rag/`.

## What Diff Means

Diff compares a staging batch with the current production RAG. It identifies new, same, changed, conflicting, duplicate, and invalid files. Diff never moves files into `rag/`.

## What Dry-Run Means

Dry-run approve shows what would be copied and what would be skipped. It must be clean before real approve. Dry-run does not create backups and does not change `rag/`.

## When Approve Is Allowed

Approve is allowed only after:

- inventory has been reviewed;
- import report has no unexpected errors;
- diff report has no blocking conflicts for the intended scope;
- dry-run approve shows exactly the intended files;
- the user explicitly confirms apply.

## Errors And Conflicts

If `errors` or `conflicts` appear:

- stop the ingest;
- inspect the specific file and report;
- fix the staging/import tooling or source file;
- recreate the staging batch;
- repeat diff and dry-run.

Do not fix conflicts by editing production `rag/` directly.

## Verify After Approve

After real approve, verify via RAG query:

```powershell
python main.py rag-query "Что говорит статья 145 семейного кодекса РК?"
python main.py rag-query "Что написано в статье 9999?"
```

The second command must return "Информация не найдена в базе данных".

## Why Not Write Directly To RAG

Direct writes bypass validation, diff, conflict detection, backups, and review. That can overwrite hand-curated legal text, break article lookup, or silently add malformed JSON that the retriever cannot use correctly.
