from __future__ import annotations

import argparse
import json
import os
import time
import sys
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


def ambiguity(items: list[dict[str, Any]], interpreted: dict[str, Any], ratio: float) -> list[dict[str, str]]:
    if interpreted["constraints"].get("multipleProjects"):
        return []
    best: dict[str, dict[str, Any]] = {}
    for item in items:
        best.setdefault(str(item["documentId"]), item)
    ranked = sorted(best.values(), key=lambda item: -float(item["retrieval"]["rerankScore"]))
    if len(ranked) < 2 or float(ranked[1]["retrieval"]["rerankScore"]) < float(ranked[0]["retrieval"]["rerankScore"]) * ratio:
        return []
    return [{"documentId": str(item["documentId"]), "label": str((item.get("metadata") or {}).get("title", item["documentId"]))} for item in ranked[:3]]


def unavailable(question: str, reason: str) -> dict[str, Any]:
    return {"schemaVersion": "2.0", "status": "UNAVAILABLE", "question": question, "answer": None,
        "claims": [], "citations": [], "confidence": {"score": 0.0, "reasons": [reason]}, "readyForUse": False}


def answer(question: str, config_path: Path | None = None, qdrant_path: Path | None = None, qdrant_url: str | None = None, explain: bool = False) -> dict[str, Any]:
    load_dotenv()
    try:
        config = load_config(config_path)
        api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
        if not api_key:
            return unavailable(question, "OPENROUTER_API_KEY is not configured")
        interpreted = interpret_query(question, config, api_key)
        found = retrieve(question, interpreted, config, api_key, qdrant_path, qdrant_url, explain)
        evidence = expose_evidence(found["evidence"])
        common = {"schemaVersion": "2.0", "question": question, "detectedLanguage": interpreted["language"],
            "normalizedRetrievalQuery": interpreted["normalizedRomanianQuery"], "interpretedConstraints": interpreted["constraints"]}
        if not evidence:
            return {**common, "status": "NOT_FOUND", "answer": "Informația nu a fost găsită în corpusul disponibil." if interpreted["language"] == "ro" else "Информация не найдена в доступном корпусе.", "claims": [], "citations": [], "confidence": {"score": .96, "reasons": ["No candidate passed the relevance threshold"]}, "readyForUse": True}
        choices = ambiguity(found["evidence"], interpreted, float(config.raw["thresholds"]["ambiguityScoreRatio"]))
        if choices:
            return {**common, "status": "NEEDS_CLARIFICATION", "answer": None, "claims": [], "citations": [],
                "clarificationQuestion": "La care proiect vă referiți?" if interpreted["language"] == "ro" else "Какой проект вы имеете в виду?",
                "clarificationChoices": choices, "confidence": {"score": .9, "reasons": ["Several project interpretations rank similarly"]}, "readyForUse": True}
        prompt_evidence = [{key: item.get(key) for key in ("id", "documentId", "evidenceKind", "exactQuote", "title", "url", "locator")} for item in evidence]
        generated = chat_json(config.generator_model,
            "Answer the question directly in the question language using only exact evidence. Return JSON claims [{text,evidenceIds}]. Every text must be a declarative answer, never repeat or paraphrase the question, and must include the requested value when the evidence contains it. Separate projects. Never merge numeric values across documents. A headline alone cannot support a claim.",
            json.dumps({"question": question, "evidence": prompt_evidence}, ensure_ascii=False), api_key, CLAIMS_SCHEMA)
        claims = generated.get("claims") if isinstance(generated.get("claims"), list) else []
        verified, decisions = verify_claims(claims, evidence, config.verifier_model, api_key, question)
        if claims and len(verified) != len(claims):
            corrected = chat_json(config.generator_model, "Correct once: answer the question directly with declarative claims [{text,evidenceIds}], using only the S identifiers in evidence. Never repeat the question. Include the requested number/date/name when present and remove unsupported claims.", json.dumps({"question": question, "evidence": prompt_evidence, "claims": claims, "verifier": decisions}, ensure_ascii=False), api_key, CLAIMS_SCHEMA)
            claims = corrected.get("claims") if isinstance(corrected.get("claims"), list) else []
            verified, decisions = verify_claims(claims, evidence, config.verifier_model, api_key, question)
        used = {identifier for claim in verified for identifier in claim.get("evidenceIds", [])}
        citations = [item for item in evidence if item["id"] in used]
        mapping = {item["id"]: f"S{index}" for index, item in enumerate(citations, 1)}
        for item in citations:
            item["id"] = mapping[item["id"]]
        for claim in verified:
            claim["evidenceIds"] = [mapping[item] for item in claim.get("evidenceIds", []) if item in mapping]
        status = ("CONTRADICTION" if generated.get("status") == "CONTRADICTION" and verified else
                  "SUPPORTED" if verified and len(verified) == len(claims) else
                  "PARTIAL" if verified else "NOT_FOUND")
        text = "\n".join(f"{claim['text']} {' '.join(f'[{value}]' for value in claim['evidenceIds'])}" for claim in verified)
        result = {**common, "status": status, "answer": text or ("Informația nu a putut fi confirmată." if interpreted["language"] == "ro" else "Информацию не удалось подтвердить."), "claims": verified, "citations": citations,
            "confidence": {"score": .9 if status == "SUPPORTED" else .55 if status == "PARTIAL" else .2, "reasons": ["Independent claim verification completed", f"{len(verified)}/{len(claims)} claims retained"]}, "readyForUse": True}
        result["_trace"] = {"generation": generated.get("_managedResponse"), "verifierDecisions": decisions}
        if explain:
            result["diagnostics"] = {"retrieval": found["diagnostics"], "verifierDecisions": decisions, "models": config.raw["models"], "generation": generated.get("_managedResponse")}
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
