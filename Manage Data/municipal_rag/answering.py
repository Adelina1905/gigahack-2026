from __future__ import annotations

import argparse
import json
import os
import time
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Callable

from . import guardrails
from .api import chat_json, embed
from .config import RagConfig, load_config, load_dotenv
from .retrieval import interpret_query, retrieve
from .verification import ChatJson, verify_claims
from .tracing import write_trace

CLAIMS_SCHEMA = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": ["SUPPORTED", "PARTIAL", "NOT_FOUND", "CONTRADICTION"]},
        "claims": {
            "type": "array",
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
SCREEN_MARKER = "Screen retrieved municipal passages"


def screen_schema(identifiers: list[str]) -> dict[str, Any]:
    """One reason code per passage id; mapping ids to codes keeps the screen's output (and latency) small."""
    return {"type": "object", "properties": {value: {"type": "string", "enum": list(guardrails.SCREEN_CODES)} for value in identifiers},
            "required": list(identifiers), "additionalProperties": False}


SCREEN_PROMPT = (
    SCREEN_MARKER + " for one question; today is {today}. For every passage id decide whether the passage is about "
    "the same subject the question asks about: the same event or project, the same institution, person, street or district, and the "
    "same period. A relevant passage is about that subject, even if it lacks the exact requested value; label it RELEVANT_A. "
    "Passages about the same specific thing share a letter, even when they complement each other. When the question does not say "
    "which one of several distinct things of the same kind it means (which lyceum, which sector's office, which tournament, which "
    "year's edition), give each distinct thing its own letter: RELEVANT_A, RELEVANT_B, RELEVANT_C, RELEVANT_D. Label every other passage DIFFERENT_EVENT (another event or project), DIFFERENT_PERIOD (another year or period "
    "than the question asks), DIFFERENT_ENTITY (another institution, person, street, locality or district, or another kind of "
    "institution or service, such as kindergarten instead of school) or TOPIC_ONLY (it only "
    "shares words or a broad theme with the question). Be strict. Return an object mapping every passage id to its label.")
GENERATION_PROMPT = (
    "Answer the question in {language} using only the exact evidence. Return JSON {{status, claims:[{{text,evidenceIds}}]}}. "
    "Every claim is one or two declarative sentences that directly answer the question; never repeat or paraphrase the question. "
    "Name the locality, institution or date of a fact when the evidence gives it. "
    "The question asks for {expected}: state it explicitly{legal}. When the evidence covers only part of it, answer that part. "
    "Only when no evidence contains any of it, return status NOT_FOUND with an empty claims list. Never write claims about what the "
    "evidence does not mention or claims that only describe related context. Separate projects. Never merge numeric values across documents. A headline alone cannot support a "
    "claim. Only evidence about the same event, entity, place and period as the question can answer it. When documents state "
    "conflicting values for the same thing, give each value as its own claim with its own evidence and set status CONTRADICTION. "
    "Evidence marked outdated is from an earlier year: name that year in the claim.")
CORRECTION_PROMPT = (
    "Correct once: answer the question in {language} with declarative claims [{{text,evidenceIds}}], using only the S identifiers in "
    "evidence. The evidence was screened as relevant to the question, and earlier claims (possibly none) are given with the "
    "verifier's decisions. Never repeat the question. The question asks for {expected}; include it when present{legal}. Remove every claim the "
    "verifier rejected unless you can fix it from the evidence, and keep the claims it accepted. Only when no evidence contains any "
    "of the requested information, return an empty claims list with status NOT_FOUND. Never write a claim about what the evidence "
    "does not mention.")
PROMPT_TYPES = {"hours": "working or opening hours", "date": "a date or period", "amount": "an amount or value",
    "person": "a person", "place": "a place or address", "procedure": "the steps or required documents",
    "legal_act": "the applicable legal acts", "list": "the items asked about", "other": "the requested information"}
LANGUAGE_NAMES = {"ro": "Romanian", "ru": "Russian", "en": "English"}
CITATION_FIELDS = ("id", "evidenceId", "documentId", "versionId", "evidenceKind", "exactQuote", "title", "url", "sourceFile",
                   "locator", "publisher", "publishedDate", "outdated", "retrieval")


@dataclass(frozen=True)
class AnswerDependencies:
    """Model and search calls used by `run_answer`; tests pass hand-written implementations."""

    chat: ChatJson
    embed: Callable[[str], list[float]]
    # (question, interpreted, dense query vector) -> {"evidence": [...], "diagnostics": ...}
    retrieve: Callable[[str, dict[str, Any], list[float]], dict[str, Any]]
    today: Callable[[], date] = date.today


def live_dependencies(config: RagConfig, api_key: str, qdrant_path: Path | None, qdrant_url: str | None, explain: bool) -> AnswerDependencies:
    return AnswerDependencies(
        chat=lambda model, system, user, schema=None: chat_json(model, system, user, api_key, schema),
        embed=lambda text: embed(text, config.embedding_model, api_key),
        retrieve=lambda question, interpreted, dense: retrieve(question, interpreted, config, api_key, qdrant_path, qdrant_url, explain, dense))


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
            "sourceFile": meta.get("sourceFile"), "publisher": meta.get("publisher"), "publishedDate": meta.get("publishedDate"),
            "category": meta.get("category"), "district": meta.get("district"), "heading": meta.get("heading") or [],
            "locator": item.get("sourceLocator") or ((item.get("citations") or [{}])[0].get("locator")),
            "retrieval": item.get("retrieval"), "score": float((item.get("retrieval") or {}).get("rerankScore") or 0.0),
            "outdated": False})
    return result


