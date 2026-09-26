from __future__ import annotations

import json
import re
from typing import Any

from .api import chat_json

NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)?")
VERDICT_SCHEMA = {"type": "object", "properties": {"supported": {"type": "boolean"}, "reason": {"type": "string"}}, "required": ["supported", "reason"], "additionalProperties": False}


def deterministic_issues(claim: dict[str, Any], evidence: dict[str, dict[str, Any]], question: str = "") -> list[str]:
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
    return issues


def verify_claims(claims: list[dict[str, Any]], evidence: list[dict[str, Any]], model: str, api_key: str, question: str = "") -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    indexed = {item["id"]: item for item in evidence}
    retained, decisions = [], []
    for claim in claims:
        issues = deterministic_issues(claim, indexed, question)
        if issues:
            decisions.append({"claim": claim.get("text"), "evidenceIds": claim.get("evidenceIds"), "supported": False, "reasons": issues})
            continue
        cited = [indexed[item] for item in claim["evidenceIds"]]
        verdict = chat_json(model, "Verify full entailment from exact quotations and same project/place/time. No outside knowledge. Return supported boolean and reason.", json.dumps({"claim": claim["text"], "evidence": cited}, ensure_ascii=False), api_key, VERDICT_SCHEMA)
        supported = verdict.get("supported") is True
        decisions.append({"claim": claim.get("text"), "supported": supported, "reason": verdict.get("reason"), "managedResponse": verdict.get("_managedResponse")})
        if supported:
            retained.append(claim)
    return retained, decisions
