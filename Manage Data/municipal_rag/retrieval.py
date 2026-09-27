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
REQUIREMENT_SCHEMA = {
    "type": "object",
    "properties": {
        "id": {"type": "string", "pattern": "^R[1-9][0-9]*$"},
        "question": {"type": "string"},
        "normalizedRomanianQuery": {"type": "string"},
        "answerType": {"type": "string", "enum": list(ANSWER_TYPES)},
        "yearlyTopic": {"type": "boolean"},
        "topicCategory": {"type": "string", "enum": CATEGORIES},
    },
    "required": ["id", "question", "normalizedRomanianQuery", "answerType", "yearlyTopic", "topicCategory"],
    "additionalProperties": False,
}
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
        "requirements": {"type": "array", "items": REQUIREMENT_SCHEMA, "maxItems": 8},
    },
    "required": ["standaloneQuestion", "language", "normalizedRomanianQuery", "entities", "streets", "locations", "dates",
                 "factTypes", "answerType", "yearlyTopic", "topicCategory", "inScope", "requirements"],
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
    "requirements: split a multi-part request into at most eight independently answerable requirements R1..Rn. Preserve every explicit "
    "constraint (place, period, project and requested fact) in the relevant requirement. Do not split a simple request: return one "
    "requirement. Each requirement has a self-contained question in the user's language, a faithful Romanian retrieval query, its "
    "answerType, yearlyTopic and topicCategory. Separate distinct institutions, services and financial stages; for example school "
    "enrolment and kindergarten enrolment are separate requirements, as are budgeted, contracted and paid amounts. Requirements are "
    "facts the user wants, not answer-format or safety instructions: do not create requirements for citing sources, flagging unsupported "
    "or promotional content, avoiding invention, limiting list length, or separating categories. Treat those as answer rules. Never add a request the user did not make. "
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
    requirements = []
    for raw in parsed.get("requirements") or []:
        if not isinstance(raw, dict) or len(requirements) >= 8:
            continue
        requirement_question = str(raw.get("question") or "").strip()
        requirement_query = str(raw.get("normalizedRomanianQuery") or "").strip()
        if not requirement_question or not requirement_query:
            continue
        answer_type = expected_answer_type(f"{requirement_question}\n{requirement_query}", str(raw.get("answerType") or ""))
        category = str(raw.get("topicCategory") or "none")
        requirements.append({"id": f"R{len(requirements) + 1}", "question": requirement_question,
            "normalizedRomanianQuery": requirement_query, "answerType": answer_type,
            "yearlyTopic": raw.get("yearlyTopic") is True,
            "topicCategory": category if category in CATEGORIES else "none"})
    if not requirements:
        requirements = [{"id": "R1", "question": standalone, "normalizedRomanianQuery": normalized,
            "answerType": expected_answer_type(f"{standalone}\n{normalized}", str(parsed.get("answerType") or "")),
            "yearlyTopic": is_yearly_topic(f"{standalone}\n{normalized}", parsed.get("yearlyTopic") is True),
            "topicCategory": str(parsed.get("topicCategory") or "none") if parsed.get("topicCategory") in CATEGORIES else "none"}]
    return {"language": language, "standaloneQuestion": standalone, "normalizedRomanianQuery": normalized, "constraints": {
        **lists,
        "multipleProjects": multiple_projects,
        "historicalIntent": historical,
        "answerType": expected_answer_type(f"{standalone}\n{normalized}", str(parsed.get("answerType") or "")),
        "yearlyTopic": is_yearly_topic(f"{standalone}\n{normalized}", parsed.get("yearlyTopic") is True),
        "topicCategory": str(parsed.get("topicCategory") or "none") if parsed.get("topicCategory") in CATEGORIES else "none",
        "inScope": parsed.get("inScope") is not False,
        "requirements": requirements,
        "multiIntent": len(requirements) > 1,
    }}


def rrf(dense: list[Any], sparse: list[Any], k: int = 60) -> list[dict[str, Any]]:
    return rrf_channels([("dense", dense), ("sparse", sparse)], k)


def rrf_channels(channels: list[tuple[str, list[Any]]], k: int = 60) -> list[dict[str, Any]]:
    combined: dict[str, dict[str, Any]] = {}
    for channel, points in channels:
        for rank, point in enumerate(points, start=1):
            item = combined.setdefault(str(point.id), {"point": point, "score": 0.0, "ranks": {}})
            item["score"] += 1.0 / (k + rank)
            item["ranks"][channel] = rank
    return sorted(combined.values(), key=lambda item: (-item["score"], str(item["point"].id)))