def ambiguity(items: list[dict[str, Any]], interpreted: dict[str, Any], ratio: float, minimum_score: float) -> list[dict[str, str]]:
    """Choices when several strong, distinct documents tie; weak ties are left to generation and verification."""
    scored = [{**item, "effectiveScore": float(item.get("effectiveScore", (item.get("retrieval") or {}).get("rerankScore", 0)))}
              for item in items]
    return choices_for(guardrails.clarification_documents(scored, bool(interpreted["constraints"].get("multipleProjects")), ratio, minimum_score))


def choices_for(documents: list[dict[str, Any]]) -> list[dict[str, str]]:
    choices, labels = [], set()
    for item in documents:
        label = guardrails.choice_label({**(item.get("metadata") or {}), **item, "url": item.get("url") or (item.get("metadata") or {}).get("sourceUrl")})
        if label in labels:
            label = f"{label[:100]} ({str(item['documentId'])[-6:]})"
        labels.add(label)
        choices.append({"documentId": str(item["documentId"]), "label": label})
    return choices


def dense_text(text: str, yearly: bool, today: date) -> str:
    """Yearly topics asked without a year search for the current year's documents."""
    return f"{text} {today.year}" if yearly and not guardrails.years_in(text) else text


def unavailable(question: str, reason: str) -> dict[str, Any]:
    return {"schemaVersion": "2.0", "status": "UNAVAILABLE", "question": question, "answer": None, "reason": None, "flags": [],
        "claims": [], "citations": [], "confidence": {"score": 0.0, "reasons": [reason]}, "readyForUse": False}


def prompt_evidence(items: list[dict[str, Any]], quote_limit: int | None = None) -> list[dict[str, Any]]:
    fields = ("id", "documentId", "evidenceKind", "title", "publisher", "publishedDate", "category", "exactQuote")
    result = []
    for item in items:
        value = {key: item.get(key) for key in fields}
        if quote_limit is not None:
            value["exactQuote"] = str(value.get("exactQuote") or "")[:quote_limit]
        if item.get("outdated"):
            value["outdated"] = True
        result.append(value)
    return result


def claims_of(generated: dict[str, Any]) -> list[dict[str, Any]]:
    claims = generated.get("claims") if isinstance(generated.get("claims"), list) else []
    return [claim for claim in claims if isinstance(claim, dict)]


def answer(question: str, config_path: Path | None = None, qdrant_path: Path | None = None, qdrant_url: str | None = None,
           explain: bool = False, history: list[dict[str, str]] | None = None,
           dependencies: AnswerDependencies | None = None) -> dict[str, Any]:
    load_dotenv()
    try:
        config = load_config(config_path)
        if dependencies is None:
            api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
            if not api_key:
                return unavailable(question, "OPENROUTER_API_KEY is not configured")
            dependencies = live_dependencies(config, api_key, qdrant_path, qdrant_url, explain)
        return run_answer(question, history or [], config, dependencies, explain)
    except Exception as error:
        return unavailable(question, str(error))


