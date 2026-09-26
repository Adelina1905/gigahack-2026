# Municipal data pipeline

## RAG v3: high-precision bilingual evidence

The production path now creates schema-v3 evidence units and publishes two verified,
versioned Qdrant collections behind atomic aliases:

- `municipal_evidence_current`: named `dense` and Romanian-aware BM25 `sparse` vectors;
- `municipal_catalog_current`: document titles and trusted metadata used as a separate
  discovery signal.

`citationText` is always exact source text. Titles occur only in `retrievalText` and
the document catalog, so a title can no longer appear as a duplicated body citation.
Bad passages are quarantined individually; only broken source identity, unreadable
input, or broken provenance blocks a complete document. The newest immutable version
is indexed by normal full runs.

Build and atomically publish a production index:

```powershell
python run_all.py --execute
```

Ask in Romanian or Russian:

```powershell
python 10_answer_question.py --question "Ce lucrări au fost planificate în sectorul Botanica?" --json --explain
```

The answerer performs dense and sparse retrieval, reciprocal-rank fusion, a maximum
of three passages per document, managed reranking, ambiguity detection, structured
claim generation, deterministic number/date/currency checks, and an independent
managed entailment check. Learned-service failures return `UNAVAILABLE` without an
unverified answer. Final evidence is renumbered contiguously as S1…Sn.

Configuration is versioned in `config/rag.v3.json`. The 100-case 60/40 Romanian/Russian
candidate benchmark is `evaluation/questions.v1.jsonl`. Its labels intentionally use
`reviewStatus=PENDING`; `municipal_rag.evaluation` refuses to score it until humans
approve every case. This prevents generated labels from being reported as measured
quality. Use `build_evaluation_candidates.py` to regenerate candidates, then review
and enrich relevant evidence, expected facts, ambiguity, contradiction, historical,
and unanswerable labels before tuning thresholds or claiming acceptance metrics.

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
       -> production (fully trusted only)
  -> 7. embeddings
  -> 8. vector database
  -> 9. retrieval tests

Any warning or error is stopped before production and recorded under
`data/09_review/<run-id>` without interrupting other documents.
```

The first six stages are format-independent after extraction. Source-specific
logic stays in step 2, so adding DOCX or a different website parser does not
change validation and chunking.

Important data rules:

- Originals are stored by content-derived document ID under `data/01_sources`.
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

Secrets may be provided as environment variables or in the ignored
`Manage Data/.env` file. The recognized names are `OPENROUTER_API_KEY`,
`CF_ACCESS_CLIENT_ID`, `CF_ACCESS_CLIENT_SECRET`, and (for remote Qdrant)
`QDRANT_API_KEY`. Existing process environment variables take precedence.

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

## Run collected corpus snapshots

The corpus collector stores immutable API JSON snapshots under
`Original Data/municipal_corpus`. Process the latest snapshot of every document
through stages 1–6 with one command:

```powershell
python run_corpus_pipeline.py
```

The runner maps API metadata automatically, preserves page-level citations, and
uses four workers by default. Every document receives one status:

- `READY`: clean, chunked, and eligible for the production database.
- `WARNING`: OCR, validation, citation, or data-quality review is required.
- `ERROR`: discovery, parsing, or a pipeline stage failed.

Warnings and errors never stop the rest of the batch. Use `--max-documents 5`
for a bounded batch or `--pipeline-workers N` to change document concurrency.

The runner also detects scraper exports laid out as
`<snapshot>/text/<source>/<sha1>.json`. These records are adapted in memory; the
snapshot is never edited. Invalid records, empty documents, pending OCR, low OCR
confidence, truncated OCR, and OCR timeouts are excluded from production and
reported independently. OCR completion is taken from the export's authoritative
`manifest.sqlite`; `needs_ocr_pages` alone does not mean OCR is still pending.
Process such an export by passing its root explicitly:

```powershell
python run_all.py `
  --input-root "Original Data/chisinau-corpus-20260926T0640Z" `
  --ready-only `
  --execute
```

Always use a bounded `--max-documents 5 --mock` run before the first production
import of a new export.

`run_all.py` streams live progress for document processing, embedding generation,
and Qdrant import. Each phase shows completed/total documents, percentage,
throughput, and an estimated remaining time while keeping the final stdout value
machine-readable JSON.

For normal operation, run document preparation and database indexing together:

