from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from .api import chat_json

MAX_PARALLEL_VERIFICATIONS = 8
VERIFIER_PROMPT = ("Verify that the claim is fully entailed by the exact quotations, for the same project/place/time, and that it directly "
    "answers the question about the same event, entity and period. A claim about a different event, year or entity, or one that only "
    "says the evidence lacks the requested information, is not supported. No outside knowledge. Return supported boolean and reason.")
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

    def check(claim: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
        issues = deterministic_issues(claim, indexed, question)
        if issues:
            return False, {"claim": claim.get("text"), "evidenceIds": claim.get("evidenceIds"), "supported": False, "reasons": issues}
        cited = [indexed[item] for item in claim["evidenceIds"]]
        verdict = chat_json(model, VERIFIER_PROMPT, json.dumps({"question": question, "claim": claim["text"], "evidence": cited}, ensure_ascii=False), api_key, VERDICT_SCHEMA)
        supported = verdict.get("supported") is True
        return supported, {"claim": claim.get("text"), "supported": supported, "reason": verdict.get("reason"), "managedResponse": verdict.get("_managedResponse")}

    # Claims are verified independently, so the managed calls run concurrently; results keep claim order.
    with ThreadPoolExecutor(max_workers=max(1, min(MAX_PARALLEL_VERIFICATIONS, len(claims)))) as pool:
        results = list(pool.map(check, claims))
    retained = [claim for claim, (supported, _) in zip(claims, results) if supported]
    return retained, [decision for _, decision in results]
