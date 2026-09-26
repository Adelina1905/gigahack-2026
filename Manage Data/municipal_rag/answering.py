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

from .api import chat_json
from .config import load_config, load_dotenv
from .retrieval import interpret_query, retrieve
from .verification import verify_claims
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

OBSERVATIONS_SCHEMA = {
    "type": "object",
    "properties": {
        "observations": {
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
            "sourceFile": meta.get("sourceFile"),
            "locator": item.get("sourceLocator") or ((item.get("citations") or [{}])[0].get("locator")),
            "retrieval": item.get("retrieval")})
    return result


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


def normalized_text(value: str) -> str:
    folded = "".join(
        character for character in unicodedata.normalize("NFKD", value.casefold())
        if not unicodedata.combining(character)
    )
    folded = re.sub(r"\bbd(?:\.(?=\s|$)|\b)", "bulevardul", folded)
    folded = re.sub(r"\bstr(?:\.(?=\s|$)|\b)", "strada", folded)
    return re.sub(r"\bmln\b", "milioane", folded)


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


def contextual_observations(question: str, interpreted: dict[str, Any], evidence: list[dict[str, Any]],
                            prompt_evidence: list[dict[str, Any]], config: Any,
                            api_key: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    generated = chat_json(
        config.generator_model,
        "The requested answer could not be fully verified. Extract up to three useful partial observations in the question language from the exact evidence only. Return {observations:[{text,evidenceIds}]}. Each observation must be independently useful, declarative, and limited to one project/place/work stage. Prefer explaining verified status such as planned, tendering, ongoing, or completed. Do not invent missing values, do not assert that the entire corpus lacks a fact, and do not attach a number, date, amount or duration to a place unless the exact quotation explicitly links them. Use only supplied S identifiers.",
        json.dumps({"question": question, "constraints": interpreted.get("constraints") or {},
                    "evidence": prompt_evidence}, ensure_ascii=False),
        api_key,
        OBSERVATIONS_SCHEMA,
    )
    observations = generated.get("observations") if isinstance(generated.get("observations"), list) else []
    verified, decisions = verify_claims(
        observations, evidence, config.verifier_model, api_key, "", interpreted.get("constraints")
    )
    return verified, decisions, generated


def answer(question: str, config_path: Path | None = None, qdrant_path: Path | None = None, qdrant_url: str | None = None, explain: bool = False) -> dict[str, Any]:
    load_dotenv()
    try:
        config = load_config(config_path)
        api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
        if not api_key:
            return unavailable(question, "OPENROUTER_API_KEY is not configured")
        interpreted = interpret_query(question, config, api_key)
        found = retrieve(question, interpreted, config, api_key, qdrant_path, qdrant_url, explain)
        scoped_items, choices, ambiguity_reasons, ambiguity_diagnostics = resolve_ambiguity(
            found["evidence"], interpreted, float(config.raw["thresholds"]["ambiguityScoreRatio"])
        )
        evidence = expose_evidence(scoped_items)
        common = {"schemaVersion": "2.0", "question": question, "detectedLanguage": interpreted["language"],
            "normalizedRetrievalQuery": interpreted["normalizedRomanianQuery"], "interpretedConstraints": interpreted["constraints"]}
        if not evidence:
            return {**common, "status": "NOT_FOUND", "answer": "Informația nu a fost găsită în corpusul disponibil." if interpreted["language"] == "ro" else "Информация не найдена в доступном корпусе.", "claims": [], "citations": [], "confidence": {"score": .96, "reasons": ["No candidate passed the relevance threshold"]}, "readyForUse": True}
        if choices:
            result = {**common, "status": "NEEDS_CLARIFICATION", "answer": None, "claims": [], "citations": [],
                "clarificationQuestion": "La care proiect vă referiți?" if interpreted["language"] == "ro" else "Какой проект вы имеете в виду?",
                "clarificationChoices": choices, "confidence": {"score": .75, "reasons": ambiguity_reasons}, "readyForUse": True}
            if explain:
                result["diagnostics"] = {"retrieval": found["diagnostics"], "ambiguity": ambiguity_diagnostics}
            return result
        headline = headline_only_amount(scoped_items, interpreted) if ambiguity_diagnostics.get("decision") == "exact-title-override" else None
        if headline:
            if interpreted["language"] == "ro":
                claim_text = f"Titlul articolului indică suma de {headline['amount']}, dar pasajele disponibile din corpul articolului nu o confirmă independent."
            else:
                claim_text = f"В заголовке статьи указана сумма {headline['amount']}, но доступные фрагменты текста статьи независимо её не подтверждают."
            result = {**common, "status": "PARTIAL", "answer": f"{claim_text} [S1]",
                "claims": [{"text": claim_text, "evidenceIds": ["S1"]}],
                "citations": [headline["citation"]],
                "confidence": {"score": .55, "reasons": ["HEADLINE_ONLY", "The requested amount is not corroborated by an indexed body passage"]},
                "readyForUse": True}
            if explain:
                result["diagnostics"] = {"retrieval": found["diagnostics"], "ambiguity": ambiguity_diagnostics,
                    "answerability": "headline-only"}
            return result
        prompt_evidence = [{key: item.get(key) for key in ("id", "documentId", "evidenceKind", "exactQuote", "title", "url", "locator")} for item in evidence]
        generated = chat_json(config.generator_model,
            "Answer only the fact type requested by the question, in the question language, using only exact evidence. Return JSON claims [{text,evidenceIds}]. If the evidence does not contain the requested amount/date/name/count, return an empty claims list instead of answering a different fact. Every text must be a declarative answer, never repeat or paraphrase the question, and must include the requested value when the evidence contains it. Separate projects. Never merge numeric values across documents. A headline alone cannot support a claim.",
            json.dumps({"question": question, "evidence": prompt_evidence}, ensure_ascii=False), api_key, CLAIMS_SCHEMA)
        claims = generated.get("claims") if isinstance(generated.get("claims"), list) else []
        verified, decisions = verify_claims(
            claims, evidence, config.verifier_model, api_key, question, interpreted.get("constraints")
        )
        if claims and len(verified) != len(claims):
            corrected = chat_json(config.generator_model, "Correct once: answer the question directly with declarative claims [{text,evidenceIds}], using only the S identifiers in evidence. Keep one project and location scope per claim. Never attach an amount, duration, date or count to a place mentioned only in a later planned/tender/procurement clause. Planned work is not completed work. Never repeat the question. Include the requested number/date/name only when the exact quotation supports it and remove unsupported claims.", json.dumps({"question": question, "constraints": interpreted.get("constraints"), "evidence": prompt_evidence, "claims": claims, "verifier": decisions}, ensure_ascii=False), api_key, CLAIMS_SCHEMA)
            claims = corrected.get("claims") if isinstance(corrected.get("claims"), list) else []
            verified, decisions = verify_claims(
                claims, evidence, config.verifier_model, api_key, question, interpreted.get("constraints")
            )
        contextual_generation: dict[str, Any] | None = None
        contextual_decisions: list[dict[str, Any]] = []
        partial_prefix: str | None = None
        if not verified and evidence:
            verified, contextual_decisions, contextual_generation = contextual_observations(
                question, interpreted, evidence, prompt_evidence, config, api_key
            )
            if verified:
                partial_prefix = partial_intro(interpreted)
                decisions.extend({"contextObservation": True, **item} for item in contextual_decisions)

        used = {identifier for claim in verified for identifier in claim.get("evidenceIds", [])}
        citations = [item for item in evidence if item["id"] in used]
        mapping = {item["id"]: f"S{index}" for index, item in enumerate(citations, 1)}
        for item in citations:
            item["id"] = mapping[item["id"]]
        for claim in verified:
            claim["evidenceIds"] = [mapping[item] for item in claim.get("evidenceIds", []) if item in mapping]
        status = ("PARTIAL" if partial_prefix else
                  "CONTRADICTION" if generated.get("status") == "CONTRADICTION" and verified else
                  "SUPPORTED" if verified and len(verified) == len(claims) else
                  "PARTIAL" if verified else "NOT_FOUND")
        claim_text = "\n".join(f"{claim['text']} {' '.join(f'[{value}]' for value in claim['evidenceIds'])}" for claim in verified)
        text = f"{partial_prefix}\n{claim_text}" if partial_prefix else claim_text
        result = {**common, "status": status, "answer": text or ("Informația nu a putut fi confirmată." if interpreted["language"] == "ro" else "Информацию не удалось подтвердить."), "claims": verified, "citations": citations,
            "confidence": {"score": .9 if status == "SUPPORTED" else .55 if status == "PARTIAL" else .2, "reasons": ["Independent claim verification completed", f"{len(verified)}/{len(claims)} claims retained"]}, "readyForUse": True}
        result["_trace"] = {"generation": generated.get("_managedResponse"), "verifierDecisions": decisions,
            "contextGeneration": None if contextual_generation is None else contextual_generation.get("_managedResponse")}
        if explain:
            result["diagnostics"] = {"retrieval": found["diagnostics"], "ambiguity": ambiguity_diagnostics,
                "verifierDecisions": decisions, "models": config.raw["models"], "generation": generated.get("_managedResponse"),
                "contextGeneration": None if contextual_generation is None else contextual_generation.get("_managedResponse")}
        return result
    except Exception as error:
        return unavailable(question, str(error))


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