def prioritize_channels(items: list[dict[str, Any]], channels: list[str], limit: int,
                        maximum_per_document: int | None = None) -> list[dict[str, Any]]:
    """Reserve one candidate per requirement channel, then fill in global score order."""
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    document_counts: defaultdict[str, int] = defaultdict(int)

    def add(item: dict[str, Any]) -> bool:
        point_id = str(item["point"].id)
        document_id = str((item["point"].payload or {}).get("documentId", ""))
        if point_id in seen or len(selected) >= limit:
            return False
        if maximum_per_document is not None and document_counts[document_id] >= maximum_per_document:
            return False
        seen.add(point_id)
        document_counts[document_id] += 1
        selected.append(item)
        return True

    for channel in channels:
        candidates = sorted((item for item in items if channel in item.get("ranks", {})),
                            key=lambda item: (item["ranks"][channel], -float(item.get("score", 0))))
        for candidate in candidates:
            if add(candidate):
                break
    for item in items:
        add(item)
    return selected


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


def _passage_position(point: Any) -> tuple[int, int, int, str]:
    payload = point.payload or {}
    locator = payload.get("sourceLocator") or {}

    def number(value: Any) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return 10**9

    return (
        number(locator.get("page", locator.get("pageNumber"))),
        number(locator.get("startLine")),
        number(locator.get("blockIndex")),
        str(payload.get("evidenceId") or point.id),
    )


def _introduces_following_context(payload: dict[str, Any]) -> bool:
    quote = str(payload.get("citationText") or "").strip()
    normalized = quote.casefold()
    return (
        str(payload.get("evidenceKind") or "").casefold() == "headline"
        or quote.endswith(":")
        or bool(re.search(r"\b(?:pa(?:ș|s)ii|etapele|lista|documentele necesare)\b", normalized))
    )


def add_following_context(candidates: list[dict[str, Any]], document_points: dict[tuple[str, str], list[Any]],
                          maximum_per_anchor: int = 6, maximum_added: int = 12) -> list[dict[str, Any]]:
    """Add list items immediately following a retrieved heading before reranking.

    Municipal web pages often store a heading and every numbered step as separate passages. The heading can win hybrid
    retrieval while the actual steps are excluded by per-document diversity. Context candidates are still reranked, so
    adjacent but irrelevant passages do not automatically reach answer generation.
    """
    output = list(candidates)
    seen = {str(item["point"].id) for item in output}
    added = 0
    for anchor in candidates:
        payload = anchor["point"].payload or {}
        if not _introduces_following_context(payload):
            continue
        key = (str(payload.get("documentId") or ""), str(payload.get("versionId") or ""))
        points = sorted(document_points.get(key) or [], key=_passage_position)
        anchor_index = next((index for index, point in enumerate(points) if str(point.id) == str(anchor["point"].id)), None)
        if anchor_index is None:
            continue
        for distance, point in enumerate(points[anchor_index + 1:anchor_index + 1 + maximum_per_anchor], start=1):
            point_id = str(point.id)
            if point_id in seen:
                continue
            context = dict(anchor)
            context["point"] = point
            context["score"] = float(anchor.get("score") or 0.0) / (distance + 1)
            context["ranks"] = {"contextAfter": distance}
            context["contextAnchorId"] = str(anchor["point"].id)
            output.append(context)
            seen.add(point_id)
            added += 1
            if added >= maximum_added:
                return output
    return output


