from __future__ import annotations

import argparse
import json
import os
import re
import time
import sys
import unicodedata
from pathlib import Path
from typing import Any

from .api import begin_interactive_request, chat_json, end_interactive_request
from .config import load_config, load_dotenv
from .retrieval import interpret_query, requested_fact_slots, retrieve
from .verification import verify_claims
from .tracing import write_trace

CLAIMS_SCHEMA = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": ["SUPPORTED", "PARTIAL", "NOT_FOUND", "CONTRADICTION"]},
        "claims": {
            "type": "array",
            "maxItems": 16,
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "evidenceIds": {
                        "type": "array",
                        "items": {"type": "string", "pattern": "^S[1-9][0-9]*$"},
                    },
                },
                "required": ["text", "evidenceIds"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["status", "claims"],
    "additionalProperties": False,
}

OBSERVATIONS_SCHEMA = {
    "type": "object",
    "properties": {
        "observations": {
            "type": "array",
            "maxItems": 16,
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "evidenceIds": {
                        "type": "array",
                        "items": {"type": "string", "pattern": "^S[1-9][0-9]*$"},
                    },
                },
                "required": ["text", "evidenceIds"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["observations"],
    "additionalProperties": False,
}


def expose_evidence(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result, seen = [], set()
    for item in items:
        key = item.get("evidenceId") or item.get("chunkId")
        if not key or key in seen:
            continue
        seen.add(key)
        meta = item.get("metadata") or {}
        result.append({"id": f"S{len(result)+1}", "evidenceId": key, "documentId": item.get("documentId"),
            "versionId": item.get("versionId"), "evidenceKind": item.get("evidenceKind"),
            "exactQuote": item.get("citationText"), "title": meta.get("title"), "url": meta.get("sourceUrl"),
            "sourceFile": meta.get("sourceFile"), "publisher": meta.get("publisher"),
            "publishedDate": meta.get("publishedDate"), "category": meta.get("category"),
            "district": meta.get("district"),
            "locator": item.get("sourceLocator") or ((item.get("citations") or [{}])[0].get("locator")),
            "facts": item.get("facts") or {},
            "retrieval": item.get("retrieval")})
    return result


def retain_cited_claims(claims: list[dict[str, Any]], evidence: list[dict[str, Any]],
                        max_claims: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Keep Qwen's answer while enforcing only structural citation integrity.

    This intentionally does not judge wording, project scope, completeness, or
    entailment. It only prevents a generated source identifier from pointing to
    a passage that was never supplied to the model, then makes identifiers
    contiguous for the public response.
    """
    available = {str(item.get("id")): item for item in evidence if item.get("id")}
    retained: list[dict[str, Any]] = []
    for original in claims[:max_claims]:
        if not isinstance(original, dict):
            continue
        text = str(original.get("text") or "").strip()
        identifiers = list(dict.fromkeys(
            str(value) for value in original.get("evidenceIds") or []
            if str(value) in available
        ))
        if text and identifiers:
            retained.append({"text": text, "evidenceIds": identifiers})

    used = {identifier for claim in retained for identifier in claim["evidenceIds"]}
    citations = [item.copy() for item in evidence if str(item.get("id")) in used]
    mapping = {str(item["id"]): f"S{index}" for index, item in enumerate(citations, 1)}
    for item in citations:
        item["id"] = mapping[str(item["id"])]
    for claim in retained:
        claim["evidenceIds"] = [mapping[value] for value in claim["evidenceIds"]]
    return retained, citations


STOPWORDS = {
    "a", "al", "ale", "articol", "articolului", "au", "cat", "cate", "catre",
    "ce", "cele", "conform", "cu", "de", "despre", "din", "fost", "in", "la",
    "o", "pe", "pentru", "prin", "si", "suma", "un", "unei",
}
TOKEN_RE = re.compile(r"[a-z0-9]+")
YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")
AMOUNT_RE = re.compile(
    r"\b\d+(?:[.,]\d+)?\s*(?:mln|milioane?|mii)?\s*(?:de\s+)?(?:lei|mdl|eur|euro)\b",
    re.I,
)
SELECTED_DOCUMENT_RE = re.compile(
    r'\n?Document selectat pentru clarificare:\s*["“](.+?)["”]\s*$', re.I | re.S,
)


def normalized_text(value: str) -> str:
    folded = "".join(
        character for character in unicodedata.normalize("NFKD", value.casefold())
        if not unicodedata.combining(character)
    )
    folded = re.sub(r"\bbd(?:\.(?=\s|$)|\b)", "bulevardul", folded)
    folded = re.sub(r"\bstr(?:\.(?=\s|$)|\b)", "strada", folded)
    return re.sub(r"\bmln\b", "milioane", folded)


def split_explicit_selection(question: str) -> tuple[str, str | None]:
    match = SELECTED_DOCUMENT_RE.search(question)
    if not match:
        return question, None
    cleaned = question[:match.start()].strip()
    return (cleaned or question, match.group(1).strip())


def evidence_for_selected_title(items: list[dict[str, Any]], selected_title: str) -> list[dict[str, Any]]:
    expected = normalized_text(selected_title).strip()
    exact = [item for item in items
             if normalized_text(str((item.get("metadata") or {}).get("title") or "")).strip() == expected]
    if exact:
        return exact
    # Tolerate UI truncation/typographic changes, but require an almost exact
    # bidirectional token match so a related project cannot inherit the choice.
    expected_tokens = content_tokens(selected_title)
    return [item for item in items if
            token_coverage(expected_tokens, content_tokens(str((item.get("metadata") or {}).get("title") or ""))) >= .95
            and token_coverage(content_tokens(str((item.get("metadata") or {}).get("title") or "")), expected_tokens) >= .95]


def content_tokens(value: str) -> list[str]:
    return [token for token in TOKEN_RE.findall(normalized_text(value)) if token not in STOPWORDS]


def token_matches(left: str, right: str) -> bool:
    if left == right:
        return True
    if left.isdigit() or right.isdigit():
        return False
    shorter, longer = sorted((left, right), key=len)
    return len(shorter) >= 5 and longer.startswith(shorter[: max(5, len(shorter) - 1)])


def token_coverage(needles: list[str], haystack: list[str]) -> float:
    if not needles:
        return 0.0
    return sum(any(token_matches(needle, value) for value in haystack) for needle in needles) / len(needles)


def phrase_matches(value: str, candidate: str) -> bool:
    tokens = content_tokens(value)
    return bool(tokens) and token_coverage(tokens, content_tokens(candidate)) >= 0.8


def temporal_conflict(question: str, candidate: str) -> bool:
    query = normalized_text(question)
    text = normalized_text(candidate)
    current = ("anul curent", "acest an", "anul acesta")
    previous = ("anul trecut", "anul precedent")
    if any(value in query for value in current) and any(value in text for value in previous) and not any(value in text for value in current):
        return True
    if any(value in query for value in previous) and any(value in text for value in current) and not any(value in text for value in previous):
        return True
    requested_years = set(YEAR_RE.findall(query))
    candidate_years = set(YEAR_RE.findall(text))
    return bool(requested_years and candidate_years and requested_years.isdisjoint(candidate_years))


def candidate_profile(item: dict[str, Any], interpreted: dict[str, Any]) -> dict[str, Any]:
    metadata = item.get("metadata") or {}
    constraints = interpreted.get("constraints") or {}
    query = str(interpreted.get("normalizedRomanianQuery") or "")
    title = str(metadata.get("title") or item.get("documentId") or "")
    candidate = " ".join(str(value) for value in (
        title, metadata.get("district"), metadata.get("publishedDate"),
        item.get("retrievalText"), item.get("citationText"),
    ) if value)
    entities = [str(value) for value in constraints.get("entities") or [] if str(value).strip()]
    locations = [str(value) for value in constraints.get("locations") or [] if str(value).strip()]
    dates = [str(value) for value in constraints.get("dates") or [] if str(value).strip()]
    matched_title_entities = sum(phrase_matches(value, title) for value in entities)
    matched_body_entities = sum(phrase_matches(value, candidate) for value in entities)
    title_score = token_coverage(content_tokens(query), content_tokens(title))
    entity_title_score = matched_title_entities / len(entities) if entities else 0.0
    entity_body_score = matched_body_entities / len(entities) if entities else 0.0
    locations_match = all(phrase_matches(value, candidate) for value in locations)
    dates_match = all(phrase_matches(value, candidate) for value in dates)
    conflict = temporal_conflict(" ".join([query, *dates]), candidate)
    query_numbers = set(re.findall(r"\d+(?:[.,]\d+)?", query))
    title_numbers = set(re.findall(r"\d+(?:[.,]\d+)?", title))
    numeric_title_match = bool(query_numbers) and query_numbers <= title_numbers
    exact_title_match = (
        title_score >= 0.72
        or (title_score >= 0.52 and entity_title_score >= 0.5)
        or (numeric_title_match and title_score >= 0.45)
    ) and locations_match and dates_match and not conflict
    compatibility = (
        (title_score >= 0.18 or entity_body_score >= 0.5)
        and locations_match and dates_match and not conflict
    )
    rerank_score = float((item.get("retrieval") or {}).get("rerankScore") or 0.0)
    match_score = 0.55 * title_score + 0.30 * entity_title_score + 0.15 * rerank_score
    reasons = [f"rerank={rerank_score:.3f}", f"titleMatch={title_score:.2f}",
               f"entityMatch={matched_body_entities}/{len(entities)}"]
    if locations:
        reasons.append("locations=matched" if locations_match else "locations=mismatch")
    if dates:
        reasons.append("dates=matched" if dates_match and not conflict else "dates=mismatch")
    return {"item": item, "documentId": str(item.get("documentId")), "title": title,
            "rerankScore": rerank_score, "titleScore": title_score,
            "entityTitleScore": entity_title_score, "entityBodyScore": entity_body_score,
            "matchScore": match_score, "exactTitleMatch": exact_title_match,
            "compatible": compatibility, "reasons": reasons}


def resolve_ambiguity(items: list[dict[str, Any]], interpreted: dict[str, Any], ratio: float) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str], dict[str, Any]]:
    if interpreted.get("constraints", {}).get("multipleProjects"):
        return items, [], [], {"decision": "multiple-project-request"}
    best: dict[str, dict[str, Any]] = {}
    for item in items:
        document_id = str(item.get("documentId") or "")
        if document_id and document_id not in best:
            best[document_id] = item
    profiles = sorted(
        (candidate_profile(item, interpreted) for item in best.values()),
        key=lambda value: (-value["matchScore"], -value["rerankScore"], value["documentId"]),
    )
    exact = [value for value in profiles if value["exactTitleMatch"]]
    if exact:
        winner = exact[0]
        runner = exact[1] if len(exact) > 1 else None
        if runner is None or winner["matchScore"] - runner["matchScore"] >= 0.08:
            selected = [item for item in items if str(item.get("documentId")) == winner["documentId"]]
            return selected, [], ["Exact title/entity match selected a single document"], {
                "decision": "exact-title-override", "selectedDocumentId": winner["documentId"],
                "selectedTitleMatch": round(winner["titleScore"], 4),
            }

    requested_locations = [str(value) for value in interpreted.get("constraints", {}).get("locations") or []
                           if str(value).strip()]
    title_scoped = [value for value in profiles if requested_locations and
                    all(phrase_matches(location, value["title"]) for location in requested_locations)]
    title_scoped.sort(key=lambda value: (-value["titleScore"], -value["matchScore"], value["documentId"]))
    title_runner = title_scoped[1] if len(title_scoped) > 1 else None
    dominant_location_title = bool(title_scoped and title_scoped[0]["titleScore"] >= .35 and
                                   (title_runner is None or
                                    title_scoped[0]["titleScore"] - title_runner["titleScore"] >= .12))
    if len(title_scoped) == 1 or dominant_location_title:
        winner = title_scoped[0]
        selected = [item for item in items if str(item.get("documentId")) == winner["documentId"]]
        return selected, [], ["A single document title matches every requested location"], {
            "decision": "location-title-override", "selectedDocumentId": winner["documentId"],
        }

    compatible = [value for value in profiles if value["compatible"]]
    if len(compatible) < 2:
        return items, [], [], {"decision": "not-ambiguous", "compatibleDocuments": len(compatible)}
    top = compatible[0]
    close = [value for value in compatible if value["rerankScore"] >= top["rerankScore"] * ratio]
    if len(close) < 2:
        return items, [], [], {"decision": "rerank-margin", "compatibleDocuments": len(compatible)}

    # Near-duplicate titles are the same interpretation, not a reason to ask the user.
    distinct: list[dict[str, Any]] = []
    for profile in close:
        title_tokens = content_tokens(profile["title"])
        if any(token_coverage(title_tokens, content_tokens(item["title"])) >= 0.85 and
               token_coverage(content_tokens(item["title"]), title_tokens) >= 0.85 for item in distinct):
            continue
        distinct.append(profile)
    if len(distinct) < 2:
        return items, [], [], {"decision": "same-project-duplicates"}

    choices = [{"documentId": value["documentId"], "label": value["title"],
                "rerankScore": round(value["rerankScore"], 4),
                "matchReasons": value["reasons"]} for value in distinct[:3]]
    reasons = [
        f"{len(distinct[:3])} distinct projects remain compatible after title, entity, location and time checks",
        f"Competing rerank scores are within the configured ratio {ratio:.2f}",
    ]
    return items, choices, reasons, {"decision": "needs-clarification", "candidates": choices}


def ambiguity(items: list[dict[str, Any]], interpreted: dict[str, Any], ratio: float) -> list[dict[str, Any]]:
    """Compatibility wrapper for callers that only need clarification choices."""
    return resolve_ambiguity(items, interpreted, ratio)[1]


def headline_only_amount(items: list[dict[str, Any]], interpreted: dict[str, Any]) -> dict[str, Any] | None:
    if not items:
        return None
    question = str(interpreted.get("normalizedRomanianQuery") or "")
    fact_types = " ".join(str(value) for value in interpreted.get("constraints", {}).get("factTypes") or [])
    if not re.search(r"\b(?:suma|milioane|lei|buget|alocat\w*|financiar\w*)\b", normalized_text(f"{question} {fact_types}")):
        return None
    first = items[0]
    metadata = first.get("metadata") or {}
    title = str(metadata.get("title") or "")
    title_amounts = AMOUNT_RE.findall(normalized_text(title))
    if not title_amounts:
        return None
    query_numbers = set(re.findall(r"\d+(?:[.,]\d+)?", question))
    amount = next((value for value in title_amounts if not query_numbers or
                   re.search(r"\d+(?:[.,]\d+)?", value).group() in query_numbers), title_amounts[0])
    amount_number = re.search(r"\d+(?:[.,]\d+)?", amount)
    if amount_number and any(
        amount_number.group() in str(item.get("citationText") or "") and
        re.search(r"\b(?:lei|mdl|eur|euro)\b", str(item.get("citationText") or ""), re.I)
        for item in items
    ):
        return None
    document_id = str(first.get("documentId") or "")
    return {
        "amount": amount,
        "citation": {
            "id": "S1", "evidenceId": f"headline:{document_id}", "documentId": document_id,
            "versionId": first.get("versionId"), "evidenceKind": "headline",
            "exactQuote": title, "title": title, "url": metadata.get("sourceUrl"),
            "sourceFile": metadata.get("sourceFile"), "locator": {"kind": "headline"},
            "retrieval": first.get("retrieval"),
        },
    }


def unavailable(question: str, reason: str) -> dict[str, Any]:
    return {"schemaVersion": "2.0", "status": "UNAVAILABLE", "question": question, "answer": None,
        "claims": [], "citations": [], "confidence": {"score": 0.0, "reasons": [reason]}, "readyForUse": False}


def partial_intro(interpreted: dict[str, Any]) -> str:
    """Describe the verified gap without claiming that the whole corpus lacks an answer."""
    constraints = interpreted.get("constraints") or {}
    locations = [str(value) for value in constraints.get("locations") or [] if str(value).strip()]
    language = interpreted.get("language")
    if language == "ru":
        scope = f" для {', '.join(locations)}" if locations else ""
        return f"Доступные доказательства не подтверждают полностью запрошенную информацию{scope}. Вот что удалось подтвердить:"
    scope = f" pentru {', '.join(locations)}" if locations else ""
    return f"Dovezile disponibile nu confirmă complet informațiile solicitate{scope}. Iată ce poate fi confirmat:"


def requested_scopes(interpreted: dict[str, Any]) -> list[str]:
    """Return stable, user-visible scopes that must not disappear from an answer."""
    values = (interpreted.get("constraints") or {}).get("locations") or []
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        label = str(value).strip()
        key = normalized_text(label)
        if label and key not in seen:
            seen.add(key)
            result.append(label)
    return result


def _scope_in_text(scope: str, text: str) -> bool:
    scope_tokens = content_tokens(scope)
    return bool(scope_tokens) and token_coverage(scope_tokens, content_tokens(text)) >= 0.8


def evidence_for_scopes(evidence: list[dict[str, Any]], scopes: list[str]) -> list[dict[str, Any]]:
    if not scopes:
        return evidence
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for scope in scopes:
        # Recovery claims must be supported by the exact quotation. A title-only
        # location match is merely a retrieval hint and cannot establish scope.
        direct = [item for item in evidence if _scope_in_text(scope, str(item.get("exactQuote") or ""))]
        candidates = direct or [item for item in evidence
                                if _scope_in_text(scope, str(item.get("title") or ""))]
        for item in candidates:
            key = str(item.get("id") or item.get("evidenceId") or id(item))
            if key not in seen:
                seen.add(key)
                selected.append(item)
    return selected


def coverage_ledger(scopes: list[str], claims: list[dict[str, Any]],
                    evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Account for every requested scope using explicit claim wording, never citation proximity."""
    indexed = {str(item.get("id")): item for item in evidence}
    result = []
    for scope in scopes:
        matching_claims = [claim for claim in claims if _scope_in_text(scope, str(claim.get("text") or ""))]
        matching_evidence = [item for item in evidence if _scope_in_text(scope, " ".join(str(value or "") for value in
            (item.get("title"), item.get("exactQuote"))))]
        cited = sorted({identifier for claim in matching_claims for identifier in claim.get("evidenceIds") or []
                        if identifier in indexed})
        result.append({
            "scope": scope,
            "status": "CONFIRMED" if matching_claims else "UNCONFIRMED",
            "claimCount": len(matching_claims),
            "evidenceIds": cited,
            "candidateEvidenceCount": len(matching_evidence),
        })
    return result


FACT_LABELS = {
    "ro": {"amount": "Sumă", "duration": "Durată", "count": "Număr", "status": "Stadiu", "date": "Dată"},
    "ru": {"amount": "Сумма", "duration": "Срок", "count": "Количество", "status": "Статус", "date": "Дата"},
}


def requested_atomic_cells(interpreted: dict[str, Any]) -> list[dict[str, str]]:
    scopes = requested_scopes(interpreted)
    facts = requested_fact_slots(str(interpreted.get("normalizedRomanianQuery") or ""),
                                 interpreted.get("constraints") or {})
    if len(scopes) < 2 or len(facts) < 2:
        return []
    return [{"scope": scope, "factType": fact} for scope in scopes for fact in facts]


def _fact_in_text(fact_type: str, text: str) -> bool:
    value = normalized_text(text)
    if fact_type == "amount":
        return bool(AMOUNT_RE.search(text) or re.search(r"\b(?:buget|contract|valoare|alocat)\w*\b", value))
    if fact_type == "duration":
        return bool(re.search(r"\b(?:durat|perioad|termen)\w*\b", value)
                    or re.search(r"\b\d+\s+(?:de\s+)?(?:luni|luna|zile|ore|saptamani|ani)\b", value))
    if fact_type == "count":
        return bool(re.search(r"\b\d+\s+(?:de\s+)?(?:accese|proiecte|strazi|obiecte|institutii|lucrari)\b", value)
                    or re.search(r"\b(?:numar|cate)\b", value))
    if fact_type == "status":
        return bool(re.search(r"\b(?:stadiu|statut|planificat|preconizat|licitat|achizit|desfasur|demarat|inceput|finalizat|reabilitat|executat)\w*\b", value))
    if fact_type == "date":
        return bool(YEAR_RE.search(text) or re.search(r"\b(?:data|ianuarie|februarie|martie|aprilie|mai|iunie|iulie|august|septembrie|octombrie|noiembrie|decembrie)\b", value))
    return False


def atomic_coverage_ledger(cells: list[dict[str, str]], claims: list[dict[str, Any]],
                           evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    indexed = {str(item.get("id")): item for item in evidence}
    result: list[dict[str, Any]] = []
    for cell in cells:
        scope, fact_type = cell["scope"], cell["factType"]
        matching_claims = [claim for claim in claims
                           if _scope_in_text(scope, str(claim.get("text") or ""))
                           and _fact_in_text(fact_type, str(claim.get("text") or ""))]
        candidates = [item for item in evidence
                      if _scope_in_text(scope, " ".join(str(value or "") for value in
                          (item.get("title"), item.get("exactQuote"))))
                      and (_fact_in_text(fact_type, str(item.get("exactQuote") or ""))
                           or bool((item.get("facts") or {}).get({
                               "amount": "amounts", "duration": "durations", "count": "counts",
                               "date": "dates", "status": "statuses",
                           }.get(fact_type, ""))))]
        cited = sorted({identifier for claim in matching_claims for identifier in claim.get("evidenceIds") or []
                        if identifier in indexed})
        result.append({"scope": scope, "factType": fact_type,
                       "status": "CONFIRMED" if matching_claims else "UNCONFIRMED",
                       "claimCount": len(matching_claims), "evidenceIds": cited,
                       "candidateEvidenceCount": len(candidates)})
    return result


def format_atomic_answer(claims: list[dict[str, Any]], ledger: list[dict[str, Any]],
                         language: str) -> str:
    if not ledger:
        return ""
    fact_types = list(dict.fromkeys(str(item["factType"]) for item in ledger))
    scopes = list(dict.fromkeys(str(item["scope"]) for item in ledger))
    labels = FACT_LABELS.get(language, FACT_LABELS["ro"])
    first_header = "Сектор" if language == "ru" else "Sector"
    missing = "Не подтверждено" if language == "ru" else "Neconfirmat"
    header = f"| {first_header} | " + " | ".join(labels.get(fact, fact) for fact in fact_types) + " |"
    separator = "|---" * (len(fact_types) + 1) + "|"
    rows = [header, separator]
    for scope in scopes:
        cells: list[str] = []
        for fact_type in fact_types:
            matches = [claim for claim in claims
                       if _scope_in_text(scope, str(claim.get("text") or ""))
                       and _fact_in_text(fact_type, str(claim.get("text") or ""))]
            if not matches:
                cells.append(missing)
                continue
            rendered = []
            for claim in matches:
                references = " ".join(f"[{value}]" for value in claim.get("evidenceIds") or [])
                rendered.append(f"{claim['text']} {references}".strip().replace("|", "\\|"))
            cells.append("<br>".join(rendered))
        rows.append(f"| {scope} | " + " | ".join(cells) + " |")
    return "\n".join(rows)


def format_scoped_answer(claims: list[dict[str, Any]], ledger: list[dict[str, Any]], language: str,
                         partial: bool) -> str:
    lines: list[str] = []
    rendered: set[int] = set()
    for entry in ledger:
        scope = str(entry["scope"])
        scoped = [(index, claim) for index, claim in enumerate(claims)
                  if _scope_in_text(scope, str(claim.get("text") or ""))]
        if scoped:
            for index, claim in scoped:
                references = " ".join(f"[{value}]" for value in claim.get("evidenceIds") or [])
                lines.append(f"- {claim['text']} {references}".rstrip())
                rendered.add(index)
        else:
            message = ("информацию по этому пункту не удалось подтвердить по найденным фрагментам."
                       if language == "ru" else
                       "informația pentru acest punct nu a putut fi confirmată din pasajele recuperate.")
            lines.append(f"- {scope}: {message}")
    for index, claim in enumerate(claims):
        if index not in rendered:
            references = " ".join(f"[{value}]" for value in claim.get("evidenceIds") or [])
            lines.append(f"- {claim['text']} {references}".rstrip())
    if not lines:
        return ""
    if not partial:
        return "\n".join(lines)
    intro = ("Доступные доказательства подтверждают только часть запрошенных пунктов:"
             if language == "ru" else
             "Dovezile disponibile confirmă doar o parte dintre punctele solicitate:")
    return f"{intro}\n" + "\n".join(lines)


def contextual_observations(question: str, interpreted: dict[str, Any], evidence: list[dict[str, Any]],
                            prompt_evidence: list[dict[str, Any]], config: Any,
                            api_key: str, target_scopes: list[str] | None = None,
                            target_cells: list[dict[str, str]] | None = None
                            ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    targets = target_scopes or requested_scopes(interpreted)
    generated = chat_json(
        config.generator_model,
        "The requested answer could not be fully verified. Extract useful partial observations in the question language from the exact evidence only. Return {observations:[{text,evidenceIds}]}. Cover each target scope separately when evidence supports it and explicitly name that scope. When targetCells is non-empty, each observation must cover exactly one scope and one requested factType. Each observation must be independently useful, declarative, and limited to one project/place/fact. Prefer precise status such as planned, tendering, ongoing, or completed. Do not invent missing values, do not assert that the entire corpus lacks a fact, and do not attach a number, date, amount or duration to a place unless the exact quotation explicitly links them. Omit an unsupported target instead of guessing. Use only supplied S identifiers.",
        json.dumps({"question": question, "constraints": interpreted.get("constraints") or {},
                    "targetScopes": targets, "targetCells": target_cells or [],
                    "evidence": prompt_evidence}, ensure_ascii=False),
        api_key,
        OBSERVATIONS_SCHEMA,
    )
    observations = generated.get("observations") if isinstance(generated.get("observations"), list) else []
    observations = observations[:config.max_claims]
    verified, decisions = verify_claims(
        observations, evidence, config.verifier_model, api_key, "", interpreted.get("constraints")
    )
    return verified, decisions, generated


def answer(question: str, config_path: Path | None = None, qdrant_path: Path | None = None, qdrant_url: str | None = None, explain: bool = False) -> dict[str, Any]:
    load_dotenv()
    request_tokens = None
    try:
        config = load_config(config_path)
        request_tokens = begin_interactive_request(
            config.interactive_deadline_seconds, config.per_call_timeout_seconds,
            config.fallback_models,
        )
        api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
        if not api_key:
            return unavailable(question, "OPENROUTER_API_KEY is not configured")
        question, selected_title = split_explicit_selection(question)
        interpreted = interpret_query(question, config, api_key)
        retrieval_question = f"{question}\n{selected_title}" if selected_title else question
        retrieval_interpreted = interpreted
        if selected_title:
            retrieval_interpreted = {**interpreted,
                "normalizedRomanianQuery": f'{interpreted["normalizedRomanianQuery"]} {selected_title}'}
        found = retrieve(retrieval_question, retrieval_interpreted, config, api_key, qdrant_path, qdrant_url, explain)
        explicitly_selected = evidence_for_selected_title(found["evidence"], selected_title) if selected_title else []
        scoped_items = explicitly_selected or found["evidence"]
        ambiguity_diagnostics = ({"decision": "explicit-selection", "selectedTitle": selected_title,
                                  "selectedDocumentId": explicitly_selected[0].get("documentId")}
                                 if explicitly_selected else
                                 {"decision": "qwen-first", "policy": "model interprets retrieved evidence"})
        evidence = expose_evidence(scoped_items)
        common = {"schemaVersion": "2.0", "question": question, "detectedLanguage": interpreted["language"],
            "normalizedRetrievalQuery": interpreted["normalizedRomanianQuery"], "interpretedConstraints": interpreted["constraints"]}
        if not evidence:
            return {**common, "status": "NOT_FOUND", "answer": "Informația nu a fost găsită în corpusul disponibil." if interpreted["language"] == "ro" else "Информация не найдена в доступном корпусе.", "claims": [], "citations": [], "confidence": {"score": .96, "reasons": ["No candidate passed the relevance threshold"]}, "readyForUse": True}
        prompt_evidence = [{key: item.get(key) for key in
            ("id", "documentId", "evidenceKind", "exactQuote", "title", "url", "locator", "facts",
             "publisher", "publishedDate", "category", "district")}
            for item in evidence]
        generated = chat_json(config.generator_model,
            "You are a helpful municipal information assistant. Interpret the user's question naturally and answer directly in the same language. Synthesize the most relevant retrieved passages yourself instead of asking the user to select a document. First identify every item the user actually requests, then include only claims that directly answer those items or clearly explain a missing item. Do not pad the answer with related but different statistics, and never treat a facility, service, participant, meal, project, or budget count as an institution count. Use only information present in the supplied evidence, and cite every factual statement with one or more supplied S identifiers. When sources are dated, distinguish historical information from a current status; do not silently present an old status as current. If the evidence answers only part of the question, return PARTIAL, provide the useful part, and briefly identify exactly what could not be established. If sources genuinely conflict, explain the conflict. Return JSON with status and claims [{text,evidenceIds}]. Do not invent source identifiers or facts.",
            json.dumps({"question": question, "interpretedContext": interpreted.get("constraints") or {},
                        "evidence": prompt_evidence}, ensure_ascii=False), api_key, CLAIMS_SCHEMA)
        raw_claims = generated.get("claims") if isinstance(generated.get("claims"), list) else []
        claims, citations = retain_cited_claims(raw_claims, evidence, config.max_claims)
        proposed_status = str(generated.get("status") or "PARTIAL")
        if not claims:
            status = "NOT_FOUND"
        elif proposed_status in {"SUPPORTED", "PARTIAL", "CONTRADICTION"}:
            status = proposed_status
        else:
            status = "PARTIAL"
        text = "\n".join(
            f"{claim['text']} {' '.join(f'[{value}]' for value in claim['evidenceIds'])}"
            for claim in claims
        )
        result = {**common, "status": status,
            "answer": text or ("Informația nu a putut fi confirmată din pasajele recuperate."
                               if interpreted["language"] == "ro" else
                               "Информацию не удалось подтвердить по найденным фрагментам."),
            "claims": claims, "citations": citations, "coverage": [],
            "confidence": {"score": .82 if status == "SUPPORTED" else .6 if claims else .2,
                           "reasons": ["Qwen synthesized the retrieved evidence",
                                       "Citation identifiers were structurally validated"]},
            "readyForUse": True}
        result["_trace"] = {"generation": generated.get("_managedResponse"), "answerPolicy": "qwen-first"}
        if explain:
            result["diagnostics"] = {"retrieval": found["diagnostics"], "ambiguity": ambiguity_diagnostics,
                "answerPolicy": "qwen-first", "models": config.raw["models"],
                "generation": generated.get("_managedResponse")}
        return result
    except Exception as error:
        return unavailable(question, str(error))
    finally:
        if request_tokens is not None:
            end_interactive_request(request_tokens)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="High-precision bilingual municipal RAG answerer")
    parser.add_argument("--question")
    parser.add_argument("--config", type=Path)
    location = parser.add_mutually_exclusive_group()
    location.add_argument("--qdrant-url")
    location.add_argument("--qdrant-path", type=Path)
    parser.add_argument("--explain", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    question = (args.question or input("Scrie întrebarea în română sau rusă: ")).strip()
    started = time.monotonic()
    result = answer(question, args.config, args.qdrant_path, args.qdrant_url, args.explain)
    try:
        write_trace(result, int((time.monotonic() - started) * 1000), load_config(args.config).raw["models"])
    except OSError:
        pass
    result.pop("_trace", None)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(result.get("answer") or result.get("clarificationQuestion") or "Serviciul nu este disponibil.")
        for source in result.get("citations", []):
            print(f"- [{source['id']}] {source['title']}\n  {source['exactQuote']}\n  {source.get('url') or ''}")
    return 1 if result["status"] == "UNAVAILABLE" else 0