```powershell
$env:OPENROUTER_API_KEY = "your-key"
python run_all.py --execute
```

`run_all.py` invokes `run_corpus_pipeline.py` followed by
`prepare_ai_database.py`. It generates missing embeddings with two workers,
imports documents sequentially, and reconciles Qdrant with the authoritative run
manifest. Run `python run_all.py --mock` for a no-cost integration test, or run it
without a mode flag for a dry run. Use `--verbose` only when per-document terminal
details are needed.

A full run removes stale Qdrant points for documents that are now warnings or
errors. A bounded `--max-documents N` run only reconciles those selected documents
and preserves all unprocessed database entries.

API collection remains opt-in because it can retrieve thousands of records. To
include it in the same command, set the Cloudflare credential environment
variables and add `--collect`:

```powershell
python run_all.py --collect --execute
```

Use `--collect-max-documents 5` for a bounded collection test.

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
| `07_embeddings` | Cached vectors matching the prepared chunks |
| `08_qdrant` | Persistent local vector database |
| `09_review/<run-id>` | Durable summary, manifest, and per-problem reports |

## Review reports and retries

Each run creates:

- `summary.json`, with compact counts and database consistency.
- `run-manifest.json`, the authoritative status and artifacts for every selected
  document.
- `documents/<document-id>.json`, for each warning or error, with the failed
  stage, issue code, retryability, original snapshot pointer, and completed
  artifact pointers.

`data/09_review/latest.json` is atomically updated to the newest run. Historical
run directories are preserved. Fix the source or stage problem and run the normal
command again; content hashes reuse unchanged artifacts and cached embeddings.
Review reports only contain pointers—the immutable originals are not duplicated.

## Embeddings and Romanian search

Only chunks whose `indexingStatus` is `READY` belong in the production Qdrant
collection. Keep review chunks in a separate collection or do not embed them.

The database builder generates only missing embeddings, caches their relationship
to the chunk files, and imports every prepared document into persistent local
Qdrant storage. Step 7 uses OpenRouter's Qwen3 Embedding 8B model. Keep the key
outside source code in the `OPENROUTER_API_KEY` environment variable:

```powershell
$env:OPENROUTER_API_KEY = "your-key"
python prepare_ai_database.py `
  --run-manifest "data/09_review/<run-id>/run-manifest.json" `
  --execute
```

The default collection is `municipal_documents` in `data/08_qdrant`. No separate
Qdrant server is required. To use a remote Qdrant instance instead, pass
`--qdrant-url` and set `QDRANT_API_KEY` when the server requires it.

For a connectivity test that makes no OpenRouter request, use a strictly isolated
mock collection:

```powershell
python prepare_ai_database.py `
  --run-manifest "data/09_review/<run-id>/run-manifest.json" `
  --mock
```

Mock vectors are never imported into the production collection and are not usable
for semantic search.

Search it with a Romanian question:

```powershell
python 09_search_qdrant.py `
  --text "Ce lucrări municipale sunt descrise?"
```

For a shorter interactive display, run:

```powershell
python test_romanian_search.py
```

Then type a Romanian question at the prompt. You can also supply it directly:

```powershell
python test_romanian_search.py --question "Câte instituții de învățământ general gestionează DGETS?"
```

Every returned result includes the exact citations and its indexing status.

## Step 10: grounded answers

Step 10 retrieves evidence, asks the OpenRouter chat model to answer in Romanian,
and validates every evidence identifier returned by the model:

```powershell
python 10_answer_question.py
```

Or pass the question directly:

```powershell
python 10_answer_question.py `
  --question "Când au avut loc verificările instituțiilor?"
```

The result explicitly reports one of `SUPPORTED`, `PARTIAL`, `NOT_FOUND`, or
`CONTRADICTION`. A source that is not production-ready also produces a separate
warning. Use `--json` when integrating the result into a website or API.

## Design references

- [Docling supported formats](https://docling-project.github.io/docling/usage/supported_formats/)
- [Docling OCR configuration](https://docling-project.github.io/docling/concepts/OCR/)
- [Docling structure-aware chunking](https://docling-project.github.io/docling/concepts/chunking/)
- [Trafilatura extraction API](https://trafilatura.readthedocs.io/en/latest/corefunctions.html)
- [W3C PROV-O](https://www.w3.org/TR/prov-o/)
- [JSON Schema Draft 2020-12](https://json-schema.org/draft/2020-12)
