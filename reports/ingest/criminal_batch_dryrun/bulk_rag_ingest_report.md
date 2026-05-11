# Bulk RAG Ingest — Dry Run Report

_Generated_: 2026-05-11T10:55:58

## Totals

- registered sources: **10**
- enabled and present: **9**
- ready to apply: **8**
- no-op (already in rag): **1**
- blocked (errors/conflicts/mojibake): **0**
- disabled in registry: **1**
- missing on disk: **0**

## Ready to apply (green)

| source_id | type | file | blocks | new | conflicts | mojibake | apply_allowed | reason |
|---|---|---|---:|---:|---:|---:|:---:|---|
| `kz_law_aml_cft_code` | law | `inbox/acts/kz_law_aml_cft_code.docx` | 34 | 34 | 0 | 0 | ✅ |  |
| `kz_law_operational_search_activity_code` | law | `inbox/acts/kz_law_operational_search_activity_code.docx` | 28 | 28 | 0 | 0 | ✅ |  |
| `kz_law_law_enforcement_service_code` | law | `inbox/acts/kz_law_law_enforcement_service_code.docx` | 98 | 98 | 0 | 0 | ✅ |  |
| `kz_law_prosecutor_office_code` | law | `inbox/acts/kz_law_prosecutor_office_code.docx` | 49 | 49 | 0 | 0 | ✅ |  |
| `kz_law_anti_corruption_code` | law | `inbox/acts/kz_law_anti_corruption_code.docx` | 33 | 33 | 0 | 0 | ✅ |  |
| `kz_vs_np_criminal_minors_code` | vs_np | `inbox/vs_np/criminal/kz_vs_np_criminal_minors_code.docx` | 39 | 39 | 0 | 0 | ✅ |  |
| `kz_book_vs_np_commentary` | commentary | `inbox/books/criminal/kz_book_vs_np_commentary.docx` | 1 | 1 | 0 | 0 | ✅ |  |
| `kz_book_uk_special_part_commentary_old` | commentary | `inbox/books/criminal/kz_book_uk_special_part_commentary_old.docx` | 18 | 18 | 0 | 0 | ✅ |  |

## No-op (already in rag, no new blocks)

| source_id | type | file | blocks | new | conflicts | mojibake | apply_allowed | reason |
|---|---|---|---:|---:|---:|---:|:---:|---|
| `kz_law_advocacy_legal_aid_code` | law | `inbox/acts/kz_law_advocacy_legal_aid_code.docx` | 106 | 0 | 0 | 0 | — | no_op |

## Blocked

_none_

## Missing on disk

_none_

## Disabled in registry

| source_id | type | file | blocks | new | conflicts | mojibake | apply_allowed | reason |
|---|---|---|---:|---:|---:|---:|:---:|---|
| `kz_vs_np_criminal_amendments_code` | vs_np | `inbox/vs_np/criminal/kz_vs_np_criminal_amendments_code.docx` | 0 | 0 | 0 | 0 | — |  |