def run_answer(question: str, history: list[dict[str, str]], config: RagConfig, deps: AnswerDependencies, explain: bool = False) -> dict[str, Any]:
    settings = config.raw.get("guardrails", {})
    thresholds = config.raw["thresholds"]
    followup = guardrails.clarification_followup(question, history)
    # A picked clarification choice re-asks the original question scoped to that document; no rewrite is needed.
    search_question, turns, scope_label = (followup[0], [], followup[1]) if followup else (question, history, None)
    today = deps.today()
    # The dense query embeds the question as asked, so it does not wait for the interpreter.
    embedded_text = dense_text(search_question, guardrails.is_yearly_topic(search_question), today)
    with ThreadPoolExecutor(max_workers=2) as pool:
        embedding = pool.submit(deps.embed, embedded_text)
        interpreted = interpret_query(search_question, config, "", history=turns, chat=deps.chat, message=search_question)
        dense_query = embedding.result()
    standalone = interpreted["standaloneQuestion"]
    constraints = interpreted["constraints"]
    language, answer_type = interpreted["language"], constraints["answerType"]
    wanted_text = dense_text(standalone, bool(constraints["yearlyTopic"]), today)
    if wanted_text != embedded_text:
        dense_query = deps.embed(wanted_text)
    interpreted["retrievalQuery"] = dense_text(interpreted["normalizedRomanianQuery"], bool(constraints["yearlyTopic"]), today)
    found = deps.retrieve(standalone, interpreted, dense_query)
    common = {"schemaVersion": "2.0", "question": question, "standaloneQuestion": standalone, "detectedLanguage": language,
        "normalizedRetrievalQuery": interpreted["normalizedRomanianQuery"], "interpretedConstraints": constraints}
    rules = guardrails.question_constraints(standalone, interpreted["normalizedRomanianQuery"], constraints)
    candidates, rule_drops = guardrails.apply_rules(expose_evidence(found["evidence"]), rules, float(settings.get("categoryPenalty", 0.85)))
    candidates, merged = guardrails.merge_duplicates(candidates)
    candidates = candidates[:int(settings.get("screenPassages", 10))]
    screen_drops: list[dict[str, Any]] = []
    screen_response = None
    if candidates and not constraints["inScope"]:
        # General-knowledge questions are not answered from municipal passages, even ones that share a theme.
        relevant = []
        screen_drops = [{"id": item["id"], "documentId": item["documentId"], "reason": "TOPIC_ONLY", "source": "scope"} for item in candidates]
    elif candidates:
        screened = deps.chat(config.verifier_model, SCREEN_PROMPT.format(today=today.isoformat()), json.dumps({
            "question": standalone, "romanianQuery": interpreted["normalizedRomanianQuery"], "expectedAnswerType": answer_type,
            "passages": prompt_evidence(candidates, int(settings.get("screenQuoteChars", 700)))}, ensure_ascii=False),
            screen_schema([item["id"] for item in candidates]))
        screen_response = screened.get("_managedResponse")
        relevant, screen_drops = guardrails.apply_screen(candidates, guardrails.screen_verdicts(screened))
    else:
        relevant = []
    relevant, _ = guardrails.apply_recency(relevant, bool(constraints["yearlyTopic"]), rules["years"], today, int(settings.get("recencyDays", 365)))
    if scope_label:
        # The picked document and the passages the screen put in the same subject answer the re-asked question.
        chosen = {item.get("subject") for item in relevant if guardrails.choice_label(item) == scope_label}
        relevant = [item for item in relevant if item.get("subject") in chosen] or relevant
    off_topic = len(rule_drops) + len(screen_drops)
    trace: dict[str, Any] = {"ruleDrops": rule_drops, "screenDrops": screen_drops, "screen": screen_response, "duplicatesMerged": merged}

    def finish(result: dict[str, Any]) -> dict[str, Any]:
        result["_trace"] = {**trace, **result.get("_trace", {})}
        if explain:
            result["diagnostics"] = {"retrieval": found.get("diagnostics"), "models": config.raw["models"], "guardrails": trace,
                                     "verifierDecisions": trace.get("verifierDecisions"), "generation": trace.get("generation")}
        return result

    def not_found(reason: str, flags: list[str], reasons: list[str]) -> dict[str, Any]:
        return finish({**common, "status": "NOT_FOUND", "reason": reason, "flags": flags,
            "answer": guardrails.not_found_answer(language, reason, answer_type), "claims": [], "citations": [],
            "confidence": {"score": .9, "reasons": reasons}, "readyForUse": True})

    if not relevant:
        reason = guardrails.not_found_reason(in_scope=bool(constraints["inScope"]), relevant=0, claims=0, lacks_value=False)
        return not_found(reason, guardrails.build_flags(off_topic=off_topic, duplicates=merged), ["No passage relevant to the question remained after screening"])
    documents = [] if scope_label else guardrails.clarification_documents(relevant, bool(constraints["multipleProjects"]),
        float(thresholds["ambiguityScoreRatio"]), float(thresholds["clarificationMinimumScore"]))
    # Colliding documents are only offered as choices after verification, and only those with a verified answer: a question
    # the index cannot answer gets NOT_FOUND, never a list of documents to pick from.
    expected = PROMPT_TYPES[answer_type]
    legal = " and name each legal act with its type, number and date" if answer_type == "legal_act" else ""
    language_name = LANGUAGE_NAMES[language]
    evidence_for_model = prompt_evidence(relevant)
    generated = deps.chat(config.generator_model, GENERATION_PROMPT.format(language=language_name, expected=expected, legal=legal),
        json.dumps({"question": standalone, "evidence": evidence_for_model}, ensure_ascii=False), CLAIMS_SCHEMA)
    claims = claims_of(generated)
    verified, decisions = verify_claims(claims, relevant, config.verifier_model, "", standalone, answer_type, deps.chat)
    corrected = False
    # One correction round, only when it can change the outcome: nothing was generated from relevant evidence, or fewer than
    # half of the claims survived. Otherwise the verified claims are answered (PARTIAL when some were rejected).
    if not claims or len(verified) * 2 < len(claims):
        corrected = True
        first = (generated, claims, verified, decisions)
        generated = deps.chat(config.generator_model, CORRECTION_PROMPT.format(language=language_name, expected=expected, legal=legal),
            json.dumps({"question": standalone, "evidence": evidence_for_model, "claims": claims, "verifier": decisions}, ensure_ascii=False), CLAIMS_SCHEMA)
        claims = claims_of(generated)
        verified, decisions = verify_claims(claims, relevant, config.verifier_model, "", standalone, answer_type, deps.chat)
        if len(verified) < len(first[2]):
            # The correction made things worse: keep the first round's verified claims.
            generated, claims, verified, decisions = first
    trace.update({"generation": generated.get("_managedResponse"), "verifierDecisions": decisions})
    lacks_value = bool(verified) and not guardrails.has_expected_value(verified, answer_type, relevant)
    text, final_claims, citations = "", [], []
    if verified and not lacks_value:
        text, final_claims, citations, _ = guardrails.render_answer(verified, relevant)
    rejected = len(claims) - len(final_claims)
    flags_args = {"off_topic": off_topic, "duplicates": merged, "rejected": rejected, "total": len(claims), "corrected": corrected}
    if not final_claims:
        reason = guardrails.not_found_reason(in_scope=bool(constraints["inScope"]), relevant=len(relevant), claims=len(claims), lacks_value=lacks_value)
        return not_found(reason, guardrails.build_flags(**flags_args), [f"0/{len(claims)} claims retained"])
    answered = {item.get("documentId") for item in citations}
    choices = [item for item in documents if item.get("documentId") in answered]
    if len(choices) >= 2:
        clarification_citations = [{**{key: item.get(key) for key in CITATION_FIELDS}, "id": f"S{index}"} for index, item in enumerate(choices, 1)]
        clarification = guardrails.clarification_question(language)
        return finish({**common, "status": "NEEDS_CLARIFICATION", "reason": None,
            "flags": guardrails.build_flags(**flags_args), "answer": clarification, "claims": [],
            "citations": clarification_citations, "clarificationQuestion": clarification, "clarificationChoices": choices_for(choices),
            "confidence": {"score": .9, "reasons": ["Several distinct documents each answer the question"]}, "readyForUse": True})
    outdated = any(item.get("outdated") for item in citations)
    if outdated:
        text = f"{text}\n{guardrails.outdated_note(language, citations)}"
    if generated.get("status") == "CONTRADICTION" and len({item.get("documentId") for item in citations}) < 2:
        # Different values from one document are a misreading, not conflicting documents.
        return not_found("CLAIMS_UNVERIFIED", guardrails.build_flags(**{**flags_args, "rejected": len(claims)}),
                         ["Conflicting values came from a single document"])
    status = ("CONTRADICTION" if generated.get("status") == "CONTRADICTION" and len(final_claims) > 1 else
              "SUPPORTED" if rejected == 0 else "PARTIAL")
    return finish({**common, "status": status, "reason": guardrails.CONFLICT_REASON if status == "CONTRADICTION" else None,
        "flags": guardrails.build_flags(**flags_args, outdated=outdated), "answer": text, "claims": final_claims,
        "citations": [{key: item.get(key) for key in CITATION_FIELDS} for item in citations],
        "confidence": {"score": .9 if status == "SUPPORTED" else .55, "reasons": ["Independent claim verification completed",
            f"{len(final_claims)}/{len(claims)} claims retained"]}, "readyForUse": True})


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="High-precision trilingual municipal RAG answerer")
    parser.add_argument("--question")
    parser.add_argument("--config", type=Path)
    location = parser.add_mutually_exclusive_group()
    location.add_argument("--qdrant-url")
    location.add_argument("--qdrant-path", type=Path)
    parser.add_argument("--explain", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    question = (args.question or input("Scrie întrebarea în română, rusă sau engleză: ")).strip()
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
