from __future__ import annotations

import json
import os
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from qdrant_client import QdrantClient, models

from .api import chat_json, embed, request_json
from .config import RagConfig
from .guardrails import ANSWER_TYPES, LANGUAGES, detect_language, expected_answer_type, is_yearly_topic, recent_history
from .sparse import bm25_sparse
from .verification import ChatJson

CATEGORIES = ["education", "healthcare", "mobility", "urban_utilities", "legal_act", "district_admin", "transparency",
    "services", "other_services", "none"]
STRINGS = {"type": "array", "items": {"type": "string"}}
INTERPRETER_SCHEMA = {
    "type": "object",
    "properties": {
        "standaloneQuestion": {"type": "string"},
        "language": {"type": "string", "enum": list(LANGUAGES)},
        "normalizedRomanianQuery": {"type": "string"},
        "entities": STRINGS, "streets": STRINGS, "locations": STRINGS, "dates": STRINGS, "factTypes": STRINGS,
        "answerType": {"type": "string", "enum": list(ANSWER_TYPES)},
        "yearlyTopic": {"type": "boolean"},
        "topicCategory": {"type": "string", "enum": CATEGORIES},
        "inScope": {"type": "boolean"},
    },
    "required": ["standaloneQuestion", "language", "normalizedRomanianQuery", "entities", "streets", "locations", "dates",
                 "factTypes", "answerType", "yearlyTopic", "topicCategory", "inScope"],
    "additionalProperties": False,
}
INTERPRETER_PROMPT = (
    "Interpret a question for a search over Romanian municipal documents of Chișinău (Moldova). "
    "If recent conversation turns are given and the question is a follow-up (pronouns, ellipsis, 'and for ...?'), rewrite it into "
    "standaloneQuestion, a self-contained question in the user's language using only those turns; otherwise copy the question unchanged. "
    "normalizedRomanianQuery: the standalone question translated faithfully into Romanian (normalized if already Romanian), adding no facts. "
    "streets: street names the question mentions, in Romanian spelling without the word strada. "
    "answerType: hours (working or opening hours), date (when), amount (money, fees, quantities), person (who), place (where, address), "
    "procedure (how to, steps, required documents), legal_act (laws, legislation, orders, decisions), list, or other. "
    "yearlyTopic: true when the answer changes every year or school year (enrolment, school year, local taxes and fees, annual programmes). "
    "topicCategory: the document category that best fits, or none. "
    "inScope: false when the answer is general knowledge rather than a fact from Chișinău or Moldovan public administration, city "
    "services, local events or public documents: recipes, international sports results or tournaments, celebrities, world history, "
    "science or trivia. A local event, service or document on the same theme keeps it in scope only if the question asks about it.")


def interpret_query(question: str, config: RagConfig, api_key: str, history: list[dict[str, str]] | None = None,
                    chat: ChatJson | None = None, message: str | None = None) -> dict[str, Any]:
    """Language, standalone question, Romanian retrieval query and constraints; history rewrites follow-ups.

    `message` is the user's own words, used for language detection when `question` was rewritten.
    """
    chat = chat or (lambda model, system, user, schema=None: chat_json(model, system, user, api_key, schema))
    turns = recent_history(history, int(config.raw.get("guardrails", {}).get("historyTurns", 3)))
    payload = json.dumps({"recentTurns": turns, "question": question}, ensure_ascii=False) if turns else question
    parsed = chat(config.generator_model, INTERPRETER_PROMPT, payload, INTERPRETER_SCHEMA)
    standalone = str(parsed.get("standaloneQuestion") or "").strip() if turns else question
    standalone = standalone or question
    language = detect_language(message or question, str(parsed.get("language") or ""))
    normalized = str(parsed.get("normalizedRomanianQuery") or (standalone if language == "ro" else "")).strip()
    if not normalized:
        raise RuntimeError("Query interpreter returned no Romanian retrieval query")
    historical = bool(re.search(r"\b(?:19|20)\d{2}\b|\b(?:istoric|istorică|versiunea din|la data de|în anul|историческ\w*|по состоянию)\b", standalone, re.I))
    multiple_projects = bool(re.search(r"\b(?:compară|comparați|mai multe proiecte|toate proiectele|сравн(?:и|ите)|compare)\b", standalone, re.I))
    lists = {key: [str(value) for value in parsed.get(key) or [] if str(value).strip()] for key in ("entities", "streets", "locations", "dates", "factTypes")}
    return {"language": language, "standaloneQuestion": standalone, "normalizedRomanianQuery": normalized, "constraints": {
        **lists,
        "multipleProjects": multiple_projects,
        "historicalIntent": historical,
        "answerType": expected_answer_type(f"{standalone}\n{normalized}", str(parsed.get("answerType") or "")),
        "yearlyTopic": is_yearly_topic(f"{standalone}\n{normalized}", parsed.get("yearlyTopic") is True),
        "topicCategory": str(parsed.get("topicCategory") or "none") if parsed.get("topicCategory") in CATEGORIES else "none",
        "inScope": parsed.get("inScope") is not False,
    }}


