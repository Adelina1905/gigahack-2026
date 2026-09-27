"""Evaluation harness for the strict municipal RAG chat endpoint.

Sends every case in questions.json to POST /v1/chat (fresh chatId, empty history),
scores each reply against the case expectations and prints a JSON report plus a
human summary. Scoring is a set of pure functions (`score_case`, `aggregate`) so it
can be tested without a network. Standard library only.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
import threading
import time
import unicodedata
import urllib.error
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_URL = "http://127.0.0.1:8001/v1/chat"
DEFAULT_CASES = Path(__file__).with_name("questions.json")

PASS, FAIL, NA = "pass", "fail", "n/a"
ANSWER_STATUSES = {"SUPPORTED", "PARTIAL", "CONTRADICTION"}
# Kinds whose question the index can answer; a NOT_FOUND on them is a false NOT_FOUND.
ANSWERABLE_KINDS = {"answerable", "yearly_topic", "duplicate_heavy"}
MARKER_RE = re.compile(r"\[S(\d+)\]")
# Split after sentence punctuation unless citation markers follow it ("… lei. [S1]" stays one sentence).
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?…])\s+(?!\[S\d)|\n+")


# ---------------------------------------------------------------- helpers

def normalize_label(text: str | None) -> str:
    """Case-, accent- and punctuation-insensitive form used to spot duplicate choices."""
    folded = unicodedata.normalize("NFKD", (text or "").casefold())
    folded = "".join(ch for ch in folded if not unicodedata.combining(ch))
    return " ".join(re.sub(r"[^\w]+", " ", folded).split())


def _search(patterns: list[str], text: str | None) -> bool:
    return bool(text) and any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns)


def has_relevance_rule(expect: dict[str, Any]) -> bool:
    return any(expect.get(key) for key in ("acceptableDocumentIds", "acceptableTitlePatterns", "acceptableUrlPatterns"))


def is_acceptable(item: dict[str, Any], expect: dict[str, Any]) -> bool:
    """True when a citation or clarification choice points at a document the case accepts."""
    if item.get("documentId") and item["documentId"] in set(expect.get("acceptableDocumentIds") or []):
        return True
    title = item.get("title") or item.get("label")
    if _search(expect.get("acceptableTitlePatterns") or [], title):
        return True
    return _search(expect.get("acceptableUrlPatterns") or [], item.get("url"))


def citation_markers(answer: str | None) -> list[int]:
    return [int(value) for value in MARKER_RE.findall(answer or "")]


def citation_labels(citations: list[dict[str, Any]]) -> set[int]:
    """Marker numbers the citations answer to: their `id` ("S3") or, without one, their position."""
    labels = set()
    for index, item in enumerate(citations, 1):
        match = re.fullmatch(r"S(\d+)", str(item.get("id") or ""))
        labels.add(int(match.group(1)) if match else index)
    return labels


def uncited_sentences(answer: str | None) -> tuple[int, int]:
    """(sentences without an [S#] marker, sentences) ignoring headings, list stubs and short fragments."""
    sentences = []
    for part in SENTENCE_SPLIT_RE.split(answer or ""):
        stripped = part.strip().lstrip("-*•> ").strip()
        if stripped.startswith("#") or len(MARKER_RE.sub("", stripped).strip()) < 25:
            continue
        sentences.append(stripped)
    missing = sum(1 for sentence in sentences if not MARKER_RE.search(sentence))
    return missing, len(sentences)


def duplicate_choices(choices: list[dict[str, Any]], groups: list[list[str]]) -> int:
    """Number of choices that repeat an earlier one (same document, same label, or same duplicate group)."""
    group_of = {doc_id: index for index, group in enumerate(groups) for doc_id in group}
    seen_docs, seen_labels, seen_groups = set(), set(), set()
    duplicates = 0
    for choice in choices:
        doc_id = choice.get("documentId")
        label = normalize_label(choice.get("label"))
        group = group_of.get(doc_id)
        if (doc_id and doc_id in seen_docs) or (label and label in seen_labels) or (group is not None and group in seen_groups):
            duplicates += 1
        if doc_id:
            seen_docs.add(doc_id)
        if label:
            seen_labels.add(label)
        if group is not None:
            seen_groups.add(group)
    return duplicates


def percentile(values: list[float], q: float) -> float | None:
    """Nearest-rank percentile, q in (0, 100]."""
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(q / 100 * len(ordered)))
    return ordered[rank - 1]


# ---------------------------------------------------------------- scoring

def score_case(case: dict[str, Any], response: dict[str, Any] | None, latency_ms: float | None = None,
               error: str | None = None) -> dict[str, Any]:
    """Scores one reply against its case. Pure: no I/O."""
    result: dict[str, Any] = {
        "id": case["id"], "kind": case.get("kind"), "language": case.get("language"),
        "question": case.get("question"), "latencyMs": latency_ms,
    }
    if error is not None or response is None:
        result.update(passed=False, error=error or "no response", failures=[f"request failed: {error or 'no response'}"],
                      checks={}, counts={}, response=None)
        return result

    expect = case.get("expect") or {}
    status = str(response.get("status") or "")
    answer = response.get("answer") or ""
    citations = [item for item in response.get("citations") or [] if isinstance(item, dict)]
    choices = [item for item in response.get("clarificationChoices") or [] if isinstance(item, dict)]
    has_reason, has_flags = "reason" in response, "flags" in response
    reason = response.get("reason")
    flags = response.get("flags") if isinstance(response.get("flags"), list) else []
    checks: dict[str, str] = {}
    failures: list[str] = []

    def check(name: str, ok: bool | None, message: str = "") -> None:
        checks[name] = NA if ok is None else (PASS if ok else FAIL)
        if ok is False:
            failures.append(f"{name}: {message}")

    allowed = expect.get("status") or []
    check("status", status in allowed if allowed else None, f"got {status or '<empty>'}, expected one of {allowed}")

    allowed_reasons = expect.get("reasons") or []
    if status == "NOT_FOUND" and allowed_reasons:
        check("reason", (reason in allowed_reasons) if has_reason else None,
              f"got {reason}, expected one of {allowed_reasons}")
    else:
        check("reason", None)

    check("notFoundWithoutCitations", not citations if status == "NOT_FOUND" else None,
          f"NOT_FOUND carried {len(citations)} citation(s)")

    max_citations = expect.get("maxCitations")
    check("citationCount", len(citations) <= max_citations if max_citations is not None else None,
          f"{len(citations)} citation(s), at most {max_citations} allowed")

    forbidden = set(expect.get("forbiddenDocumentIds") or [])
    relevance_known = has_relevance_rule(expect) or max_citations == 0
    unrelated = [item for item in citations
                 if item.get("documentId") not in forbidden
                 and (max_citations == 0 or not is_acceptable(item, expect))] if relevance_known else []
    check("citationRelevance", not unrelated if relevance_known and citations else None,
          "unrelated: " + ", ".join(f"{item.get('documentId')} ({(item.get('title') or '')[:60]})" for item in unrelated))

    choices_scored = has_relevance_rule(expect) or max_citations == 0
    unrelated_choices = [item for item in choices
                         if item.get("documentId") not in forbidden
                         and (max_citations == 0 or not is_acceptable(item, expect))] if choices_scored else []
    check("choiceRelevance", not unrelated_choices if choices_scored and choices else None,
          "unrelated choices: " + ", ".join(f"{item.get('documentId')} ({(item.get('label') or '')[:60]})"
                                            for item in unrelated_choices))

    if status == "NEEDS_CLARIFICATION":
        distinct = len(choices) - duplicate_choices(choices, expect.get("duplicateGroups") or [])
        check("clarificationChoices", distinct >= 2, f"clarification offers {distinct} distinct choice(s), needs at least 2")
    else:
        check("clarificationChoices", None)

    duplicates = duplicate_choices(choices, expect.get("duplicateGroups") or [])
    check("noDuplicateChoices", duplicates == 0 if choices else None, f"{duplicates} duplicate choice(s)")

    cited_ids = {item.get("documentId") for item in citations}
    required = expect.get("requiredDocumentIds") or []
    missing_required = [doc_id for doc_id in required if doc_id not in cited_ids]
    check("requiredDocuments", not missing_required if required else None, f"missing {missing_required}")

    offered_ids = cited_ids | {item.get("documentId") for item in choices}
    outdated = sorted(doc_id for doc_id in offered_ids if doc_id in forbidden)
    check("noOutdatedSources", not outdated if forbidden else None, f"cited or offered outdated {outdated}")

    answer_bearing = status in ANSWER_STATUSES or (response.get("mode") in {"llm", "demo"} and bool(answer.strip()))
    markers = citation_markers(answer)
    labels = citation_labels(citations)
    valid_markers = [marker for marker in markers if marker in labels]
    dangling = sorted({marker for marker in markers if marker not in labels})
    uncited = answer_bearing and (not citations or not valid_markers)
    check("answerCited", not uncited if answer_bearing else None,
          "answer has no citations" if not citations else "answer has no [S#] marker matching a citation")
    check("noDanglingMarkers", not dangling if answer_bearing and markers else None, f"markers without citation {dangling}")
    missing_sentences, sentence_total = uncited_sentences(answer) if answer_bearing else (0, 0)

    answered = status in {"SUPPORTED", "PARTIAL"}
    value_pattern = expect.get("valuePattern")
    check("valuePresentWhenAnswered", bool(re.search(value_pattern, answer, re.IGNORECASE)) if value_pattern and answered else None,
          "answered without the requested value (expected NOT_FOUND/EVIDENCE_LACKS_VALUE)")
    answer_pattern = expect.get("answerPattern")
    check("answerContent", bool(re.search(answer_pattern, answer, re.IGNORECASE)) if answer_pattern and answered else None,
          f"answer does not match /{answer_pattern}/")

    result.update(
        passed=not failures,
        failures=failures,
        checks=checks,
        counts={
            "citations": len(citations),
            "relevanceScored": relevance_known,
            "unrelatedCitations": len(unrelated),
            "choices": len(choices),
            "choicesScored": choices_scored,
            "unrelatedChoices": len(unrelated_choices),
            "duplicateChoices": duplicates,
            "outdatedDocuments": len(outdated),
            "answerBearing": answer_bearing,
            "uncitedAnswer": uncited,
            "uncitedSentences": missing_sentences,
            "sentences": sentence_total,
            "reasonReported": has_reason,
            "flagsReported": has_flags,
        },
        response={
            "mode": response.get("mode"), "status": status, "answer": answer,
            **({"reason": reason} if has_reason else {}), **({"flags": flags} if has_flags else {}),
            "citations": [{key: item.get(key) for key in ("id", "documentId", "title", "url", "publishedDate", "outdated")}
                          for item in citations],
            "clarificationChoices": choices or None,
        },
    )
    return result


def _rate(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def aggregate(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Suite-level metrics from scored cases. Pure: no I/O."""
    ok = [item for item in results if item.get("response") is not None]
    counts = [item["counts"] for item in ok]
    scored_citations = sum(c["citations"] for c in counts if c["relevanceScored"])
    unrelated = sum(c["unrelatedCitations"] for c in counts)
    answer_bearing = sum(1 for c in counts if c["answerBearing"])
    uncited = sum(1 for c in counts if c["uncitedAnswer"])
    sentences = sum(c["sentences"] for c in counts)
    uncited_sentences_total = sum(c["uncitedSentences"] for c in counts)
    answerable = [item for item in ok if item["kind"] in ANSWERABLE_KINDS]
    false_not_found = sum(1 for item in answerable if item["response"]["status"] == "NOT_FOUND")
    scored_choices = sum(c["choices"] for c in counts if c["choicesScored"])
    unrelated_choices = sum(c["unrelatedChoices"] for c in counts)
    ambiguous = [item for item in ok if item["kind"] == "ambiguous"]
    clarified = sum(1 for item in ambiguous if item["response"]["status"] == "NEEDS_CLARIFICATION")
    yearly = [item for item in ok if item["kind"] == "yearly_topic"]
    outdated_cases = sum(1 for item in yearly if item["counts"]["outdatedDocuments"])
    latencies = [item["latencyMs"] for item in ok if item.get("latencyMs") is not None]
    reason_cases = [item for item in ok if item["checks"].get("reason") != NA]
    by_kind: dict[str, dict[str, int]] = {}
    for item in results:
        bucket = by_kind.setdefault(item["kind"] or "?", {"cases": 0, "passed": 0})
        bucket["cases"] += 1
        bucket["passed"] += int(bool(item["passed"]))
    return {
        "cases": len(results),
        "passed": sum(1 for item in results if item["passed"]),
        "failed": sum(1 for item in results if not item["passed"]),
        "requestErrors": len(results) - len(ok),
        "unrelatedCitations": unrelated,
        "scoredCitations": scored_citations,
        "unrelatedCitationRate": _rate(unrelated, scored_citations),
        "uncitedAnswers": uncited,
        "answerBearingReplies": answer_bearing,
        "uncitedAnswerRate": _rate(uncited, answer_bearing),
        "uncitedSentenceRate": _rate(uncited_sentences_total, sentences),
        "falseNotFound": false_not_found,
        "answerableCases": len(answerable),
        "falseNotFoundRate": _rate(false_not_found, len(answerable)),
        "clarificationPrecision": _rate(scored_choices - unrelated_choices, scored_choices),
        "scoredChoices": scored_choices,
        "ambiguousClarifiedRate": _rate(clarified, len(ambiguous)),
        "outdatedSourceCases": outdated_cases,
        "yearlyCases": len(yearly),
        "outdatedSourceRate": _rate(outdated_cases, len(yearly)),
        "duplicateChoices": sum(c["duplicateChoices"] for c in counts),
        "latencyP50Ms": percentile(latencies, 50),
        "latencyP95Ms": percentile(latencies, 95),
        "reasonReported": any(c["reasonReported"] for c in counts),
        "flagsReported": any(c["flagsReported"] for c in counts),
        "reasonChecksScored": len(reason_cases),
        "byKind": by_kind,
    }


def exit_code(metrics: dict[str, Any]) -> int:
    return 1 if metrics["unrelatedCitations"] or metrics["uncitedAnswers"] else 0


def _fmt_rate(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.1f}%"


def _fmt_ms(value: float | None) -> str:
    return "n/a" if value is None else f"{value / 1000:.1f}s"


def format_summary(report: dict[str, Any]) -> str:
    m = report["metrics"]
    lines = [
        f"RAG evaluation: {report.get('url')}  ({m['passed']}/{m['cases']} cases passed, {m['requestErrors']} request errors)",
        f"  unrelated-citation rate : {_fmt_rate(m['unrelatedCitationRate'])} ({m['unrelatedCitations']}/{m['scoredCitations']} citations; target 0)",
        f"  uncited-answer rate     : {_fmt_rate(m['uncitedAnswerRate'])} ({m['uncitedAnswers']}/{m['answerBearingReplies']} answers)"
        f"; uncited sentences {_fmt_rate(m['uncitedSentenceRate'])}",
        f"  false NOT_FOUND rate    : {_fmt_rate(m['falseNotFoundRate'])} ({m['falseNotFound']}/{m['answerableCases']} answerable cases)",
        f"  clarification precision : {_fmt_rate(m['clarificationPrecision'])} ({m['scoredChoices']} choices)"
        f"; ambiguous clarified {_fmt_rate(m['ambiguousClarifiedRate'])}",
        f"  outdated-source rate    : {_fmt_rate(m['outdatedSourceRate'])} ({m['outdatedSourceCases']}/{m['yearlyCases']} yearly cases)",
        f"  duplicate choices       : {m['duplicateChoices']}",
        f"  latency p50 / p95       : {_fmt_ms(m['latencyP50Ms'])} / {_fmt_ms(m['latencyP95Ms'])}",
        f"  reason/flags reported   : {'yes' if m['reasonReported'] else 'no (reason checks n/a)'} / {'yes' if m['flagsReported'] else 'no'}",
        "  by kind: " + ", ".join(f"{kind} {v['passed']}/{v['cases']}" for kind, v in sorted(m["byKind"].items())),
        "",
    ]
    for item in report["cases"]:
        response = item.get("response") or {}
        status = response.get("status") or "ERROR"
        mark = "PASS" if item["passed"] else "FAIL"
        latency = _fmt_ms(item.get("latencyMs"))
        lines.append(f"{mark} {item['id']:<42} {status:<20} {latency:>7}")
        for failure in item["failures"]:
            lines.append(f"       - {failure}")
    return "\n".join(lines)


# ---------------------------------------------------------------- HTTP client

def post_chat(url: str, message: str, timeout: float) -> tuple[dict[str, Any] | None, float, str | None]:
    body = json.dumps({"chatId": str(uuid.uuid4()), "message": message, "history": []}).encode("utf-8")
    request = urllib.request.Request(url, data=body, method="POST",
                                     headers={"Content-Type": "application/json", "Accept": "application/json"})
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as reply:
            payload = json.loads(reply.read().decode("utf-8"))
        return payload, (time.perf_counter() - started) * 1000, None
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", "replace")[:300]
        return None, (time.perf_counter() - started) * 1000, f"HTTP {error.code}: {detail}"
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as error:
        return None, (time.perf_counter() - started) * 1000, f"{type(error).__name__}: {error}"


def load_cases(path: Path, only: list[str] | None = None) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    cases = data["cases"] if isinstance(data, dict) else data
    if only:
        wanted = set(only)
        unknown = wanted - {case["id"] for case in cases}
        if unknown:
            raise ValueError(f"unknown case id(s): {', '.join(sorted(unknown))}")
        cases = [case for case in cases if case["id"] in wanted]
    return cases


def progress_snapshot(results: list[dict[str, Any]], total: int, elapsed_s: float, url: str) -> dict[str, Any]:
    """What a watcher needs mid-run: counts, the last case and a naive ETA from the average time per case so far."""
    done = len(results)
    per_case = elapsed_s / done if done else None
    return {
        "url": url,
        "done": done,
        "total": total,
        "passed": sum(1 for item in results if item["passed"]),
        "failed": sum(1 for item in results if not item["passed"]),
        "lastCase": results[-1]["id"] if results else None,
        "elapsedS": round(elapsed_s),
        "etaS": round(per_case * (total - done)) if per_case is not None else None,
        "finished": done == total,
        "updatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def write_progress(path: Path | None, snapshot: dict[str, Any]) -> None:
    if path is None:
        return
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate the strict municipal RAG /v1/chat endpoint")
    parser.add_argument("--url", default=DEFAULT_URL, help=f"chat endpoint (default {DEFAULT_URL})")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES, help="questions file (default questions.json)")
    parser.add_argument("--only", help="comma-separated case ids to run")
    parser.add_argument("--out", type=Path, help="write the JSON report here")
    parser.add_argument("--timeout", type=float, default=240.0, help="per-request timeout in seconds")
    parser.add_argument("--rescore", type=Path, metavar="REPORT",
                        help="re-score the replies saved in an earlier report instead of calling the service")
    parser.add_argument("--progress", type=Path, metavar="FILE",
                        help="rewrite this JSON file after every case (default: <out>.progress.json when --out is set)")
    parser.add_argument("--concurrency", type=int, default=4,
                        help="questions in flight at once (default 4; use 1 against a shared service or to measure latency alone)")
    args = parser.parse_args(argv)
    if args.concurrency < 1:
        parser.error("--concurrency must be at least 1")
    progress_path = args.progress or (args.out.with_name(args.out.name + ".progress.json") if args.out else None)

    only = [item.strip() for item in args.only.split(",") if item.strip()] if args.only else None
    try:
        cases = load_cases(args.cases, only)
    except (OSError, ValueError, KeyError) as error:
        print(f"cannot load cases: {error}", file=sys.stderr)
        return 2

    saved: dict[str, dict[str, Any]] = {}
    url = args.url
    if args.rescore:
        try:
            previous = json.loads(args.rescore.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            print(f"cannot load report: {error}", file=sys.stderr)
            return 2
        saved = {item["id"]: item for item in previous.get("cases") or []}
        url = previous.get("url") or url

    def run_case(case: dict[str, Any]) -> dict[str, Any]:
        if args.rescore:
            old = saved.get(case["id"]) or {}
            response, error = old.get("response"), old.get("error")
            latency = old.get("latencyMs") or 0.0
            if not old:
                error = "case not present in the rescored report"
        else:
            response, latency, error = post_chat(url, case["question"], args.timeout)
        return score_case(case, response, round(latency, 1), error)

    started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    started = time.monotonic()
    finished: dict[str, dict[str, Any]] = {}
    lock = threading.Lock()
    write_progress(progress_path, progress_snapshot([], len(cases), 0.0, url))
    # Cases are independent, so up to --concurrency of them are in flight; the report keeps the questions.json order.
    with ThreadPoolExecutor(max_workers=1 if args.rescore else args.concurrency) as pool:
        futures = {pool.submit(run_case, case): case for case in cases}
        for future in as_completed(futures):
            scored = future.result()
            with lock:
                finished[scored["id"]] = scored
                done = list(finished.values())
                snapshot = progress_snapshot(done, len(cases), time.monotonic() - started, url)
                write_progress(progress_path, snapshot)
            status = (scored.get("response") or {}).get("status") or "ERROR"
            eta = f" eta {snapshot['etaS'] // 60}m{snapshot['etaS'] % 60:02d}s" if snapshot["etaS"] else ""
            print(f"[{len(done)}/{len(cases)}] {'PASS' if scored['passed'] else 'FAIL'} {scored['id']} {status} "
                  f"{(scored.get('latencyMs') or 0) / 1000:.1f}s{eta}", file=sys.stderr, flush=True)
    results = [finished[case["id"]] for case in cases]

    report = {
        "url": url,
        "rescoredFrom": str(args.rescore) if args.rescore else None,
        "casesFile": str(args.cases),
        "concurrency": 1 if args.rescore else args.concurrency,
        "startedAt": started_at,
        "finishedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "metrics": aggregate(results),
        "cases": results,
    }
    if args.out:
        args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(format_summary(report))
    return exit_code(report["metrics"])


if __name__ == "__main__":
    raise SystemExit(main())