def load_candidate_documents(client: QdrantClient, collection: str,
                             candidates: list[dict[str, Any]]) -> dict[tuple[str, str], list[Any]]:
    keys = {
        (str(payload.get("documentId") or ""), str(payload.get("versionId") or ""))
        for item in candidates
        if _introduces_following_context(payload := (item["point"].payload or {}))
        and payload.get("documentId") and payload.get("versionId")
    }
    result: dict[tuple[str, str], list[Any]] = {}
    for document_id, version_id in keys:
        points, offset = [], None
        while True:
            page, offset = client.scroll(
                collection_name=collection,
                scroll_filter=models.Filter(must=[
                    models.FieldCondition(key="documentId", match=models.MatchValue(value=document_id)),
                    models.FieldCondition(key="versionId", match=models.MatchValue(value=version_id)),
                ]),
                limit=256,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
            points.extend(page)
            if offset is None:
                break
        result[(document_id, version_id)] = points
    return result


def eligible_with_context(ranked: list[dict[str, Any]], minimum: float) -> list[dict[str, Any]]:
    """Keep adjacent list items when their retrieved heading passed the reranker threshold."""
    eligible_ids = {str(item["point"].id) for item in ranked if float(item.get("rerankScore") or 0.0) >= minimum}
    return [item for item in ranked if float(item.get("rerankScore") or 0.0) >= minimum
            or str(item.get("contextAnchorId") or "") in eligible_ids]


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
    requirements = list((interpreted.get("constraints") or {}).get("requirements") or [])
    requirement_channels = [f"requirement:{item['id']}" for item in requirements]
    client = client_for(path, url)
    try:
        dense = client.query_points(config.evidence_alias, query=dense_query, using="dense", limit=int(limits["denseCandidates"]), with_payload=True).points
        sparse = client.query_points(config.evidence_alias, query=models.SparseVector(indices=indices, values=values), using="sparse", limit=int(limits["sparseCandidates"]), with_payload=True).points
        requirement_sparse: list[tuple[str, list[Any]]] = []
        for requirement, channel in zip(requirements, requirement_channels):
            requirement_query = str(requirement.get("retrievalQuery") or requirement.get("normalizedRomanianQuery") or "").strip()
            if not requirement_query:
                continue
            requirement_indices, requirement_values = bm25_sparse(requirement_query)
            points = client.query_points(config.evidence_alias,
                query=models.SparseVector(indices=requirement_indices, values=requirement_values), using="sparse",
                limit=min(16, int(limits["sparseCandidates"])), with_payload=True).points
            requirement_sparse.append((channel, points))
        catalog = client.query_points(config.catalog_alias, query=models.SparseVector(indices=indices, values=values), using="sparse", limit=10, with_payload=True).points
    finally:
        client.close()
    fused = rrf_channels([("dense", dense), ("sparse", sparse), *requirement_sparse], int(limits["rrfK"]))
    catalog_ranks = {str((point.payload or {}).get("documentId")): rank for rank, point in enumerate(catalog, 1)}
    for item in fused:
        document_id = str((item["point"].payload or {}).get("documentId"))
        if document_id in catalog_ranks:
            item["score"] += 1.0 / (int(limits["rrfK"]) + catalog_ranks[document_id])
            item["ranks"]["catalog"] = catalog_ranks[document_id]
    fused.sort(key=lambda item: (-item["score"], str(item["point"].id)))
    grouped = prioritize_channels(fused, requirement_channels, int(limits["rerankCandidates"]),
                                  int(limits["maxPerDocument"]))
    context_client = client_for(path, url)
    try:
        grouped = add_following_context(grouped, load_candidate_documents(context_client, config.evidence_alias, grouped))
    finally:
        context_client.close()
    rerank_query = query
    if len(requirements) > 1:
        rerank_query += "\nCerințe: " + " | ".join(str(item.get("normalizedRomanianQuery") or "") for item in requirements)
    ranked = rerank(rerank_query, grouped, config, api_key)
    minimum = float(config.raw["thresholds"]["minimumRerankScore"])
    output = []
    eligible = eligible_with_context(ranked, minimum)
    selected = prioritize_channels(eligible, requirement_channels, int(limits["finalEvidence"]))
    for item in selected:
        matches = [requirement["id"] for requirement, channel in zip(requirements, requirement_channels)
                   if channel in item["ranks"]]
        output.append({**(item["point"].payload or {}), "retrieval": {"fusedScore": item["score"],
            "denseRank": item["ranks"].get("dense"), "sparseRank": item["ranks"].get("sparse"),
            "requirementIds": matches, "rerankedPosition": item["rerankRank"], "rerankScore": item["rerankScore"]}})
    return {"evidence": output, "diagnostics": ({"dense": len(dense), "sparse": len(sparse),
        "requirements": len(requirements), "requirementCandidates": sum(len(points) for _, points in requirement_sparse),
        "catalog": len(catalog), "fused": len(fused), "grouped": len(grouped)} if explain else None)}
