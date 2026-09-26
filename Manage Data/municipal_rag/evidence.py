from __future__ import annotations

import re
from typing import Any

from pipeline_core import estimate_tokens, normalize_search_text, sha256_text, stable_id


SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?…])\s+(?=[A-ZĂÂÎȘȚА-ЯЁ0-9])")
MONEY_RE = re.compile(r"\b\d+(?:[.,]\d+)?\s*(?:milioane|milioan|mln|mii)?\s*(?:lei|MDL|EUR|euro)\b", re.I)
DATE_RE = re.compile(r"\b(?:\d{1,2}[./-]\d{1,2}[./-]\d{2,4}|20\d{2}|19\d{2})\b")
DURATION_RE = re.compile(r"\b\d+(?:[.,]\d+)?\s*(?:zile|luni|ani|ore|дн(?:я|ей)|месяц(?:а|ев)?|лет|час(?:а|ов)?)\b", re.I)
COUNT_RE = re.compile(r"\b\d+(?:[.,]\d+)?\s+(?:de\s+)?(?:străzi|accese|blocuri|kilometri|km|unități|улиц|двор|километр|км)\w*", re.I)


def evidence_kind(passage: dict[str, Any]) -> str:
    kind = str(passage.get("type", "")).casefold()
    if "table" in kind:
        return "table"
    if "list" in kind or "item" in kind:
        return "list"
    if "heading" in kind or "headline" in kind:
        return "headline"
    return "body"


def quality(passage: dict[str, Any]) -> tuple[str, list[str]]:
    issues: list[str] = []
    validation = passage.get("validation") or {}
    for field in ("dataIssues", "citationIssues"):
        issues.extend(str(item) for item in validation.get(field) or [])
    issues.extend(str(item) for item in passage.get("warnings") or [])
    text = str(passage.get("citationText") or "")
    if not text.strip():
        issues.append("EMPTY_PASSAGE")
    if "�" in text or text.count("?") > max(4, len(text) // 30):
        issues.append("ENCODING_NOISE")
    if len(text.split()) < 4 and evidence_kind(passage) == "body":
        issues.append("FRAGMENT")
    alphabetic_tokens = re.findall(r"[^\W\d_]+", text, re.UNICODE)
    if len(alphabetic_tokens) >= 10 and sum(len(token) == 1 for token in alphabetic_tokens) / len(alphabetic_tokens) > 0.4:
        issues.append("OCR_NOISE")
    status = "READY" if validation.get("overallStatus", "READY") == "READY" and not issues else "QUARANTINED"
    return status, sorted(set(issues))


def split_exact(text: str, hard_max_tokens: int = 420, overlap: int = 1) -> list[tuple[str, int, int]]:
    """Split exact source text at sentence boundaries and retain character offsets."""
    if estimate_tokens(text) <= hard_max_tokens:
        return [(text, 0, len(text))]
    sentences: list[tuple[str, int, int]] = []
    start = 0
    for match in SENTENCE_BOUNDARY.finditer(text):
        sentences.append((text[start:match.start()], start, match.start()))
        start = match.end()
    sentences.append((text[start:], start, len(text)))
    result: list[tuple[str, int, int]] = []
    cursor = 0
    while cursor < len(sentences):
        end = cursor
        while end + 1 < len(sentences):
            candidate = text[sentences[cursor][1]:sentences[end + 1][2]]
            if estimate_tokens(candidate) > hard_max_tokens:
                break
            end += 1
        if end == cursor and estimate_tokens(sentences[cursor][0]) > hard_max_tokens:
            # A pathological sentence remains exact, split only at whitespace.
            words = list(re.finditer(r"\S+", sentences[cursor][0]))
            index = 0
            while index < len(words):
                finish = index + 1
                while finish < len(words):
                    candidate = sentences[cursor][0][words[index].start():words[finish].end()]
                    if estimate_tokens(candidate) > hard_max_tokens:
                        break
                    finish += 1
                group = words[index:finish]
                absolute_start = sentences[cursor][1] + group[0].start()
                absolute_end = sentences[cursor][1] + group[-1].end()
                result.append((text[absolute_start:absolute_end], absolute_start, absolute_end))
                index = finish
        else:
            begin = sentences[cursor][1]
            finish = sentences[end][2]
            result.append((text[begin:finish], begin, finish))
        cursor = max(cursor + 1, end + 1 - overlap)
    return result


def extract_facts(text: str) -> dict[str, list[str]]:
    return {
        "amounts": MONEY_RE.findall(text),
        "dates": DATE_RE.findall(text),
        "durations": DURATION_RE.findall(text),
        "counts": COUNT_RE.findall(text),
    }


def build_evidence(document: dict[str, Any], hard_max_tokens: int = 420) -> list[dict[str, Any]]:
    source = document.get("source") or {}
    metadata = document.get("sourceMetadata") or {}
    version_id = str(source.get("sha256") or sha256_text(str(source.get("snapshotPath", ""))))
    result: list[dict[str, Any]] = []
    for passage in document.get("passages") or []:
        citation = str(passage.get("citationText") or "")
        status, issues = quality(passage)
        title_key = normalize_search_text(str(document["title"])).lstrip("# ").casefold()
        heading = [str(value) for value in passage.get("headingPath") or []
                   if normalize_search_text(str(value)).lstrip("# ").casefold() != title_key]
        context = [document["title"], *heading]
        if document.get("publishedDate"):
            context.append(f"Data publicării: {document['publishedDate']}")
        context_text = " | ".join(context)
        quotation_budget = max(32, hard_max_tokens - estimate_tokens(context_text) - 2)
        for part_index, (quote, char_start, char_end) in enumerate(split_exact(citation, quotation_budget), start=1):
            evidence_id = stable_id("evidence", document["documentId"], version_id, passage["passageId"], str(part_index), sha256_text(quote))
            retrieval = context_text + "\n\n" + normalize_search_text(quote)
            locator = dict(passage.get("provenance") or {})
            locator.update({"passageId": passage["passageId"], "charStart": char_start, "charEnd": char_end})
            kind = evidence_kind(passage)
            facts = extract_facts(quote)
            facts["locations"] = [str(metadata["district"])] if metadata.get("district") else []
            facts["projectNames"] = [str(document["title"])]
            item = {
                "schemaVersion": "3.0",
                "chunkId": evidence_id,
                "evidenceId": evidence_id,
                "documentId": document["documentId"],
                "versionId": version_id,
                "documentType": document["documentType"],
                "language": document.get("language", "ro"),
                "text": retrieval,
                "retrievalText": retrieval,
                "citationText": quote,
                "textSha256": sha256_text(retrieval),
                "tokenCountEstimate": estimate_tokens(retrieval),
                "passageIds": [passage["passageId"]],
                "evidenceKind": kind,
                "sourceLocator": locator,
                "citations": [{"passageId": passage["passageId"], "sourceUrl": source.get("sourceUrl"), "sourceFile": source.get("originalFilename"), "locator": locator, "quote": quote}],
                "facts": facts,
                "quality": {"status": status, "issueCodes": issues},
                "indexingStatus": "READY" if status == "READY" else "NEEDS_REVIEW",
                "targetCollection": "production" if status == "READY" else "review",
                "metadata": {
                    "title": document["title"], "heading": heading, "publisher": document.get("publisher"),
                    "publishedDate": document.get("publishedDate"), "category": metadata.get("category"),
                    "district": metadata.get("district"), "sourceUrl": source.get("sourceUrl"),
                    "sourceFile": source.get("originalFilename"), "isCurrentVersion": True,
                },
            }
            result.append(item)
    return result