def rrf(dense: list[Any], sparse: list[Any], k: int = 60) -> list[dict[str, Any]]:
    combined: dict[str, dict[str, Any]] = {}
    for channel, points in (("dense", dense), ("sparse", sparse)):
        for rank, point in enumerate(points, start=1):
            item = combined.setdefault(str(point.id), {"point": point, "score": 0.0, "ranks": {}})
            item["score"] += 1.0 / (k + rank)
            item["ranks"][channel] = rank
    return sorted(combined.values(), key=lambda item: (-item["score"], str(item["point"].id)))


def group_documents(items: list[dict[str, Any]], maximum: int) -> list[dict[str, Any]]:
    counts: defaultdict[str, int] = defaultdict(int)
    selected = []
    for item in items:
        document_id = str((item["point"].payload or {}).get("documentId", ""))
        if counts[document_id] >= maximum:
            continue
        counts[document_id] += 1
        selected.append(item)
    return selected


def rerank(query: str, candidates: list[dict[str, Any]], config: RagConfig, api_key: str) -> list[dict[str, Any]]:
    documents = [str((item["point"].payload or {}).get("retrievalText") or (item["point"].payload or {}).get("text") or "") for item in candidates]
    if not documents:
        return []
    response = request_json("rerank", {"model": config.reranker_model, "query": query, "documents": documents,
        "top_n": len(documents), "instruction": "Prefer direct body evidence matching the same municipal project, place and period. A headline alone is insufficient."}, api_key)
    results = response.get("results") or response.get("data")
    if not isinstance(results, list):
        raise RuntimeError("Managed reranker returned no ranked results")
    ranked = []
    for rank, result in enumerate(results, start=1):
        index = result.get("index") if isinstance(result, dict) else None
        if isinstance(index, int) and 0 <= index < len(candidates):
            item = dict(candidates[index])
            item["rerankScore"] = float(result.get("relevance_score", result.get("score", 0)))
            item["rerankRank"] = rank
            ranked.append(item)
    if not ranked:
        raise RuntimeError("Managed reranker returned invalid indexes")
    return ranked


def client_for(path: Path | None, url: str | None) -> QdrantClient:
    if url:
        return QdrantClient(url=url, api_key=os.environ.get("QDRANT_API_KEY") or None, timeout=30)
    return QdrantClient(path=str((path or Path(__file__).resolve().parents[1] / "data" / "08_qdrant").resolve()))


def retrieve(question: str, interpreted: dict[str, Any], config: RagConfig, api_key: str, path: Path | None = None, url: str | None = None, explain: bool = False, dense_query: list[float] | None = None) -> dict[str, Any]:
    if dense_query is None:
        dense_query = embed(question, config.embedding_model, api_key)
    # retrievalQuery is the Romanian query plus search-only hints (the current year for yearly topics).
    query = str(interpreted.get("retrievalQuery") or interpreted["normalizedRomanianQuery"])
    indices, values = bm25_sparse(query)
    limits = config.raw["retrieval"]
    client = client_for(path, url)
    try:
        dense = client.query_points(config.evidence_alias, query=dense_query, using="dense", limit=int(limits["denseCandidates"]), with_payload=True).points
        sparse = client.query_points(config.evidence_alias, query=models.SparseVector(indices=indices, values=values), using="sparse", limit=int(limits["sparseCandidates"]), with_payload=True).points
        catalog = client.query_points(config.catalog_alias, query=models.SparseVector(indices=indices, values=values), using="sparse", limit=10, with_payload=True).points
    finally:
        client.close()
    fused = rrf(dense, sparse, int(limits["rrfK"]))
    catalog_ranks = {str((point.payload or {}).get("documentId")): rank for rank, point in enumerate(catalog, 1)}
    for item in fused:
        document_id = str((item["point"].payload or {}).get("documentId"))
        if document_id in catalog_ranks:
            item["score"] += 1.0 / (int(limits["rrfK"]) + catalog_ranks[document_id])
            item["ranks"]["catalog"] = catalog_ranks[document_id]
    fused.sort(key=lambda item: (-item["score"], str(item["point"].id)))
    grouped = group_documents(fused, int(limits["maxPerDocument"]))[:int(limits["rerankCandidates"])]
    ranked = rerank(query, grouped, config, api_key)
    minimum = float(config.raw["thresholds"]["minimumRerankScore"])
    output = []
    for item in [value for value in ranked if value["rerankScore"] >= minimum][:int(limits["finalEvidence"])]:
        output.append({**(item["point"].payload or {}), "retrieval": {"fusedScore": item["score"], "denseRank": item["ranks"].get("dense"), "sparseRank": item["ranks"].get("sparse"), "rerankedPosition": item["rerankRank"], "rerankScore": item["rerankScore"]}})
    return {"evidence": output, "diagnostics": ({"dense": len(dense), "sparse": len(sparse), "catalog": len(catalog), "fused": len(fused), "grouped": len(grouped)} if explain else None)}
