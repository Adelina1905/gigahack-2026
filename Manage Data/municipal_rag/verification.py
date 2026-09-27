from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

from .api import chat_json

# (model, system, user, schema) -> parsed JSON object; the API key is bound by the caller.
ChatJson = Callable[[str, str, str, "dict[str, Any] | None"], dict[str, Any]]

MAX_PARALLEL_VERIFICATIONS = 8
VERIFIER_PROMPT = ("Verify that the claim is fully entailed by the exact quotations, for the same project/place/time, and that it directly "
    "answers the question about the same event, entity and period. A claim about a different event, year or entity, or one that only "
    "says the evidence lacks the requested information, is not supported. The claim may be written in another language than the "
    "Romanian quotations; a faithful translation is supported. No outside knowledge. Return supported boolean and a reason of at "
    "most 15 words.")
# Types a model must judge; hours, dates, amounts and legal acts are checked deterministically on the whole answer.
MODEL_CHECKED_TYPES = {"person": "a person", "place": "a place or address", "procedure": "the steps or documents of a procedure",
    "list": "the requested items"}
NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)?")
FINANCIAL_STAGES = {
    "BUDGETED": re.compile(r"\b(?:bugetat\w*|prev[aă]zut\w*\s+(?:în|din)\s+buget|budgeted|запланирован\w*\s+в\s+бюджет)\b", re.I),
    "ALLOCATED": re.compile(r"\b(?:alocat\w*|allocation|allocated|выделен\w*)\b", re.I),
    "CONTRACTED": re.compile(r"\b(?:contractat\w*|valoarea\s+contractului|contracted|законтрактован\w*|стоимость\s+контракта)\b", re.I),
    "SPENT": re.compile(r"\b(?:cheltui\w*|achitat\w*|pl[aă]tit\w*|executat\w*\s+financiar|spent|paid|израсходован\w*|оплачен\w*)\b", re.I),
}
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
    # The document title (act type, number and date) is part of the cited source, next to the exact quote.
    sources = [f"{evidence[item].get('title') or ''} {evidence[item].get('exactQuote') or ''}" for item in identifiers]
    available = {number for source in sources for number in NUMBER_RE.findall(source)}
    # "17.03.2026" in a quote also supports "17", "03" and "2026" in a translated claim.
    available |= {part for number in list(available) for part in re.split(r"[.,]", number)}
    available |= {number.lstrip("0") or "0" for number in list(available)}
    issues = []
    if all(evidence[item].get("evidenceKind") == "headline" for item in identifiers):
        issues.append("HEADLINE_ONLY")
    if claimed - available:
        issues.append("UNSUPPORTED_NUMBER:" + ",".join(sorted(claimed - available)))
    if claimed and len({evidence[item].get("documentId") for item in identifiers}) > 1:
        issues.append("CROSS_DOCUMENT_NUMERIC_CLAIM")
    currencies = {value.casefold() for value in re.findall(r"\b(?:lei|mdl|eur|euro)\b", text, re.I)}
    available_currencies = {value.casefold() for source in sources for value in re.findall(r"\b(?:lei|mdl|eur|euro)\b", source, re.I)}
    if currencies - available_currencies:
        issues.append("UNSUPPORTED_CURRENCY")
    source_text = " ".join(sources)
    for stage, pattern in FINANCIAL_STAGES.items():
        if pattern.search(text) and not pattern.search(source_text):
            issues.append(f"UNSUPPORTED_FINANCIAL_STAGE:{stage}")
    return issues


def verifier_prompt(answer_type: str = "other") -> str:
    expected = MODEL_CHECKED_TYPES.get(answer_type)
    return VERIFIER_PROMPT if expected is None else VERIFIER_PROMPT + f" The question asks for {expected}; a claim that provides none of it does not answer the question."


def verify_claims(claims: list[dict[str, Any]], evidence: list[dict[str, Any]], model: str, api_key: str, question: str = "",
                  answer_type: str = "other", chat: ChatJson | None = None,
                  requirements: dict[str, dict[str, Any]] | None = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    indexed = {item["id"]: item for item in evidence}
    chat = chat or (lambda model_name, system, user, schema=None: chat_json(model_name, system, user, api_key, schema))
    fields = ("id", "documentId", "title", "publisher", "publishedDate", "exactQuote")

    def check(claim: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
        requirement = (requirements or {}).get(str(claim.get("requirementId") or ""), {})
        effective_question = str(requirement.get("question") or question)
        effective_answer_type = str(requirement.get("answerType") or answer_type)
        issues = deterministic_issues(claim, indexed, effective_question)
        if issues:
            return False, {"claim": claim.get("text"), "evidenceIds": claim.get("evidenceIds"), "supported": False, "reasons": issues}
        cited = [{key: indexed[item].get(key) for key in fields} for item in claim["evidenceIds"]]
        verdict = chat(model, verifier_prompt(effective_answer_type),
                       json.dumps({"question": effective_question, "claim": claim["text"], "evidence": cited}, ensure_ascii=False),
                       VERDICT_SCHEMA)
        supported = verdict.get("supported") is True
        return supported, {"claim": claim.get("text"), "supported": supported, "reason": verdict.get("reason"), "managedResponse": verdict.get("_managedResponse")}

    # Claims are verified independently, so the managed calls run concurrently; results keep claim order.
    with ThreadPoolExecutor(max_workers=max(1, min(MAX_PARALLEL_VERIFICATIONS, len(claims)))) as pool:
        results = list(pool.map(check, claims))
    retained = [claim for claim, (supported, _) in zip(claims, results) if supported]
    return retained, [decision for _, decision in results]
