from __future__ import annotations

import json
import re
import unicodedata
from typing import Any

from .api import chat_json

NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)?")
VERDICT_SCHEMA = {"type": "object", "properties": {"supported": {"type": "boolean"}, "reason": {"type": "string"}}, "required": ["supported", "reason"], "additionalProperties": False}
BATCH_VERDICT_SCHEMA = {
    "type": "object",
    "properties": {
        "verdicts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "index": {"type": "integer", "minimum": 0},
                    "supported": {"type": "boolean"},
                    "reason": {"type": "string"},
                },
                "required": ["index", "supported", "reason"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["verdicts"],
    "additionalProperties": False,
}

KNOWN_DISTRICTS = ("botanica", "buiucani", "centru", "ciocana", "rascani")
COMPLETED_RE = re.compile(r"\b(?:reparat\w*|realizat\w*|executat\w*|finalizat\w*|construit\w*|modernizat\w*)\b")
FUTURE_RE = re.compile(
    r"\b(?:urmeaza|vor fi|va fi|preconizat\w*|planificat\w*|licitati\w*|achiziti\w*|se va|предстоит|планиру\w*)\b"
)
CONTENT_STOPWORDS = {
    "a", "al", "ale", "au", "catre", "care", "cu", "de", "din", "este", "fi", "fost",
    "in", "la", "o", "pe", "pentru", "prin", "se", "si", "sunt", "un", "unei", "urmeaza",
    "были", "для", "из", "на", "по", "и", "в", "с",
}


def _normalize(value: str) -> str:
    folded = "".join(character for character in unicodedata.normalize("NFKD", value.casefold())
                     if not unicodedata.combining(character))
    folded = re.sub(r"\bbd(?:\.(?=\s|$)|\b)", "bulevardul", folded)
    return re.sub(r"\bstr(?:\.(?=\s|$)|\b)", "strada", folded)


def _time_conflict(question: str, evidence: str) -> bool:
    query, text = _normalize(question), _normalize(evidence)
    current = ("anul curent", "acest an", "anul acesta")
    previous = ("anul trecut", "anul precedent")
    if any(value in query for value in current) and any(value in text for value in previous) and not any(value in text for value in current):
        return True
    if any(value in query for value in previous) and any(value in text for value in current) and not any(value in text for value in previous):
        return True
    query_years = set(re.findall(r"\b(?:19|20)\d{2}\b", query))
    evidence_years = set(re.findall(r"\b(?:19|20)\d{2}\b", text))
    return bool(query_years and evidence_years and query_years.isdisjoint(evidence_years))


def _quoted_title_mismatch(question: str, title: str) -> bool:
    quoted = re.findall(r"[«\"]([^»\"]{20,})[»\"]", question)
    if not quoted:
        return False
    title_tokens = set(re.findall(r"[a-z0-9]+", _normalize(title)))
    requested = set(re.findall(r"[a-z0-9]+", _normalize(max(quoted, key=len))))
    ignored = {"a", "al", "ale", "cu", "de", "din", "in", "la", "pe", "pentru", "si"}
    requested -= ignored
    return bool(requested) and len(requested & title_tokens) / len(requested) < 0.5


def _locations(question: str, constraints: dict[str, Any] | None) -> list[str]:
    values = [str(value) for value in (constraints or {}).get("locations") or [] if str(value).strip()]
    normalized_question = _normalize(question)
    values.extend(district for district in KNOWN_DISTRICTS if district in normalized_question)
    result: list[str] = []
    for value in values:
        normalized = _normalize(value).strip()
        normalized = re.sub(r"\b(?:sectorul|sector|sec)\.?\s+", "", normalized).strip()
        if normalized and normalized not in result:
            result.append(normalized)
    return result


def _contains_location(text: str, location: str) -> bool:
    normalized = _normalize(text)
    return bool(re.search(rf"\b{re.escape(location)}\b", normalized))


def claim_scope_constraints(text: str, constraints: dict[str, Any] | None) -> dict[str, Any]:
    """Narrow answer-wide locations to those explicitly asserted by one claim."""
    scoped = dict(constraints or {})
    original = [str(value) for value in scoped.get("locations") or [] if str(value).strip()]
    scoped["locations"] = [value for value in original
                           if _contains_location(text, re.sub(r"\b(?:sectorul|sector|sec)\.?\s+", "",
                                                             _normalize(value)).strip())]
    scoped["multipleProjects"] = len(scoped["locations"]) > 1
    return scoped


def _sentences(text: str) -> list[str]:
    return [value.strip() for value in re.split(r"(?<=[.!?])\s+|[\r\n]+", _normalize(text)) if value.strip()]


def _content_tokens(text: str) -> list[str]:
    return [token for token in re.findall(r"[^\W_]+|\d+", _normalize(text), re.UNICODE)
            if len(token) > 2 and token not in CONTENT_STOPWORDS]


def _lexically_matches(token: str, available: str) -> bool:
    if token == available:
        return True
    if token.isdigit() or available.isdigit():
        return False
    shorter, longer = sorted((token, available), key=len)
    return len(shorter) >= 5 and longer.startswith(shorter[:max(5, len(shorter) - 1)])


def _lexical_entailment_issue(text: str, cited: list[dict[str, Any]]) -> str | None:
    """Fail closed on long claims that add many details absent from exact evidence."""
    claim_tokens = _content_tokens(text)
    if len(claim_tokens) < 12:
        return None
    evidence_tokens = _content_tokens(" ".join(str(source.get("exactQuote") or "") for source in cited))
    if not evidence_tokens:
        return "LOW_LEXICAL_ENTAILMENT"
    covered = sum(any(_lexically_matches(token, available) for available in evidence_tokens)
                  for token in claim_tokens)
    return "LOW_LEXICAL_ENTAILMENT" if covered / len(claim_tokens) < 0.55 else None


def _scope_issues(text: str, question: str, cited: list[dict[str, Any]],
                  constraints: dict[str, Any] | None) -> list[str]:
    """Ensure quantities are tied to every place asserted by the claim."""
    requested_locations = _locations(question, constraints)
    claim_locations = [value for value in requested_locations if _contains_location(text, value)]
    numbers = set(NUMBER_RE.findall(text))
    if len(requested_locations) > 1 and numbers and not claim_locations:
        return ["MISSING_CLAIM_LOCATION_SCOPE"]

    issues: list[str] = []
    quotes = [str(source.get("exactQuote") or "") for source in cited]
    for location in claim_locations:
        if not any(_contains_location(quote, location) for quote in quotes):
            issues.append(f"UNSUPPORTED_LOCATION:{location}")
            continue
        for number in numbers:
            linked = False
            for quote in quotes:
                sentences = _sentences(quote)
                for index, sentence in enumerate(sentences):
                    if number not in NUMBER_RE.findall(sentence):
                        continue
                    # A project/place introduced immediately before a numeric
                    # sentence scopes that number. A place mentioned only later
                    # must not inherit an earlier contract value.
                    context = " ".join(sentences[max(0, index - 1):index + 1])
                    if _contains_location(context, location):
                        linked = True
                        break
                if linked:
                    break
            if not linked:
                issues.append(f"NUMBER_LOCATION_SCOPE_MISMATCH:{number}:{location}")

    normalized_claim = _normalize(text)
    if COMPLETED_RE.search(normalized_claim):
        for location in claim_locations:
            relevant = " ".join(sentence for quote in quotes for sentence in _sentences(quote)
                                if _contains_location(sentence, location))
            if relevant and FUTURE_RE.search(relevant) and not COMPLETED_RE.search(relevant):
                issues.append(f"PROJECT_STAGE_MISMATCH:{location}")
    return issues


def minimize_numeric_evidence(claim: dict[str, Any], evidence: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Keep the best single citation when it independently supports a numeric claim."""
    identifiers = [item for item in claim.get("evidenceIds") or [] if item in evidence]
    numbers = set(NUMBER_RE.findall(str(claim.get("text") or "")))
    if not numbers or len(identifiers) < 2:
        return claim
    currencies = {value.casefold() for value in re.findall(r"\b(?:lei|mdl|eur|euro)\b", str(claim.get("text") or ""), re.I)}
    claim_tokens = set(re.findall(r"[a-z0-9]+", _normalize(str(claim.get("text") or ""))))
    claim_tokens -= {"a", "au", "de", "fost", "in", "la", "pe", "pentru", "reparat", "reparate", "reparati", "accese"}
    candidates: list[tuple[float, str]] = []
    for identifier in identifiers:
        source = evidence[identifier]
        quote = str(source.get("exactQuote") or "")
        available_numbers = set(NUMBER_RE.findall(quote))
        available_currencies = {value.casefold() for value in re.findall(r"\b(?:lei|mdl|eur|euro)\b", quote, re.I)}
        if not numbers <= available_numbers or not currencies <= available_currencies:
            continue
        source_text = f"{source.get('title') or ''} {quote}"
        source_tokens = set(re.findall(r"[a-z0-9]+", _normalize(source_text)))
        lexical_score = len(claim_tokens & source_tokens) / max(len(claim_tokens), 1)
        candidates.append((lexical_score, identifier))
    if not candidates:
        return claim
    candidates.sort(key=lambda item: (-item[0], item[1]))
    return {**claim, "evidenceIds": [candidates[0][1]]}


def deterministic_issues(claim: dict[str, Any], evidence: dict[str, dict[str, Any]], question: str = "",
                         constraints: dict[str, Any] | None = None) -> list[str]:
    identifiers = claim.get("evidenceIds") or []
    if not identifiers or any(item not in evidence for item in identifiers):
        return ["MISSING_OR_UNKNOWN_EVIDENCE"]
    text = str(claim.get("text") or "")
    if not text.strip() or text.rstrip().endswith("?"):
        return ["CLAIM_IS_NOT_DECLARATIVE"]
    normalized_question = re.sub(r"\W+", " ", question.casefold()).strip()
    normalized_claim = re.sub(r"\W+", " ", text.casefold()).strip()
    if normalized_question and normalized_claim.startswith(normalized_question):
        return ["CLAIM_ECHOES_QUESTION"]
    claimed = set(NUMBER_RE.findall(text))
    available = {number for item in identifiers for number in NUMBER_RE.findall(str(evidence[item].get("exactQuote", "")))}
    issues = []
    if all(evidence[item].get("evidenceKind") == "headline" for item in identifiers):
        issues.append("HEADLINE_ONLY")
    if claimed - available:
        issues.append("UNSUPPORTED_NUMBER:" + ",".join(sorted(claimed - available)))
    if claimed and len({evidence[item].get("documentId") for item in identifiers}) > 1:
        issues.append("CROSS_DOCUMENT_NUMERIC_CLAIM")
    currencies = {value.casefold() for value in re.findall(r"\b(?:lei|mdl|eur|euro)\b", text, re.I)}
    available_currencies = {value.casefold() for item in identifiers for value in re.findall(r"\b(?:lei|mdl|eur|euro)\b", str(evidence[item].get("exactQuote", "")), re.I)}
    if currencies - available_currencies:
        issues.append("UNSUPPORTED_CURRENCY")
    amount_question = bool(re.search(
        r"\b(?:ce sum[aă]|care (?:este )?suma|c[aâ]te milioane|buget|alocat\w*)\b",
        _normalize(question), re.I,
    ))
    if amount_question and not currencies:
        issues.append("REQUESTED_AMOUNT_MISSING")
    for item in identifiers:
        source = evidence[item]
        source_text = " ".join(str(value or "") for value in (source.get("title"), source.get("exactQuote")))
        if _time_conflict(question, source_text):
            issues.append("QUESTION_EVIDENCE_TIME_CONFLICT")
            break
    if any(_quoted_title_mismatch(question, str(evidence[item].get("title") or "")) for item in identifiers):
        issues.append("PROJECT_TITLE_MISMATCH")
    lexical_issue = _lexical_entailment_issue(text, [evidence[item] for item in identifiers])
    if lexical_issue:
        issues.append(lexical_issue)
    issues.extend(_scope_issues(text, question, [evidence[item] for item in identifiers], constraints))
    return issues


def verify_claims(claims: list[dict[str, Any]], evidence: list[dict[str, Any]], model: str, api_key: str,
                  question: str = "", constraints: dict[str, Any] | None = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    indexed = {item["id"]: item for item in evidence}
    retained_by_index: dict[int, dict[str, Any]] = {}
    decisions_by_index: dict[int, dict[str, Any]] = {}
    pending: list[dict[str, Any]] = []
    normalized_claims: list[dict[str, Any]] = []
    for index, original in enumerate(claims):
        claim = minimize_numeric_evidence(original, indexed)
        normalized_claims.append(claim)
        issues = deterministic_issues(claim, indexed, question, constraints)
        if issues:
            decisions_by_index[index] = {"claim": claim.get("text"), "evidenceIds": claim.get("evidenceIds"),
                                         "supported": False, "reasons": issues}
            continue
        cited = [indexed[item] for item in claim["evidenceIds"]]
        claim_constraints = claim_scope_constraints(str(claim.get("text") or ""), constraints)
        pending.append({"index": index, "claim": claim["text"],
                        "claimScopeConstraints": claim_constraints, "evidence": cited})

    if pending:
        response = chat_json(
            model,
            "Verify every indexed claim independently and return exactly one verdict per index. Judge only whether that individual claim is fully entailed clause by clause by its exact quotations. Do not reject a locally supported claim merely because the overall question asks about additional locations; answer completeness is checked separately. Reject when an amount, date, duration, count, activity, project, place, period, or work stage is absent or belongs elsewhere. Planned procurement is not completed work. Never infer that one value applies to multiple places. No outside knowledge.",
            json.dumps({"question": question, "answerWideConstraints": constraints or {},
                        "claims": pending}, ensure_ascii=False),
            api_key,
            BATCH_VERDICT_SCHEMA,
        )
        verdicts = {item.get("index"): item for item in response.get("verdicts") or []
                    if isinstance(item, dict) and isinstance(item.get("index"), int)}
        for item in pending:
            index = item["index"]
            verdict = verdicts.get(index)
            supported = bool(verdict and verdict.get("supported") is True)
            decisions_by_index[index] = {
                "claim": normalized_claims[index].get("text"),
                "supported": supported,
                "reason": (verdict or {}).get("reason") or "Verifier returned no verdict for this claim",
                "managedResponse": response.get("_managedResponse"),
            }
            if supported:
                retained_by_index[index] = normalized_claims[index]
    return ([retained_by_index[index] for index in sorted(retained_by_index)],
            [decisions_by_index[index] for index in sorted(decisions_by_index)])
