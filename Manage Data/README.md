# Municipal data pipeline

This pipeline converts original municipal sources into small, searchable records
without losing the evidence needed to cite an answer. It is designed for Romanian
source documents; a Russian question should be translated or embedded with a
multilingual model at query time. The source corpus remains in Romanian.

## Architecture

```text
Original artifact
  -> 1. immutable snapshot + manifest
  -> 2. layout/content extraction
  -> 3. generic document + cited passages
  -> 4. deterministic dates/counts enrichment
  -> 5. schema, integrity, and citation validation
  -> 6. structure-aware chunks
       -> production (fully trusted)
       -> review (missing/uncertain evidence)
  -> 7. embeddings
  -> 8. vector database
  -> 9. retrieval tests
```

The first six stages are format-independent after extraction. Source-specific
logic stays in step 2, so adding DOCX or a different website parser does not
change validation and chunking.

Important data rules:

- Originals are stored by content-derived document ID under `data/v2/01_sources`.
- Every artifact is versioned with a SHA-256 suffix. Re-running unchanged input
  is idempotent; changed content creates another version instead of overwriting it.
- `citationText` preserves exact source wording. `searchText` is Unicode-normalized
  for retrieval. Never cite `searchText`.
- Facts are deterministic extractions attached to a passage; they are not an
  AI-generated summary.
- Each chunk carries exact quote, locator, source URL, document metadata, and
  stable IDs.
- Failed or incomplete provenance is routed to `review`; it is not production-ready.
- Dates are ISO 8601 where they can be resolved. Missing years are explicitly
  reported instead of guessed.

## Install

From this directory:

```powershell
python -m pip install -r requirements.txt
```

For OCR and complex PDF/Office layout extraction, install the optional profile:

```powershell
python -m pip install -r requirements-ocr.txt
```

The lightweight extractor uses Trafilatura for HTML and pypdf for text PDFs.
An image-only PDF is deliberately returned as `OCR_REQUIRED`; install and connect
Docling before it can be indexed. The runner stops after extraction with an
`indexingDecision` of `BLOCKED`. This prevents an empty or fabricated extraction.

## Run steps 1-6

```powershell
python run_pipeline.py "Original Data/information 1.txt" `
  --title "Evaluarea instituțiilor de învățământ" `
  --source-url "https://detsciocana.educ.md/evaluarea-institutiilor-de-invatamant-primar-si-secundar-ciclul-i-si-ii-catre-debutul-anului-de-studii-2024-2025/" `
  --source-type derived_web_text `
  --document-type webpage_article `
  --publisher "DETS Ciocana" `
  --published-date 2024-08-23
```

Use `--ready-only` when generating files intended to be imported into the
production vector collection. A review-only document will then generate zero
chunks rather than leaking unverified data into production.

Each stage also remains independently runnable with `python <script> --help`.

## Output directories

| Directory | Meaning |
|---|---|
| `01_sources` | Immutable original snapshots |
| `01_manifests` | Origin, language, publisher, URL, timestamp, hash |
| `02_extracted` | Format-adapter output with source locators |
| `03_structured` | Generic municipal document and passages |
| `04_enriched` | Cited dates, intervals, and numeric facts |
| `05_validated` | Quality report and indexing decision |
| `06_chunks` | JSONL records ready for embeddings or review |

## Current example status

`information 1.txt` is derived from a webpage rather than a saved raw HTML
snapshot. Its facts and line citations validate, but it is correctly routed to
`review` with `RAW_WEBPAGE_SNAPSHOT_MISSING`. To promote it to production, ingest
the original HTML response and run the pipeline on that snapshot.

`information.txt` contains event records without authoritative source URLs and
one date without a year. Those omissions are also explicit review issues.

## Embeddings and Romanian search

Only chunks whose `indexingStatus` is `READY` belong in the production Qdrant
collection. Keep review chunks in a separate collection or do not embed them.

Step 7 uses OpenRouter's Qwen3 Embedding 8B model. Keep the key outside source
code in the `OPENROUTER_API_KEY` environment variable:

```powershell
$env:OPENROUTER_API_KEY = "your-key"
python 07_generate_embeddings.py "data/v2/06_chunks/document__chunks__hash.jsonl" --execute
```

Import verified production chunks with step 8. Non-ready examples can only be
imported by explicitly using `--allow-review` and a collection whose name contains
`review` or `test`:

```powershell
python 08_import_to_qdrant.py `
  --chunks "data/v2/06_chunks/document__chunks__hash.jsonl" `
  --embeddings "data/embeddings/embeddings__model__hash.jsonl" `
  --collection "municipal_documents_review_qwen3_8b" `
  --allow-review
```

Search it with a Romanian question:

```powershell
python 09_search_qdrant.py `
  --text "Care este scopul evaluării instituțiilor?" `
  --collection "municipal_documents_review_qwen3_8b"
```

For a shorter interactive display, run:

```powershell
python test_romanian_search.py
```

Then type a Romanian question at the prompt. You can also supply it directly:

```powershell
python test_romanian_search.py --question "Câte instituții de învățământ general gestionează DGETS?"
```

Every returned result includes the exact citations and its indexing status. The
current example remains in the review collection because its raw HTML snapshot is
missing; this search setup is for retrieval evaluation, not production answers.

## Design references

- [Docling supported formats](https://docling-project.github.io/docling/usage/supported_formats/)
- [Docling OCR configuration](https://docling-project.github.io/docling/concepts/OCR/)
- [Docling structure-aware chunking](https://docling-project.github.io/docling/concepts/chunking/)
- [Trafilatura extraction API](https://trafilatura.readthedocs.io/en/latest/corefunctions.html)
- [W3C PROV-O](https://www.w3.org/TR/prov-o/)
- [JSON Schema Draft 2020-12](https://json-schema.org/draft/2020-12)
