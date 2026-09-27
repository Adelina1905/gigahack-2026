# Strict-RAG evaluation harness

Checks the municipal assistant's core rule against a live `/v1/chat` endpoint. Every reply must be one of three things:

- an answer in which each sentence cites a relevant document (`[S#]` markers),
- a clarification that offers only relevant, distinct documents, or
- an explicit `NOT_FOUND` with a reason.

It must never cite unrelated documents or give an uncited answer.

Files:

| File | Purpose |
| --- | --- |
| `questions.json` | 45 cases (ro/ru/en) grounded in real `documentId`s of the current Qdrant index |
| `eval_rag.py` | HTTP client, pure scoring functions, JSON report and human summary (stdlib only) |
| `test_eval_rag.py` | Unit tests for the scoring, using hand-written replies (no network) |
| `baseline-8000.json` | One baseline run against the shared service on port 8000 (older code, no `reason`/`flags`) |

## Running

Start the service you want to measure (see `CLAUDE.md`), then:

```
cd "Manage Data/eval"
../.venv/bin/python eval_rag.py                                   # default --url http://127.0.0.1:8001/v1/chat
../.venv/bin/python eval_rag.py --url http://127.0.0.1:8000/v1/chat --out report.json
../.venv/bin/python eval_rag.py --only off-pizza-ro,year-grade1-2026-start-ro
../.venv/bin/python -m unittest test_eval_rag                     # scoring tests
../.venv/bin/python eval_rag.py --rescore report.json --out report.json   # re-score saved replies, no service calls
```

The harness uses only the standard library, so any Python 3.11+ works in place of `../.venv/bin/python`. Each one uses a fresh UUID `chatId` and an empty history. Progress goes to stderr, and the summary goes to stdout. `--out` writes the full report: metrics, plus the per-case checks, failures, latency and a compact copy of the reply. `--timeout` sets the per-request limit (default 240 s). `--rescore REPORT` scores the replies saved in an earlier report against the current `questions.json` and scoring, without calling the service. Use it after you edit expectations.

### Checking progress during a run

A full run takes 10–15 minutes. After every case, the harness rewrites a small JSON progress file: by default `<out>.progress.json` next to `--out`, or wherever `--progress FILE` points. The file holds `done`/`total`, `passed`/`failed`, `lastCase`, `elapsedS`, an `etaS` estimate from the average time per case so far, and `finished`. So a run started in the background can be checked from another shell:

```
cat report.json.progress.json
```

The stderr line for each case also shows the ETA.

### Running cases in parallel

`--concurrency N` (default 4) keeps N questions in flight at once, which cuts a full run from about 10–15 minutes to about 3–4. The report keeps the `questions.json` order. Two caveats:

- Latencies measured under concurrency include queueing on the service and OpenRouter, so use `--concurrency 1` when latency itself is what you're measuring.
- Use `--concurrency 1` against a shared service, such as the :8000 one serving both staging stacks, so real users aren't slowed down.

Exit codes: `0` means no unrelated citation and no uncited answer occurred. `1` means at least one did. Other failures, such as a wrong status or a missing value, show up in the report but do not change the exit code. `2` means the cases file could not be loaded.

**Cost:** each case runs the full RAG pipeline, so it costs roughly 4–6 OpenRouter calls: embedding, rerank, generation, verification and sometimes a correction round. A full run is about 200–270 calls and takes around 10–20 minutes. Use `--only` while you iterate.

## Metrics

| Metric | Definition |
| --- | --- |
| unrelated-citation rate | Citations outside the case's acceptable set, divided by all citations in cases that define relevance. On `off_topic` and `wrong_period` cases (`maxCitations: 0`), every citation counts as unrelated. Target 0. |
| uncited-answer rate | Answer-bearing replies (`SUPPORTED`/`PARTIAL`/`CONTRADICTION`, or an `llm`/`demo` mode answer) with no citations, or with no `[S#]` marker that matches a citation. The report also gives the share of sentences without a marker, for information only. |
| false NOT_FOUND rate | `NOT_FOUND` on `answerable`, `yearly_topic` and `duplicate_heavy` cases. |
| clarification precision | Clarification choices inside the acceptable set, divided by all scored choices. The report also shows how many `ambiguous` cases got a clarification. |
| outdated-source rate | `yearly_topic` cases that cite or offer a `forbiddenDocumentIds` entry, such as an older year's copy. |
| duplicate choices | Choices that repeat an earlier one: the same `documentId`, the same normalised label, or a document from the same `duplicateGroups` entry. |
| p50 / p95 latency | Nearest-rank percentiles over the successful requests. |

When a reply has no `reason` or `flags` (the older service), the reason check is marked `n/a` and the other checks are still scored.

## Case format

```json
{
  "id": "unique-kebab-id",
  "question": "…",
  "language": "ro | ru | en",
  "kind": "answerable | off_topic | wrong_period | lacks_value | ambiguous | yearly_topic | duplicate_heavy",
  "expect": {
    "status": ["SUPPORTED", "PARTIAL"],
    "reasons": ["NO_RELEVANT_EVIDENCE"],
    "maxCitations": 0,
    "acceptableDocumentIds": ["municipal-…"],
    "acceptableTitlePatterns": ["regex on citation title / choice label"],
    "acceptableUrlPatterns": ["regex on citation url"],
    "requiredDocumentIds": ["municipal-…"],
    "forbiddenDocumentIds": ["municipal-…"],
    "duplicateGroups": [["municipal-a", "municipal-b"]],
    "answerPattern": "regex the answer must contain when SUPPORTED/PARTIAL",
    "valuePattern": "lacks_value: regex for the value; an answer without it fails"
  }
}
```

- `status` is required. The other fields are optional, and a check whose field is missing is `n/a`.
- `reasons` is only checked when the status is `NOT_FOUND` and the reply carries a `reason`.
- A citation or choice is relevant when its `documentId` is in `acceptableDocumentIds`, or its title/label matches `acceptableTitlePatterns`, or its url matches `acceptableUrlPatterns`. The regexes are case-insensitive.
- Every id in `requiredDocumentIds` must appear among the citations. `forbiddenDocumentIds` count as outdated, not as unrelated.
- A `NEEDS_CLARIFICATION` reply must offer at least 2 distinct choices.

## Adding cases

1. Find real documents in Qdrant without writing to it. `municipal_catalog_current` holds one point per document, with payload `documentId`, `title`, `sourceUrl`, `publisher`, `publishedDate`, `district` and `category`. `municipal_evidence_current` holds the chunks, with `documentId`, `text` and `metadata.*`. For example:

   ```
   curl -s -X POST localhost:6333/collections/municipal_evidence_current/points/scroll \
     -H 'content-type: application/json' \
     -d '{"limit":10,"with_payload":["documentId","text","metadata.title"],"filter":{"must":[{"key":"text","match":{"text":"teren de fotbal"}}]}}'
   ```

   To look up a single document, filter on `{"key":"documentId","match":{"value":"municipal-…"}}`.
2. Read the evidence text before you write `answerPattern`. For `lacks_value`, make sure that no chunk of the relevant documents actually contains the value.
3. For yearly or republished topics, list the older copies in `forbiddenDocumentIds` and the republished copies in `duplicateGroups`.
4. Run `python -m unittest test_eval_rag`. It validates the file shape. Then run the new case with `--only`.

Document ids come from the current index build. After a reindex that changes the ids, check the cases again. A quick way is to grep every `municipal-…` id against a catalog scroll.
